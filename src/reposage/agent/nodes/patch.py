"""Patch node generating minimal unified diff bug fix proposals."""

import hashlib
import json
from typing import Any
import uuid

from reposage.agent.nodes import AgentDependencies
from reposage.agent.patching import PatchProposal, PatchValidator
from reposage.agent.state import AgentState
from reposage.config import settings
from reposage.db.models import Patch
from reposage.llm.prompts import load_prompt
from reposage.llm.types import LLMRequest, Message


def patch_node(deps: AgentDependencies):
    """Factory returning Patch node execution function."""

    async def execute(state: AgentState) -> dict[str, Any]:
        task_id = state.get("task_id", "")
        deps.emit_event(task_id, "node_started", {"node": "patch"})

        # Budget assertion
        breach = deps.budget.check(state)
        if breach:
            return {"status_hint": f"budget_exceeded:{breach}"}

        try:
            prompt_text, phash = load_prompt("patch.v1.md")
        except Exception:
            prompt_text = "Generate a minimal unified diff fixing the bug."
            phash = "static_patch"

        # Assemble prompt context
        req_data = state.get("request", {})
        baseline = state.get("baseline_test_results") or {}
        evidence_text = "\n\n".join(
            f"FILE: {e['path']}:{e['start_line']}..{e['end_line']} ({e['symbol']}):\n{e['snippet']}"
            for e in state.get("evidence", [])[:8]
        )

        prior_patch = state.get("patch")
        prior_verify = state.get("verify_result")
        repair_context = ""
        if prior_patch and prior_verify:
            repair_context = (
                f"\nPREVIOUS ATTEMPT FAILED:\n"
                f"Previous Diff:\n{prior_patch.get('diff')}\n"
                f"Failure Details:\n{prior_verify.get('failure_digest', '')}\n"
            )

        user_content = (
            f"Failing Tests: {req_data.get('failing_tests', [])}\n"
            f"Baseline Failure Log:\n{str(baseline.get('log_tail', ''))[:1500]}\n"
            f"Evidence:\n{evidence_text}\n"
            f"{repair_context}\n"
            f"Propose minimal unified diff fixing the failure without modifying tests."
        )

        # Call strongest reasoning tier model
        resp = await deps.llm.chat(
            LLMRequest(
                model=settings.model_strong,
                messages=[
                    Message(role="system", content=prompt_text),
                    Message(role="user", content=user_content),
                ],
                response_schema=PatchProposal.model_json_schema(),
                max_tokens=2500,
                temperature=0.0,
                meta={
                    "task_id": task_id,
                    "node": "patch",
                    "prompt_name": "patch.v1.md",
                    "prompt_hash": phash,
                },
            )
        )

        # Parse patch proposal
        parsed_proposal: PatchProposal
        if resp.text:
            try:
                parsed_proposal = PatchProposal.model_validate(json.loads(resp.text))
            except Exception:
                parsed_proposal = PatchProposal(
                    root_cause="Heuristic fix proposal",
                    files=[],
                    unified_diff=resp.text,
                    rationale="Model generated raw unified diff",
                )
        else:
            parsed_proposal = PatchProposal(
                root_cause="Unknown",
                files=[],
                unified_diff="",
                rationale="No patch content produced",
            )

        # Validate patch against deterministic policies
        validator = PatchValidator()
        val_res = validator.validate(
            parsed_proposal.unified_diff,
            deps.snapshot_root,
        )

        diff_sha = hashlib.sha256(
            parsed_proposal.unified_diff.encode("utf-8")
        ).hexdigest()
        attempt_num = state.get("patch_attempts", 0) + 1

        # Persist patch record to database
        db_patch = Patch(
            task_id=uuid.UUID(task_id),
            attempt=attempt_num,
            diff=parsed_proposal.unified_diff,
            diff_sha256=diff_sha,
            validation={"ok": val_res.ok, "errors": val_res.errors},
        )
        deps.db.add(db_patch)
        await deps.db.commit()

        patch_dict = {
            "id": str(db_patch.id),
            "diff": parsed_proposal.unified_diff,
            "sha256": diff_sha,
            "attempt": attempt_num,
            "rationale": parsed_proposal.rationale,
            "validation": {"ok": val_res.ok, "errors": val_res.errors},
        }

        updated_budget = deps.budget.snapshot(state, "patch")
        deps.emit_event(
            task_id, "node_finished", {"node": "patch", "validation": val_res.ok}
        )

        return {
            "patch": patch_dict,
            "patch_attempts": attempt_num,
            "budget": updated_budget,
        }

    return execute
