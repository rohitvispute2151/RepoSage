"""Hybrid code retrieval combining vector similarity, full-text search, and trigram fuzzy matching.

Merges multi-source candidate rankings using Reciprocal Rank Fusion (RRF).
"""

from collections import defaultdict
import math
from typing import Sequence
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from reposage.config import settings
from reposage.db.models import Chunk
from reposage.retrieval.reranker import Candidate


def rrf_merge(
    ranked_lists: Sequence[list[Candidate]], k: int = 60
) -> list[Candidate]:
    """Merge multiple ordered candidate lists using Reciprocal Rank Fusion."""
    scores: dict[uuid.UUID, float] = defaultdict(float)
    cand_by_id: dict[uuid.UUID, Candidate] = {}

    for cand_list in ranked_lists:
        for rank, cand in enumerate(cand_list, start=1):
            cand_by_id[cand.id] = cand
            scores[cand.id] += 1.0 / (k + rank)

    sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
    return [cand_by_id[cid].with_score(scores[cid]) for cid in sorted_ids]


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def hybrid_search_postgres(
    db: AsyncSession,
    snapshot_id: uuid.UUID,
    query_text: str,
    query_ident: str,
    query_vec: list[float] | None,
    k: int = 40,
    rrf_k: int = 60,
    limit: int = 30,
    include_tests: bool = False,
) -> list[Candidate]:
    """Execute native PostgreSQL hybrid query with vector, FTS, and trigram CTEs."""
    sql = text("""
    WITH vec AS (
      SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> :qvec) AS rnk
      FROM chunks
      WHERE snapshot_id = :snap
        AND (:include_tests OR NOT is_test)
        AND embedding IS NOT NULL
      ORDER BY embedding <=> :qvec
      LIMIT :k
    ),
    fts AS (
      SELECT id, ROW_NUMBER() OVER (
               ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('simple', :qtext)) DESC) AS rnk
      FROM chunks
      WHERE snapshot_id = :snap
        AND tsv @@ websearch_to_tsquery('simple', :qtext)
        AND (:include_tests OR NOT is_test)
      ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('simple', :qtext)) DESC
      LIMIT :k
    ),
    trg AS (
      SELECT id, ROW_NUMBER() OVER (ORDER BY similarity(qualname, :qident) DESC) AS rnk
      FROM chunks
      WHERE snapshot_id = :snap
        AND qualname % :qident
      ORDER BY similarity(qualname, :qident) DESC
      LIMIT :k
    ),
    fused AS (
      SELECT id, SUM(1.0 / (:rrf_k + rnk)) AS score
      FROM (SELECT * FROM vec UNION ALL SELECT * FROM fts UNION ALL SELECT * FROM trg) u
      GROUP BY id
    )
    SELECT c.id, c.path, c.qualname, c.kind, c.start_line, c.end_line, c.content, f.score
    FROM fused f JOIN chunks c ON c.id = f.id
    ORDER BY f.score DESC
    LIMIT :limit;
    """)

    vec_str = f"[{','.join(str(x) for x in (query_vec or []))}]"
    res = await db.execute(
        sql,
        {
            "snap": snapshot_id,
            "qtext": query_text,
            "qident": query_ident,
            "qvec": vec_str,
            "k": k,
            "rrf_k": rrf_k,
            "limit": limit,
            "include_tests": include_tests,
        },
    )
    rows = res.fetchall()
    return [
        Candidate(
            id=row.id,
            path=row.path,
            qualname=row.qualname,
            kind=row.kind,
            start_line=row.start_line,
            end_line=row.end_line,
            content=row.content,
            score=float(row.score),
        )
        for row in rows
    ]


async def hybrid_search_python(
    db: AsyncSession,
    snapshot_id: uuid.UUID,
    query_text: str,
    query_ident: str,
    query_vec: list[float] | None,
    k: int = 40,
    rrf_k: int = 60,
    limit: int = 30,
    include_tests: bool = False,
) -> list[Candidate]:
    """In-memory hybrid search fallback for non-Postgres / SQLite test environments."""
    stmt = select(Chunk).where(Chunk.snapshot_id == snapshot_id)
    if not include_tests:
        stmt = stmt.where(Chunk.is_test.is_(False))
    res = await db.execute(stmt)
    chunks = res.scalars().all()

    if not chunks:
        return []

    # 1. Vector ranking
    vec_ranked: list[Candidate] = []
    if query_vec:
        scored_vec = []
        for c in chunks:
            if c.embedding:
                sim = _cosine_similarity(query_vec, c.embedding)
                scored_vec.append((c, sim))
        scored_vec.sort(key=lambda x: x[1], reverse=True)
        vec_ranked = [
            Candidate(
                id=c.id,
                path=c.path,
                qualname=c.qualname,
                kind=c.kind,
                start_line=c.start_line,
                end_line=c.end_line,
                content=c.content,
                score=sim,
            )
            for c, sim in scored_vec[:k]
        ]

    # 2. Lexical / text ranking
    tokens = set(query_text.lower().split())
    scored_lex = []
    for c in chunks:
        content_lower = c.content.lower()
        search_lower = c.search_text.lower()
        hits = sum(1 for tok in tokens if tok in content_lower or tok in search_lower)
        if hits > 0:
            scored_lex.append((c, float(hits)))
    scored_lex.sort(key=lambda x: x[1], reverse=True)
    lex_ranked = [
        Candidate(
            id=c.id,
            path=c.path,
            qualname=c.qualname,
            kind=c.kind,
            start_line=c.start_line,
            end_line=c.end_line,
            content=c.content,
            score=score,
        )
        for c, score in scored_lex[:k]
    ]

    # 3. Identifier / qualname ranking
    ident_tokens = set(query_ident.lower().split())
    scored_trg = []
    for c in chunks:
        qn_lower = c.qualname.lower()
        path_lower = c.path.lower()
        hits = sum(1 for tok in ident_tokens if tok in qn_lower or tok in path_lower)
        if hits > 0:
            scored_trg.append((c, float(hits)))
    scored_trg.sort(key=lambda x: x[1], reverse=True)
    trg_ranked = [
        Candidate(
            id=c.id,
            path=c.path,
            qualname=c.qualname,
            kind=c.kind,
            start_line=c.start_line,
            end_line=c.end_line,
            content=c.content,
            score=score,
        )
        for c, score in scored_trg[:k]
    ]

    # Merge rankings via RRF
    merged = rrf_merge([vec_ranked, lex_ranked, trg_ranked], k=rrf_k)
    return merged[:limit]


async def hybrid_search(
    db: AsyncSession,
    snapshot_id: uuid.UUID,
    query_text: str,
    query_ident: str,
    query_vec: list[float] | None = None,
    k: int = 40,
    rrf_k: int = 60,
    limit: int = 30,
    include_tests: bool = False,
) -> list[Candidate]:
    """Execute hybrid search selecting PostgreSQL native CTE or python fallback."""
    if "postgresql" in settings.database_url:
        try:
            return await hybrid_search_postgres(
                db,
                snapshot_id,
                query_text,
                query_ident,
                query_vec,
                k=k,
                rrf_k=rrf_k,
                limit=limit,
                include_tests=include_tests,
            )
        except Exception:
            # Fall back to Python computation if Postgres extension missing
            await db.rollback()

    return await hybrid_search_python(
        db,
        snapshot_id,
        query_text,
        query_ident,
        query_vec,
        k=k,
        rrf_k=rrf_k,
        limit=limit,
        include_tests=include_tests,
    )
