"""Unit tests for evaluation metrics: Recall, MRR, pass@k, and trajectory waste."""

from reposage.evals.metrics import (
    compute_trajectory_metrics,
    outcome_consistency,
    pass_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_recall_and_mrr():
    """Verify Recall@k and Reciprocal Rank calculation."""
    ranked = ["pkg.mod.foo", "pkg.mod.bar", "pkg.mod.target"]
    gold = ["pkg.mod.target"]

    assert recall_at_k(ranked, gold, 1) == 0.0
    assert recall_at_k(ranked, gold, 3) == 1.0
    assert reciprocal_rank(ranked, gold) == pytest.approx(1.0 / 3.0)


def test_pass_at_k():
    """Verify pass@k calculations for perfect and partial success rates."""
    assert pass_at_k(n=5, c=5, k=1) == 1.0
    assert pass_at_k(n=5, c=0, k=1) == 0.0
    assert 0.0 < pass_at_k(n=5, c=2, k=1) < 1.0


def test_trajectory_metrics():
    """Verify wasted and unique tool call metrics."""
    tool_calls = [
        {"tool": "read_file", "args_hash": "h1"},
        {"tool": "read_file", "args_hash": "h1"},  # duplicate
        {"tool": "grep", "args_hash": "h2"},
    ]
    metrics = compute_trajectory_metrics(tool_calls)
    assert metrics["total_calls"] == 3
    assert metrics["wasted_calls"] == 1


import pytest
