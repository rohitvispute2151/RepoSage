"""Unified type definitions and protocols for LLM interactions.

Abstracts model providers (Anthropic, OpenAI, Bedrock, Stubs) behind common
request/response data structures and tool calling conventions.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Message:
    """Chat message exchanged with an LLM provider."""

    role: str  # 'system', 'user', 'assistant', 'tool'
    content: str | list[dict[str, Any]]
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


@dataclass
class ToolSpec:
    """Schema defining a tool available to the model."""

    name: str
    description: str
    json_schema: dict[str, Any]


@dataclass
class LLMRequest:
    """Standardized invocation request for LLM generation."""

    model: str
    messages: list[Message]
    tools: list[ToolSpec] = field(default_factory=list)
    response_schema: dict[str, Any] | None = None  # Structured output JSON schema
    max_tokens: int = 2048
    temperature: float = 0.0
    timeout_s: float = 60.0
    meta: dict[str, Any] = field(default_factory=dict)  # task_id, node, prompt_name, prompt_hash


@dataclass
class LLMResponse:
    """Standardized response from an LLM provider."""

    text: str | None
    tool_calls: list[dict[str, Any]]
    tokens_in: int
    tokens_out: int
    model: str
    provider: str
    latency_ms: int
    raw_stop_reason: str = "stop"


class Provider(Protocol):
    """Protocol satisfied by all LLM client implementations."""

    name: str

    async def chat(self, req: LLMRequest) -> LLMResponse: ...
    async def embed(self, texts: list[str], model: str) -> list[list[float]]: ...
