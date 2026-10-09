"""AST-based chunker for Python source code.

Extracts symbol-level semantic chunks (functions, methods, classes) annotated
with docstrings, formal signatures, and line boundaries.
"""

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Optional

MAX_CHUNK_LINES: int = 120


@dataclass
class CodeChunk:
    """A semantic chunk of code with header metadata and source body."""

    path: str
    qualname: str
    kind: str  # 'function', 'method', 'class', 'module_header'
    signature: str
    docstring: Optional[str]
    start_line: int
    end_line: int
    body: str
    is_test: bool
    content: str
    content_hash: str


def _build_chunk_content(
    path: str,
    qualname: str,
    kind: str,
    signature: str,
    docstring: str | None,
    body: str,
) -> str:
    """Format structured header and source body for embedding and citation."""
    header_lines = [
        f"# path: {path}",
        f"# symbol: {qualname} ({kind})",
        f"# signature: {signature}",
    ]
    if docstring:
        clean_doc = " ".join(docstring.strip().splitlines()[:2])
        header_lines.append(f"# doc: {clean_doc}")

    return "\n".join(header_lines) + "\n" + body


def _get_signature(node: ast.AST) -> str:
    """Extract def or class signature line representation."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
        try:
            args = ast.unparse(node.args)
            returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
            return f"{prefix}{node.name}({args}){returns}"
        except Exception:
            return f"{prefix}{node.name}(...)"
    elif isinstance(node, ast.ClassDef):
        bases = [ast.unparse(b) for b in node.bases] if node.bases else []
        bases_str = f"({', '.join(bases)})" if bases else ""
        return f"class {node.name}{bases_str}"
    return ""


def _split_oversized(
    chunk: CodeChunk, max_lines: int = MAX_CHUNK_LINES
) -> list[CodeChunk]:
    """Split a large function into multiple contiguous sub-parts repeating header."""
    lines = chunk.body.splitlines()
    if len(lines) <= max_lines:
        return [chunk]

    parts: list[CodeChunk] = []
    total_parts = (len(lines) + max_lines - 1) // max_lines

    for idx in range(total_parts):
        start_idx = idx * max_lines
        end_idx = min(start_idx + max_lines, len(lines))
        sub_body = "\n".join(lines[start_idx:end_idx])
        sub_start_line = chunk.start_line + start_idx
        sub_end_line = chunk.start_line + end_idx - 1
        sub_qualname = f"{chunk.qualname} (part {idx + 1}/{total_parts})"

        content = _build_chunk_content(
            chunk.path,
            sub_qualname,
            chunk.kind,
            chunk.signature,
            chunk.docstring,
            sub_body,
        )
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        parts.append(
            CodeChunk(
                path=chunk.path,
                qualname=sub_qualname,
                kind=chunk.kind,
                signature=chunk.signature,
                docstring=chunk.docstring,
                start_line=sub_start_line,
                end_line=sub_end_line,
                body=sub_body,
                is_test=chunk.is_test,
                content=content,
                content_hash=content_hash,
            )
        )

    return parts


def chunk_python(
    path: str, source: str, is_test: bool, module_prefix: str = ""
) -> list[CodeChunk]:
    """Parse Python source into symbol-level chunks."""
    lines = source.splitlines()
    if not source.strip():
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fallback to single raw text chunk on syntax error
        content = _build_chunk_content(
            path, path, "module_header", f"file: {path}", None, source
        )
        return [
            CodeChunk(
                path=path,
                qualname=path,
                kind="module_header",
                signature=path,
                docstring=None,
                start_line=1,
                end_line=len(lines) or 1,
                body=source,
                is_test=is_test,
                content=content,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        ]

    raw_chunks: list[CodeChunk] = []
    prefix = module_prefix if module_prefix else Path(path).stem

    def get_node_span(node: ast.AST) -> tuple[int, int, str]:
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start)
        snippet = "\n".join(lines[start - 1 : end])
        return start, end, snippet

    def visit(node: ast.AST, current_scope: str, in_class: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                s, e, body = get_node_span(child)
                qn = f"{current_scope}.{child.name}"
                kind = "method" if in_class else "function"
                sig = _get_signature(child)
                doc = ast.get_docstring(child)
                content = _build_chunk_content(path, qn, kind, sig, doc, body)

                raw_chunks.append(
                    CodeChunk(
                        path=path,
                        qualname=qn,
                        kind=kind,
                        signature=sig,
                        docstring=doc,
                        start_line=s,
                        end_line=e,
                        body=body,
                        is_test=is_test,
                        content=content,
                        content_hash=hashlib.sha256(
                            content.encode("utf-8")
                        ).hexdigest(),
                    )
                )
                # Do not recurse into nested function defs

            elif isinstance(child, ast.ClassDef):
                s, e, body = get_node_span(child)
                qn = f"{current_scope}.{child.name}"
                sig = _get_signature(child)
                doc = ast.get_docstring(child)

                # Emit class chunk
                if e - s + 1 <= MAX_CHUNK_LINES:
                    content = _build_chunk_content(
                        path, qn, "class", sig, doc, body
                    )
                    raw_chunks.append(
                        CodeChunk(
                            path=path,
                            qualname=qn,
                            kind="class",
                            signature=sig,
                            docstring=doc,
                            start_line=s,
                            end_line=e,
                            body=body,
                            is_test=is_test,
                            content=content,
                            content_hash=hashlib.sha256(
                                content.encode("utf-8")
                            ).hexdigest(),
                        )
                    )
                else:
                    # Large class: emit class declaration and docstring header chunk
                    header_end = (
                        child.body[0].end_lineno if child.body else s + 5
                    )
                    header_body = "\n".join(lines[s - 1 : header_end])
                    content = _build_chunk_content(
                        path, qn, "class", sig, doc, header_body
                    )
                    raw_chunks.append(
                        CodeChunk(
                            path=path,
                            qualname=qn,
                            kind="class",
                            signature=sig,
                            docstring=doc,
                            start_line=s,
                            end_line=header_end,
                            body=header_body,
                            is_test=is_test,
                            content=content,
                            content_hash=hashlib.sha256(
                                content.encode("utf-8")
                            ).hexdigest(),
                        )
                    )

                # Always visit class body to extract methods
                visit(child, qn, in_class=True)

            elif isinstance(child, (ast.If, ast.Try, ast.With)):
                visit(child, current_scope, in_class)

    visit(tree, prefix, in_class=False)

    # Add module header chunk (imports and top-level docstring)
    doc = ast.get_docstring(tree)
    module_header_lines = []
    if doc:
        module_header_lines.append(f'"""{doc}"""')
    for item in tree.body:
        if isinstance(item, (ast.Import, ast.ImportFrom)):
            s, e, text = get_node_span(item)
            module_header_lines.append(text)
    header_body = "\n".join(module_header_lines) or (
        lines[0] if lines else f"# {path}"
    )

    header_content = _build_chunk_content(
        path, prefix, "module_header", f"module: {prefix}", doc, header_body
    )
    raw_chunks.append(
        CodeChunk(
            path=path,
            qualname=prefix,
            kind="module_header",
            signature=f"module {prefix}",
            docstring=doc,
            start_line=1,
            end_line=min(30, len(lines)) or 1,
            body=header_body,
            is_test=is_test,
            content=header_content,
            content_hash=hashlib.sha256(
                header_content.encode("utf-8")
            ).hexdigest(),
        )
    )

    # Split oversized chunks if any
    final_chunks: list[CodeChunk] = []
    for chunk in raw_chunks:
        final_chunks.extend(_split_oversized(chunk))

    return final_chunks
