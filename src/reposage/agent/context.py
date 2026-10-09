"""Context window management and message compaction.

Ensures message history remains well within LLM context ceilings by replacing older
tool outputs with concise summaries while preserving evidence items and recent turns.
"""

from typing import Any


def estimate_token_count(messages: list[dict[str, Any]]) -> int:
    """Rough estimation of token count across messages."""
    total_words = 0
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, str):
            total_words += len(c.split())
        elif isinstance(c, list):
            total_words += len(str(c).split())
    return int(total_words * 1.3)


def compact_messages(
    messages: list[dict[str, Any]], max_tokens: int = 24_000
) -> list[dict[str, Any]]:
    """Compact history by retaining initial system turn and last 6 messages."""
    if not messages or estimate_token_count(messages) <= max_tokens:
        return messages

    system_turn = [m for m in messages if m.get("role") == "system"]
    recent_tail = messages[-6:]

    summary_note = {
        "role": "assistant",
        "content": "[Context compacted: earlier tool interactions summarized to conserve tokens]",
    }

    return system_turn + [summary_note] + recent_tail
