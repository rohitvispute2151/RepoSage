"""Unit tests for task state machine transitions and invariants."""

import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from reposage.db.models import Repo, RepoSnapshot, Task
from reposage.db.session import (
    ALLOWED_TRANSITIONS,
    IllegalTransitionError,
    transition_task_status,
)


@pytest.mark.asyncio
async def test_legal_and_illegal_task_transitions(async_db: AsyncSession):
    """Verify task state machine permits valid transitions and rejects invalid ones."""
    # 1. Create task
    repo = Repo(name="test", source_uri="http://test")
    async_db.add(repo)
    await async_db.flush()

    snap = RepoSnapshot(repo_id=repo.id, commit_sha="abc1234", status="ready", mirror_path="/tmp")
    async_db.add(snap)
    await async_db.flush()

    task = Task(
        snapshot_id=snap.id,
        mode="qa",
        request={"question": "test"},
        status="queued",
        budgets={},
        config_fingerprint="fp1",
    )
    async_db.add(task)
    await async_db.commit()

    # 2. Legal transition: queued -> running
    updated = await transition_task_status(
        db=async_db,
        task_id=task.id,
        new_status="running",
        expect_from={"queued"},
    )
    assert updated.status == "running"

    # 3. Illegal transition: running -> queued (not permitted)
    with pytest.raises(IllegalTransitionError):
        await transition_task_status(
            db=async_db,
            task_id=task.id,
            new_status="queued",
            expect_from={"running"},
        )
