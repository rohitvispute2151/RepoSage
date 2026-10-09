"""Structured JSON logging with request and task correlation.

Ensures all log messages are formatted in standard JSON and automatically
passed through secret redaction.
"""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import sys
from typing import Any

from reposage.observability.secrets import redact_secrets

# Context variables for request and task correlation
current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)
current_task_id: ContextVar[str | None] = ContextVar("current_task_id", default=None)


class JSONFormatter(logging.Formatter):
    """Formats log records as structured, secret-scanned JSON strings."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "msg": redact_secrets(record.getMessage()),
            "logger": record.name,
        }

        # Include ambient context variables
        req_id = current_request_id.get()
        if req_id:
            log_entry["request_id"] = req_id

        task_id = current_task_id.get()
        if task_id:
            log_entry["task_id"] = task_id

        # Merge extra properties passed directly on record
        for key in (
            "step_id",
            "node",
            "tool",
            "provider",
            "model",
            "duration_ms",
            "error_kind",
        ):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with structured JSON formatting."""
    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)


logger = logging.getLogger("reposage")
