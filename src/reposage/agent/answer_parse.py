"""Tolerant parsing of the answer model's JSON output.

Models routinely wrap JSON in a ```json fence or add a sentence around it. Treating that as "not JSON" stored the raw
fenced text as the user-visible answer, so extract the object first and only fall back when none can be decoded.
"""

import json
import re
from typing import Any, Optional

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def parse_answer_payload(text: str) -> Optional[dict[str, Any]]:
    """Return the first JSON object found in `text`, or None."""
    candidates = [text.strip(), *[m.strip() for m in _FENCE.findall(text)]]
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            return obj
    return None
