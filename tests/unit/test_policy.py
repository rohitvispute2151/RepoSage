"""Unit tests for tool policy engine and path containment validation."""

from pathlib import Path
import pytest

from reposage.tools.policy import PolicyEngine, PolicyDeniedError


def test_path_traversal_prevention(temp_repo: Path):
    """Verify that path traversal attempts raise PolicyDeniedError."""
    policy = PolicyEngine(temp_repo)

    with pytest.raises(PolicyDeniedError) as exc_info:
        policy.resolve_safe("../../etc/passwd")
    assert "path_escape" in str(exc_info.value)


def test_forbidden_file_rejection(temp_repo: Path):
    """Verify that sensitive secret files (.env, credentials) are denied."""
    (temp_repo / ".env").write_text("SECRET=123", encoding="utf-8")
    policy = PolicyEngine(temp_repo)

    with pytest.raises(PolicyDeniedError) as exc_info:
        policy.resolve_safe(".env")
    assert "forbidden_path" in str(exc_info.value)


def test_valid_selector():
    """Verify pytest node id validation rejects bash command injections."""
    policy = PolicyEngine(Path("/tmp"))

    assert policy.is_valid_selector("tests/test_x.py::test_func") is True
    assert policy.is_valid_selector("tests/test_x.py::TestClass::test_method") is True
    assert policy.is_valid_selector("-k test_func") is False  # Flags rejected
    assert policy.is_valid_selector("test_x.py; rm -rf /") is False  # Command chaining rejected
