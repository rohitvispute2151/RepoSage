"""Retrieval service orchestrating query rewriting, hybrid search, and reranking.

Coordinates the end-to-end pipeline providing code evidence items with exact line anchors.
"""

import asyncio
from dataclasses import dataclass
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from reposage.config import settings
from reposage.llm.client import ResilientLLM
from reposage.observability.metrics import retrieval_latency_seconds
from reposage.observability.tracing import tracer
from reposage.retrieval.hybrid import hybrid_search, rrf_merge
from reposage.retrieval.reranker import Candidate, Reranker, get_reranker
from reposage.retrieval.rewriter import RewriteOut, rewrite_query


@dataclass
class RetrievalResult:
    """Consolidated outcome of the retrieval pipeline."""

    candidates: list[Candidate]
    rewrite: RewriteOut
    stage_timings: dict[str, float]
    pre_rerank_ids: list[uuid.UUID]


async def retrieve(
    snapshot_id: uuid.UUID,
    question: str,
    db: AsyncSession,
    llm: ResilientLLM,
    reranker: Reranker | None = None,
    include_tests: bool = False,
) -> RetrievalResult:
    """Execute end-to-end multi-variant code retrieval pipeline."""
    timings: dict[str, float] = {}
    active_reranker = reranker or get_reranker(settings.reranker_type)

    with tracer.span("retrieval", question=question):
        # 1. Rewrite query into natural language and identifier variants
        t0 = time.perf_counter()
        rw = await rewrite_query(llm, question)
        timings["rewrite_ms"] = (time.perf_counter() - t0) * 1000.0
        retrieval_latency_seconds.labels(stage="rewrite").observe(
            timings["rewrite_ms"] / 1000.0
        )

        variants = [question] + rw.nl_queries
        ident_text = " ".join(rw.identifiers + rw.file_hints) or question

        # 2. Parallel hybrid retrieval per variant
        t1 = time.perf_counter()

        async def search_variant(variant_text: str) -> list[Candidate]:
            # Generate query vector using local SentenceTransformer embedder
            query_vec: list[float] | None = None
            try:
                from reposage.ingest.embedder import get_default_embedder
                embedder = get_default_embedder(settings.embedding_model)
                vecs = await embedder.embed([variant_text], model=settings.embedding_model)
                if vecs:
                    query_vec = vecs[0]
            except Exception:
                pass

            return await hybrid_search(
                db=db,
                snapshot_id=snapshot_id,
                query_text=variant_text,
                query_ident=ident_text,
                query_vec=query_vec,
                k=settings.retrieve_vector_k,
                rrf_k=settings.rrf_k,
                limit=settings.rerank_input_n,
                include_tests=include_tests,
            )

        variant_results = []
        for v in variants:
            res = await search_variant(v)
            variant_results.append(res)
        timings["hybrid_ms"] = (time.perf_counter() - t1) * 1000.0
        retrieval_latency_seconds.labels(stage="hybrid").observe(
            timings["hybrid_ms"] / 1000.0
        )

        # 3. Merge candidates across query variants using RRF
        merged_candidates = rrf_merge(
            variant_results, k=settings.rrf_k
        )[: settings.rerank_input_n]
        pre_rerank_ids = [c.id for c in merged_candidates]

        # 4. Re-rank top candidates
        t2 = time.perf_counter()
        final_top = await active_reranker.rerank(
            query=question,
            cands=merged_candidates,
            top_n=settings.rerank_output_n,
        )
        timings["rerank_ms"] = (time.perf_counter() - t2) * 1000.0
        retrieval_latency_seconds.labels(stage="rerank").observe(
            timings["rerank_ms"] / 1000.0
        )

    return RetrievalResult(
        candidates=final_top,
        rewrite=rw,
        stage_timings=timings,
        pre_rerank_ids=pre_rerank_ids,
    )
