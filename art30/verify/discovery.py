"""Module discovery, the skip list and the R13 string search (03-verifier.md 1.1).

Walks the repository with directory names sorted, parses every `*.py` the skip
table admits, records what it refused and why, and runs the one search that reads
non-Python files: the S3 versioning declaration of R13 [S22] [S23], which never
produces an edge and is reported as the string search it is.
"""

from __future__ import annotations

import ast
import fnmatch
import os
import re
from dataclasses import dataclass
from pathlib import Path

from art30.verify.rules import RuleSet


@dataclass
class ParsedModule:
    module: str
    file: str
    path: Path
    source: str
    tree: ast.Module
    is_package: bool


def module_name(rel: str) -> str:
    """1.2: relative path, "/" -> ".", ".py" stripped, "__init__" dropped."""
    stem = rel[:-3] if rel.endswith(".py") else rel
    parts = [p for p in stem.replace("\\", "/").split("/") if p]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def walk(root: Path, rules: RuleSet) -> tuple[list[str], dict[str, int]]:
    """Every candidate `*.py` path, relative and sorted, plus the skip tally."""
    excluded = set(rules.scan["excluded_dirs"])
    kept: list[str] = []
    skipped: dict[str, int] = {}
    for current, dirs, files in os.walk(root):
        rel_dir = os.path.relpath(current, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        keep_dirs = []
        for name in sorted(dirs):
            child = f"{rel_dir}/{name}" if rel_dir else name
            if name in excluded and not _holds_always_scan(root / child):
                skipped[f"dir:{name}"] = skipped.get(f"dir:{name}", 0) + 1
                continue
            keep_dirs.append(name)
        dirs[:] = keep_dirs
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            rel = f"{rel_dir}/{name}" if rel_dir else name
            reason = rules.skip_reason(rel)
            if reason:
                skipped[reason] = skipped.get(reason, 0) + 1
                continue
            kept.append(rel)
    return sorted(kept), skipped


def _holds_always_scan(directory: Path) -> bool:
    """The two 1.1 exceptions: `settings/*.py` and `management/commands/*.py` are
    parsed wherever they sit, so their directories are never pruned."""
    return directory.name in {"settings", "management", "commands"}


def parse_all(root: Path, rules: RuleSet) -> tuple[list[ParsedModule], dict[str, int], list[dict]]:
    """Parse every admitted file. A file that will not parse is recorded, not raised."""
    rels, skipped = walk(root, rules)
    modules: list[ParsedModule] = []
    unparsed: list[dict] = []
    limit = int(rules.scan["max_file_bytes"])
    for rel in rels:
        path = root / rel
        try:
            size = path.stat().st_size
        except OSError as exc:  # pragma: no cover - a race we still report
            unparsed.append({"file": rel, "error": type(exc).__name__})
            continue
        if size > limit:
            unparsed.append({"file": rel, "error": "TooLarge"})
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            unparsed.append({"file": rel, "error": type(exc).__name__})
            continue
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError as exc:
            unparsed.append({"file": rel, "error": type(exc).__name__})
            continue
        modules.append(
            ParsedModule(
                module=module_name(rel),
                file=rel,
                path=path,
                source=source,
                tree=tree,
                is_package=Path(rel).name == "__init__.py",
            )
        )
    return modules, skipped, unparsed


def versioning_search(root: Path, rules: RuleSet, python_sources: dict[str, str]) -> list[dict]:
    """R13 [S22] [S23]: a fixed-string search, reported as a string search.

    One of the five literals with `status[:=]enabled` within the qualifier window,
    over the non-Python globs at depth <= 4 and over every scanned Python source as
    text (the research finds the declaration in a bootstrap script, 1.1).
    """
    data = rules.patterns["versioning_declarations"]
    literals = list(data["literals"])
    qualifier = re.compile(data["qualifier_regex"], re.IGNORECASE)
    window = int(data["qualifier_window"])
    found: list[dict] = []
    surfaces: list[tuple[str, str]] = sorted(python_sources.items())
    for rel, text in _non_python(root, rules):
        surfaces.append((rel, text))
    for rel, text in sorted(surfaces):
        lines = text.splitlines()
        for i, line in enumerate(lines):
            hit = next((lit for lit in literals if lit in line), None)
            if hit is None:
                continue
            block = "\n".join(lines[i : i + window + 1])
            if qualifier.search(block):
                found.append({"file": rel, "line": i + 1, "literal": hit,
                              "how": "string search"})
    return sorted(found, key=lambda v: (v["file"], v["line"]))


def _non_python(root: Path, rules: RuleSet) -> list[tuple[str, str]]:
    globs = list(rules.scan["non_python_globs"])
    max_depth = int(rules.scan["non_python_max_depth"])
    excluded = set(rules.scan["excluded_dirs"])
    out: list[tuple[str, str]] = []
    for current, dirs, files in os.walk(root):
        rel_dir = os.path.relpath(current, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        depth = 0 if not rel_dir else rel_dir.count("/") + 1
        dirs[:] = sorted(d for d in dirs if d not in excluded)
        if depth >= max_depth:
            dirs[:] = []
        for name in sorted(files):
            if not any(fnmatch.fnmatch(name, pattern) for pattern in globs):
                continue
            rel = f"{rel_dir}/{name}" if rel_dir else name
            path = root / rel
            try:
                if path.stat().st_size > int(rules.scan["max_file_bytes"]):
                    continue
                out.append((rel, path.read_text(encoding="utf-8", errors="replace")))
            except OSError:  # pragma: no cover
                continue
    return out
