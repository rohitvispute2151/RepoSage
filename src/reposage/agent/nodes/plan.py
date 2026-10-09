"""Plan node formulating initial triage hypotheses and test reproduction baselines."""

import json
from typing import Any

from reposage.agent.nodes import AgentDependencies
from reposage.agent.state import AgentState
from reposage.config import settings
from reposage.llm.prompts import load_prompt
from reposage.llm.types import LLMRequest, Message


def plan_node(deps: AgentDependencies):
    """Factory returning Plan node execution function."""

    async def execute(state: AgentState) -> dict[str, Any]:
        task_id = state.get("task_id", "")
        deps.emit_event(task_id, "node_started", {"node": "plan"})

        # 1. Check budget ceiling
        breach = deps.budget.check(state)
        if breach:
            return {"status_hint": f"budget_exceeded:{breach}"}

        mode = state.get("mode", "qa")
        req_data = state.get("request", {})
        repo_map_summary = state.get("repo_map_summary", "")

        try:
            prompt_text, phash = load_prompt("plan.v1.md")
        except Exception:
            prompt_text = "Triage the following codebase request."
            phash = "static_plan"

        user_content = (
            f"Mode: {mode}\n"
            f"Request: {json.dumps(req_data)}\n"
            f"Repo Map Outline: {repo_map_summary[:2000]}"
        )

        resp = await deps.llm.chat(
            LLMRequest(
                model=settings.model_small,
                messages=[
                    Message(role="system", content=prompt_text),
                    Message(role="user", content=user_content),
                ],
                max_tokens=800,
                temperature=0.0,
                meta={
                    "task_id": task_id,
                    "node": "plan",
                    "prompt_name": "plan.v1.md",
                    "prompt_hash": phash,
                },
            )
        )

        plan_data: dict[str, Any] = {}
        if resp.text:
            try:
                plan_data = json.loads(resp.text)
            except Exception:
                plan_data = {
                    "kind": mode,
                    "hypotheses": ["Initial triage completed"],
                }

        # 2. For fix tasks: run baseline tests to verify failing test reproduction
        baseline_results: dict[str, Any] | None = None
        if mode == "fix" and deps.sandbox_client:
            failing_selectors = req_data.get("failing_tests", [])
            if failing_selectors:
                baseline_run = await deps.sandbox_client.run(
                    snapshot_id=state.get("snapshot_id", ""),
                    selectors=failing_selectors,
                    patch_diff=None,
                )
                baseline_results = {
                    "status": baseline_run.status,
                    "summary": baseline_run.summary.model_dump(),
                    "log_tail": baseline_run.log_tail,
                }
                # If baseline unexpectedly passes, flag non-reproducible outcome
                if baseline_run.status == "passed":
                    return {
                        "plan": plan_data,
                        "baseline_test_results": baseline_results,
                        "status_hint": "not_reproducible",
                    }

        updated_budget = deps.budget.snapshot(state, "plan")
        deps.emit_event(task_id, "node_finished", {"node": "plan"})

        return {
            "plan": plan_data,
            "baseline_test_results": baseline_results,
            "budget": updated_budget,
        }

    return execute
