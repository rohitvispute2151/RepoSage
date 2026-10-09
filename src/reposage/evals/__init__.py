"""Evaluation harness, bug injector, metric suite, and CLI runner."""

from reposage.evals.bug_injector import InjectedBug, inject_bug
from reposage.evals.cli import cli_app
from reposage.evals.judge import JudgeResult, judge_qa_answer
from reposage.evals.metrics import (
    compute_trajectory_metrics,
    outcome_consistency,
    pass_at_k,
    recall_at_k,
    reciprocal_rank,
)
from reposage.evals.runner import run_retrieval_eval_case, run_suite

__all__ = [
    "InjectedBug",
    "inject_bug",
    "recall_at_k",
    "reciprocal_rank",
    "pass_at_k",
    "outcome_consistency",
    "compute_trajectory_metrics",
    "JudgeResult",
    "judge_qa_answer",
    "run_retrieval_eval_case",
    "run_suite",
    "cli_app",
]
