"""Global configuration and settings management for RepoSage.

Loads runtime configuration from environment variables with sensible defaults
for local development, CI pipelines, and production deployments.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for RepoSage service layers, model tiers, and budget limits."""

    # Runtime environment flag ('local', 'ci', or 'prod')
    env: str = "local"

    # Database connection string (asyncpg driver for PostgreSQL)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/reposage"
    # Redis broker and ephemeral cache URL
    redis_url: str = "redis://localhost:6379/0"

    # Default authentication key for API client validation
    api_key: str = "reposage-dev-key"

    # Base filesystem directory for cloned repository mirrors and working trees
    storage_root: Path = Path("/tmp/reposage/repos")
    # Base directory containing versioned prompt markdown definitions
    prompts_dir: Path = Path(__file__).resolve().parent.parent.parent / "prompts"

    # Primary & Fallback LLM Provider configurations (Google Gemini + Groq)
    gemini_api_key: str | None = None
    gemini_model_id: str = "gemini-flash-lite-latest"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"

    groq_api_key: str | None = None
    groq_model_id: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Model IDs partitioned by tier to allow independent ablation and cost optimization
    model_small: str = "gemini-flash-lite-latest"    # Fast classification & query rewrites
    model_mid: str = "gemini-flash-lite-latest"      # Multi-turn tool selection in Explore
    model_strong: str = "gemini-flash-lite-latest"   # Complex reasoning for code patches
    model_fallback: str = "openai/gpt-oss-120b"      # Provider-outage fallback model
    embedding_model: str = "jinaai/jina-embeddings-v2-base-code"  # Code & text semantic vector model
    embedding_dim: int = 768                         # Vector dimensions for pgvector
    embedding_device: str = "cpu"                    # Device for local embedding model ('cpu', 'cuda', 'mps')

    # Retrieval pipeline parameters
    retrieve_vector_k: int = 40  # Top candidates retrieved via pgvector cosine similarity
    retrieve_lexical_k: int = 40 # Top candidates retrieved via full-text search (tsvector)
    rrf_k: int = 60              # Reciprocal Rank Fusion constant denominator
    rerank_input_n: int = 30     # Pre-filtered candidate pool sent to the reranker
    rerank_output_n: int = 8     # Final top-k symbols provided to agent evidence
    reranker_type: str = "noop"  # 'noop', 'cross_encoder', or 'llm'

    # Safety budgets and task termination guards
    budget_max_steps: int = 30        # Maximum graph node executions per task
    budget_max_tokens: int = 250_000  # Combined input + output token ceiling per task
    budget_max_usd: float = 1.00      # Hard dollar spending limit per task
    budget_max_seconds: int = 900     # 15-minute wall-clock timeout
    patch_max_repair_attempts: int = 3 # Maximum fix retries upon test verification failure
    patch_max_lines_changed: int = 80  # Upper bound on diff size for policy compliance
    patch_max_files: int = 3           # Upper bound on touched files in a candidate patch
    loop_repeat_threshold: int = 3     # Duplicate (tool, args) count triggering loop detector

    # MCP tool safety boundaries
    tool_output_max_chars: int = 12_000 # Truncation limit on single tool response stdout
    read_file_max_lines: int = 300      # Maximum continuous line span per read_file call

    # Isolated Docker execution sandbox settings
    sandbox_url: str = "http://localhost:9000" # Dedicated runner service HTTP endpoint
    sandbox_cpu: float = 1.0                  # Dedicated CPU quota allocated to container
    sandbox_mem_mb: int = 1024                # Hard memory cap in megabytes
    sandbox_pids: int = 256                   # Process limit preventing fork-bomb attacks
    sandbox_timeout_s: int = 300              # Maximum test execution duration in seconds
    sandbox_slots: int = 4                    # Concurrency semaphore for parallel sandbox jobs

    # Celery worker lease and human approval timeout
    lease_ttl_s: int = 60          # Distributed task lease validity period
    lease_renew_s: int = 20        # Heartbeat lease renewal interval
    approval_ttl_s: int = 24 * 3600 # 24-hour expiration window for pending human review

    # Price table for token cost calculations ($ per million tokens)
    pricing_in_per_million: dict[str, float] = {
        "claude-3-5-haiku-latest": 0.80,
        "claude-3-5-sonnet-latest": 3.00,
        "claude-3-7-sonnet-latest": 3.00,
        "gpt-4o-mini": 0.15,
        "text-embedding-3-small": 0.02,
        "jinaai/jina-embeddings-v2-base-code": 0.00,
    }
    pricing_out_per_million: dict[str, float] = {
        "claude-3-5-haiku-latest": 4.00,
        "claude-3-5-sonnet-latest": 15.00,
        "claude-3-7-sonnet-latest": 15.00,
        "gpt-4o-mini": 0.60,
        "text-embedding-3-small": 0.00,
        "jinaai/jina-embeddings-v2-base-code": 0.00,
    }

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Singleton settings instance
settings = Settings()
