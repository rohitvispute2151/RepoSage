"""Evaluation metrics computation for retrieval, fix, trajectory, and consistency.

Includes unbiased pass@k estimators, MRR, Recall@k, and trajectory waste analytics.
"""

from collections import Counter
import math
from typing import Any, Sequence


def recall_at_k(ranked_ids: Sequence[str], gold_ids: Sequence[str], k: int) -> float:
    """Calculate Recall@k: 1.0 if any gold entity appears in top k ranks, else 0.0."""
    if not gold_ids or not ranked_ids:
        return 0.0
    top_k = set(ranked_ids[:k])
    return 1.0 if any(g in top_k for g in gold_ids) else 0.0


def reciprocal_rank(ranked_ids: Sequence[str], gold_ids: Sequence[str]) -> float:
    """Compute Reciprocal Rank: reciprocal of first gold hit rank (1.0 / rank)."""
    gold_set = set(gold_ids)
    for rank, rid in enumerate(ranked_ids, start=1):
        if rid in gold_set:
            return 1.0 / rank
    return 0.0


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased pass@k estimator from n evaluations with c successes."""
    if n - c < k:
        return 1.0
    return 1.0 - math.prod((n - c - i) / (n - i) for i in range(k))


def outcome_consistency(outcomes: list[str]) -> float:
    """Compute modal agreement proportion across repeated runs."""
    if not outcomes:
        return 0.0
    most_common_count = Counter(outcomes).most_common(1)[0][1]
    return most_common_count / float(len(outcomes))


def compute_trajectory_metrics(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate call volume, exact duplicate repetition waste, and denial rates."""
    total_calls = len(tool_calls)
    if total_calls == 0:
        return {"total_calls": 0, "wasted_calls": 0, "denied_calls": 0}

    unique_calls = {
        f"{c.get('tool')}:{c.get('args_hash') or c.get('args')}" for c in tool_calls
    }
    wasted = total_calls - len(unique_calls)
    denied = sum(1 for c in tool_calls if c.get("status") == "denied")

    return {
        "total_calls": total_calls,
        "wasted_calls": wasted,
        "denied_calls": denied,
    }
