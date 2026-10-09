"""Loop detection logic identifying repetitive or oscillating tool invocations.

Computes call argument fingerprints and flags pathological exploration loops.
"""

import hashlib
import json
from typing import Any

from reposage.observability.metrics import loop_detections_total


def compute_call_fingerprint(tool: str, args: dict[str, Any]) -> str:
    """Compute normalized SHA-256 hash of a tool call and its arguments."""
    norm_args = json.dumps(args, sort_keys=True)
    return hashlib.sha256(f"{tool}:{norm_args}".encode("utf-8")).hexdigest()[:16]


class LoopDetector:
    """Tracks tool invocation sequence history to detect cycles."""

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def detect_loop(
        self,
        recent_fingerprints: list[str],
        frequency_map: dict[str, int],
    ) -> bool:
        """Check whether current call frequency or historical alternation indicates a loop."""
        # 1. Exact repetition threshold check
        for count in frequency_map.values():
            if count > self.threshold:
                loop_detections_total.inc()
                return True

        # 2. Oscillating pattern check (e.g. A -> B -> A -> B -> A -> B in last 6 calls)
        if len(recent_fingerprints) >= 6:
            tail = recent_fingerprints[-6:]
            if tail[0] == tail[2] == tail[4] and tail[1] == tail[3] == tail[5]:
                loop_detections_total.inc()
                return True

        return False
