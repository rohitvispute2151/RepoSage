"""Repository code ingestion package."""

from reposage.ingest.chunker import CodeChunk, chunk_python
from reposage.ingest.embedder import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingProvider,
    SentenceTransformerEmbedder,
    SentenceTransformerProvider,
    embed_chunks,
    get_default_embedder,
)
from reposage.ingest.identifiers import expand_identifiers
from reposage.ingest.pipeline import ingest_snapshot
from reposage.ingest.walker import DiscoveredFile, is_test_file, walk_repo

__all__ = [
    "walk_repo",
    "is_test_file",
    "DiscoveredFile",
    "CodeChunk",
    "chunk_python",
    "expand_identifiers",
    "EmbeddingProvider",
    "SentenceTransformerEmbedder",
    "SentenceTransformerProvider",
    "DEFAULT_EMBEDDING_MODEL",
    "get_default_embedder",
    "embed_chunks",
    "ingest_snapshot",
]
