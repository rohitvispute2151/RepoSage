"""Prometheus metric definitions for RepoSage.

Maintains bounded cardinality labels for system throughput, token consumption,
cost tracking, latency percentiles, and policy rejections.
"""

from prometheus_client import Counter, Histogram

tasks_total = Counter(
    "tasks_total",
    "Total task invocations partitioned by mode, terminal status, and outcome",
    ["mode", "status", "outcome"],
)

task_duration_seconds = Histogram(
    "task_duration_seconds",
    "Overall wall-clock task execution latency",
    ["mode"],
    buckets=[5, 15, 30, 60, 120, 300, 600, 900],
)

llm_calls_total = Counter(
    "llm_calls_total",
    "Total LLM provider calls partitioned by provider, model ID, and outcome",
    ["provider", "model", "outcome"],
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Token usage counter broken down by model and direction (in or out)",
    ["model", "direction"],
)

llm_cost_usd_total = Counter(
    "llm_cost_usd_total",
    "Cumulative dollar spend on LLM calls partitioned by model and graph node",
    ["model", "node"],
)

llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "Latency of individual model API calls",
    ["model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 45.0],
)

retrieval_latency_seconds = Histogram(
    "retrieval_latency_seconds",
    "Latency of retrieval pipeline sub-stages",
    ["stage"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

tool_calls_total = Counter(
    "tool_calls_total",
    "Total tool invocations partitioned by tool name and execution status",
    ["tool", "status"],
)

policy_denials_total = Counter(
    "policy_denials_total",
    "Guardrail denials intercepted before tool execution",
    ["reason"],
)

sandbox_runs_total = Counter(
    "sandbox_runs_total",
    "Test container executions partitioned by status outcome",
    ["status"],
)

sandbox_queue_wait_seconds = Histogram(
    "sandbox_queue_wait_seconds",
    "Queue wait duration while awaiting an available sandbox worker slot",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

budget_breaches_total = Counter(
    "budget_breaches_total",
    "Count of task budget terminations partitioned by budget dimension",
    ["type"],
)

loop_detections_total = Counter(
    "loop_detections_total",
    "Frequency of agent exploration loops intercepted by loop detector",
)

approvals_total = Counter(
    "approvals_total",
    "Human approval decisions submitted",
    ["decision"],
)

task_resumes_total = Counter(
    "task_resumes_total",
    "Frequency of task resumption after worker restart or human review",
    ["reason"],
)
