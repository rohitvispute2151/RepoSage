"""Per-provider circuit breaker protecting against upstream API outages.

Transitions through CLOSED, OPEN, and HALF_OPEN states to shed load when a provider
exhibits consecutive failures, automatically attempting probes after cooldown.
"""

from collections import deque
import time


class CircuitBreaker:
    """Stateful circuit breaker tracking consecutive failure counts within a sliding window."""

    def __init__(
        self,
        fail_threshold: int = 5,
        window_s: float = 30.0,
        cooldown_s: float = 20.0,
    ) -> None:
        self.fail_threshold = fail_threshold
        self.window_s = window_s
        self.cooldown_s = cooldown_s

        self.state: str = "CLOSED"  # 'CLOSED', 'OPEN', 'HALF_OPEN'
        self.failure_times: deque[float] = deque()
        self.opened_at: float = 0.0

    def allow(self) -> bool:
        """Check whether outgoing requests should be permitted."""
        now = time.monotonic()

        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            if now - self.opened_at >= self.cooldown_s:
                self.state = "HALF_OPEN"
                return True
            return False

        if self.state == "HALF_OPEN":
            # Allow single probe request
            return True

        return True

    def record_success(self) -> None:
        """Record a successful call, resetting failure counters and closing the breaker."""
        if self.state in {"HALF_OPEN", "OPEN"}:
            self.state = "CLOSED"
        self.failure_times.clear()

    def record_failure(self) -> None:
        """Record an upstream failure and open the breaker if threshold is reached."""
        now = time.monotonic()
        self.failure_times.append(now)

        # Evict failures outside time window
        while self.failure_times and now - self.failure_times[0] > self.window_s:
            self.failure_times.popleft()

        if self.state == "HALF_OPEN":
            self.state = "OPEN"
            self.opened_at = now
        elif len(self.failure_times) >= self.fail_threshold:
            self.state = "OPEN"
            self.opened_at = now
