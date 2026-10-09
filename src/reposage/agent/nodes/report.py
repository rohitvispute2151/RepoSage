"""Report node synthesizing final verified answers, citations, and execution summaries."""

import json
from pathlib import Path
import time
from typing import Any
import uuid

from sqlalchemy import update

from reposage.agent.citations import Citation, verify_citation
from reposage.agent.nodes import AgentDependencies
from reposage.agent.state import AgentState
from reposage.config import settings
from reposage.db.models import Task
from reposage.llm.prompts import load_prompt
from reposage.llm.types import LLMRequest, Message


def report_node(deps: AgentDependencies):
    """Factory returning Report node execution function."""

    async def execute(state: AgentState) -> dict[str, Any]:
        task_id = state.get("task_id", "")
        deps.emit_event(task_id, "node_started", {"node": "report"})

        mode = state.get("mode", "qa")
        status_hint = state.get("status_hint")
        budget = state.get("budget", {})
        started_at = budget.get("started_at", time.time())
        elapsed_seconds = round(time.time() - started_at, 2)

        budget_report = {
            "steps": budget.get("steps", 0),
            "tokens": budget.get("tokens", 0),
            "usd": round(budget.get("usd", 0.0), 4),
            "seconds": elapsed_seconds,
            "limits": budget.get("limits", {}),
        }

        final_result: dict[str, Any] = {"budget_report": budget_report}
        outcome: str = "completed"
        terminal_status: str = "completed"

        # 1. Handle budget breaches, loops, or reproduction failures
        if status_hint:
            if "budget_exceeded" in status_hint:
                terminal_status = "budget_exceeded"
                outcome = "budget_exceeded"
                final_result["notes"] = [
                    f"Task halted early due to budget breach: {status_hint}"
                ]
            elif status_hint == "loop_detected":
                terminal_status = "completed"
                outcome = "loop_detected"
                final_result["notes"] = [
                    "Task halted due to repetitive tool call cycles."
                ]
            elif status_hint == "not_reproducible":
                terminal_status = "completed"
                outcome = "not_reproducible"
                final_result["notes"] = [
                    "Target test cases passed in baseline repository snapshot."
                ]

        # 2. QA Mode: Generate grounded answer and verify citations
        elif mode == "qa":
            try:
                prompt_text, phash = load_prompt("answer.v1.md")
            except Exception:
                prompt_text = "Answer the question using only the provided evidence."
                phash = "static_answer"

            evidence_items = state.get("evidence", [])
            evidence_formatted = "\n\n".join(
                f"[{idx+1}] File: {e['path']}:{e['start_line']}..{e['end_line']} ({e['symbol']}):\n{e['snippet']}"
                for idx, e in enumerate(evidence_items[:10])
            )
            question = state.get("request", {}).get("question", "")

            user_msg = (
                f"Question: {question}\n\n"
                f"Retrieved Evidence:\n{evidence_formatted}\n\n"
                f"Answer the question thoroughly and provide exact citations."
            )

            resp = await deps.llm.chat(
                LLMRequest(
                    model=settings.model_mid,
                    messages=[
                        Message(role="system", content=prompt_text),
                        Message(role="user", content=user_msg),
                    ],
                    max_tokens=1500,
                    temperature=0.0,
                    meta={
                        "task_id": task_id,
                        "node": "report",
                        "prompt_name": "answer.v1.md",
                        "prompt_hash": phash,
                    },
                )
            )

            answer_text = resp.text or "Unable to locate answer."
            citations_list: list[dict[str, Any]] = []

            # Parse citations from structured or semi-structured model output
            try:
                parsed_ans = json.loads(answer_text)
                answer_text = parsed_ans.get("answer", answer_text)
                raw_cites = parsed_ans.get("citations", [])
            except Exception:
                raw_cites = [
                    {
                        "path": e["path"],
                        "start_line": e["start_line"],
                        "end_line": e["end_line"],
                        "symbol": e["symbol"],
                    }
                    for e in evidence_items[:3]
                ]

            # Verify citations deterministically
            verified_cites: list[dict[str, Any]] = []
            for c_dict in raw_cites:
                try:
                    c_obj = Citation(**c_dict)
                    valid, reason = verify_citation(c_obj, deps.snapshot_root)
                    if valid:
                        verified_cites.append(c_obj.model_dump())
                    else:
                        final_result.setdefault("notes", []).append(
                            f"Filtered invalid citation {c_obj.path}:{c_obj.start_line}: {reason}"
                        )
                except Exception:
                    continue

            final_result["answer"] = answer_text
            final_result["citations"] = verified_cites
            outcome = "answered"

        # 3. Fix Mode: Assemble patch, test summary, and rationale
        elif mode == "fix":
            patch_data = state.get("patch") or {}
            final_sub = state.get("final") or {}
            verify_sub = state.get("verify_result") or {}

            outcome = final_sub.get("outcome", "unresolved")
            final_result["patch_diff"] = patch_data.get("diff")
            final_result["test_summary"] = verify_sub
            final_result["rationale"] = patch_data.get("rationale")
            final_result["applied"] = final_sub.get("applied", False)

        final_result["outcome"] = outcome

        # Persist final task outcome to database
        stmt = (
            update(Task)
            .where(Task.id == uuid.UUID(task_id))
            .values(
                status=terminal_status,
                outcome=outcome,
                result=final_result,
            )
        )
        await deps.db.execute(stmt)
        await deps.db.commit()

        deps.emit_event(
            task_id, "completed", {"status": terminal_status, "outcome": outcome}
        )

        return {"final": final_result}

    return execute
