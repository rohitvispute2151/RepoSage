"""Celery asynchronous tasks driving agent execution and periodic reaper cleanups."""

import asyncio
from datetime import timedelta
import os
from pathlib import Path
import socket
import time
from typing import Any, Optional
import uuid

from langgraph.types import Command
from sqlalchemy import select, update

from reposage.agent.budget import BudgetManager
from reposage.agent.graph import build_graph
from reposage.agent.nodes import AgentDependencies
from reposage.agent.state import AgentState, BudgetState
from reposage.config import settings
from reposage.db.models import Approval, RepoSnapshot, Task, TaskEvent, utc_now
from reposage.db.session import async_session_factory
from reposage.llm.client import ResilientLLM
from reposage.llm.ledger import CostLedger
from reposage.llm.providers.fake import FakeProvider
from reposage.llm.providers.openai_ import OpenAIProvider
from reposage.observability.logging import current_task_id, logger
from reposage.observability.metrics import task_resumes_total
from reposage.observability.tracing import tracer
from reposage.sandbox.client import SandboxClient
from reposage.workers.celery_app import celery_app
from reposage.workers.lease import TaskLeaseManager


async def _run_task_async(task_id_str: str, approval_id: Optional[str] = None) -> None:
    """Asynchronous worker core driving task graph execution and recovery."""
    task_id = uuid.UUID(task_id_str)
    current_task_id.set(task_id_str)
    worker_owner = f"{socket.gethostname()}:{os.getpid()}"

    async with async_session_factory() as db:
        lease = TaskLeaseManager(db)
        acquired = await lease.acquire(task_id, worker_owner, ttl_seconds=settings.lease_ttl_s)
        if not acquired:
            logger.info(f"Task {task_id} is currently locked by another worker.")
            return

        # Start background lease renewal heartbeat loop
        renew_task = asyncio.create_task(
            lease.renew_loop(task_id, worker_owner, interval_seconds=settings.lease_renew_s)
        )

        try:
            # 1. Fetch task and repository snapshot records
            task_row = await db.scalar(select(Task).where(Task.id == task_id))
            if not task_row:
                return

            snapshot_row = await db.scalar(
                select(RepoSnapshot).where(RepoSnapshot.id == task_row.snapshot_id)
            )
            snapshot_root = (
                Path(snapshot_row.mirror_path)
                if snapshot_row
                else settings.storage_root / str(task_row.snapshot_id)
            )

            # 2. Setup agent dependencies with Gemini primary and Groq fallback
            providers: dict[str, Any] = {}
            chain: list[tuple[str, str]] = []

            gemini_key = settings.gemini_api_key or os.getenv("GEMINI_API_KEY")
            if gemini_key:
                providers["gemini"] = OpenAIProvider(
                    api_key=gemini_key,
                    base_url=settings.gemini_base_url,
                    name="gemini",
                )
                chain.append(("gemini", settings.gemini_model_id))

            groq_key = settings.groq_api_key or os.getenv("GROQ_API_KEY")
            if groq_key:
                providers["groq"] = OpenAIProvider(
                    api_key=groq_key,
                    base_url=settings.groq_base_url,
                    name="groq",
                )
                chain.append(("groq", settings.groq_model_id))

            # Safety fallback for offline / mock testing
            fake_provider = FakeProvider()
            providers["fake"] = fake_provider
            chain.append(("fake", "default"))

            llm = ResilientLLM(
                providers=providers,
                chain=chain,
                breakers={},
                ledger=CostLedger(db=db),
            )
            budget_mgr = BudgetManager()
            sandbox_cli = SandboxClient(base_url=settings.sandbox_url)

            def event_sink(t_id: str, etype: str, payload: dict[str, Any]):
                pass

            deps = AgentDependencies(
                db=db,
                llm=llm,
                budget=budget_mgr,
                tracer=tracer,
                snapshot_root=snapshot_root,
                sandbox_client=sandbox_cli,
                event_sink=event_sink,
            )

            # 3. Assemble graph
            graph = build_graph(deps)
            config = {"configurable": {"thread_id": task_id_str}}

            # Check if this invocation is resuming from a human approval decision
            if approval_id:
                appr_row = await db.scalar(
                    select(Approval).where(Approval.id == uuid.UUID(approval_id))
                )
                if appr_row:
                    task_resumes_total.labels(reason="hitl_approval").inc()
                    decision_dict = {
                        "decision": appr_row.decision,
                        "approved_diff_sha256": appr_row.approved_diff_sha256,
                        "approval_id": str(appr_row.id),
                        "comment": appr_row.comment,
                    }
                    await graph.ainvoke(Command(resume=decision_dict), config)
            else:
                # Fresh task start
                stmt_status = (
                    update(Task).where(Task.id == task_id).values(status="running")
                )
                await db.execute(stmt_status)
                await db.commit()

                repo_map_str = ""
                if snapshot_row and snapshot_row.repo_map:
                    repo_map_str = str(snapshot_row.repo_map)

                initial_state: AgentState = {
                    "task_id": task_id_str,
                    "snapshot_id": str(task_row.snapshot_id),
                    "mode": task_row.mode,  # type: ignore
                    "request": task_row.request,
                    "plan": {},
                    "repo_map_summary": repo_map_str,
                    "evidence": [],
                    "messages": [],
                    "scratchpad": {},
                    "baseline_test_results": None,
                    "patch": None,
                    "patch_attempts": 0,
                    "verify_result": None,
                    "approval": None,
                    "budget": BudgetState(
                        steps=0,
                        tokens=0,
                        usd=0.0,
                        started_at=time.time(),
                        limits=task_row.budgets,
                    ),
                    "loop_fingerprints": {},
                    "status_hint": None,
                    "final": None,
                }
                await graph.ainvoke(initial_state, config)

        finally:
            renew_task.cancel()
            try:
                await renew_task
            except asyncio.CancelledError:
                pass
            try:
                async with async_session_factory() as release_db:
                    release_lease = TaskLeaseManager(release_db)
                    await release_lease.release(task_id, worker_owner)
            except Exception as exc:
                logger.warning(f"Failed to release lease for task {task_id}: {exc}")


@celery_app.task(name="reposage.workers.tasks.run_task", bind=True)
def run_task(self, task_id: str, approval_id: Optional[str] = None) -> None:
    """Celery task entry point driving agent execution loop."""
    asyncio.run(_run_task_async(task_id, approval_id))


@celery_app.task(name="reposage.workers.tasks.reaper_task")
def reaper_task() -> None:
    """Periodic task reclaiming orphaned tasks and expiring timed-out approvals."""
    async def _sweep():
        now = utc_now()
        async with async_session_factory() as db:
            # 1. Sweep expired running tasks
            expired_running_stmt = (
                select(Task.id)
                .where(
                    Task.status == "running",
                    Task.lease_expires_at < now,
                )
            )
            expired_ids = (await db.execute(expired_running_stmt)).scalars().all()
            for tid in expired_ids:
                logger.info(f"Re-queueing orphaned task {tid} after lease expiration")
                run_task.delay(str(tid))

            # 2. Sweep timed-out approvals
            approval_cutoff = now - timedelta(seconds=settings.approval_ttl_s)
            timeout_stmt = (
                update(Task)
                .where(
                    Task.status == "awaiting_approval",
                    Task.updated_at < approval_cutoff,
                )
                .values(
                    status="approval_timeout",
                    outcome="approval_timeout",
                    updated_at=now,
                )
            )
            await db.execute(timeout_stmt)
            await db.commit()

    asyncio.run(_sweep())
