"""OpenAI provider implementation via standard HTTP client."""

import json
import logging
import os
import time
from typing import Any

import httpx

from reposage.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """Invokes OpenAI Chat Completions and Embeddings endpoints."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        name: str = "openai",
    ):
        self.name = name
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url.rstrip("/")

    async def chat(self, req: LLMRequest) -> LLMResponse:
        """Call chat completions with tools and structured output."""
        start = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages_payload: list[dict[str, Any]] = []
        for m in req.messages:
            msg: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.name:
                msg["name"] = m.name
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            if m.tool_calls:
                call_list = []
                for i, tc in enumerate(m.tool_calls):
                    call_dict: dict[str, Any] = {
                        "id": tc.get("id") or f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": tc.get("name"),
                            "arguments": json.dumps(tc.get("args", {}))
                            if isinstance(tc.get("args"), dict)
                            else str(tc.get("args", "{}")),
                        },
                    }
                    if "extra_content" in tc and tc["extra_content"]:
                        call_dict["extra_content"] = tc["extra_content"]
                    call_list.append(call_dict)
                msg["tool_calls"] = call_list
            messages_payload.append(msg)

        payload: dict[str, Any] = {
            "model": req.model,
            "messages": messages_payload,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }

        if req.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.json_schema,
                    },
                }
                for t in req.tools
            ]

        if req.response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": req.response_schema, "strict": True},
            }

        async with httpx.AsyncClient(timeout=req.timeout_s) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            if resp.status_code >= 400:
                logger.error("Provider %s error %d: %s", self.name, resp.status_code, resp.text)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        msg_out = choice["message"]
        tool_calls: list[dict[str, Any]] = []
        if "tool_calls" in msg_out and msg_out["tool_calls"]:
            for tc in msg_out["tool_calls"]:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except Exception:
                    args = {}
                call_info: dict[str, Any] = {
                    "name": tc["function"]["name"],
                    "args": args,
                    "id": tc.get("id"),
                }
                if "extra_content" in tc:
                    call_info["extra_content"] = tc["extra_content"]
                tool_calls.append(call_info)

        usage = data.get("usage", {})
        latency = int((time.perf_counter() - start) * 1000)

        return LLMResponse(
            text=msg_out.get("content") or msg_out.get("reasoning"),
            tool_calls=tool_calls,
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            model=req.model,
            provider=self.name,
            latency_ms=latency,
            raw_stop_reason=choice.get("finish_reason", "stop"),
        )

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Call embeddings endpoint."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"input": texts, "model": model}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self.base_url}/embeddings", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # Sort items by index to preserve input ordering
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_data]
