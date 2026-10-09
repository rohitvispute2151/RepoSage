"""REST routes managing repository registration and snapshot indexing."""

import asyncio
import logging
from pathlib import Path
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reposage.api.deps import verify_api_key
from reposage.api.schemas import RepoCreate, RepoSnapshotResponse
from reposage.config import settings
from reposage.db.models import Chunk, Repo, RepoSnapshot
from reposage.db.session import async_session_factory, get_db
from reposage.ingest import get_default_embedder
from reposage.ingest.pipeline import ingest_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repos", tags=["repos"])


@router.post(
    "",
    response_model=RepoSnapshotResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_api_key)],
)
async def create_repo(
    body: RepoCreate,
    db: AsyncSession = Depends(get_db),
) -> RepoSnapshotResponse:
    """Register repository and commit SHA, creating snapshot record and launching ingestion."""
    # 1. Create or retrieve base Repo
    stmt_repo = select(Repo).where(Repo.name == body.name)
    repo = await db.scalar(stmt_repo)
    if not repo:
        repo = Repo(name=body.name, source_uri=body.source_uri)
        db.add(repo)
        await db.flush()

    # 2. Check if snapshot at this commit already exists and has chunks
    stmt_snap = select(RepoSnapshot).where(
        RepoSnapshot.repo_id == repo.id,
        RepoSnapshot.commit_sha == body.commit_sha,
    )
    existing_snap = await db.scalar(stmt_snap)
    if existing_snap and existing_snap.status == "ready":
        chunk_count = await db.scalar(
            select(func.count(Chunk.id)).where(Chunk.snapshot_id == existing_snap.id)
        )
        if chunk_count and chunk_count > 0:
            return RepoSnapshotResponse.model_validate(existing_snap, from_attributes=True)
        # Empty previous snapshot; delete and re-index
        await db.delete(existing_snap)
        await db.commit()

    # 3. Create new snapshot record
    snapshot_id = uuid.uuid4()
    mirror_dir = settings.storage_root / str(snapshot_id)
    mirror_dir.mkdir(parents=True, exist_ok=True)

    # Copy local source or clone if uri is a remote git URL
    source_p = Path(body.source_uri)
    if source_p.exists() and source_p.is_dir():
        shutil.copytree(source_p, mirror_dir, dirs_exist_ok=True)
    else:
        # Clone from git remote URI
        clone_cmd = ["git", "clone", body.source_uri, str(mirror_dir)]
        proc = await asyncio.create_subprocess_exec(
            *clone_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            shutil.rmtree(mirror_dir, ignore_errors=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to clone repository from {body.source_uri}: {stderr.decode()}",
            )

        if body.commit_sha:
            checkout_cmd = ["git", "-C", str(mirror_dir), "checkout", body.commit_sha]
            c_proc = await asyncio.create_subprocess_exec(
                *checkout_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await c_proc.communicate()

    snapshot = RepoSnapshot(
        id=snapshot_id,
        repo_id=repo.id,
        commit_sha=body.commit_sha,
        status="queued",
        mirror_path=str(mirror_dir),
    )
    db.add(snapshot)
    await db.commit()

    # 4. Trigger ingestion in background task with dedicated session
    target_snapshot_id = snapshot_id

    async def _run_ingest():
        async with async_session_factory() as session:
            try:
                await ingest_snapshot(
                    snapshot_id=target_snapshot_id,
                    db=session,
                    embedder=get_default_embedder(settings.embedding_model),
                )
            except Exception as exc:
                logger.exception(
                    f"Background ingestion failed for snapshot {target_snapshot_id}: {exc}"
                )

    asyncio.create_task(_run_ingest())

    return RepoSnapshotResponse.model_validate(snapshot, from_attributes=True)


@router.get(
    "/{snapshot_id}",
    response_model=RepoSnapshotResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_snapshot(
    snapshot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RepoSnapshotResponse:
    """Retrieve indexing status and symbol outline for a repository snapshot."""
    stmt = select(RepoSnapshot).where(RepoSnapshot.id == snapshot_id)
    snap = await db.scalar(stmt)
    if not snap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot {snapshot_id} not found",
        )
    return RepoSnapshotResponse.model_validate(snap, from_attributes=True)
