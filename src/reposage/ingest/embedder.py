"""Vector embedding batch processor with persistent deduplication caching.

Integrates SentenceTransformer using jinaai/jina-embeddings-v2-base-code for code embeddings,
avoiding duplicate embedding calls when re-indexing unchanged symbols or files.
"""

import asyncio
import logging
from typing import Any, Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reposage.db.models import EmbeddingCache
from reposage.ingest.chunker import CodeChunk


def _patch_transformers_compatibility() -> None:
    """Ensure transformers maintains backwards compatibility for remote model definitions.

    Fixes missing find_pruneable_heads_and_indices in transformers>=5 for jina-bert remote code.
    """
    try:
        import transformers.pytorch_utils as _tpu

        if not hasattr(_tpu, "find_pruneable_heads_and_indices"):
            import torch

            def find_pruneable_heads_and_indices(
                heads: list[int],
                n_heads: int,
                head_size: int,
                already_pruned_heads: set[int],
            ) -> tuple[set[int], torch.LongTensor]:
                mask = torch.ones(n_heads, head_size)
                heads_set = set(heads) - set(already_pruned_heads)
                for head in heads_set:
                    mask[head] = 0
                mask = mask.view(-1)
                index = mask.nonzero().view(-1)
                return heads_set, index

            _tpu.find_pruneable_heads_and_indices = find_pruneable_heads_and_indices  # type: ignore[attr-defined]
    except Exception:
        pass


_patch_transformers_compatibility()

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment, misc]

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "jinaai/jina-embeddings-v2-base-code"


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers producing float vectors."""

    async def embed(
        self, texts: list[str], model: str
    ) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """SentenceTransformer embedding provider.

    Defaults to `jinaai/jina-embeddings-v2-base-code` with `trust_remote_code=True`.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        trust_remote_code: bool = True,
        device: str | None = "cpu",
        max_seq_length: int = 1024,
    ) -> None:
        self.model_name = model_name
        self.trust_remote_code = trust_remote_code
        self.device = device or "cpu"
        self.max_seq_length = max_seq_length
        self._model: Any = None

    @property
    def model(self) -> Any:
        """Lazily load and cache the underlying SentenceTransformer model."""
        if self._model is None:
            _patch_transformers_compatibility()
            if SentenceTransformer is None:
                try:
                    from sentence_transformers import SentenceTransformer as _ST
                except ImportError as err:
                    raise ImportError(
                        "sentence-transformers is not installed. "
                        "Install it via `pip install sentence-transformers`."
                    ) from err
                st_cls = _ST
            else:
                st_cls = SentenceTransformer

            kwargs: dict[str, Any] = {"trust_remote_code": self.trust_remote_code}
            if self.device:
                kwargs["device"] = self.device
            self._model = st_cls(self.model_name, **kwargs)
            if hasattr(self._model, "max_seq_length") and self.max_seq_length:
                self._model.max_seq_length = self.max_seq_length
        return self._model

    def encode(self, sentences: list[str] | str, **kwargs: Any) -> Any:
        """Synchronously encode sentences using the SentenceTransformer model."""
        return self.model.encode(sentences, **kwargs)

    def similarity(self, embeddings1: Any, embeddings2: Any) -> Any:
        """Compute similarities between embeddings using the SentenceTransformer model."""
        return self.model.similarity(embeddings1, embeddings2)

    async def embed(
        self, texts: list[str], model: str | None = None
    ) -> list[list[float]]:
        """Asynchronously compute embeddings for a list of text strings.

        Converts output to a list of float vectors, running in an async thread pool.
        """
        if not texts:
            return []

        def _run_encode() -> list[list[float]]:
            if model and model != self.model_name:
                _patch_transformers_compatibility()
                if SentenceTransformer is None:
                    from sentence_transformers import SentenceTransformer as _ST
                    st_cls = _ST
                else:
                    st_cls = SentenceTransformer
                sub_model = st_cls(
                    model, trust_remote_code=self.trust_remote_code
                )
                raw_vecs = sub_model.encode(texts)
            else:
                raw_vecs = self.encode(texts)

            if hasattr(raw_vecs, "tolist"):
                return raw_vecs.tolist()
            return [
                v.tolist() if hasattr(v, "tolist") else list(v)
                for v in raw_vecs
            ]

        return await asyncio.to_thread(_run_encode)


# Alias for naming consistency across codebase
SentenceTransformerProvider = SentenceTransformerEmbedder


_cached_embedder: SentenceTransformerEmbedder | None = None


def get_default_embedder(
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    device: str | None = None,
) -> SentenceTransformerEmbedder:
    """Return a shared singleton instance of SentenceTransformerEmbedder."""
    global _cached_embedder
    from reposage.config import settings

    target_device = device or getattr(settings, "embedding_device", "cpu")
    if (
        _cached_embedder is None
        or _cached_embedder.model_name != model_name
        or _cached_embedder.device != target_device
    ):
        _cached_embedder = SentenceTransformerEmbedder(
            model_name=model_name,
            device=target_device,
        )
    return _cached_embedder


async def embed_chunks(
    chunks: Sequence[CodeChunk],
    embedder: EmbeddingProvider | None = None,
    db: AsyncSession | None = None,
    model: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 8,
) -> dict[str, list[float]]:
    """Embed chunks in batches, checking and updating the persistent embedding cache."""
    if not chunks:
        return {}

    if embedder is None:
        embedder = get_default_embedder(model_name=model)

    cached_map: dict[str, list[float]] = {}
    content_hashes = [c.content_hash for c in chunks]

    # 1. Query existing cached embeddings if db session is provided
    if db is not None:
        stmt = select(EmbeddingCache).where(
            EmbeddingCache.content_hash.in_(content_hashes),
            EmbeddingCache.model == model,
        )
        res = await db.execute(stmt)
        cached_entries = res.scalars().all()
        cached_map = {
            row.content_hash: row.embedding for row in cached_entries
        }

    # 2. Identify missing chunk hashes to embed (deduplicated by content_hash)
    seen_hashes: set[str] = set()
    to_embed: list[CodeChunk] = []
    for c in chunks:
        if c.content_hash not in cached_map and c.content_hash not in seen_hashes:
            seen_hashes.add(c.content_hash)
            to_embed.append(c)

    # 3. Batch embed missing items
    for i in range(0, len(to_embed), batch_size):
        batch = to_embed[i : i + batch_size]
        texts = [c.content for c in batch]
        vectors = await embedder.embed(texts, model=model)

        for chunk_item, vec in zip(batch, vectors):
            cached_map[chunk_item.content_hash] = vec
            if db is not None:
                cache_row = EmbeddingCache(
                    content_hash=chunk_item.content_hash,
                    model=model,
                    embedding=vec,
                )
                db.add(cache_row)

        if db is not None:
            await db.commit()

    return cached_map


if __name__ == "__main__":
    _patch_transformers_compatibility()
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("jinaai/jina-embeddings-v2-base-code", trust_remote_code=True)

    sentences = [
        "The weather is lovely today.",
        "It's so sunny outside!",
        "He drove to the stadium.",
    ]
    embeddings = model.encode(sentences)

    similarities = model.similarity(embeddings, embeddings)
    print(similarities.shape)
