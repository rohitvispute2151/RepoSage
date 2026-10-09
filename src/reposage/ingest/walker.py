"""Repository filesystem traversal and file policy filtering.

Discovers source and configuration files while strictly ignoring dependencies,
binary assets, secret credentials, and oversized blobs.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Generator

# Directories excluded from walking
IGNORED_DIRS: set[str] = {
    ".git",
    "venv",
    ".venv",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
}

# Patterns indicating credentials or secrets
SECRET_FILE_PATTERNS: tuple[str, ...] = (
    ".env",
    ".pem",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "secret_key",
)

# Maximum allowed file size for indexing (500 KB)
MAX_FILE_SIZE_BYTES: int = 500 * 1024


@dataclass
class DiscoveredFile:
    """Metadata for a validated repository file."""

    relative_path: str
    absolute_path: Path
    is_test: bool
    sha256: str
    line_count: int
    content: str


def is_test_file(rel_path: str) -> bool:
    """Determine whether relative path represents a test or test configuration file."""
    parts = Path(rel_path).parts
    filename = Path(rel_path).name.lower()

    if "tests" in parts or "test" in parts:
        return True
    if filename.startswith("test_") or filename.endswith("_test.py"):
        return True
    if filename in {"conftest.py", "tox.ini"}:
        return True
    return False


def is_forbidden_file(path: Path) -> bool:
    """Check whether a file matches known secret or sensitive filename patterns."""
    name = path.name.lower()
    for pattern in SECRET_FILE_PATTERNS:
        if pattern in name:
            return True
    return False


def walk_repo(repo_dir: Path) -> Generator[DiscoveredFile, None, None]:
    """Walk repo directory and yield discovered source and documentation files."""
    repo_dir = repo_dir.resolve()

    for path in repo_dir.rglob("*"):
        if not path.is_file():
            continue

        # Check for ignored directories in path hierarchy
        rel = path.relative_to(repo_dir)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue

        # Skip forbidden / secret files
        if is_forbidden_file(path):
            continue

        # Skip files exceeding size cap or minified files
        if path.stat().st_size > MAX_FILE_SIZE_BYTES or ".min." in path.name:
            continue

        # Only index Python files and key repository configuration / documentation files
        is_py = path.suffix == ".py"
        is_doc_or_config = path.name.lower() in {
            "readme.md",
            "readme",
            "pyproject.toml",
            "setup.cfg",
            "setup.py",
        }

        if not (is_py or is_doc_or_config):
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel_str = str(rel)
        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        lines = content.splitlines()

        yield DiscoveredFile(
            relative_path=rel_str,
            absolute_path=path,
            is_test=is_test_file(rel_str),
            sha256=file_hash,
            line_count=len(lines),
            content=content,
        )
