"""Versioned prompt loader and SHA-256 fingerprinting.

Guarantees reproducibility by tracking prompt file hashes across tasks and runs.
"""

import hashlib
from pathlib import Path
from typing import Any

from reposage.config import settings


def load_prompt(name: str) -> tuple[str, str]:
    """Read prompt markdown file and return its content and 12-char SHA-256 hash."""
    prompt_file = settings.prompts_dir / name
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt template '{name}' not found at {prompt_file}")

    content = prompt_file.read_text(encoding="utf-8")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    return content, content_hash


def compute_config_fingerprint(overrides: dict[str, Any] | None = None) -> str:
    """Compute a deterministic hash of active model IDs, prompt hashes, and retrieval settings."""
    fingerprint_items = [
        f"model_small={settings.model_small}",
        f"model_mid={settings.model_mid}",
        f"model_strong={settings.model_strong}",
        f"model_fallback={settings.model_fallback}",
        f"embedding_model={settings.embedding_model}",
        f"rrf_k={settings.rrf_k}",
        f"rerank_type={settings.reranker_type}",
    ]

    # Include all prompt file hashes
    prompt_names = [
        "plan.v1.md",
        "rewrite.v1.md",
        "explore.v1.md",
        "patch.v1.md",
        "answer.v1.md",
        "judge_qa.v1.md",
    ]
    for pname in sorted(prompt_names):
        try:
            _, phash = load_prompt(pname)
            fingerprint_items.append(f"{pname}={phash}")
        except Exception:
            fingerprint_items.append(f"{pname}=missing")

    if overrides:
        for k in sorted(overrides.keys()):
            fingerprint_items.append(f"{k}={overrides[k]}")

    joined = "|".join(fingerprint_items)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]
