"""Unit tests for resource budgets and loop detection."""

from reposage.agent.budget import BudgetManager
from reposage.agent.loops import LoopDetector


def test_budget_step_breach():
    """Verify that exceeding step limit returns step breach."""
    bm = BudgetManager()
    state = {
        "budget": {
            "steps": 31,
            "tokens": 100,
            "usd": 0.05,
            "started_at": 100.0,
            "limits": {"max_steps": 30, "max_tokens": 1000, "max_usd": 1.0, "max_seconds": 60},
        }
    }
    breach = bm.check(state)
    assert breach == "steps"


def test_loop_detection_frequency():
    """Verify that repeated tool invocations trigger loop detection."""
    ld = LoopDetector(threshold=3)
    freq_map = {"tool_a_hash": 4}
    assert ld.detect_loop([], freq_map) is True


def test_loop_detection_oscillation():
    """Verify that oscillating call sequences (A-B-A-B-A-B) trigger loop detection."""
    ld = LoopDetector(threshold=3)
    oscillating_sequence = ["A", "B", "A", "B", "A", "B"]
    freq_map = {"A": 3, "B": 3}
    assert ld.detect_loop(oscillating_sequence, freq_map) is True
