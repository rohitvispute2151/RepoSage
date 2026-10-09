"""Code identifier expansion for full-text search indexing.

Splits camelCase and snake_case identifiers into separate tokens so lexical search
can easily match natural language queries like 'parse retry header' against 'parse_retry_header'.
"""

import re

# Regex finding transition between lowercase/digit and uppercase character
_CAMEL_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
# Regex extracting legal programming identifier tokens
_IDENT_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def expand_identifiers(text: str) -> str:
    """Extract and split compound identifiers, appending space-separated terms to text."""
    if not text:
        return ""

    tokens = set(_IDENT_PATTERN.findall(text))
    extra_tokens: list[str] = []

    for token in tokens:
        # Convert camelCase to snake_case style, then split on underscores
        split_camel = _CAMEL_SPLIT.sub("_", token)
        subparts = [part.lower() for part in re.split(r"_+", split_camel) if part]
        if len(subparts) > 1:
            extra_tokens.append(" ".join(subparts))

    if not extra_tokens:
        return text

    return text + "\n" + "\n".join(extra_tokens)
