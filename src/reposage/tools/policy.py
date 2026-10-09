"""Policy engine and security guardrail chokepoint for tool invocations.

Enforces per-node tool allowlists, path canonicalization, symlink containment,
argument schema validation, and test selector sanitization.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Optional

from jsonschema import ValidationError, validate

from reposage.config import settings
from reposage.ingest.walker import is_forbidden_file
from reposage.observability.metrics import policy_denials_total
from reposage.tools.schemas import TOOL_SCHEMAS, ToolResult

# Permitted tools per LangGraph state node
NODE_ALLOWLIST: dict[str, set[str]] = {
    "explore": {"search_code", "read_file", "grep", "list_symbols", "run_tests"},
    "patch": {"search_code", "read_file", "grep", "list_symbols"},
    "verify": {"run_tests"},
}

# Pytest node identifier pattern: path/to/file.py::Class::test_func
SELECTOR_PATTERN = re.compile(r"^[\w./-]+\.py(::[\w\[\]\-.,]+)*$")


class PolicyDeniedError(Exception):
    """Raised when an operation violates security or safety guardrails."""

    def __init__(self, reason: str, details: Any = None):
        super().__init__(f"Policy denied: {reason}")
        self.reason = reason
        self.details = details


@dataclass
class PolicyDecision:
    """Outcome of a policy evaluation."""

    allowed: bool
    reason: Optional[str] = None
    details: Any = None


class PolicyEngine:
    """Evaluates security rules before granting tool execution permissions."""

    def __init__(self, snapshot_root: Path):
        self.snapshot_root = snapshot_root.resolve()

    def resolve_safe(self, rel_path: str) -> Path:
        """Resolve a relative path, verifying containment inside repo snapshot root."""
        # Clean relative path
        cleaned = rel_path.strip().lstrip("/")
        resolved = (self.snapshot_root / cleaned).resolve()

        # Strict containment check preventing traversal escapes (e.g. ../../)
        try:
            resolved.relative_to(self.snapshot_root)
        except ValueError:
            raise PolicyDeniedError("path_escape", f"Path escapes repository boundary: {rel_path}")

        # Check for forbidden files and secret keys
        if is_forbidden_file(resolved):
            raise PolicyDeniedError("forbidden_path", f"Access to secret/restricted path denied: {rel_path}")

        return resolved

    def is_valid_selector(self, selector: str) -> bool:
        """Validate that a test selector is a valid pytest node ID and not command flags."""
        if selector.startswith("-") or " " in selector or ";" in selector:
            return False
        return bool(SELECTOR_PATTERN.match(selector))

    def check(self, node: str, tool: str, args: dict[str, Any]) -> PolicyDecision:
        """Verify whether tool invocation is permissible within current graph node."""
        # 1. Node allowlist check
        allowed_tools = NODE_ALLOWLIST.get(node, set())
        if tool not in allowed_tools:
            policy_denials_total.labels(reason="tool_not_allowed_in_node").inc()
            return PolicyDecision(allowed=False, reason="tool_not_allowed_in_node")

        # 2. JSON schema parameter validation
        schema = TOOL_SCHEMAS.get(tool)
        if schema:
            try:
                validate(instance=args, schema=schema["input_schema"])
            except ValidationError as val_err:
                policy_denials_total.labels(reason="schema_invalid").inc()
                return PolicyDecision(allowed=False, reason="schema_invalid", details=str(val_err))

        # 3. Path safety check
        if "path" in args:
            try:
                self.resolve_safe(args["path"])
            except PolicyDeniedError as pd_err:
                policy_denials_total.labels(reason=pd_err.reason).inc()
                return PolicyDecision(allowed=False, reason=pd_err.reason, details=pd_err.details)

        # 4. Tool-specific domain policy validation
        if tool == "read_file":
            start_l = args.get("start_line", 1)
            end_l = args.get("end_line", 1)
            if end_l < start_l:
                policy_denials_total.labels(reason="bad_range").inc()
                return PolicyDecision(allowed=False, reason="bad_range")
            if (end_l - start_l + 1) > settings.read_file_max_lines:
                policy_denials_total.labels(reason="range_too_large").inc()
                return PolicyDecision(allowed=False, reason="range_too_large")

        elif tool == "run_tests":
            selectors = args.get("selectors", [])
            for s in selectors:
                if not self.is_valid_selector(s):
                    policy_denials_total.labels(reason="bad_selector").inc()
                    return PolicyDecision(allowed=False, reason="bad_selector", details=s)

        return PolicyDecision(allowed=True)


def compute_idempotency_key(task_id: str, step_id: int, tool: str, args: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 idempotency key for a tool execution."""
    canonical_args = json.dumps(args, sort_keys=True)
    raw = f"{task_id}|{step_id}|{tool}|{canonical_args}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def render_tool_result_envelope(result: ToolResult) -> str:
    """Format tool output for inclusion in LLM assistant context."""
    status_str = "true" if result.ok else "false"
    trunc_str = "true" if result.truncated else "false"

    if result.ok:
        content_str = (
            json.dumps(result.data, indent=2)
            if isinstance(result.data, (dict, list))
            else str(result.data or "")
        )
    else:
        content_str = f"ERROR [{result.error_kind or 'error'}]: {result.error}"

    return (
        f'<tool_result tool="{result.tool}" ok="{status_str}" truncated="{trunc_str}">\n'
        f"{content_str}\n"
        f"</tool_result>"
    )
