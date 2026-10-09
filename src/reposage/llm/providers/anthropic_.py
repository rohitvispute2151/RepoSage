"""Anthropic provider implementation via standard HTTP messages API."""

import json
import os
import time
from typing import Any

import httpx

from reposage.llm.types import LLMRequest, LLMResponse


class AnthropicProvider:
    """Invokes Anthropic Messages API."""

    name: str = "anthropic"

    def __init__(self, api_key: str | None = None, base_url: str = "https://api.anthropic.com/v1"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.base_url = base_url.rstrip("/")

    async def chat(self, req: LLMRequest) -> LLMResponse:
        """Call Anthropic Messages endpoint."""
        start = time.perf_counter()
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        # Separate system messages from user/assistant turns
        system_content = ""
        user_msgs: list[dict[str, Any]] = []

        for m in req.messages:
            if m.role == "system":
                system_content += f"\n{m.content}" if system_content else str(m.content)
            elif m.role == "tool":
                user_msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id or "tool_call",
                        "content": str(m.content),
                    }]
                })
            else:
                user_msgs.append({"role": m.role, "content": m.content})

        payload: dict[str, Any] = {
            "model": req.model,
            "messages": user_msgs,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        if system_content:
            payload["system"] = system_content

        if req.tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.json_schema,
                }
                for t in req.tools
            ]

        async with httpx.AsyncClient(timeout=req.timeout_s) as client:
            resp = await client.post(f"{self.base_url}/messages", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for content_block in data.get("content", []):
            if content_block["type"] == "text":
                text_parts.append(content_block["text"])
            elif content_block["type"] == "tool_use":
                tool_calls.append({
                    "name": content_block["name"],
                    "args": content_block["input"],
                    "id": content_block["id"],
                })

        usage = data.get("usage", {})
        latency = int((time.perf_counter() - start) * 1000)

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            tokens_in=usage.get("input_tokens", 0),
            tokens_out=usage.get("output_tokens", 0),
            model=req.model,
            provider="anthropic",
            latency_ms=latency,
            raw_stop_reason=data.get("stop_reason", "end_turn"),
        )

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Anthropic does not offer embeddings; fallback to zero/pseudo vectors."""
        raise NotImplementedError("Anthropic does not host a native embeddings API")
