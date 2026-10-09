"""Integration tests for FastAPI REST endpoints."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from unittest.mock import patch as mock_patch
from reposage.config import settings
from reposage.db.models import Patch, Repo, RepoSnapshot, Task


@pytest.mark.asyncio
async def test_health_and_metrics_endpoints(client: AsyncClient):
    """Verify healthz, readyz, and Prometheus metrics scrape targets."""
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    resp = await client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}

    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "tasks_total" in resp.text


@pytest.mark.asyncio
async def test_task_creation_and_approval_api(client: AsyncClient, async_db: AsyncSession):
    """Verify task submission and HITL approval submission via HTTP API."""
    # 1. Setup repository and snapshot
    repo = Repo(name="test_repo", source_uri="http://example.com")
    async_db.add(repo)
    await async_db.flush()

    snap = RepoSnapshot(repo_id=repo.id, commit_sha="abcdef123", status="ready", mirror_path="/tmp")
    async_db.add(snap)
    await async_db.commit()

    headers = {"X-API-Key": settings.api_key}

    with mock_patch("reposage.api.routes_tasks.run_task.apply_async") as mock_enqueue:
        # 2. Submit QA task
        task_payload = {
            "snapshot_id": str(snap.id),
            "mode": "qa",
            "qa": {"question": "Where is the retry logic located?"},
        }
        resp = await client.post("/v1/tasks", json=task_payload, headers=headers)
        assert resp.status_code == 202
        data = resp.json()
        task_id = data["id"]
        assert data["status"] == "queued"
        assert mock_enqueue.called

    # 3. Test approval gate endpoint
    # Set task to awaiting_approval and create candidate patch
    patch = Patch(
        task_id=uuid.UUID(task_id),
        attempt=1,
        diff="--- a/file.py\n+++ b/file.py\n@@ -1,1 +1,1 @@\n-old\n+new\n",
        diff_sha256="patchsha123456",
        validation={"ok": True, "errors": []},
    )
    async_db.add(patch)
    task_row = await async_db.get(Task, uuid.UUID(task_id))
    task_row.status = "awaiting_approval"
    await async_db.commit()

    with mock_patch("reposage.api.routes_tasks.run_task.apply_async") as mock_enqueue_appr:
        approval_payload = {
            "decision": "approve",
            "patch_sha256": "patchsha123456",
            "comment": "LGTM verified",
        }
        appr_resp = await client.post(f"/v1/tasks/{task_id}/approval", json=approval_payload, headers=headers)
        assert appr_resp.status_code == 200
        assert appr_resp.json() == {"status": "accepted"}
        assert mock_enqueue_appr.called


@pytest.mark.asyncio
async def test_create_repo_endpoint(client: AsyncClient, tmp_path, monkeypatch):
    """Verify repo registration creates snapshot and launches ingestion with dedicated session."""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    monkeypatch.setattr(settings, "storage_root", storage_dir)

    dummy_repo_dir = tmp_path / "dummy_repo"
    dummy_repo_dir.mkdir()
    (dummy_repo_dir / "main.py").write_text("def hello(): return 'world'\n")

    headers = {"X-API-Key": settings.api_key}
    payload = {
        "name": "test_repo_new",
        "source_uri": str(dummy_repo_dir),
        "commit_sha": "abc1234567890",
    }

    with mock_patch("reposage.api.routes_repos.ingest_snapshot") as mock_ingest:
        resp = await client.post("/v1/repos", json=payload, headers=headers)
        assert resp.status_code == 202
        data = resp.json()
        assert data["commit_sha"] == "abc1234567890"
        assert data["status"] == "queued"
