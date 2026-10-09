"""Secret scanning and redaction utility for RepoSage.

Prevents credentials, API keys, private keys, and high-entropy tokens from leaking
into LLM prompts, tool outputs, event streams, or traces.
"""

import math
import re
from typing import Any

# Standard pattern matches for common token formats and headers
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL)),
    ("aws_key", re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}")),
    ("generic_api_key", re.compile(r"""(?i)(?:api[_-]?key|secret|token|password|auth)[\s:=]+['"]?([a-zA-Z0-9_\-\.]{16,})['"]?""")),
    ("bearer_token", re.compile(r"""(?i)bearer\s+([a-zA-Z0-9_\-\.]{20,})""")),
    ("github_token", re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}")),
]


def shannon_entropy(data: str) -> float:
    """Calculate the Shannon entropy of a string."""
    if not data:
        return 0.0
    entropy = 0.0
    for x in set(data):
        p_x = float(data.count(x)) / len(data)
        entropy += -p_x * math.log2(p_x)
    return entropy


def redact_secrets(text: str) -> str:
    """Replace discovered secrets and high-entropy tokens with redaction tags."""
    if not text:
        return ""

    sanitized = text
    # 1. Regex pattern matching
    for name, pattern in _PATTERNS:
        sanitized = pattern.sub(f"[REDACTED:{name}]", sanitized)

    # 2. High-entropy candidate check for long single tokens (> 32 alphanumeric chars)
    words = re.findall(r"\b[A-Za-z0-9_-]{32,}\b", sanitized)
    for word in words:
        if "[REDACTED:" in word:
            continue
        if shannon_entropy(word) > 4.5:
            sanitized = sanitized.replace(word, "[REDACTED:high_entropy_secret]")

    return sanitized


def sanitize_payload(payload: Any) -> Any:
    """Recursively redact secrets in dicts, lists, and strings."""
    if isinstance(payload, str):
        return redact_secrets(payload)
    elif isinstance(payload, dict):
        return {k: sanitize_payload(v) for k, v in payload.items()}
    elif isinstance(payload, list):
        return [sanitize_payload(v) for v in payload]
    return payload
