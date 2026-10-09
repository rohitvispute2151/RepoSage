"""Unit tests for SentenceTransformer embedding provider and chunk caching."""

from unittest.mock import MagicMock, patch
import pytest

from reposage.ingest.chunker import CodeChunk
from reposage.ingest.embedder import (
    DEFAULT_EMBEDDING_MODEL,
    SentenceTransformerEmbedder,
    embed_chunks,
    get_default_embedder,
)


def test_embedder_defaults():
    """Verify embedder default model configuration."""
    embedder = SentenceTransformerEmbedder()
    assert embedder.model_name == DEFAULT_EMBEDDING_MODEL
    assert embedder.trust_remote_code is True


@patch("reposage.ingest.embedder.SentenceTransformer")
def test_embedder_encode_and_similarity(mock_st_cls):
    """Verify encode and similarity methods delegate correctly to SentenceTransformer."""
    mock_model = MagicMock()
    mock_model.encode.return_value = [[0.1, 0.2], [0.3, 0.4]]
    mock_model.similarity.return_value = MagicMock(shape=(2, 2))
    mock_st_cls.return_value = mock_model

    embedder = SentenceTransformerEmbedder()
    sentences = ["def add(a, b): return a + b", "class Worker: pass"]

    embeddings = embedder.encode(sentences)
    assert embeddings == [[0.1, 0.2], [0.3, 0.4]]
    mock_model.encode.assert_called_once_with(sentences)

    similarities = embedder.similarity(embeddings, embeddings)
    assert similarities.shape == (2, 2)
    mock_model.similarity.assert_called_once_with(embeddings, embeddings)


@pytest.mark.asyncio
@patch("reposage.ingest.embedder.SentenceTransformer")
async def test_embedder_async_embed(mock_st_cls):
    """Verify async embed method runs non-blocking in thread pool and formats floats."""
    import numpy as np

    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
    mock_st_cls.return_value = mock_model

    embedder = SentenceTransformerEmbedder()
    vecs = await embedder.embed(["hello world"])

    assert len(vecs) == 1
    assert isinstance(vecs[0], list)
    assert pytest.approx(vecs[0]) == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_embed_chunks_without_db():
    """Verify embed_chunks without database session embeds missing items directly."""
    mock_provider = MagicMock()

    async def fake_embed(texts, model=None):
        return [[1.0, 0.0] for _ in texts]

    mock_provider.embed = fake_embed

    chunks = [
        CodeChunk(
            path="src/app.py",
            qualname="app.main",
            kind="function",
            signature="def main():",
            docstring="",
            start_line=1,
            end_line=5,
            body="def main(): pass",
            is_test=False,
            content="def main(): pass",
            content_hash="hash_123",
        )
    ]

    res = await embed_chunks(chunks=chunks, embedder=mock_provider, db=None)
    assert "hash_123" in res
    assert res["hash_123"] == [1.0, 0.0]


def test_get_default_embedder_singleton():
    """Verify get_default_embedder returns cached singleton."""
    emb1 = get_default_embedder("test-model-1")
    emb2 = get_default_embedder("test-model-1")
    assert emb1 is emb2
