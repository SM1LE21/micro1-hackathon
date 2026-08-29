"""The four model-facing tools and their jailed implementations.

Nothing here imports, compiles or executes repository code, opens a socket, or
emits an absolute path. Every traversal is sorted before it is emitted: tool
output sits inside the hash of every later request, so filesystem order would
be a replay miss on every machine but the one that recorded the cache.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

EXCLUDED_DIRS = frozenset({".git", "__pycache__", "node_modules", "static", "media"})
MAX_FILE_BYTES = 2_000_000
MAX_READ_LINES = 400
MAX_GREP_RESULTS = 100

SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "record.schema.json"

DESCRIPTIONS: dict[str, str] = {
    "list_tree": (
        'List the repository tree under path, indented, with a byte size per entry. Use "."\n'
        "for the repository root and a max_depth of 4 unless you need more. .git,\n"
        "__pycache__, node_modules, static and media are never listed."
    ),
    "read_file": (
        "Read a file from the repository. Returns at most 400 numbered lines per call.\n"
        "start_line is 1-based; set end_line to the last line you want, or null to read to\n"
        "the end of the file, capped at 400 lines. Take the range you need rather than the\n"
        "file twice."
    ),
    "grep": (
        "Search the repository with a Python regular expression. Returns file:line: text,\n"
        "at most max_results matches and never more than 100. glob selects the files to\n"
        'search and defaults to *.py; path defaults to "." for the whole repository.'
    ),
    "submit_record": (
        "Submit the finished record for this repository. The record must match this\n"
        "schema exactly. The result is either an acceptance or a list of problems with the\n"
        "submission and the number of attempts left."
    ),
}


class ToolError(Exception):
    """A tool refused: a jail escape, a missing path, an unreadable file."""


def record_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _submit_input_schema() -> dict:
    # `$ref` targets resolve against the document root, and a tool's document
    # root is its `input_schema`: nested `$defs` would leave every ref dangling.
    schema = record_schema()
    schema.pop("$schema", None)
    schema.pop("$id", None)
    defs = schema.pop("$defs")
    return {
        "type": "object",
        "properties": {"record": schema},
        "required": ["record"],
        "additionalProperties": False,
        "$defs": defs,
    }


SPEC: tuple[dict, ...] = (
    {
        "name": "list_tree",
        "description": DESCRIPTIONS["list_tree"],
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "max_depth": {"type": "integer"}},
            "required": ["path", "max_depth"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_file",
        "description": DESCRIPTIONS["read_file"],
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            },
            "required": ["path", "start_line", "end_line"],
            "additionalProperties": False,
        },
    },
    {
        "name": "grep",
        "description": DESCRIPTIONS["grep"],
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "glob": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["pattern", "path", "glob", "max_results"],
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_record",
        "description": DESCRIPTIONS["submit_record"],
        "strict": True,
        "input_schema": _submit_input_schema(),
    },
)


@dataclass(frozen=True)
class ToolCtx:
    root: Path
    max_read_lines: int = MAX_READ_LINES
    max_grep: int = MAX_GREP_RESULTS


def resolve(root: Path, rel: str) -> Path:
    """The jail. Symlinks are resolved before the containment check."""
    if os.path.isabs(rel):
        raise ToolError(f"path must be relative to the repository root: {rel}")
    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_real, rel))
    if os.path.commonpath([root_real, candidate]) != root_real:
        raise ToolError(f"path escapes the repository root: {rel}")
    return Path(candidate)


def _lines(text: str) -> list[str]:
    """Split on \\n only, strip one trailing \\r, drop the empty tail at EOF."""
    parts = text.split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    return [p[:-1] if p.endswith("\r") else p for p in parts]


def _read_text(path: Path, label: str) -> str:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ToolError(f"file is larger than {MAX_FILE_BYTES} bytes: {label}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ToolError(f"file is not UTF-8 text: {label}") from None


def _entries(directory: Path) -> list[os.DirEntry]:
    with os.scandir(directory) as it:
        return sorted(it, key=lambda e: e.name)


def list_tree(ctx: ToolCtx, path: str = ".", max_depth: int = 4) -> str:
    base = resolve(ctx.root, path)
    if not base.is_dir():
        raise ToolError(f"not a directory: {path}")
    lines: list[str] = []
    _walk(base, 0, max(1, max_depth), lines)
    return "\n".join(lines) if lines else "(empty)"


def _walk(directory: Path, depth: int, max_depth: int, lines: list[str]) -> None:
    if depth >= max_depth:
        return
    indent = "  " * depth
    for entry in _entries(directory):
        if entry.name in EXCLUDED_DIRS:
            continue
        # A symlinked directory is never descended: it can leave the jail.
        if entry.is_dir(follow_symlinks=False):
            lines.append(f"{indent}{entry.name}/")
            _walk(Path(entry.path), depth + 1, max_depth, lines)
        else:
            lines.append(f"{indent}{entry.name}  ({entry.stat(follow_symlinks=False).st_size} B)")


def read_file(ctx: ToolCtx, path: str, start_line: int = 1, end_line: int | None = None) -> str:
    target = resolve(ctx.root, path)
    if not target.is_file():
        raise ToolError(f"not a file: {path}")
    lines = _lines(_read_text(target, path))
    if not lines:
        # An empty `__init__.py` is a normal answer, not a tool failure; and a
        # tool_result block rejects an empty string, as in grep and list_tree.
        return "(empty file)\n"
    if start_line < 1:
        raise ToolError(f"start_line is 1-based, got {start_line}")
    if start_line > len(lines):
        raise ToolError(f"start_line {start_line} is past the end of {path} ({len(lines)} lines)")
    # Clamping, so no model-side value for "absent" changes the emitted bytes.
    last = len(lines) if end_line is None or end_line <= 0 or end_line < start_line else end_line
    last = min(last, len(lines), start_line + ctx.max_read_lines - 1)
    return "".join(f"{n}: {lines[n - 1]}\n" for n in range(start_line, last + 1))


def grep(
    ctx: ToolCtx,
    pattern: str,
    path: str = ".",
    glob: str = "*.py",
    max_results: int = MAX_GREP_RESULTS,
) -> str:
    base = resolve(ctx.root, path)
    if os.path.isabs(glob):
        # `rglob` raises NotImplementedError on an absolute pattern, and
        # `dispatch` promises the loop a message rather than an exception.
        raise ToolError(f"glob must be relative to the repository root: {glob}")
    try:
        expression = re.compile(pattern)
    except re.error as exc:
        raise ToolError(f"invalid regular expression: {exc}") from None
    cap = ctx.max_grep if max_results <= 0 else min(max_results, ctx.max_grep)
    hits: list[tuple[str, int, str]] = []
    for candidate in sorted(base.rglob(glob)):
        if not _greppable(candidate, base, ctx.root):
            continue
        try:
            text = _read_text(candidate, candidate.name)
        except (ToolError, OSError):
            continue
        rel = os.path.relpath(candidate, ctx.root)
        for number, line in enumerate(_lines(text), 1):
            if expression.search(line):
                hits.append((rel, number, line))
    # Sorted before the cut, so truncation drops the same matches everywhere.
    hits.sort(key=lambda hit: (hit[0], hit[1]))
    if not hits:
        return "no matches\n"
    return "".join(f"{rel}:{number}: {line}\n" for rel, number, line in hits[:cap])


def _greppable(candidate: Path, base: Path, root: Path) -> bool:
    if candidate.is_symlink() or not candidate.is_file():
        return False
    # The jail again: `glob` never passes through `resolve()`, so a pattern of
    # its own ("../other/*.py", or anything under a symlinked directory) walks
    # out of the root and puts a foreign path into the next request hash.
    root_real = os.path.realpath(root)
    if os.path.commonpath([root_real, os.path.realpath(candidate)]) != root_real:
        return False
    return not any(part in EXCLUDED_DIRS for part in candidate.relative_to(base).parts)


def dispatch(name: str, args: Mapping[str, object], ctx: ToolCtx) -> tuple[str, bool]:
    """Run one tool call. Never raises: a failure is `(message, True)`."""
    try:
        if name == "list_tree":
            return list_tree(ctx, _str(args, "path", "."), _int(args, "max_depth", 4)), False
        if name == "read_file":
            path, start = _str(args, "path", ""), _int(args, "start_line", 1)
            return read_file(ctx, path, start, _opt(args, "end_line")), False
        if name == "grep":
            pattern, where = _str(args, "pattern", ""), _str(args, "path", ".")
            glob, cap = _str(args, "glob", "*.py"), _int(args, "max_results", MAX_GREP_RESULTS)
            return grep(ctx, pattern, where, glob, cap), False
        raise ToolError(f"unknown tool: {name}")
    except (ToolError, OSError, TypeError, ValueError) as exc:
        return f"{exc}", True


def _str(args: Mapping[str, object], key: str, default: str) -> str:
    value = args.get(key)
    return default if value is None else str(value)


def _int(args: Mapping[str, object], key: str, default: int) -> int:
    value = args.get(key)
    return default if value is None else int(value)  # type: ignore[arg-type]


def _opt(args: Mapping[str, object], key: str) -> int | None:
    value = args.get(key)
    return None if value is None else int(value)  # type: ignore[arg-type]


def format_schema_errors(errors: Iterable[Any]) -> list[str]:
    """One rendering of `jsonschema` errors, shared by both arms.

    Sorted by JSON pointer so the handler invariants (10-instructions section
    4.6) sort into the same list without either arm's wording drifting.
    """
    rendered: list[str] = []
    for error in errors:
        pointer = "/" + "/".join(str(part) for part in error.absolute_path)
        allowed = error.validator_value if error.validator == "enum" else None
        if allowed is None:
            rendered.append(f"{pointer}: {error.message}")
        else:
            values = ", ".join(sorted(str(value) for value in allowed))
            rendered.append(
                f"{pointer}: {error.instance!r} is not one of the allowed values; allowed: {values}"
            )
    return sorted(rendered)
