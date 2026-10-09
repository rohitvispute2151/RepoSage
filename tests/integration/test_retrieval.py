"""Integration tests for repository ingestion and hybrid retrieval."""

from pathlib import Path
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from reposage.db.models import Repo, RepoSnapshot
from reposage.ingest.pipeline import ingest_snapshot
from reposage.llm.client import ResilientLLM
from reposage.llm.providers.fake import FakeProvider
from reposage.retrieval.service import retrieve


@pytest.mark.asyncio
async def test_ingest_and_retrieve_symbols(
    temp_repo: Path,
    async_db: AsyncSession,
    fake_llm: ResilientLLM,
):
    """Verify that a repository is ingested into chunks and retrieved by semantic query."""
    # 1. Register repo and snapshot pointing to temp_repo
    repo = Repo(name="sample_repo", source_uri=str(temp_repo))
    async_db.add(repo)
    await async_db.flush()

    snap = RepoSnapshot(
        repo_id=repo.id,
        commit_sha="c0ffee123",
        status="queued",
        mirror_path=str(temp_repo),
    )
    async_db.add(snap)
    await async_db.commit()

    # 2. Run ingestion pipeline
    fake_embedder = FakeProvider()
    ready_snap = await ingest_snapshot(
        snapshot_id=snap.id,
        db=async_db,
        embedder=fake_embedder,
    )
    assert ready_snap.status == "ready"
    assert "src/http.py" in ready_snap.repo_map

    # 3. Retrieve code chunks for retry query
    res = await retrieve(
        snapshot_id=snap.id,
        question="Where is retry backoff logic?",
        db=async_db,
        llm=fake_llm,
    )

    qualnames = [c.qualname for c in res.candidates]
    assert any("http" in q.lower() for q in qualnames)
