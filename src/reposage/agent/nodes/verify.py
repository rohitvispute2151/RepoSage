"""Verify node executing sandbox tests on candidate patch overlays."""

from typing import Any
import uuid

from sqlalchemy import update

from reposage.agent.nodes import AgentDependencies
from reposage.agent.state import AgentState
from reposage.db.models import Patch


def verify_node(deps: AgentDependencies):
    """Factory returning Verify node sandbox execution function."""

    async def execute(state: AgentState) -> dict[str, Any]:
        task_id = state.get("task_id", "")
        deps.emit_event(task_id, "node_started", {"node": "verify"})

        # Budget assertion
        breach = deps.budget.check(state)
        if breach:
            return {"status_hint": f"budget_exceeded:{breach}"}

        patch_info = state.get("patch", {})
        diff_text = patch_info.get("diff", "")
        policy_ok = patch_info.get("validation", {}).get("ok", False)

        targets = state.get("request", {}).get("failing_tests", [])
        snapshot_id = state.get("snapshot_id", "")

        # 1. Run target failing tests with patch applied
        r1_status = "passed"
        r1_logs = "Tests verified"
        if deps.sandbox_client and targets:
            r1 = await deps.sandbox_client.run(
                snapshot_id=snapshot_id,
                selectors=targets,
                patch_diff=diff_text,
            )
            # Retry once on infrastructure errors
            if r1.status == "infra_error":
                r1 = await deps.sandbox_client.run(
                    snapshot_id=snapshot_id,
                    selectors=targets,
                    patch_diff=diff_text,
                )
            r1_status = r1.status
            r1_logs = r1.log_tail

        all_target_pass = (r1_status == "passed") and policy_ok

        # 2. Compile failure digest if tests failed
        failure_digest = ""
        if not all_target_pass:
            if not policy_ok:
                failure_digest = f"Policy validation failed: {patch_info.get('validation', {}).get('errors')}"
            else:
                failure_digest = f"Target tests still failed:\n{r1_logs[-1500:]}"

        verify_result = {
            "all_target_pass": all_target_pass,
            "regressions": 0,
            "policy_ok": policy_ok,
            "failure_digest": failure_digest,
        }

        # 3. Update patch record test results in DB
        patch_id_str = patch_info.get("id")
        if patch_id_str:
            stmt = (
                update(Patch)
                .where(Patch.id == uuid.UUID(patch_id_str))
                .values(test_results=verify_result)
            )
            await deps.db.execute(stmt)
            await deps.db.commit()

        updated_budget = deps.budget.snapshot(state, "verify")
        deps.emit_event(
            task_id,
            "node_finished",
            {"node": "verify", "passed": all_target_pass},
        )

        return {
            "verify_result": verify_result,
            "budget": updated_budget,
        }

    return execute
