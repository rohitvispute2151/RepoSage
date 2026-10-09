"""Resilient LLM client wrapper with multi-provider fallback and retry policies.

Handles provider circuit breaking, token rate limiting, full-jitter exponential backoff,
cost auditing, and structured JSON schema repair loops.
"""

import asyncio
from dataclasses import replace
import json
import random
import time
from typing import Any

from jsonschema import ValidationError, validate

from reposage.llm.breaker import CircuitBreaker
from reposage.llm.ledger import CostLedger
from reposage.llm.types import LLMRequest, LLMResponse, Message, Provider
from reposage.observability.logging import logger

MAX_RETRIES: int = 3
BACKOFF_BASE: float = 0.5
BACKOFF_CAP: float = 8.0


class LLMError(Exception):
    """Base exception for LLM client failures."""
    pass


class LLMFatalError(LLMError):
    """Non-retryable client error (e.g. invalid request format or authentication rejection)."""
    pass


class LLMUnavailableError(LLMError):
    """Raised when all configured providers in the fallback chain have been exhausted."""
    pass


class SchemaError(LLMError):
    """Model output failed JSON schema validation."""
    pass


def full_jitter_backoff(attempt: int) -> float:
    """Calculate exponential sleep duration with full random jitter."""
    return random.uniform(0, min(BACKOFF_CAP, BACKOFF_BASE * (2**attempt)))


class TokenBucketLimiter:
    """In-memory rate limiter tracking token and request rate bounds."""

    def __init__(self, requests_per_minute: int = 600, tokens_per_minute: int = 500_000):
        self.rpm = requests_per_minute
        self.tpm = tokens_per_minute
        self.tokens = tokens_per_minute
        self.requests = requests_per_minute
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, estimated_tokens: int = 1000) -> None:
        """Wait until sufficient capacity exists within the rate limit window."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now

            self.tokens = min(self.tpm, self.tokens + elapsed * (self.tpm / 60.0))
            self.requests = min(self.rpm, self.requests + elapsed * (self.rpm / 60.0))

            if self.tokens < estimated_tokens or self.requests < 1:
                wait_time = max(
                    (estimated_tokens - self.tokens) / (self.tpm / 60.0),
                    (1 - self.requests) / (self.rpm / 60.0),
                    0.05,
                )
                await asyncio.sleep(min(wait_time, 2.0))

            self.tokens -= estimated_tokens
            self.requests -= 1


class ResilientLLM:
    """Orchestrates reliable LLM requests across a prioritized provider chain."""

    def __init__(
        self,
        providers: dict[str, Provider],
        chain: list[tuple[str, str]],
        breakers: dict[str, CircuitBreaker],
        ledger: CostLedger,
        limiter: TokenBucketLimiter | None = None,
    ):
        self.providers = providers
        self.chain = chain  # [(provider_name, model_id), ...]
        self.breakers = breakers
        self.ledger = ledger
        self.limiter = limiter or TokenBucketLimiter()

    def _chain_for(self, req: LLMRequest) -> list[tuple[str, str]]:
        """Resolve ordered list of (provider, model) candidates for this request."""
        # Check if the requested model corresponds to any known chain entry
        matching = [entry for entry in self.chain if entry[1] == req.model]
        if matching:
            # Place matching candidate first, followed by remaining fallbacks
            return matching + [e for e in self.chain if e != matching[0]]
        return self.chain

    async def chat(self, req: LLMRequest) -> LLMResponse:
        """Execute chat request with circuit breaking, retries, and fallback failover."""
        last_err: Exception | None = None
        chain_to_try = self._chain_for(req)

        for chain_idx, (pname, model_id) in enumerate(chain_to_try):
            provider = self.providers.get(pname)
            if not provider:
                continue

            breaker = self.breakers.setdefault(pname, CircuitBreaker())
            if not breaker.allow():
                logger.warning(f"Circuit breaker for provider '{pname}' is OPEN. Skipping.")
                continue

            attempt_req = replace(req, model=model_id)

            for attempt in range(MAX_RETRIES + 1):
                await self.limiter.acquire(estimated_tokens=attempt_req.max_tokens)
                try:
                    resp = await asyncio.wait_for(
                        provider.chat(attempt_req),
                        timeout=attempt_req.timeout_s,
                    )

                    # Validate structured JSON schema if requested
                    if attempt_req.response_schema and resp.text:
                        try:
                            parsed_json = json.loads(resp.text)
                            validate(instance=parsed_json, schema=attempt_req.response_schema)
                        except (json.JSONDecodeError, ValidationError) as schema_exc:
                            raise SchemaError(f"Invalid schema: {schema_exc}") from schema_exc

                    breaker.record_success()
                    if self.ledger:
                        await self.ledger.record(
                            resp,
                            attempt_req,
                            retries=attempt,
                            fallback_used=(chain_idx > 0),
                            outcome="ok",
                        )
                    return resp

                except SchemaError as schema_err:
                    # Model response did not match schema: append correction turn and retry
                    last_err = schema_err
                    logger.warning(f"Model schema mismatch (attempt {attempt}): {schema_err}")
                    repair_msg = Message(
                        role="user",
                        content=f"Your previous output failed JSON validation: {schema_err}. Please output strictly valid JSON matching the schema.",
                    )
                    attempt_req = replace(
                        attempt_req,
                        messages=list(attempt_req.messages) + [repair_msg],
                    )

                except asyncio.TimeoutError as timeout_exc:
                    last_err = timeout_exc
                    breaker.record_failure()
                    logger.warning(f"Provider '{pname}' timed out on attempt {attempt}")
                    await asyncio.sleep(full_jitter_backoff(attempt))

                except Exception as exc:
                    err_msg = str(exc).lower()
                    # Check for fatal non-retryable errors (e.g. 400 Bad Request, auth failure)
                    if "401" in err_msg or "403" in err_msg or "invalid api key" in err_msg:
                        raise LLMFatalError(f"Authentication failure: {exc}") from exc

                    last_err = exc
                    breaker.record_failure()
                    logger.warning(f"Provider '{pname}' failure (attempt {attempt}): {exc}")
                    await asyncio.sleep(full_jitter_backoff(attempt))

        raise LLMUnavailableError(f"All LLM providers failed. Last error: {last_err}")

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Call active embedding provider in fallback order."""
        for pname, _ in self.chain:
            provider = self.providers.get(pname)
            if not provider:
                continue
            try:
                return await provider.embed(texts, model=model)
            except Exception as exc:
                logger.warning(f"Embedding failed on provider '{pname}': {exc}")
                continue
        raise LLMUnavailableError("No available provider capable of embedding")
