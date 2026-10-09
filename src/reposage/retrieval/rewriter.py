"""Query rewriting pipeline expanding questions into search variants.

Generates alternative phrasing, candidate code identifiers, file hints, and error literals.
"""

import json
from pydantic import BaseModel, Field

from reposage.config import settings
from reposage.llm.client import ResilientLLM
from reposage.llm.prompts import load_prompt
from reposage.llm.types import LLMRequest, Message
from reposage.observability.logging import logger


class RewriteOut(BaseModel):
    """Structured outputs from query rewriting."""

    nl_queries: list[str] = Field(default_factory=list, max_length=3)
    identifiers: list[str] = Field(default_factory=list, max_length=8)
    file_hints: list[str] = Field(default_factory=list, max_length=4)
    error_strings: list[str] = Field(default_factory=list, max_length=3)


async def rewrite_query(llm: ResilientLLM, question: str) -> RewriteOut:
    """Invoke small LLM tier to expand user query into retrieval targets."""
    try:
        prompt_text, prompt_hash = load_prompt("rewrite.v1.md")
    except Exception:
        prompt_text = "Expand the following code question into search variants."
        prompt_hash = "static_rewrite"

    req = LLMRequest(
        model=settings.model_small,
        messages=[
            Message(role="system", content=prompt_text),
            Message(role="user", content=question),
        ],
        response_schema=RewriteOut.model_json_schema(),
        max_tokens=600,
        temperature=0.0,
        meta={"node": "rewrite", "prompt_name": "rewrite.v1.md", "prompt_hash": prompt_hash},
    )

    try:
        resp = await llm.chat(req)
        if resp.text:
            data = json.loads(resp.text)
            parsed = RewriteOut.model_validate(data)
            return parsed
    except Exception as exc:
        logger.warning(f"Query rewriter encountered error: {exc}. Falling back to default.")

    # Safe fallback: empty variants so only the original question is searched
    return RewriteOut(nl_queries=[], identifiers=[], file_hints=[], error_strings=[])
