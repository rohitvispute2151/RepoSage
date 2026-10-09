"""Citation verification ensuring claims anchor to verifiable code locations.

Validates that cited files exist, line numbers are valid, and cited symbols
actually occur within the specified line range.
"""

from pathlib import Path

from pydantic import BaseModel


class Citation(BaseModel):
    """Citation pointer referencing code line span."""

    path: str
    start_line: int
    end_line: int
    symbol: str


def verify_citation(citation: Citation, snapshot_root: Path) -> tuple[bool, str]:
    """Verify that cited file exists and referenced symbol appears in line range."""
    target_file = snapshot_root / citation.path
    if not target_file.is_file():
        return False, "file_missing"

    try:
        lines = target_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as read_err:
        return False, f"file_read_error: {read_err}"

    total_lines = len(lines)
    if not (1 <= citation.start_line <= citation.end_line <= total_lines):
        return False, f"range_invalid (lines 1..{total_lines}, cited {citation.start_line}..{citation.end_line})"

    snippet = "\n".join(lines[citation.start_line - 1 : citation.end_line])
    symbol_basename = citation.symbol.split(".")[-1]

    # Verify symbol name presence inside the cited line block
    if symbol_basename not in snippet:
        return False, f"symbol_not_in_range ('{symbol_basename}' not in lines {citation.start_line}..{citation.end_line})"

    return True, "ok"
