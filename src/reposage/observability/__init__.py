"""Observability tools: metrics, tracing, logging, and secret redaction."""

from reposage.observability.logging import (
    JSONFormatter,
    current_request_id,
    current_task_id,
    logger,
    setup_logging,
)
from reposage.observability.metrics import (
    approvals_total,
    budget_breaches_total,
    llm_calls_total,
    llm_cost_usd_total,
    llm_latency_seconds,
    llm_tokens_total,
    loop_detections_total,
    policy_denials_total,
    retrieval_latency_seconds,
    sandbox_queue_wait_seconds,
    sandbox_runs_total,
    task_duration_seconds,
    task_resumes_total,
    tasks_total,
    tool_calls_total,
)
from reposage.observability.secrets import (
    redact_secrets,
    sanitize_payload,
    shannon_entropy,
)
from reposage.observability.tracing import Span, Tracer, span, tracer

__all__ = [
    "redact_secrets",
    "sanitize_payload",
    "shannon_entropy",
    "logger",
    "setup_logging",
    "current_request_id",
    "current_task_id",
    "JSONFormatter",
    "tasks_total",
    "task_duration_seconds",
    "llm_calls_total",
    "llm_tokens_total",
    "llm_cost_usd_total",
    "llm_latency_seconds",
    "retrieval_latency_seconds",
    "tool_calls_total",
    "policy_denials_total",
    "sandbox_runs_total",
    "sandbox_queue_wait_seconds",
    "budget_breaches_total",
    "loop_detections_total",
    "approvals_total",
    "task_resumes_total",
    "Span",
    "Tracer",
    "tracer",
    "span",
]
