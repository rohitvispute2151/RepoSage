"""LLM gateway, client abstractions, and prompt management."""

from reposage.llm.breaker import CircuitBreaker
from reposage.llm.client import (
    LLMFatalError,
    LLMUnavailableError,
    ResilientLLM,
    SchemaError,
    TokenBucketLimiter,
)
from reposage.llm.ledger import CostLedger, calculate_cost_usd
from reposage.llm.prompts import compute_config_fingerprint, load_prompt
from reposage.llm.providers.fake import FakeProvider
from reposage.llm.types import (
    LLMRequest,
    LLMResponse,
    Message,
    Provider,
    ToolSpec,
)

__all__ = [
    "Message",
    "ToolSpec",
    "LLMRequest",
    "LLMResponse",
    "Provider",
    "CircuitBreaker",
    "CostLedger",
    "calculate_cost_usd",
    "load_prompt",
    "compute_config_fingerprint",
    "TokenBucketLimiter",
    "ResilientLLM",
    "LLMUnavailableError",
    "LLMFatalError",
    "SchemaError",
    "FakeProvider",
]
