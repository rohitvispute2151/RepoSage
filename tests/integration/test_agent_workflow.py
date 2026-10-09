"""Integration test verifying end-to-end LangGraph agent QA execution."""

from pathlib import Path
import time
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from reposage.agent.budget import BudgetManager
from reposage.agent.graph import build_graph
from reposage.agent.nodes import AgentDependencies
from reposage.agent.state import AgentState, BudgetState
from reposage.db.models import Repo, RepoSnapshot, Task
from reposage.ingest.pipeline import ingest_snapshot
from reposage.llm.client import ResilientLLM
from reposage.llm.providers.fake import FakeProvider
from reposage.observability.tracing import tracer


@pytest.mark.asyncio
async def test_qa_agent_graph_execution(
    temp_repo: Path,
    async_db: AsyncSession,
    fake_llm: ResilientLLM,
):
    """Verify that a QA task runs through the complete LangGraph state machine to report."""
    # 1. Ingest repository
    repo = Repo(name="test_proj", source_uri=str(temp_repo))
    async_db.add(repo)
    await async_db.flush()

    snap = RepoSnapshot(
        repo_id=repo.id,
        commit_sha="aabbcc123",
        status="queued",
        mirror_path=str(temp_repo),
    )
    async_db.add(snap)
    await async_db.commit()

    await ingest_snapshot(snapshot_id=snap.id, db=async_db, embedder=FakeProvider())

    # 2. Create Task
    task_id = uuid.uuid4()
    task = Task(
        id=task_id,
        snapshot_id=snap.id,
        mode="qa",
        request={"question": "Where is the retry handler implemented?"},
        status="running",
        budgets={"max_steps": 20, "max_tokens": 50000, "max_usd": 1.0, "max_seconds": 300},
        config_fingerprint="fingerprint_test",
    )
    async_db.add(task)
    await async_db.commit()

    # 3. Setup agent graph
    deps = AgentDependencies(
        db=async_db,
        llm=fake_llm,
        budget=BudgetManager(),
        tracer=tracer,
        snapshot_root=temp_repo,
    )
    graph = build_graph(deps)

    initial_state: AgentState = {
        "task_id": str(task_id),
        "snapshot_id": str(snap.id),
        "mode": "qa",
        "request": task.request,
        "plan": {},
        "repo_map_summary": str(snap.repo_map or ""),
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
            limits=task.budgets,
        ),
        "loop_fingerprints": {},
        "status_hint": None,
        "final": None,
    }

    # 4. Invoke graph execution
    result = await graph.ainvoke(initial_state)

    assert "final" in result
    final_report = result["final"]
    assert final_report.get("outcome") in {"answered", "completed"}
    assert "budget_report" in final_report
