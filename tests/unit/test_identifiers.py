"""Unit tests for identifier token expansion for code search."""

from reposage.ingest.identifiers import expand_identifiers


def test_expand_snake_and_camel_case():
    """Verify that identifiers are expanded to separate lowercased tokens."""
    text = "parse_retry_header and RetryPolicyHandler"
    expanded = expand_identifiers(text)

    assert "parse retry header" in expanded
    assert "retry policy handler" in expanded


def test_empty_text():
    """Verify expansion handles empty or non-identifier text safely."""
    assert expand_identifiers("") == ""
    assert expand_identifiers("---") == "---"
