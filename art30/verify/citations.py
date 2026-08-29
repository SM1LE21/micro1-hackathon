"""The citation re-read (03-verifier.md 7.2).

Every position the record carries is read back off disk: the path has to resolve
inside the repository, the line has to exist, and -- for the six object types 7.2
says carry a symbol -- the **logical** line (the statement whose span contains the
cited physical line) has to contain it after normalisation.

Read from disk rather than from the graph on purpose: the check exists to catch a
plausible line number the model produced without looking, and a graph the model
never saw cannot corroborate that. The statement spans come from one `ast.parse`
per cited file, cached for the batch.

The problem strings are 7.2's own set and the `expected` strings are
10-instructions.md 4.3's; nothing here invents a sentence.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from art30.verify.findings import Graph
from art30.verify.rules import norm

TOKEN = re.compile(r"[A-Za-z0-9_]+")

# 7.2 rule 3: the logical line is "the statement whose span contains it", and the point
# of the rule is "a field declaration split across three lines or a call broken by a
# formatter". A compound statement's span is its whole body, so entering one here would
# let `class User(...)` stand as the citation for every field in the class and a `def`
# line for any token in the function -- exactly the plausible-line-without-looking the
# check exists to catch. Compound headers fall back to the physical line, which still
# carries the class or function name.
COMPOUND = tuple(node for node in (
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.For, ast.AsyncFor,
    ast.While, ast.If, ast.With, ast.AsyncWith, ast.Try,
    getattr(ast, "TryStar", None), getattr(ast, "Match", None)) if node is not None)

# 10-instructions.md 4.3: the two `expected` strings, and the one 7.2 leaves to the
# rows that carry no symbol (a retention item, a subject link) to say.
CITE_SYMBOL = "cite the line where {symbol} appears, or drop the claim"
CITE_SCANNED = "cite a line in a file this scan read, or drop the claim"
CITE_LINE = "cite a line that exists in {file}, or drop the claim"
# 7.2 is silent on a `symbol` that normalises to nothing, and `record.schema.json` sets
# no `minLength`, so `""` and `"!!!"` are schema-valid. The conservative reading is that
# a citation carrying no symbol makes no claim rather than passing rule 3 vacuously;
# this is a fifth `problem` string beyond 10-instructions.md 4.3's four (deviation).
NO_SYMBOL = "the citation names no symbol to check"
CITE_NAME = "name the symbol that line carries, or drop the claim"


def tokens(text: str) -> set[str]:
    """Identifier-shaped tokens, normalised. `_` is not a token boundary.

    7.2: "`email` matches `email = models.EmailField()` and does not match
    `user_email_verified_at` on its own", so a compound identifier stays one token
    and only the contract's own normalisation (plural and singular equal) is applied.
    """
    return {norm(word) for word in TOKEN.findall(text)}


def contains(text: str, symbol: str) -> bool:
    """7.2 rule 3: the symbol, normalised, on the logical line.

    A symbol that normalises to nothing never matches; `check_one` rejects it before
    it gets here, with a problem string of its own.
    """
    wanted = norm(symbol)
    found = tokens(text)
    if wanted in found:
        return True
    parts = [norm(part) for part in symbol.split(".") if norm(part)]
    return len(parts) > 1 and all(part in found for part in parts)


class Files:
    """One repository's files, re-read from disk once per citation batch (7.2)."""

    def __init__(self, root: Path, scanned: set[str]) -> None:
        self.root = Path(root).resolve()
        self.scanned = scanned
        self._lines: dict[str, list[str] | None] = {}
        self._spans: dict[str, list[tuple[int, int]]] = {}

    def resolve(self, rel: str) -> Path | None:
        """The path must exist under the repository root and resolve inside it."""
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            return None
        try:
            real = (self.root / rel).resolve()
            if real.is_file() and real.is_relative_to(self.root):
                return real
        except OSError:                  # pragma: no cover - a race we report as absent
            return None
        return None

    def lines(self, rel: str) -> list[str] | None:
        if rel not in self._lines:
            path = self.resolve(rel)
            try:
                text = path.read_text(encoding="utf-8", errors="replace") if path else None
            except OSError:              # pragma: no cover
                text = None
            self._lines[rel] = text.splitlines() if text is not None else None
        return self._lines[rel]

    def _statement_spans(self, rel: str) -> list[tuple[int, int]]:
        if rel in self._spans:
            return self._spans[rel]
        spans: list[tuple[int, int]] = []
        lines = self.lines(rel)
        if lines is not None and rel.endswith(".py"):
            try:
                tree = ast.parse("\n".join(lines))
            except (SyntaxError, ValueError):
                tree = None
            for node in ast.walk(tree) if tree is not None else ():
                if (isinstance(node, ast.stmt) and node.end_lineno
                        and not isinstance(node, COMPOUND)):    # 7.2 rule 3
                    spans.append((node.lineno, node.end_lineno))
        self._spans[rel] = sorted(spans, key=lambda s: (s[1] - s[0], s[0]))
        return self._spans[rel]

    def logical(self, rel: str, line: int) -> str:
        """The cited physical line, or the statement whose span contains it (7.2)."""
        lines = self.lines(rel)
        if lines is None or not 1 <= line <= len(lines):
            return ""
        for start, end in self._statement_spans(rel):
            if start <= line <= end:     # the smallest enclosing statement, sorted first
                return "\n".join(lines[start - 1: end])
        return lines[line - 1]


def _item(cite: dict, symbol: str, problem: str, expected: str) -> dict:
    return {"file": str(cite.get("file") or ""), "line": int(cite.get("line") or 0),
            "symbol": symbol, "problem": problem, "expected": expected}


def check_one(files: Files, cite: dict, symbol: str | None,
              scanned_only: bool) -> dict | None:
    """7.2's four checks, in order; the first failure is the entry."""
    rel = str(cite.get("file") or "")
    line = int(cite.get("line") or 0)
    name = symbol or ""
    if files.resolve(rel) is None:
        return _item(cite, name, f"file {rel} does not exist under the repository root",
                     CITE_SCANNED)
    if scanned_only and rel not in files.scanned:
        return _item(cite, name, f"file {rel} is not in the scanned set", CITE_SCANNED)
    lines = files.lines(rel) or []
    if not 1 <= line <= len(lines):
        return _item(cite, name, f"line {line} is beyond end of file ({len(lines)} lines)",
                     CITE_SYMBOL.format(symbol=name) if name
                     else CITE_LINE.format(file=rel))
    if symbol is not None and not norm(symbol):
        # 7.2 rule 3 has nothing to compare, and a free pass would let a citation that
        # carries no claim satisfy a blocking list. Rejected rather than skipped.
        return _item(cite, str(symbol), NO_SYMBOL, CITE_NAME)
    if symbol is None:                   # 7.2: two of the objects carry no symbol at all
        return None
    if not contains(files.logical(rel, line), symbol):
        return _item(cite, name, f"line {line} does not contain '{symbol}'",
                     CITE_SYMBOL.format(symbol=name))
    return None


def positions(record: dict) -> list[tuple[dict, str | None, bool]]:
    """7.2's table, row by row: the citation, its symbol, and whether it must be scanned."""
    out: list[tuple[dict, str | None, bool]] = []
    for store in record.get("stores") or []:
        if store.get("declared_at"):
            out.append((store["declared_at"], store["declared_at"].get("symbol"), True))
        if store.get("subject_link"):
            out.append((store["subject_link"], None, True))
        for item in store.get("fields") or []:
            out.append((item, item.get("name"), True))
            out += _evidence(item.get("erasure"))
        out += _evidence(store.get("erasure"))
    for entry in record.get("entry_points") or []:
        out.append((entry, entry.get("name"), True))
    for item in record.get("retention") or []:
        if item.get("file") is not None and item.get("line") is not None:
            out.append((item, None, False))
    for subject in record.get("data_subjects") or []:
        out.append((subject, None, False))
    hints = record.get("hints") or {}
    for key in ("observed_region_hints", "security_evidence"):
        for cite in hints.get(key) or []:
            out.append((cite, None, False))   # 7.2: a Dockerfile is honest evidence
    return out


def _evidence(block: dict | None) -> list[tuple[dict, str | None, bool]]:
    return [(cite, cite.get("symbol"), True) for cite in (block or {}).get("evidence") or []]


def check_citations(record: dict, graph: Graph, root: Path) -> list[dict]:
    """Every position in the record, re-read; sorted by (file, line, symbol) (7.5)."""
    files = Files(root, {module.file for module in graph.modules.values()})
    found: list[dict] = []
    for cite, symbol, scanned_only in positions(record):
        item = check_one(files, cite, symbol, scanned_only)
        if item is not None and item not in found:
            found.append(item)
    return sorted(found, key=lambda i: (i["file"], i["line"], i["symbol"]))
