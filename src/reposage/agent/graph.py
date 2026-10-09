"""LangGraph state machine graph compilation and conditional routing.

Defines the explicit state transitions governing Plan, Retrieve, Explore, Patch,
Verify, Approval, and Report nodes.
"""

from typing import Any

from langgraph.graph import END, START, StateGraph

from reposage.agent.nodes import AgentDependencies
from reposage.agent.nodes.approval import approval_node
from reposage.agent.nodes.explore import explore_node
from reposage.agent.nodes.patch import patch_node
from reposage.agent.nodes.plan import plan_node
from reposage.agent.nodes.report import report_node
from reposage.agent.nodes.retrieve import retrieve_node
from reposage.agent.nodes.verify import verify_node
from reposage.agent.state import AgentState
from reposage.config import settings


def route_after_plan(state: AgentState) -> str:
    """Route to report on baseline reproduction failure or budget breach, otherwise retrieve."""
    if state.get("status_hint"):
        return "report"
    return "retrieve"


def route_after_explore(state: AgentState) -> str:
    """Continue tool loop if exploration incomplete; route to report for QA or patch for Fix."""
    if state.get("status_hint"):
        return "report"
    if state.get("plan", {}).get("explore_done") is not True:
        return "explore"
    return "report" if state.get("mode") == "qa" else "patch"


def route_after_verify(state: AgentState) -> str:
    """Route to approval gate on passing tests; repair loop back to patch or exit to report."""
    if state.get("status_hint"):
        return "report"

    v = state.get("verify_result") or {}
    if (
        v.get("all_target_pass")
        and v.get("regressions", 0) == 0
        and v.get("policy_ok", False)
    ):
        return "approval"

    if state.get("patch_attempts", 0) >= settings.patch_max_repair_attempts:
        return "report"  # Repair attempts exhausted

    return "patch"


def route_after_approval(state: AgentState) -> str:
    """Route edited diff back to verification sandbox; otherwise finalize report."""
    approval_decision = state.get("approval", {}).get("decision")
    if approval_decision == "edit":
        return "verify"
    return "report"


def build_graph(deps: AgentDependencies, checkpointer: Any = None):
    """Assemble and compile the RepoSage LangGraph agent."""
    workflow = StateGraph(AgentState)

    # Register graph nodes
    workflow.add_node("plan", plan_node(deps))
    workflow.add_node("retrieve", retrieve_node(deps))
    workflow.add_node("explore", explore_node(deps))
    workflow.add_node("patch", patch_node(deps))
    workflow.add_node("verify", verify_node(deps))
    workflow.add_node("approval", approval_node(deps))
    workflow.add_node("report", report_node(deps))

    # Connect edges
    workflow.add_edge(START, "plan")
    workflow.add_conditional_edges(
        "plan",
        route_after_plan,
        {"retrieve": "retrieve", "report": "report"},
    )
    workflow.add_edge("retrieve", "explore")
    workflow.add_conditional_edges(
        "explore",
        route_after_explore,
        {"explore": "explore", "patch": "patch", "report": "report"},
    )
    workflow.add_edge("patch", "verify")
    workflow.add_conditional_edges(
        "verify",
        route_after_verify,
        {"patch": "patch", "approval": "approval", "report": "report"},
    )
    workflow.add_conditional_edges(
        "approval",
        route_after_approval,
        {"verify": "verify", "report": "report"},
    )
    workflow.add_edge("report", END)

    return workflow.compile(checkpointer=checkpointer)
