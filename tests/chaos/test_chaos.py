"""Chaos and resilience tests verifying worker lease recovery and timeouts."""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from reposage.db.models import Repo, RepoSnapshot, Task
from reposage.workers.lease import TaskLeaseManager


@pytest.mark.asyncio
async def test_lease_recovery_after_worker_crash(async_db: AsyncSession):
    """Verify that an expired task lease can be re-claimed by a surviving worker."""
    # 1. Create task
    repo = Repo(name="chaos_repo", source_uri="http://test")
    async_db.add(repo)
    await async_db.flush()

    snap = RepoSnapshot(repo_id=repo.id, commit_sha="11223344", status="ready", mirror_path="/tmp")
    async_db.add(snap)
    await async_db.flush()

    task = Task(
        snapshot_id=snap.id,
        mode="fix",
        request={"description": "fix bug"},
        status="running",
        budgets={},
        config_fingerprint="fp_chaos",
        lease_owner="worker_dead:1234",
        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),  # expired
    )
    async_db.add(task)
    await async_db.commit()

    # 2. Worker B attempts acquisition on expired lease
    lease_mgr = TaskLeaseManager(async_db)
    acquired = await lease_mgr.acquire(task.id, owner="worker_live:5678", ttl_seconds=60)
    assert acquired is True

    # 3. Verify task is now owned by worker B
    await async_db.refresh(task)
    assert task.lease_owner == "worker_live:5678"
