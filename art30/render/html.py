"""`record.json` plus the repository to one self-contained page.

No JavaScript, no external stylesheet, no web font, no image: the page opens
from a USB stick with no network and prints on A4. The page is built from the
Markdown render's own lines, so the two documents cannot drift in section
order or heading text (07-ui.md section 8).
"""

from __future__ import annotations

import ast
import html
import re
from pathlib import Path

from art30.render import RenderError, VERDICT_ORDER, words
from art30.render.markdown import render_markdown

CITE = re.compile(r"`([^`\s]+\.[A-Za-z0-9_]+):(\d+)`")
CODE = re.compile(r"`([^`]+)`")
TOOLTIP_CHARS = 120
LOGICAL_LINES = 20
SECTION_IDS = {
    "A": "a-inventory",
    "B": "b-recipients",
    "C": "c-retention",
    "D": "d-erasure",
    "E": "e-observations",
    "F": "f-human",
    "G": "g-verification",
    "H": "h-evidence",
}
VERDICTS = {words(v).upper() for v in VERDICT_ORDER}
REACHING = {words(v).upper() for v in ("erased", "erased_after_timer", "anonymised")}
STYLE = """
:root { color-scheme: light; }
body { background: #fff; color: #111; margin: 2rem auto; max-width: 60rem; padding: 0 1rem;
       font-family: Georgia, "Times New Roman", serif; line-height: 1.5; }
h1 { font-size: 1.6rem; } h2 { font-size: 1.25rem; margin-top: 2.5rem; } h3 { font-size: 1.05rem; }
table { border-collapse: collapse; width: 100%; margin: 0.75rem 0; font-size: 0.92rem; }
caption { text-align: left; font-style: italic; padding-bottom: 0.3rem; }
th, td { border: 1px solid #bbb; padding: 0.3rem 0.5rem; text-align: left; vertical-align: top; }
th { background: #f2f2f2; }
code { font-family: "DejaVu Sans Mono", Menlo, monospace; font-size: 0.86em; }
code.cite { border-bottom: 1px dotted #666; }
.boundary { border: 1px solid #444; padding: 0.8rem 1rem; margin: 1.2rem 0; }
.verdict { font-weight: bold; letter-spacing: 0.02em; }
.verdict.not-reaching { color: #8b0000; }
tr.not-reaching td:first-child { border-left: 4px solid #8b0000; }
.empty { font-style: italic; color: #444; }
.footnotes { display: none; }
@media print {
  @page { size: A4; margin: 18mm 16mm 22mm 16mm; }
  body { margin: 0; max-width: none; font-size: 10.5pt; }
  section { break-before: page; }
  .footnotes { display: block; font-size: 0.8rem; }
  .running-footer { position: fixed; bottom: 0; left: 0; right: 0; font-size: 0.75rem;
                    border-top: 1px solid #999; padding-top: 2mm; }
}
"""


def render_html(record: dict, repo_root: Path) -> str:
    """The page. Raises `RenderError` when a cited line lost its symbol."""
    root = Path(repo_root)
    # The citation check must read the repository as it is now, not as some
    # earlier render in this process read it.
    _CACHE.clear()
    _check_citations(record, root)
    lines = render_markdown(record).split("\n")
    prov = record.get("provenance") or {}
    body = _body(lines, root)
    title = html.escape(f"Record of processing — {record.get('repository')}")
    return (
        f"<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="generator" content="art30 run {html.escape(str(prov.get("run_id")))}">\n'
        f"<title>{title}</title>\n<style>{STYLE}</style>\n</head>\n<body>\n"
        f"{body}\n"
        f'<div class="running-footer">{html.escape(str(prov.get("run_id")))} — not legal advice;'
        f" the technical half of an Article 30(1) record.</div>\n</body>\n</html>\n"
    )


def _body(lines: list[str], root: Path) -> str:
    out: list[str] = []
    contents: list[str] = []
    notes: list[tuple[str, str]] = []
    caption = "Provenance"  # the first table sits under the h1 and has no heading
    open_section = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("## "):
            out += _close(open_section, notes)
            notes, open_section = [], True
            heading = line[3:]
            key = SECTION_IDS.get(heading[:1], f"section-{len(contents)}")
            contents.append(f'<li><a href="#{key}">{html.escape(heading)}</a></li>')
            out.append(f'<section id="{key}">\n<h2>{html.escape(heading)}</h2>')
            caption = heading
        elif line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("### "):
            caption = line[4:]
            out.append(f"<h3>{_inline(line[4:], root, notes)}</h3>")
        elif line.startswith("|"):
            rows, index = _table_rows(lines, index)
            out.append(_table(rows, caption, root, notes))
            continue
        elif line.startswith("- "):
            out.append(f"<p>{_inline(line[2:], root, notes)}</p>")
        elif line.strip():
            klass = ' class="boundary"' if line.startswith("This is the technical half") else ""
            out.append(f"<p{klass}>{_inline(line, root, notes)}</p>")
        index += 1
    out += _close(open_section, notes)
    toc = "<nav><ol>\n" + "\n".join(contents) + "\n</ol></nav>"
    head = out[:1]  # the h1 stays above the table of contents
    return "\n".join(head + [toc] + out[1:])


def _close(open_section: bool, notes: list[tuple[str, str]]) -> list[str]:
    if not open_section:
        return []
    if not notes:
        return ["</section>"]
    items = "\n".join(
        f"<li>{html.escape(where)}: {html.escape(text)}</li>" for where, text in notes
    )
    return [f'<ol class="footnotes">\n{items}\n</ol>', "</section>"]


def _table_rows(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    rows: list[list[str]] = []
    index = start
    while index < len(lines) and lines[index].startswith("|"):
        cells = [c.strip() for c in lines[index].strip().strip("|").split("|")]
        if not all(set(c) <= {"-", ":"} and c for c in cells):
            rows.append(cells)
        index += 1
    return rows, index


def _table(rows: list[list[str]], caption: str, root: Path, notes: list) -> str:
    if not rows:
        return ""
    header = "".join(f"<th>{_inline(c, root, notes)}</th>" for c in rows[0])
    body = []
    for row in rows[1:]:
        klass = ' class="not-reaching"' if _row_is_not_reaching(row) else ""
        cells = "".join(f"<td>{_inline(c, root, notes)}</td>" for c in row)
        body.append(f"<tr{klass}>{cells}</tr>")
    return (
        f"<table>\n<caption>{_inline(caption, root, notes)}</caption>\n<tr>{header}</tr>\n"
        + "\n".join(body)
        + "\n</table>"
    )


def _row_is_not_reaching(row: list[str]) -> bool:
    return any(_verdict_of(cell) in VERDICTS - REACHING for cell in row)


def _verdict_of(cell: str) -> str:
    return cell.split(" (")[0].strip()


def _inline(text: str, root: Path, notes: list[tuple[str, str]]) -> str:
    verdict = _verdict_of(text)
    if verdict in VERDICTS:
        klass = "reaching" if verdict in REACHING else "not-reaching"
        return f'<span class="verdict {klass}">{html.escape(text)}</span>'
    if text == "requires human completion" or text.endswith("— requires human completion"):
        return f'<span class="empty">{html.escape(text)}</span>'
    out: list[str] = []
    position = 0
    for match in CODE.finditer(text):
        out.append(html.escape(text[position : match.start()]).replace("&lt;br&gt;", "<br>"))
        out.append(_code(match.group(1), root, notes))
        position = match.end()
    out.append(html.escape(text[position:]).replace("&lt;br&gt;", "<br>"))
    return "".join(out)


def _code(inner: str, root: Path, notes: list[tuple[str, str]]) -> str:
    hit = CITE.fullmatch(f"`{inner}`")
    if not hit:
        return f"<code>{html.escape(inner)}</code>"
    source = _source_line(root, hit.group(1), int(hit.group(2)))
    if source is None:
        return f"<code>{html.escape(inner)}</code>"
    if (inner, source) not in notes:
        notes.append((inner, source))
    return f'<code class="cite" title="{html.escape(source, quote=True)}">{html.escape(inner)}</code>'


def _source_line(root: Path, path: str, line: int) -> str | None:
    lines = _file_lines(root, path)
    if lines is None or not 1 <= line <= len(lines):
        return None
    return lines[line - 1].strip()[:TOOLTIP_CHARS]


_CACHE: dict[tuple[str, str], list[str] | None] = {}


def _file_lines(root: Path, path: str) -> list[str] | None:
    key = (str(root), path)
    if key not in _CACHE:
        target = root / path
        try:
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            _CACHE[key] = None
        else:
            _CACHE[key] = [ln.rstrip("\r") for ln in text.split("\n")]
    return _CACHE[key]


def _check_citations(record: dict, root: Path) -> None:
    """Every cited symbol must still be on its logical line, or nothing renders.

    The logical line is read the way the verifier reads it (7.2 rule 3,
    `art30.verify.citations.Files.logical`): the cited physical line, or the
    smallest ast statement whose span contains it. Before 2026-08-31 this check
    read only the cited line plus its forward continuation, so a citation the
    verifier had accepted mid-statement failed here — after the human had
    approved (D01/R01 demo runs; DEVIATIONS D-22). The render check must never
    be stricter than the verifier that vouched for the record.
    """
    for path, line, symbol in _symbols(record):
        lines = _file_lines(root, path)
        if lines is None:
            raise RenderError(f"citation {path}:{line} names a file this scan cannot read")
        if not 1 <= line <= len(lines):
            raise RenderError(f"citation {path}:{line} is past the end of the file")
        if symbol.lower() not in _logical(lines, line).lower() \
                and symbol.lower() not in _statement(path, lines, line).lower():
            raise RenderError(f"citation {path}:{line} no longer contains {symbol}")


_SPANS: dict[tuple[str, int], list[tuple[int, int]]] = {}


def _statement(path: str, lines: list[str], line: int) -> str:
    """The smallest ast statement span containing the cited line, for a Python
    file that parses; empty otherwise. Sorted smallest-first, as the verifier's."""
    if not path.endswith(".py"):
        return ""
    key = (path, id(lines))
    if key not in _SPANS:
        spans: list[tuple[int, int]] = []
        try:
            tree = ast.parse("\n".join(lines))
        except (SyntaxError, ValueError):
            tree = None
        for node in ast.walk(tree) if tree is not None else ():
            if isinstance(node, ast.stmt) and node.end_lineno:
                spans.append((node.lineno, node.end_lineno))
        _SPANS[key] = sorted(spans, key=lambda s: (s[1] - s[0], s[0]))
    for start, end in _SPANS[key]:
        if start <= line <= end:
            return "\n".join(lines[start - 1: end])
    return ""


def _logical(lines: list[str], line: int) -> str:
    """The cited line plus its continuation: a statement spanning several
    physical lines is cited by its first (contract, Record vocabulary)."""
    text = lines[line - 1]
    depth = _depth(text)
    index = line
    while depth > 0 and index < len(lines) and index - line < LOGICAL_LINES:
        text += "\n" + lines[index]
        depth += _depth(lines[index])
        index += 1
    return text


def _depth(text: str) -> int:
    return sum(text.count(c) for c in "([{") - sum(text.count(c) for c in ")]}")


def _symbols(record: dict) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []

    def add(item: dict | None, symbol: object) -> None:
        if item and isinstance(symbol, str) and symbol:
            out.append((item["file"], item["line"], symbol))

    for entry in record.get("entry_points") or []:
        add(entry, entry.get("name"))
    for store in record.get("stores") or []:
        add(store.get("declared_at"), (store.get("declared_at") or {}).get("symbol"))
        for item in store.get("fields") or []:
            add(item, item.get("name"))
            for cited in (item.get("erasure") or {}).get("evidence") or []:
                add(cited, cited.get("symbol"))
        for cited in (store.get("erasure") or {}).get("evidence") or []:
            add(cited, cited.get("symbol"))
    hints = record.get("hints") or {}
    for cited in (hints.get("observed_region_hints") or []) + (hints.get("security_evidence") or []):
        add(cited, cited.get("symbol"))
    return out
