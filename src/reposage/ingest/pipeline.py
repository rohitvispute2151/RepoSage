"""Repository snapshot ingestion pipeline.

Coordinates file discovery, AST chunking, identifier expansion, batch embedding,
and repo map generation for a pinned commit snapshot.
"""

from pathlib import Path
from typing import Any, Optional
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from reposage.config import settings
from reposage.db.models import Chunk, File, RepoSnapshot
from reposage.ingest.chunker import CodeChunk, chunk_python
from reposage.ingest.embedder import (
    EmbeddingProvider,
    embed_chunks,
    get_default_embedder,
)
from reposage.ingest.identifiers import expand_identifiers
from reposage.ingest.walker import walk_repo
from reposage.observability.logging import logger


async def ingest_snapshot(
    snapshot_id: uuid.UUID,
    db: AsyncSession,
    embedder: Optional[EmbeddingProvider] = None,
) -> RepoSnapshot:
    """Execute complete ingestion pipeline for a repository snapshot."""
    stmt = select(RepoSnapshot).where(RepoSnapshot.id == snapshot_id)
    snapshot = await db.scalar(stmt)
    if snapshot is None:
        raise ValueError(f"Snapshot {snapshot_id} not found")

    snapshot.status = "ingesting"
    await db.commit()

    try:
        mirror_path = Path(snapshot.mirror_path)
        if not mirror_path.exists():
            raise FileNotFoundError(
                f"Mirror directory does not exist: {mirror_path}"
            )

        # Clean up any partial state from previous aborted attempts for this snapshot
        await db.execute(delete(Chunk).where(Chunk.snapshot_id == snapshot.id))
        await db.execute(delete(File).where(File.snapshot_id == snapshot.id))
        await db.commit()

        repo_map: dict[str, list[dict[str, Any]]] = {}
        all_chunks: list[CodeChunk] = []
        file_records: list[File] = []

        # 1. Discover files and parse code chunks
        for dfile in walk_repo(mirror_path):
            file_rec = File(
                snapshot_id=snapshot.id,
                path=dfile.relative_path,
                is_test=dfile.is_test,
                sha256=dfile.sha256,
                line_count=dfile.line_count,
            )
            file_records.append(file_rec)
            db.add(file_rec)
            await db.flush()

            # Chunk Python files
            if dfile.relative_path.endswith(".py"):
                chunks = chunk_python(
                    path=dfile.relative_path,
                    source=dfile.content,
                    is_test=dfile.is_test,
                )
            else:
                # Non-python config/readme: create single module_header chunk
                header_content = (
                    f"# path: {dfile.relative_path}\n"
                    f"# symbol: {dfile.relative_path} (module_header)\n"
                    f"{dfile.content[:2000]}"
                )
                import hashlib

                chunks = [
                    CodeChunk(
                        path=dfile.relative_path,
                        qualname=dfile.relative_path,
                        kind="module_header",
                        signature=dfile.relative_path,
                        docstring=None,
                        start_line=1,
                        end_line=dfile.line_count or 1,
                        body=dfile.content[:2000],
                        is_test=dfile.is_test,
                        content=header_content,
                        content_hash=hashlib.sha256(
                            header_content.encode("utf-8")
                        ).hexdigest(),
                    )
                ]

            all_chunks.extend(chunks)

            # Record symbol signatures into repo map outline
            symbols_in_file = [
                {
                    "qualname": c.qualname,
                    "kind": c.kind,
                    "signature": c.signature,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                }
                for c in chunks
                if c.kind != "module_header"
            ]
            if symbols_in_file:
                repo_map[dfile.relative_path] = symbols_in_file

        await db.commit()

        # 2. Embed chunks if embedder is provided
        if embedder is None:
            embedder = get_default_embedder(settings.embedding_model)

        embeddings_map: dict[str, list[float]] = {}
        if embedder is not None:
            embeddings_map = await embed_chunks(
                all_chunks,
                embedder,
                db,
                model=settings.embedding_model,
            )

        # 3. Persist Chunk entities
        file_map = {f.path: f.id for f in file_records}
        for chunk in all_chunks:
            file_id = file_map.get(chunk.path)
            if not file_id:
                continue

            search_text = expand_identifiers(chunk.content)
            vec = embeddings_map.get(chunk.content_hash)

            chunk_entity = Chunk(
                snapshot_id=snapshot.id,
                file_id=file_id,
                path=chunk.path,
                qualname=chunk.qualname,
                kind=chunk.kind,
                signature=chunk.signature,
                docstring=chunk.docstring,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                is_test=chunk.is_test,
                content=chunk.content,
                content_hash=chunk.content_hash,
                search_text=search_text,
                embedding=vec,
            )
            db.add(chunk_entity)

        # 4. Finalize snapshot status and save repo map
        snapshot.repo_map = repo_map
        snapshot.status = "ready"
        snapshot.error = None
        await db.commit()
        logger.info(
            f"Snapshot {snapshot_id} successfully indexed with {len(all_chunks)} chunks"
        )
        return snapshot

    except Exception as exc:
        logger.exception(f"Ingestion failed for snapshot {snapshot_id}: {exc}")
        snapshot.status = "failed"
        snapshot.error = str(exc)
        await db.commit()
        raise
