"""Evaluation runner executing benchmark suites and persisting metrics."""

import asyncio
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reposage.db.models import EvalCase, EvalResult, EvalRun, EvalSuite, utc_now
from reposage.evals.metrics import recall_at_k, reciprocal_rank
from reposage.llm.client import ResilientLLM
from reposage.llm.prompts import compute_config_fingerprint
from reposage.retrieval.service import retrieve


async def run_retrieval_eval_case(
    case: EvalCase,
    db: AsyncSession,
    llm: ResilientLLM,
) -> dict[str, Any]:
    """Execute a single retrieval evaluation case and compute Recall and MRR."""
    question = case.input.get("question", "")
    gold_symbols = case.ground_truth.get("gold_symbols", [])

    res = await retrieve(
        snapshot_id=case.snapshot_id,
        question=question,
        db=db,
        llm=llm,
    )

    ranked_symbols = [c.qualname for c in res.candidates]
    r_at_1 = recall_at_k(ranked_symbols, gold_symbols, 1)
    r_at_5 = recall_at_k(ranked_symbols, gold_symbols, 5)
    mrr = reciprocal_rank(ranked_symbols, gold_symbols)

    return {
        "recall_at_1": r_at_1,
        "recall_at_5": r_at_5,
        "mrr": mrr,
        "top_symbols": ranked_symbols[:5],
    }


async def run_suite(
    suite_name: str,
    suite_version: str,
    db: AsyncSession,
    llm: ResilientLLM,
    label: str | None = None,
    concurrency: int = 3,
) -> uuid.UUID:
    """Run an entire evaluation suite and persist aggregate run results."""
    # 1. Fetch suite
    stmt = select(EvalSuite).where(
        EvalSuite.name == suite_name,
        EvalSuite.version == suite_version,
    )
    suite = await db.scalar(stmt)
    if not suite:
        raise ValueError(f"Suite {suite_name} (v{suite_version}) not found")

    # 2. Create EvalRun record
    run_id = uuid.uuid4()
    eval_run = EvalRun(
        id=run_id,
        suite_id=suite.id,
        config_fingerprint=compute_config_fingerprint(),
        label=label,
    )
    db.add(eval_run)
    await db.commit()

    # 3. Fetch cases
    cases_stmt = select(EvalCase).where(EvalCase.suite_id == suite.id)
    cases = (await db.execute(cases_stmt)).scalars().all()

    semaphore = asyncio.Semaphore(concurrency)

    async def _eval_one(c: EvalCase):
        async with semaphore:
            metrics = await run_retrieval_eval_case(c, db, llm)
            result_row = EvalResult(
                run_id=run_id,
                case_id=c.id,
                repeat_idx=0,
                metrics=metrics,
            )
            db.add(result_row)

    await asyncio.gather(*[_eval_one(case) for case in cases])

    eval_run.finished_at = utc_now()
    await db.commit()
    return run_id
