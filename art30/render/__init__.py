"""The render package: the shared vocabulary, and the three files one run writes.

`render_all` writes `record.json` first, so an accepted record survives a
citation that the Markdown or the HTML render then refuses (02-agent-loop.md
section 1, `render_failed`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from art30.tools import EXCLUDED_DIRS

HUMAN = "requires human completion"

KIND_ORDER = (
    "relational",
    "object_storage",
    "cache",
    "search_index",
    "queue",
    "log",
    "backup",
    "third_party",
)
CATEGORY_ORDER = (
    "identifier",
    "contact",
    "financial",
    "behavioural",
    "free_text_may_contain",
    "technical",
)
# The schema's enum, with the seven verdicts that do not reach erasure first:
# a reader who stops after four rows has read the ones that matter (04 section 6 D).
VERDICT_ORDER = (
    "pseudonymised",
    "not_erased",
    "external_manual",
    "no_entry_point",
    "governed_by_retention",
    "no_schedule_evidenced",
    "unverified",
    "erased",
    "erased_after_timer",
    "anonymised",
)
TIMED = ("erased_after_timer", "governed_by_retention")


class RenderError(RuntimeError):
    """A cited line no longer carries its symbol. `record.json` is already on disk."""

    def __init__(self, message: str, record_path: str | None = None) -> None:
        super().__init__(message)
        self.record_path = record_path


@dataclass(frozen=True)
class Paths:
    json: str
    md: str
    html: str


def words(value: str) -> str:
    return str(value).replace("_", " ")


def cite(item: dict | None) -> str:
    return f"`{item['file']}:{item['line']}`" if item else "—"


def verdict_text(block: dict) -> str:
    text = words(block.get("verdict")).upper()
    if block.get("verdict") in TIMED and block.get("timer_days") is not None:
        text += f" ({block['timer_days']} days)"
    return text


def table(header: Iterable[str], rows: Iterable[Iterable[str]]) -> list[str]:
    cells = list(header)
    out = ["| " + " | ".join(cells) + " |", "|" + "---|" * len(cells)]
    return out + ["| " + " | ".join(row) + " |" for row in rows]


def ordered_stores(record: dict) -> list[dict]:
    """Section A's order: the stores a founder recognises first, then by name."""
    return sorted(record.get("stores") or [], key=lambda s: (KIND_ORDER.index(s["kind"]), s["name"]))


def erasure_rows(stores: list[dict]) -> list[dict]:
    return sorted(stores, key=lambda s: (VERDICT_ORDER.index(s["erasure"]["verdict"]), s["name"]))


def render_all(record: dict, out_dir: Path, repo_root: Path) -> Paths:
    """`record.json`, then `record.md`, then `record.html`, in that order."""
    from art30.render.html import render_html
    from art30.render.markdown import render_markdown

    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "record.json"
    target.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    kept = str(target)
    try:  # both documents are rendered before either is written: a refused
        text = render_markdown(record)  # citation leaves no half-written pair
        page = render_html(record, repo_root)
    except RenderError as exc:
        raise RenderError(str(exc), record_path=kept) from None
    (directory / "record.md").write_text(text, encoding="utf-8")
    (directory / "record.html").write_text(page, encoding="utf-8")
    return Paths(json=kept, md=str(directory / "record.md"), html=str(directory / "record.html"))


def write_draft(record: dict, out_dir: Path) -> str:
    """The gate-rejected record. Scored as `f1_draft` (05-eval-harness.md section 4.2)."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "record.draft.json"
    target.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return str(target)


def stamp() -> str:
    """Seconds-resolution UTC, the shape `provenance` carries (04 section 5)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def relative(root: Path) -> str:
    """No absolute path reaches an artefact; a path outside the tree is its name."""
    try:
        return str(Path(root).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return Path(root).name


def tree_sha(root: Path) -> str:
    """First twelve hex of a sha over the fixture tree, sorted, paths included."""
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*")):
        if path.is_file() and not any(part in EXCLUDED_DIRS for part in path.parts):
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def apply_edits(record: dict, edits: dict[str, str]) -> dict:
    """`stores.<name>.recipient_kind` - the one cell the human sets at the gate."""
    if not edits:
        return record
    updated = json.loads(json.dumps(record))
    for key, value in edits.items():
        parts = key.split(".")
        if len(parts) == 3 and parts[0] == "stores":
            for store in updated.get("stores") or []:
                if store.get("name") == parts[1]:
                    store[parts[2]] = value
    return updated


def _citation_index(record: dict, stores: list[dict]) -> dict[tuple[str, int], dict]:
    """Every citation on the page, with the symbols and the sections that used it."""
    index: dict[tuple[str, int], dict] = {}

    def add(item: dict | None, section: str, symbol: str | None = None) -> None:
        if not item or item.get("file") is None or item.get("line") is None:
            return
        entry = index.setdefault((item["file"], item["line"]), {"symbols": [], "sections": []})
        name = symbol if symbol is not None else item.get("symbol")
        if name and name not in entry["symbols"]:
            entry["symbols"].append(name)
        if section not in entry["sections"]:
            entry["sections"].append(section)

    # A label, a store name and a retention criteria are not symbols on the
    # cited line (04 section 6 H), so those rows carry the line and no symbol.
    for subject in record.get("data_subjects") or []:
        add(subject, "A")
    for entry in record.get("entry_points") or []:
        add(entry, "D", entry.get("name"))
    for store in stores:
        add(store.get("declared_at"), "A")
        add(store.get("subject_link"), "A")
        for item in store.get("fields") or []:
            add(item, "A", item["name"])
            if store["kind"] == "third_party":
                add(item, "B", item["name"])
            for evidence in (item.get("erasure") or {}).get("evidence") or []:
                add(evidence, "D")
        for evidence in store["erasure"].get("evidence") or []:
            add(evidence, "D")
    for item in record.get("retention") or []:
        add(item, "C")
    hints = record.get("hints") or {}
    for cited in (hints.get("observed_region_hints") or []) + (hints.get("security_evidence") or []):
        add(cited, "E")
    return index


def _evidence_rows(index: dict[tuple[str, int], dict]) -> list[str]:
    rows = [
        (
            f"`{path}:{line}`",
            ", ".join(f"`{s}`" for s in entry["symbols"]) or "—",
            ", ".join(sorted(entry["sections"])),
        )
        for (path, line), entry in sorted(index.items())
    ]
    return ["## H. Evidence index", ""] + table(("Evidence", "Symbol", "Sections"), rows) + [""]


def evidence_index(record: dict, stores: list[dict]) -> list[str]:
    """Section H: every citation in the document, sorted by path then line."""
    return _evidence_rows(_citation_index(record, stores))
