"""LLM-as-a-judge for QA correctness grading against ground-truth rubrics."""

import json
from typing import Any

from pydantic import BaseModel

from reposage.config import settings
from reposage.llm.client import ResilientLLM
from reposage.llm.prompts import load_prompt
from reposage.llm.types import LLMRequest, Message


class JudgeResult(BaseModel):
    """Grading evaluation output."""

    correct: bool
    reason: str
    cites_gold: bool


async def judge_qa_answer(
    llm: ResilientLLM,
    question: str,
    answer: str,
    citations: list[dict[str, Any]],
    gold: dict[str, Any],
    rubric: str = "Answer must accurately reference the implementation file and symbol.",
) -> JudgeResult:
    """Evaluate candidate QA response against reference ground truth."""
    try:
        prompt_text, phash = load_prompt("judge_qa.v1.md")
    except Exception:
        prompt_text = "Grade the QA answer against reference gold and rubric."
        phash = "static_judge"

    input_payload = {
        "question": question,
        "answer": answer,
        "citations": citations,
        "gold": gold,
        "rubric": rubric,
    }

    resp = await llm.chat(
        LLMRequest(
            model=settings.model_mid,
            messages=[
                Message(role="system", content=prompt_text),
                Message(role="user", content=json.dumps(input_payload, indent=2)),
            ],
            response_schema=JudgeResult.model_json_schema(),
            max_tokens=600,
            temperature=0.0,
            meta={"node": "judge", "prompt_name": "judge_qa.v1.md", "prompt_hash": phash},
        )
    )

    if resp.text:
        try:
            return JudgeResult.model_validate(json.loads(resp.text))
        except Exception:
            pass

    # Deterministic fallback check: does citation path intersect gold file
    gold_file = gold.get("bug_file") or gold.get("path")
    cites_gold = any(c.get("path") == gold_file for c in citations) if gold_file else False
    return JudgeResult(
        correct=cites_gold,
        reason="Deterministic fallback match against gold location",
        cites_gold=cites_gold,
    )
