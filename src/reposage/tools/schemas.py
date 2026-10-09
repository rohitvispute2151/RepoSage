"""JSON schema declarations for Model Context Protocol (MCP) repository tools.

Provides strict parameter schemas and constraints for tools visible to the agent.
"""

from typing import Any, Literal
from pydantic import BaseModel

SEARCH_CODE_SCHEMA: dict[str, Any] = {
    "name": "search_code",
    "description": "Hybrid search over the repository snapshot. Returns symbol names, file paths, and line spans.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "maxLength": 300, "description": "Search query or symbol name"},
            "path_prefix": {"type": "string", "maxLength": 200, "description": "Optional directory filter"},
            "include_tests": {"type": "boolean", "default": False, "description": "Include test code in results"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

READ_FILE_SCHEMA: dict[str, Any] = {
    "name": "read_file",
    "description": "Read a bounded line range from a repository file.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "maxLength": 300, "description": "Repository-relative file path"},
            "start_line": {"type": "integer", "minimum": 1, "description": "1-based starting line number"},
            "end_line": {"type": "integer", "minimum": 1, "description": "1-based inclusive ending line number"},
        },
        "required": ["path", "start_line", "end_line"],
        "additionalProperties": False,
    },
}

GREP_SCHEMA: dict[str, Any] = {
    "name": "grep",
    "description": "Search file contents by regex or exact literal match.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "maxLength": 200, "description": "Regex or string pattern"},
            "path_prefix": {"type": "string", "maxLength": 200, "description": "Optional subdirectory prefix"},
            "regex": {"type": "boolean", "default": False, "description": "Treat pattern as regex"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
        },
        "required": ["pattern"],
        "additionalProperties": False,
    },
}

LIST_SYMBOLS_SCHEMA: dict[str, Any] = {
    "name": "list_symbols",
    "description": "Extract top-level and class-level symbols defined in a file.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "maxLength": 300, "description": "Repository-relative file path"},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}

RUN_TESTS_SCHEMA: dict[str, Any] = {
    "name": "run_tests",
    "description": "Execute selected pytest node IDs inside an isolated container sandbox.",
    "input_schema": {
        "type": "object",
        "properties": {
            "selectors": {
                "type": "array",
                "items": {"type": "string", "maxLength": 300},
                "minItems": 1,
                "maxItems": 20,
                "description": "List of pytest test node IDs (e.g. tests/test_http.py::test_retry)",
            },
            "use_candidate_patch": {
                "type": "boolean",
                "default": False,
                "description": "Apply current candidate patch overlay before running tests",
            },
        },
        "required": ["selectors"],
        "additionalProperties": False,
    },
}

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "search_code": SEARCH_CODE_SCHEMA,
    "read_file": READ_FILE_SCHEMA,
    "grep": GREP_SCHEMA,
    "list_symbols": LIST_SYMBOLS_SCHEMA,
    "run_tests": RUN_TESTS_SCHEMA,
}


class ToolResult(BaseModel):
    """Normalized response envelope returned by all tool dispatches."""

    ok: bool
    tool: str
    data: Any | None = None
    truncated: bool = False
    error: str | None = None
    error_kind: Literal["policy", "validation", "timeout", "internal"] | None = None
