"""Agent state schemas and TypedDict models for LangGraph orchestration.

Encapsulates conversational turns, structured code evidence, budget trackers,
candidate patches, and human approval states.
"""

from operator import add
from typing import Annotated, Any, Literal, TypedDict


class Evidence(TypedDict):
    """Structured code evidence item with citation anchors."""

    path: str
    start_line: int
    end_line: int
    symbol: str
    snippet: str
    source: str  # 'retrieval' | 'read_file' | 'grep'


class BudgetState(TypedDict):
    """Real-time budget counters and ceilings."""

    steps: int
    tokens: int
    usd: float
    started_at: float
    limits: dict[str, Any]


class AgentState(TypedDict, total=False):
    """Primary state machine dictionary persisted across LangGraph checkpoints."""

    task_id: str
    snapshot_id: str
    mode: Literal["qa", "fix"]
    request: dict[str, Any]
    plan: dict[str, Any]
    repo_map_summary: str
    retrieval: dict[str, Any]
    evidence: Annotated[list[Evidence], add]
    messages: list[dict[str, Any]]
    scratchpad: dict[str, Any]
    baseline_test_results: dict[str, Any] | None
    patch: dict[str, Any] | None
    patch_attempts: int
    verify_result: dict[str, Any] | None
    approval: dict[str, Any] | None
    budget: BudgetState
    loop_fingerprints: dict[str, int]
    status_hint: str | None  # 'budget_exceeded:reason' | 'loop_detected'
    final: dict[str, Any] | None
