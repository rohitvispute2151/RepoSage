"""Distributed tracing and span instrumentation for RepoSage.

Provides a unified span context manager compatible with Langfuse, OpenTelemetry,
or local audit event logs with automatic secret redaction.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import time
from typing import Any, Generator

from reposage.observability.logging import logger
from reposage.observability.secrets import sanitize_payload


class Span:
    """Represents an active timed operation within a task trace."""

    def __init__(self, name: str, parent: "Span | None" = None, **attributes: Any):
        self.name = name
        self.parent = parent
        self.attributes = sanitize_payload(attributes)
        self.start_time = time.perf_counter()
        self.created_at = datetime.now(timezone.utc)
        self.duration_ms: float = 0.0
        self.error: Exception | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        """Add or update a sanitized span attribute."""
        self.attributes[key] = sanitize_payload(value)

    def finish(self, error: Exception | None = None) -> None:
        """Mark span completed and record execution latency."""
        self.duration_ms = (time.perf_counter() - self.start_time) * 1000.0
        self.error = error
        logger.debug(
            f"Span '{self.name}' finished in {self.duration_ms:.2f}ms",
            extra={
                "node": self.attributes.get("node"),
                "tool": self.attributes.get("tool"),
                "duration_ms": int(self.duration_ms),
            },
        )


class Tracer:
    """Manages hierarchical span execution and dispatch."""

    def __init__(self) -> None:
        self.current_span: Span | None = None

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Generator[Span, None, None]:
        """Context manager creating and terminating a monitored span."""
        prev = self.current_span
        new_span = Span(name, parent=prev, **attributes)
        self.current_span = new_span
        try:
            yield new_span
            new_span.finish()
        except Exception as exc:
            new_span.finish(error=exc)
            raise
        finally:
            self.current_span = prev


# Global default tracer
tracer = Tracer()
span = tracer.span
