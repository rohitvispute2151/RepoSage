"""Unit tests for citation verification against real file contents."""

from pathlib import Path
from reposage.agent.citations import Citation, verify_citation


def test_valid_citation(temp_repo: Path):
    """Verify that accurate file line ranges and symbol names pass citation verification."""
    cite = Citation(
        path="src/http.py",
        start_line=3,
        end_line=11,
        symbol="http.Client",
    )
    valid, reason = verify_citation(cite, temp_repo)
    assert valid is True
    assert reason == "ok"


def test_invalid_symbol_citation(temp_repo: Path):
    """Verify that citing a non-existent symbol in a valid line range fails."""
    cite = Citation(
        path="src/http.py",
        start_line=3,
        end_line=11,
        symbol="http.NonExistentClass",
    )
    valid, reason = verify_citation(cite, temp_repo)
    assert valid is False
    assert "symbol_not_in_range" in reason


def test_missing_file_citation(temp_repo: Path):
    """Verify that referencing a non-existent file fails verification."""
    cite = Citation(
        path="src/missing.py",
        start_line=1,
        end_line=10,
        symbol="missing",
    )
    valid, reason = verify_citation(cite, temp_repo)
    assert valid is False
    assert reason == "file_missing"
