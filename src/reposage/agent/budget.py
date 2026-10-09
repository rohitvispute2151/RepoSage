"""Budget manager enforcing step, token, dollar cost, and latency caps.

Terminates runaway loops early and injects wrap-up directives near budget exhaustion.
"""

import time
from typing import Any

from reposage.agent.state import AgentState, BudgetState
from reposage.observability.metrics import budget_breaches_total


class BudgetManager:
    """Monitors and asserts task resource budgets."""

    def check(self, state: AgentState) -> str | None:
        """Evaluate resource counters against maximum allowable ceilings."""
        budget: BudgetState = state.get("budget", {})  # type: ignore
        limits = budget.get("limits", {})
        if not limits:
            return None

        # Check step count
        if budget.get("steps", 0) >= limits.get("max_steps", 30):
            budget_breaches_total.labels(type="steps").inc()
            return "steps"

        # Check token usage
        if budget.get("tokens", 0) >= limits.get("max_tokens", 250_000):
            budget_breaches_total.labels(type="tokens").inc()
            return "tokens"

        # Check total dollar cost
        if budget.get("usd", 0.0) >= limits.get("max_usd", 1.0):
            budget_breaches_total.labels(type="usd").inc()
            return "usd"

        # Check elapsed wall-clock seconds
        elapsed = time.time() - budget.get("started_at", time.time())
        if elapsed >= limits.get("max_seconds", 900):
            budget_breaches_total.labels(type="seconds").inc()
            return "seconds"

        return None

    def check_midnode(self, state: AgentState) -> str | None:
        """Perform lightweight budget assertion between tool calls inside Explore loop."""
        return self.check(state)

    def snapshot(self, state: AgentState, node_name: str) -> BudgetState:
        """Return updated budget dictionary with incremented step counter."""
        cur = dict(state.get("budget", {}))
        cur["steps"] = cur.get("steps", 0) + 1
        return cur  # type: ignore
