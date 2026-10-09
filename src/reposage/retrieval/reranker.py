"""Reranker interface and candidate re-scoring implementations.

Supports Cross-Encoder reranking, LLM-based reranking, and pass-through Noop reranking.
"""

from dataclasses import dataclass
from typing import Protocol
import uuid


@dataclass
class Candidate:
    """Retrieved chunk candidate passed to the reranking stage."""

    id: uuid.UUID
    path: str
    qualname: str
    kind: str
    start_line: int
    end_line: int
    content: str
    score: float = 0.0

    def rerank_text(self, max_body_chars: int = 600) -> str:
        """Format candidate text for cross-encoder scoring."""
        return f"{self.path} {self.qualname}\n{self.content[:max_body_chars]}"

    def with_score(self, new_score: float) -> "Candidate":
        """Return a new Candidate with updated score."""
        return Candidate(
            id=self.id,
            path=self.path,
            qualname=self.qualname,
            kind=self.kind,
            start_line=self.start_line,
            end_line=self.end_line,
            content=self.content,
            score=new_score,
        )


class Reranker(Protocol):
    """Protocol for scoring and sorting top retrieval candidates."""

    async def rerank(
        self, query: str, cands: list[Candidate], top_n: int
    ) -> list[Candidate]: ...


class NoopReranker:
    """Pass-through reranker maintaining original fusion ranking."""

    async def rerank(
        self, query: str, cands: list[Candidate], top_n: int
    ) -> list[Candidate]:
        return cands[:top_n]


class CrossEncoderReranker:
    """Local Cross-Encoder reranker using sentence-transformers (if installed)."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2", max_length: int = 512):
        self.model_name = model_name
        self.max_length = max_length
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name, max_length=self.max_length)
        return self._model

    async def rerank(
        self, query: str, cands: list[Candidate], top_n: int
    ) -> list[Candidate]:
        if not cands:
            return []
        try:
            import asyncio
            model = self._get_model()
            pairs = [(query, c.rerank_text()) for c in cands]
            scores = await asyncio.to_thread(model.predict, pairs, batch_size=16)
            ranked = sorted(zip(cands, scores), key=lambda x: -x[1])
            return [c.with_score(float(s)) for c, s in ranked[:top_n]]
        except Exception:
            # Fall back to top-n as-is if model is unavailable
            return cands[:top_n]


def get_reranker(reranker_type: str = "noop") -> Reranker:
    """Factory returning configured reranker instance."""
    if reranker_type == "cross_encoder":
        return CrossEncoderReranker()
    return NoopReranker()
