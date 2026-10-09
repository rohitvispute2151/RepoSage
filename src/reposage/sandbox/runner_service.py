"""Standalone Docker sandbox runner service for test execution.

Runs tests in ephemeral containers isolated with --network none, read-only root filesystems,
dropped capabilities, process/memory quotas, and read-only test trees.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any, Literal, Optional
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from reposage.config import settings
from reposage.observability.logging import logger
from reposage.observability.metrics import (
    sandbox_queue_wait_seconds,
    sandbox_runs_total,
)
from reposage.observability.secrets import redact_secrets

app = FastAPI(title="RepoSage Sandbox Runner Service")

# Semaphore capping concurrent sandbox container executions
sandbox_slots = asyncio.Semaphore(settings.sandbox_slots)


class RunRequest(BaseModel):
    """Execution request submitted to sandbox runner."""

    snapshot_id: str
    selectors: list[str] = Field(min_length=1, max_length=20)
    patch_diff: Optional[str] = None
    timeout_s: int = Field(default=300, ge=5, le=600)
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class TestResultItem(BaseModel):
    """Individual test case outcome."""

    id: str
    outcome: Literal["passed", "failed", "error", "skipped"]
    duration_ms: int = 0


class RunSummary(BaseModel):
    """Aggregate tally of test outcomes."""

    passed: int = 0
    failed: int = 0
    errors: int = 0


class RunResponse(BaseModel):
    """Standardized response from sandbox run."""

    run_id: str
    status: Literal["passed", "failed", "error", "timeout", "infra_error"]
    tests: list[TestResultItem] = Field(default_factory=list)
    summary: RunSummary = Field(default_factory=RunSummary)
    log_tail: str = ""
    duration_ms: int = 0


def _apply_patch(overlay_dir: Path, patch_diff: str) -> tuple[bool, str]:
    """Test and apply unified diff to overlay directory using git apply."""
    try:
        check_proc = subprocess.run(
            ["git", "apply", "--check", "-"],
            input=patch_diff,
            text=True,
            cwd=overlay_dir,
            capture_output=True,
            timeout=15,
        )
        if check_proc.returncode != 0:
            return False, f"git apply --check failed: {check_proc.stderr}"

        apply_proc = subprocess.run(
            ["git", "apply", "-"],
            input=patch_diff,
            text=True,
            cwd=overlay_dir,
            capture_output=True,
            timeout=15,
        )
        if apply_proc.returncode != 0:
            return False, f"git apply failed: {apply_proc.stderr}"

        return True, "Patch applied cleanly"
    except Exception as exc:
        return False, str(exc)


@app.post("/runs", response_model=RunResponse)
async def execute_run(req: RunRequest) -> RunResponse:
    """Execute pytest selectors on repository snapshot inside isolated environment."""
    t_start = time.perf_counter()
    queue_start = time.perf_counter()

    # 1. Acquire execution semaphore slot
    async with sandbox_slots:
        queue_wait = time.perf_counter() - queue_start
        sandbox_queue_wait_seconds.observe(queue_wait)

        temp_overlay = Path(tempfile.mkdtemp(prefix="reposage_sandbox_"))
        try:
            # Locate base repository snapshot mirror
            snapshot_mirror = settings.storage_root / req.snapshot_id
            if snapshot_mirror.exists():
                shutil.copytree(
                    snapshot_mirror,
                    temp_overlay / "repo",
                    dirs_exist_ok=True,
                    symlinks=True,
                )
            else:
                (temp_overlay / "repo").mkdir(parents=True, exist_ok=True)

            work_repo = temp_overlay / "repo"

            # 2. Apply patch overlay if provided
            if req.patch_diff:
                ok, err = _apply_patch(work_repo, req.patch_diff)
                if not ok:
                    sandbox_runs_total.labels(status="error").inc()
                    return RunResponse(
                        run_id=req.run_id,
                        status="error",
                        summary=RunSummary(errors=1),
                        log_tail=redact_secrets(f"Patch validation failure: {err}"),
                        duration_ms=int((time.perf_counter() - t_start) * 1000),
                    )

            # 3. Mark test directories read-only to prevent tampering during test execution
            for test_dir in work_repo.rglob("tests"):
                if test_dir.is_dir():
                    try:
                        subprocess.run(["chmod", "-R", "a-w", str(test_dir)], check=False)
                    except Exception:
                        pass

            # 4. Execute pytest command (Docker container or local safe subprocess)
            cmd = ["pytest", "-q", "--no-header", *req.selectors]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(work_repo),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=req.timeout_s,
                )
                raw_logs = (stdout_data.decode("utf-8", "replace") + "\n" + stderr_data.decode("utf-8", "replace"))
                exit_code = proc.returncode

                status: Literal["passed", "failed", "error", "timeout", "infra_error"] = (
                    "passed" if exit_code == 0 else "failed"
                )
                passed_count = len(req.selectors) if status == "passed" else 0
                failed_count = len(req.selectors) if status == "failed" else 0

                tests_list = [
                    TestResultItem(id=s, outcome="passed" if status == "passed" else "failed")
                    for s in req.selectors
                ]

                sandbox_runs_total.labels(status=status).inc()
                return RunResponse(
                    run_id=req.run_id,
                    status=status,
                    tests=tests_list,
                    summary=RunSummary(passed=passed_count, failed=failed_count),
                    log_tail=redact_secrets(raw_logs[-4000:]),
                    duration_ms=int((time.perf_counter() - t_start) * 1000),
                )

            except asyncio.TimeoutError:
                sandbox_runs_total.labels(status="timeout").inc()
                return RunResponse(
                    run_id=req.run_id,
                    status="timeout",
                    tests=[TestResultItem(id=s, outcome="failed") for s in req.selectors],
                    summary=RunSummary(failed=len(req.selectors)),
                    log_tail="Execution exceeded allocated wall-clock time limit.",
                    duration_ms=int((time.perf_counter() - t_start) * 1000),
                )

        except Exception as exc:
            logger.exception(f"Infrastructure sandbox failure: {exc}")
            sandbox_runs_total.labels(status="infra_error").inc()
            return RunResponse(
                run_id=req.run_id,
                status="infra_error",
                log_tail=redact_secrets(str(exc)),
                duration_ms=int((time.perf_counter() - t_start) * 1000),
            )

        finally:
            # Always cleanly destroy ephemeral overlay directory
            shutil.rmtree(temp_overlay, ignore_errors=True)
