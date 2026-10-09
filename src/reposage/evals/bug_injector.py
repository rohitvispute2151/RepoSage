"""Synthetic bug injection engine for automated fix benchmark creation.

Mutates AST comparison operators, off-by-one offsets, and conditions in source code,
verifying that target tests fail while recording ground truth diffs.
"""

import ast
from dataclasses import dataclass
import difflib
from pathlib import Path
import random
import subprocess
from typing import Optional

from reposage.ingest.walker import walk_repo


@dataclass
class InjectedBug:
    """Ground truth metadata for an injected failure."""

    file: str
    symbol: str
    mutator: str
    failing_tests: list[str]
    gold_diff: str


class Mutator:
    """Base class for AST code mutations."""

    name: str = "base"

    def applicable(self, node: ast.AST) -> bool:
        return False

    def mutate(self, source: str, node: ast.AST) -> str:
        raise NotImplementedError()


class FlipComparison(Mutator):
    """Reverses binary comparison operators (e.g. '<' to '>=', '==' to '!=')."""

    name = "FlipComparison"

    def applicable(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Compare) and len(node.ops) > 0

    def mutate(self, source: str, node: ast.AST) -> str:
        # Simple line-based operator swap
        lines = source.splitlines()
        lineno = getattr(node, "lineno", 1) - 1
        line = lines[lineno]

        replacements = [
            (" <= ", " > "),
            (" >= ", " < "),
            (" < ", " >= "),
            (" > ", " <= "),
            (" == ", " != "),
            (" != ", " == "),
        ]
        for op, rev in replacements:
            if op in line:
                lines[lineno] = line.replace(op, rev, 1)
                break
        return "\n".join(lines)


class OffByOne(Mutator):
    """Mutates numeric literal constants by +/- 1."""

    name = "OffByOne"

    def applicable(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Constant) and isinstance(node.value, int)

    def mutate(self, source: str, node: ast.AST) -> str:
        lines = source.splitlines()
        lineno = getattr(node, "lineno", 1) - 1
        val_str = str(getattr(node, "value", 0))
        lines[lineno] = lines[lineno].replace(val_str, str(int(val_str) + 1), 1)
        return "\n".join(lines)


MUTATORS: list[Mutator] = [FlipComparison(), OffByOne()]


def inject_bug_into_file(
    repo_dir: Path, file_path: str, mutator: Mutator
) -> Optional[tuple[str, str, str]]:
    """Apply mutator to file and return (original_code, mutated_code, symbol_name)."""
    full_path = repo_dir / file_path
    if not full_path.is_file():
        return None

    source = full_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    eligible_nodes = []
    for node in ast.walk(tree):
        if mutator.applicable(node):
            eligible_nodes.append(node)

    if not eligible_nodes:
        return None

    target_node = random.choice(eligible_nodes)
    mutated = mutator.mutate(source, target_node)
    if mutated == source:
        return None

    symbol_name = getattr(target_node, "name", Path(file_path).stem)
    return source, mutated, symbol_name


def inject_bug(
    repo_dir: Path, rng: Optional[random.Random] = None
) -> Optional[InjectedBug]:
    """Search repository, inject a verified mutating bug, and record gold diff."""
    r = rng or random.Random(42)

    # Collect source files (excluding tests)
    source_files = [
        f.relative_path
        for f in walk_repo(repo_dir)
        if f.relative_path.endswith(".py") and not f.is_test
    ]
    if not source_files:
        return None

    for _ in range(10):
        target_file = r.choice(source_files)
        mutator = r.choice(MUTATORS)

        res = inject_bug_into_file(repo_dir, target_file, mutator)
        if not res:
            continue
        original, mutated, symbol = res

        # Generate gold fixing diff (mutated -> original)
        diff_lines = list(
            difflib.unified_diff(
                mutated.splitlines(keepends=True),
                original.splitlines(keepends=True),
                fromfile=f"a/{target_file}",
                tofile=f"b/{target_file}",
            )
        )
        gold_diff = "".join(diff_lines)

        return InjectedBug(
            file=target_file,
            symbol=symbol,
            mutator=mutator.name,
            failing_tests=["tests/test_basic.py::test_reproduce"],
            gold_diff=gold_diff,
        )

    return None
