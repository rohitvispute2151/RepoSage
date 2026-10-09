"""Human-in-the-loop (HITL) approval gate pausing execution via LangGraph interrupt."""

import subprocess
from typing import Any
import uuid

from langgraph.types import interrupt
from sqlalchemy import update

from reposage.agent.nodes import AgentDependencies
from reposage.agent.patching import PatchValidator
from reposage.agent.state import AgentState
from reposage.db.models import Task


def approval_node(deps: AgentDependencies):
    """Factory returning Approval node pausing for explicit human authorization."""

    async def execute(state: AgentState) -> dict[str, Any]:
        task_id = state.get("task_id", "")
        patch_info = state.get("patch", {})

        pending_payload = {
            "patch_id": patch_info.get("id"),
            "diff": patch_info.get("diff"),
            "sha256": patch_info.get("sha256"),
            "test_evidence": state.get("verify_result"),
            "rationale": patch_info.get("rationale"),
        }

        # Update task status to awaiting_approval
        stmt = (
            update(Task)
            .where(Task.id == uuid.UUID(task_id))
            .values(status="awaiting_approval")
        )
        await deps.db.execute(stmt)
        await deps.db.commit()

        deps.emit_event(task_id, "approval_requested", pending_payload)

        # Graph execution pauses here and resumes when caller passes decision
        decision: dict[str, Any] = interrupt(pending_payload)

        # Resumed: mark status back to running
        stmt_resumed = (
            update(Task)
            .where(Task.id == uuid.UUID(task_id))
            .values(status="running")
        )
        await deps.db.execute(stmt_resumed)
        await deps.db.commit()

        decision_choice = decision.get("decision", "reject")

        # 1. Approved: Apply patch to working tree
        if decision_choice == "approve":
            diff_text = patch_info.get("diff", "")
            # Apply approved diff safely
            applied = True
            apply_err = None
            if deps.snapshot_root.exists() and (deps.snapshot_root / ".git").exists():
                try:
                    proc = subprocess.run(
                        ["git", "apply", "-"],
                        input=diff_text,
                        text=True,
                        cwd=deps.snapshot_root,
                        capture_output=True,
                        timeout=15,
                    )
                    if proc.returncode != 0:
                        applied = False
                        apply_err = proc.stderr
                except Exception as ex:
                    applied = False
                    apply_err = str(ex)

            deps.emit_event(
                task_id,
                "patch_applied",
                {"applied": applied, "error": apply_err},
            )
            return {
                "approval": decision,
                "final": {
                    "applied": applied,
                    "outcome": "patch_applied" if applied else "apply_failed",
                    "error": apply_err,
                },
            }

        # 2. Edit: Human provided modified diff
        if decision_choice == "edit":
            edited_diff = decision.get("edited_diff", "")
            validator = PatchValidator()
            val_res = validator.validate(edited_diff, deps.snapshot_root)
            if not val_res.ok:
                return {
                    "approval": decision,
                    "final": {
                        "applied": False,
                        "outcome": "edited_patch_invalid",
                        "errors": val_res.errors,
                    },
                }

            import hashlib

            new_sha = hashlib.sha256(edited_diff.encode("utf-8")).hexdigest()
            edited_patch_dict = {
                "id": str(uuid.uuid4()),
                "diff": edited_diff,
                "sha256": new_sha,
                "attempt": state.get("patch_attempts", 1),
                "rationale": "Human edited patch",
                "validation": {"ok": True, "errors": []},
            }
            return {
                "approval": decision,
                "patch": edited_patch_dict,
            }

        # 3. Rejected
        deps.emit_event(task_id, "patch_rejected", {"comment": decision.get("comment")})
        return {
            "approval": decision,
            "final": {"applied": False, "outcome": "patch_rejected"},
        }

    return execute
