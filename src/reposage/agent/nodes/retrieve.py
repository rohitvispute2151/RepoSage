"""Retrieve node executing hybrid retrieval and populating evidence anchors."""

from typing import Any
import uuid

from reposage.agent.nodes import AgentDependencies
from reposage.agent.state import AgentState, Evidence
from reposage.retrieval.service import retrieve


def retrieve_node(deps: AgentDependencies):
    """Factory returning Retrieve node execution function."""

    async def execute(state: AgentState) -> dict[str, Any]:
        task_id = state.get("task_id", "")
        deps.emit_event(task_id, "node_started", {"node": "retrieve"})

        # Assert budget limits
        breach = deps.budget.check(state)
        if breach:
            return {"status_hint": f"budget_exceeded:{breach}"}

        snapshot_id = uuid.UUID(state.get("snapshot_id", ""))
        mode = state.get("mode", "qa")
        req_data = state.get("request", {})

        # Formulate search query from question or bug description
        if mode == "qa":
            query = req_data.get("question", "")
        else:
            tests = " ".join(req_data.get("failing_tests", []))
            query = f"{req_data.get('description', '')} {tests}".strip()

        # Execute hybrid retrieval pipeline
        res = await retrieve(
            snapshot_id=snapshot_id,
            question=query,
            db=deps.db,
            llm=deps.llm,
            include_tests=(mode == "fix"),
        )

        # Convert top candidates to structured evidence items
        initial_evidence: list[Evidence] = [
            Evidence(
                path=c.path,
                start_line=c.start_line,
                end_line=c.end_line,
                symbol=c.qualname,
                snippet=c.content[:800],
                source="retrieval",
            )
            for c in res.candidates
        ]

        retrieval_meta = {
            "query": query,
            "candidate_ids": [str(c.id) for c in res.candidates],
            "pre_rerank_ids": [str(cid) for cid in res.pre_rerank_ids],
            "timings": res.stage_timings,
        }

        updated_budget = deps.budget.snapshot(state, "retrieve")
        deps.emit_event(task_id, "node_finished", {"node": "retrieve"})

        return {
            "retrieval": retrieval_meta,
            "evidence": initial_evidence,
            "budget": updated_budget,
        }

    return execute
