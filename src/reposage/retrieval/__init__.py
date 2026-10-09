"""Code-aware retrieval package combining vector, lexical, and trigram search."""

from reposage.retrieval.hybrid import hybrid_search, rrf_merge
from reposage.retrieval.reranker import (
    Candidate,
    CrossEncoderReranker,
    NoopReranker,
    Reranker,
    get_reranker,
)
from reposage.retrieval.rewriter import RewriteOut, rewrite_query
from reposage.retrieval.service import RetrievalResult, retrieve

__all__ = [
    "Candidate",
    "Reranker",
    "NoopReranker",
    "CrossEncoderReranker",
    "get_reranker",
    "RewriteOut",
    "rewrite_query",
    "hybrid_search",
    "rrf_merge",
    "RetrievalResult",
    "retrieve",
]
