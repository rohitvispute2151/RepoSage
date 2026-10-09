"""Agent state machine and LangGraph orchestration package."""

from reposage.agent.budget import BudgetManager
from reposage.agent.citations import Citation, verify_citation
from reposage.agent.context import compact_messages, estimate_token_count
from reposage.agent.graph import build_graph
from reposage.agent.loops import LoopDetector, compute_call_fingerprint
from reposage.agent.nodes import AgentDependencies
from reposage.agent.patching import (
    PatchProposal,
    PatchValidator,
    ValidationResult,
)
from reposage.agent.state import AgentState, BudgetState, Evidence

__all__ = [
    "AgentState",
    "Evidence",
    "BudgetState",
    "BudgetManager",
    "LoopDetector",
    "compute_call_fingerprint",
    "PatchProposal",
    "PatchValidator",
    "ValidationResult",
    "Citation",
    "verify_citation",
    "compact_messages",
    "estimate_token_count",
    "AgentDependencies",
    "build_graph",
]
