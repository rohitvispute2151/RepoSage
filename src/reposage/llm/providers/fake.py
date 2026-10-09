"""Fake and scriptable LLM provider for deterministic testing and offline evaluations.

Allows tests to replay scripted responses or use pattern-based heuristics
without reaching external model APIs.
"""

import hashlib
import json
import time
from typing import Any, Callable

from reposage.llm.types import LLMRequest, LLMResponse


class FakeProvider:
    """Mock LLM provider returning programmed responses or default structured payloads."""

    name: str = "fake"

    def __init__(self) -> None:
        # Pre-recorded responses keyed by request hash
        self.recorded_responses: dict[str, LLMResponse] = {}
        # Dynamic response handler
        self.custom_handler: (
            Callable[[LLMRequest], LLMResponse | None] | None
        ) = None
        # Embeddings dimension
        self.embedding_dim: int = 1024

    def record_response(self, prompt_hash: str, response: LLMResponse) -> None:
        """Register a canned response for a given prompt hash."""
        self.recorded_responses[prompt_hash] = response

    async def chat(self, req: LLMRequest) -> LLMResponse:
        """Generate response using custom handler, recorded table, or sensible defaults."""
        start = time.perf_counter()

        if self.custom_handler:
            custom_resp = self.custom_handler(req)
            if custom_resp is not None:
                return custom_resp

        prompt_hash = req.meta.get("prompt_hash")
        if prompt_hash and prompt_hash in self.recorded_responses:
            return self.recorded_responses[prompt_hash]

        # Check prompt name for realistic mock payloads
        prompt_name = req.meta.get("prompt_name", "")
        last_msg = req.messages[-1].content if req.messages else ""
        last_text = (
            last_msg
            if isinstance(last_msg, str)
            else json.dumps(last_msg)
        )

        resp_text: str | None = "Processed request successfully."
        tool_calls: list[dict[str, Any]] = []

        if "plan" in prompt_name:
            resp_text = json.dumps(
                {
                    "kind": "qa",
                    "hypotheses": ["Relevant logic located in service module"],
                    "key_terms": ["retry", "handler"],
                    "stop_conditions": ["Identified retry configuration function"],
                }
            )
        elif "rewrite" in prompt_name:
            resp_text = json.dumps(
                {
                    "nl_queries": ["how is retry backoff configured"],
                    "identifiers": ["retry_backoff", "RetryConfig"],
                    "file_hints": ["retry.py", "config.py"],
                    "error_strings": [],
                }
            )
        elif "explore" in prompt_name:
            # If search tool available and not yet called, suggest search_code
            if req.tools and not any(
                m.role == "tool" for m in req.messages
            ):
                tool_calls = [
                    {
                        "name": "search_code",
                        "args": {"query": "retry backoff", "limit": 3},
                    }
                ]
                resp_text = None
            else:
                resp_text = "DONE: Located retry mechanism in src/http.py"
        elif "patch" in prompt_name:
            resp_text = json.dumps(
                {
                    "root_cause": "Inverted boolean comparison in retry check",
                    "files": ["src/http.py"],
                    "unified_diff": (
                        "--- a/src/http.py\n+++ b/src/http.py\n"
                        "@@ -10,1 +10,1 @@\n"
                        "-    if retries <= 0:\n"
                        "+    if retries > 0:\n"
                    ),
                    "rationale": "Corrected retry loop conditional boundary",
                    "confidence": "high",
                }
            )
        elif "answer" in prompt_name:
            resp_text = json.dumps(
                {
                    "answer": "Retry logic is implemented in `src/http.py` via exponential backoff.",
                    "citations": [
                        {
                            "path": "src/http.py",
                            "start_line": 10,
                            "end_line": 20,
                            "symbol": "http.compute_backoff",
                        }
                    ],
                    "found": True,
                }
            )
        elif "judge_qa" in prompt_name:
            resp_text = json.dumps(
                {
                    "correct": True,
                    "reason": "Accurately identified retry module and line numbers",
                    "cites_gold": True,
                }
            )
        elif req.response_schema:
            resp_text = "{}"

        latency = int((time.perf_counter() - start) * 1000)
        return LLMResponse(
            text=resp_text,
            tool_calls=tool_calls,
            tokens_in=len(last_text.split()) + 50,
            tokens_out=len(resp_text.split()) if resp_text else 20,
            model=req.model,
            provider="fake",
            latency_ms=max(1, latency),
            raw_stop_reason="stop",
        )

    async def embed(
        self, texts: list[str], model: str
    ) -> list[list[float]]:
        """Generate deterministic pseudo-vectors from text MD5 hashes."""
        vectors: list[list[float]] = []
        for text in texts:
            # Hash text into deterministic pseudo vector
            digest = hashlib.md5(text.encode("utf-8")).digest()
            vec = [
                ((digest[i % len(digest)] / 255.0) - 0.5) * 2.0
                for i in range(self.embedding_dim)
            ]
            # Normalize vector magnitude
            mag = sum(x * x for x in vec) ** 0.5 or 1.0
            norm_vec = [x / mag for x in vec]
            vectors.append(norm_vec)
        return vectors
