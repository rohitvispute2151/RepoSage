"""LLM usage ledger and cost accounting.

Computes dollar spend per request from token pricing tiers, logs audit records
to the database, and updates Prometheus metrics and in-memory accumulators.
"""

from typing import Any, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from reposage.config import settings
from reposage.db.models import LLMCall
from reposage.llm.types import LLMRequest, LLMResponse
from reposage.observability.metrics import (
    llm_calls_total,
    llm_cost_usd_total,
    llm_latency_seconds,
    llm_tokens_total,
)


def calculate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Calculate USD cost for an LLM call based on model pricing table."""
    price_in = settings.pricing_in_per_million.get(model, 1.0)
    price_out = settings.pricing_out_per_million.get(model, 3.0)

    cost_in = (tokens_in / 1_000_000.0) * price_in
    cost_out = (tokens_out / 1_000_000.0) * price_out
    return round(cost_in + cost_out, 6)


class CostLedger:
    """Records LLM usage to database and in-memory budget tracking state."""

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        # In-memory accumulators: task_id -> {"tokens": int, "usd": float, "calls": int}
        self.task_spend: dict[str, dict[str, float]] = {}

    def get_task_spend(self, task_id: str) -> dict[str, float]:
        """Return running spend statistics for an active task."""
        return self.task_spend.get(task_id, {"tokens": 0.0, "usd": 0.0, "calls": 0.0})

    async def record(
        self,
        resp: LLMResponse,
        req: LLMRequest,
        *,
        retries: int = 0,
        fallback_used: bool = False,
        outcome: str = "ok",
    ) -> float:
        """Record usage, calculate cost, update metrics, and persist audit log."""
        cost = calculate_cost_usd(resp.model, resp.tokens_in, resp.tokens_out)
        node = req.meta.get("node", "unknown")
        task_id_str = req.meta.get("task_id")

        # 1. Update in-memory task budget tracking
        if task_id_str:
            cur = self.task_spend.setdefault(
                task_id_str, {"tokens": 0.0, "usd": 0.0, "calls": 0.0}
            )
            cur["tokens"] += resp.tokens_in + resp.tokens_out
            cur["usd"] += cost
            cur["calls"] += 1.0

        # 2. Update Prometheus metrics
        llm_calls_total.labels(
            provider=resp.provider, model=resp.model, outcome=outcome
        ).inc()
        llm_tokens_total.labels(model=resp.model, direction="in").inc(
            resp.tokens_in
        )
        llm_tokens_total.labels(model=resp.model, direction="out").inc(
            resp.tokens_out
        )
        llm_cost_usd_total.labels(model=resp.model, node=node).inc(cost)
        llm_latency_seconds.labels(model=resp.model).observe(
            resp.latency_ms / 1000.0
        )

        # 3. Persist record to DB if session is active
        if self.db is not None:
            task_uuid = uuid.UUID(task_id_str) if task_id_str else None
            record_row = LLMCall(
                task_id=task_uuid,
                node=node,
                provider=resp.provider,
                model=resp.model,
                prompt_name=req.meta.get("prompt_name"),
                prompt_hash=req.meta.get("prompt_hash"),
                tokens_in=resp.tokens_in,
                tokens_out=resp.tokens_out,
                cost_usd=cost,
                latency_ms=resp.latency_ms,
                retries=retries,
                fallback_used=fallback_used,
                outcome=outcome,
            )
            self.db.add(record_row)
            await self.db.commit()

        return cost
