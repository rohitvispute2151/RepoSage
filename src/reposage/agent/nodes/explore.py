"""Explore node driving multi-turn codebase inspection tool loops."""

from typing import Any
import uuid

from reposage.agent.context import compact_messages
from reposage.agent.loops import LoopDetector, compute_call_fingerprint
from reposage.agent.nodes import AgentDependencies
from reposage.agent.state import AgentState, Evidence
from reposage.config import settings
from reposage.llm.prompts import load_prompt
from reposage.llm.types import LLMRequest, Message, ToolSpec
from reposage.tools.impl import dispatch_tool
from reposage.tools.policy import render_tool_result_envelope
from reposage.tools.schemas import TOOL_SCHEMAS

MODEL_VISIBLE_TOOLS: list[ToolSpec] = [
    ToolSpec(name=k, description=v["description"], json_schema=v["input_schema"])
    for k, v in TOOL_SCHEMAS.items()
    if k != "apply_patch"  # apply_patch is never exposed to the model
]


def explore_node(deps: AgentDependencies):
    """Factory returning Explore node multi-turn tool execution loop."""

    async def execute(state: AgentState) -> dict[str, Any]:
        task_id = state.get("task_id", "")
        deps.emit_event(task_id, "node_started", {"node": "explore"})

        # Budget assertion
        breach = deps.budget.check(state)
        if breach:
            return {"status_hint": f"budget_exceeded:{breach}"}

        # Build prompt and messages
        try:
            prompt_text, phash = load_prompt("explore.v1.md")
        except Exception:
            prompt_text = "Investigate the codebase using tools to gather evidence."
            phash = "static_explore"

        existing_messages = state.get("messages", [])
        initial_turns: list[dict[str, Any]] = []
        if not existing_messages:
            # Construct initial context turn
            evidence_summary = "\n".join(
                f"- {e['path']}:{e['start_line']}..{e['end_line']} ({e['symbol']})"
                for e in state.get("evidence", [])[:6]
            )
            req_info = str(state.get("request", {}))
            initial_user_turn = (
                f"Task request: {req_info}\n"
                f"Current Evidence Anchors:\n{evidence_summary}\n"
                f"Plan: {state.get('plan', {})}\n"
                f"Investigate any gaps or confirm implementation details."
            )
            initial_turns = [
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": initial_user_turn},
            ]
            chat_messages = [
                Message(role="system", content=prompt_text),
                Message(role="user", content=initial_user_turn),
            ]
        else:
            chat_messages = [
                Message(
                    role=m.get("role", "user"),
                    content=m.get("content", ""),
                    name=m.get("name"),
                    tool_call_id=m.get("tool_call_id"),
                    tool_calls=m.get("tool_calls"),
                )
                for m in existing_messages
            ]

        # Call mid-tier model for tool selection
        resp = await deps.llm.chat(
            LLMRequest(
                model=settings.model_mid,
                messages=chat_messages,
                tools=MODEL_VISIBLE_TOOLS,
                max_tokens=1500,
                temperature=0.0,
                meta={
                    "task_id": task_id,
                    "node": "explore",
                    "prompt_name": "explore.v1.md",
                    "prompt_hash": phash,
                },
            )
        )

        # 1. Model returned no tools -> exploration is complete
        if not resp.tool_calls:
            current_plan = dict(state.get("plan", {}))
            current_plan["explore_done"] = True
            assistant_turn = {"role": "assistant", "content": resp.text or "DONE"}
            return {
                "plan": current_plan,
                "messages": compact_messages(
                    state.get("messages", []) + initial_turns + [assistant_turn]
                ),
            }

        # 2. Process tool calls
        new_evidence: list[Evidence] = []
        new_tool_turns: list[dict[str, Any]] = []
        fingerprints = dict(state.get("loop_fingerprints", {}))
        loop_detector = LoopDetector(threshold=settings.loop_repeat_threshold)

        assistant_turn = {
            "role": "assistant",
            "content": resp.text or "",
            "tool_calls": resp.tool_calls,
        }
        new_tool_turns.append(assistant_turn)

        for step_idx, call in enumerate(resp.tool_calls[:4]):
            tool_name = call.get("name", "")
            tool_args = call.get("args", {})

            # Fingerprint check
            fp = compute_call_fingerprint(tool_name, tool_args)
            fingerprints[fp] = fingerprints.get(fp, 0) + 1

            if loop_detector.detect_loop([fp], fingerprints):
                return {
                    "status_hint": "loop_detected",
                    "loop_fingerprints": fingerprints,
                }

            # Dispatch tool
            result = await dispatch_tool(
                node="explore",
                tool=tool_name,
                args=tool_args,
                task_id=task_id,
                step_id=state.get("budget", {}).get("steps", 0) + step_idx,
                snapshot_root=deps.snapshot_root,
                snapshot_id=uuid.UUID(state.get("snapshot_id", "")),
                db=deps.db,
                llm=deps.llm,
                sandbox_client=deps.sandbox_client,
            )

            # Record rendered tool result envelope
            envelope_str = render_tool_result_envelope(result)
            tool_msg = {
                "role": "tool",
                "tool_call_id": call.get("id", f"call_{step_idx}"),
                "name": tool_name,
                "content": envelope_str,
            }
            new_tool_turns.append(tool_msg)

            # Extract new evidence if read_file succeeded
            if tool_name == "read_file" and result.ok and isinstance(result.data, dict):
                new_evidence.append(
                    Evidence(
                        path=result.data.get("path", tool_args.get("path", "")),
                        start_line=result.data.get("start_line", 1),
                        end_line=result.data.get("end_line", 1),
                        symbol=Path(tool_args.get("path", "")).stem,
                        snippet=result.data.get("content", "")[:600],
                        source="read_file",
                    )
                )

            # Intra-node budget check
            mid_breach = deps.budget.check_midnode(state)
            if mid_breach:
                return {
                    "status_hint": f"budget_exceeded:{mid_breach}",
                    "evidence": new_evidence,
                }

        updated_budget = deps.budget.snapshot(state, "explore")
        deps.emit_event(task_id, "node_finished", {"node": "explore"})

        all_messages = state.get("messages", []) + initial_turns + new_tool_turns
        return {
            "evidence": new_evidence,
            "messages": compact_messages(all_messages),
            "loop_fingerprints": fingerprints,
            "budget": updated_budget,
        }

    return execute
