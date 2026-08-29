"""What an arm sees and what it returns: the protocol, its two payloads, and
the record validation both arms run.

The `Arm` protocol, `Feedback`, `Decision` and `RunCtx` are listed under
`art30/loop.py` in 01-architecture.md section 1.3. They live here instead
because both arms import them and the loop does not: an arm package importing
the loop it is passed to reads backwards, and the ~300-line rule leaves the
loop no room for the ten handler invariants of 04-output-schema.md section 4,
which run in the submit handler of both arms and have no other home.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal, Protocol

from jsonschema import Draft202012Validator

from art30.config import Config
from art30.tools import ToolCtx, format_schema_errors, record_schema
from art30.trace import Trace

REACHING = frozenset({"erased", "erased_after_timer", "anonymised"})
NEEDS_EVIDENCE = REACHING | {"pseudonymised", "governed_by_retention"}
TIMED = frozenset({"erased_after_timer", "governed_by_retention"})
BACKUP_VERDICTS = frozenset({"governed_by_retention", "no_schedule_evidenced"})
KIND_KEEPS_VERDICT = frozenset({"backup", "third_party"})

# 04-output-schema.md I10: the vocabulary of a legal conclusion, which the
# renderer would otherwise print verbatim out of a model-written note.
LEGAL = re.compile(
    r"complian|unlawful|lawful|legal basis|legitimate interest"
    r"|consent of the data subject|Article \d+ (?:is|has been) (?:met|satisfied)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Feedback:
    accepted: bool
    attempt: int = 0
    attempts_left: int = 0
    schema_errors: list[str] = field(default_factory=list)
    rejected_claims: list[dict] = field(default_factory=list)
    missing_stores: list[dict] = field(default_factory=list)
    missing_entry_points: list[dict] = field(default_factory=list)
    bad_citations: list[dict] = field(default_factory=list)
    unverified: list[dict] = field(default_factory=list)
    conservative_divergences: list[dict] = field(default_factory=list)

    def to_tool_result(self) -> str:
        """Canonical JSON with every empty list dropped.

        One dataclass serialised one way would put six verifier-only key names
        into the baseline's only model-visible channel (01 section 1.3).
        """
        if self.accepted:
            return json.dumps({"accepted": True}, separators=(",", ":"))
        payload: dict = {
            "accepted": False,
            "attempt": self.attempt,
            "attempts_left": self.attempts_left,
        }
        for name in (
            "schema_errors",
            "rejected_claims",
            "missing_stores",
            "missing_entry_points",
            "bad_citations",
            "unverified",
            "conservative_divergences",
        ):
            items = getattr(self, name)
            if items:
                payload[name] = items
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class Decision:
    risk: Literal["low", "medium", "high"]
    approved: bool
    by: Literal["human", "simulated"]
    summary: str
    wait_s: float = 0.0
    edits: dict[str, str] = field(default_factory=dict)

    def human_completions(self) -> dict | None:
        """`{"recipient_kind": {store: value}}`, or None when nothing was filled."""
        kinds = {
            key.split(".")[1]: value
            for key, value in sorted(self.edits.items())
            if key.startswith("stores.") and key.endswith(".recipient_kind")
        }
        return {"recipient_kind": kinds} if kinds else None


@dataclass
class RunCtx:
    case: str
    arm: str
    seed: int
    root: Path
    tools: ToolCtx
    trace: Trace
    cfg: Config
    tool_calls: int = 0
    submits: int = 0
    verify_rounds: int = 0
    cost_cum_usd: float = 0.0
    accepted: dict | None = None
    # Every rejection, in order, for `verification.rejected_history` (04 section 5).
    rejections: list[dict] = field(default_factory=list)


class Arm(Protocol):
    name: str

    def tools(self) -> tuple[dict, ...]: ...

    def handle_submit(self, record: dict, ctx: RunCtx) -> Feedback: ...

    def gate(self, record: dict, ctx: RunCtx) -> Decision | None: ...


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(record_schema())


def validate(record: dict) -> list[str]:
    """Schema errors, then the ten handler invariants, sorted by JSON pointer.

    The invariants read a record that already has the schema's shape, so a
    malformed submission gets the cheap answer and no traceback.
    """
    errors = format_schema_errors(_validator().iter_errors(record))
    return errors if errors else sorted(invariants(record))


def norm(name: str) -> str:
    """Lowercase, non-alphanumerics to `_`, collapsed, singular.

    The scorer's `norm` carries the manifest's app prefixes as well; nothing
    inside `art30` may import the eval harness, so the shared half is repeated.
    """
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return base[:-1] if base.endswith("s") and len(base) > 3 else base


def invariants(record: dict) -> list[str]:
    """I1-I10 of 04-output-schema.md section 4; strings from 10 section 4.6."""
    out: list[str] = []
    stores = record.get("stores") or []
    names = [store.get("name", "") for store in stores]
    no_entry_points = not (record.get("entry_points") or [])
    seen: set[str] = set()
    for i, store in enumerate(stores):
        block = f"/stores/{i}/erasure"
        kind = store.get("kind")
        erasure = store.get("erasure") or {}
        if not store.get("fields"):
            out.append(f"/stores/{i}: a store with no personal-data field does not belong in the record")
        if no_entry_points and kind not in KIND_KEEPS_VERDICT:
            if erasure.get("verdict") != "no_entry_point":
                out.append(
                    f"{block}/verdict: entry_points is empty, so every store that is not a"
                    " backup or a third_party recipient takes verdict no_entry_point"
                )
        key = norm(store.get("name", ""))
        if key in seen:
            out.append(f"/stores/{i}/name: duplicate store name after normalisation")
        seen.add(key)
        out += _erasure(erasure, block, kind)
        field_keys: set[str] = set()
        for j, item in enumerate(store.get("fields") or []):
            fkey = norm(item.get("name", ""))
            if fkey in field_keys:
                out.append(f"/stores/{i}/fields/{j}/name: duplicate field name after normalisation")
            field_keys.add(fkey)
            override = item.get("erasure")
            if not override:
                continue
            fblock = f"/stores/{i}/fields/{j}/erasure"
            out += _erasure(override, fblock, kind)
            if override.get("verdict") == erasure.get("verdict"):
                out.append(
                    f"{fblock}/verdict: a field-level erasure block records a fate that differs"
                    " from its store's; this one repeats it"
                )
    out += _retention(record.get("retention") or [], names)
    out += _citations(record)
    out += _legal_vocabulary(record)
    return out


def _erasure(block: dict, pointer: str, kind: str | None) -> list[str]:
    out: list[str] = []
    verdict = block.get("verdict")
    timer = block.get("timer_days")
    if verdict in NEEDS_EVIDENCE and not block.get("evidence"):
        out.append(f"{pointer}/evidence: verdict {verdict} needs at least one cited line")
    if verdict in TIMED and timer is None:
        out.append(f"{pointer}/timer_days: {verdict} needs the timer you cited")
    if verdict not in TIMED and timer is not None:
        out.append(f"{pointer}/timer_days: only erased_after_timer and governed_by_retention carry a timer")
    if kind == "backup" and verdict not in BACKUP_VERDICTS:
        out.append(f"{pointer}/verdict: a backup store takes governed_by_retention or no_schedule_evidenced")
    if kind != "backup" and verdict in BACKUP_VERDICTS:
        out.append(f"{pointer}/verdict: {verdict} is only for a store of kind backup")
    return out


def _retention(items: list[dict], store_names: list[str]) -> list[str]:
    known = {norm(name) for name in store_names}
    out: list[str] = []
    for i, item in enumerate(items):
        if item.get("days") is None and not item.get("criteria"):
            out.append(f"/retention/{i}: needs days or criteria")
        if item.get("file") is None or item.get("line") is None:
            out.append(f"/retention/{i}: needs a file and a line")
        if norm(item.get("store", "")) not in known:
            out.append(f"/retention/{i}/store: names no store in this record")
        days = item.get("days")
        if isinstance(days, int) and days < 0:
            out.append(f"/retention/{i}/days: a retention period is a whole number of days, not negative")
    return out


def _citations(record: dict) -> list[str]:
    out: list[str] = []
    for pointer, cite in _cited(record):
        path = cite.get("file")
        if isinstance(path, str) and (path.startswith("/") or ".." in Path(path).parts):
            out.append(f"{pointer}: paths are repository-relative, with no leading / and no ..")
        line = cite.get("line")
        if isinstance(line, int) and line < 1:
            out.append(f"{pointer}/line: line numbers are 1-based")
    return out


def _cited(record: dict) -> list[tuple[str, dict]]:
    """Every object in the record carrying a `file` and a `line`, with its pointer."""
    found: list[tuple[str, dict]] = []
    for i, subject in enumerate(record.get("data_subjects") or []):
        found.append((f"/data_subjects/{i}", subject))
    for i, entry in enumerate(record.get("entry_points") or []):
        found.append((f"/entry_points/{i}", entry))
    for i, store in enumerate(record.get("stores") or []):
        for key in ("declared_at", "subject_link"):
            if store.get(key):
                found.append((f"/stores/{i}/{key}", store[key]))
        for j, item in enumerate(store.get("fields") or []):
            found.append((f"/stores/{i}/fields/{j}", item))
            found += _evidence(item.get("erasure") or {}, f"/stores/{i}/fields/{j}/erasure")
        found += _evidence(store.get("erasure") or {}, f"/stores/{i}/erasure")
    hints = record.get("hints") or {}
    for key in ("observed_region_hints", "security_evidence"):
        for i, cite in enumerate(hints.get(key) or []):
            found.append((f"/hints/{key}/{i}", cite))
    return found


def _evidence(block: dict, pointer: str) -> list[tuple[str, dict]]:
    return [(f"{pointer}/evidence/{i}", cite) for i, cite in enumerate(block.get("evidence") or [])]


def _legal_vocabulary(record: dict) -> list[str]:
    out: list[str] = []
    for pointer, text in _model_strings(record):
        match = LEGAL.search(text)
        if match:
            out.append(f'{pointer}: this record states no legal conclusion; remove "{match.group(0)}"')
    return out


def _model_strings(record: dict) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []

    def add(pointer: str, value: object) -> None:
        if isinstance(value, str) and value:
            found.append((pointer, value))

    for i, subject in enumerate(record.get("data_subjects") or []):
        add(f"/data_subjects/{i}/label", subject.get("label"))
    for i, entry in enumerate(record.get("entry_points") or []):
        add(f"/entry_points/{i}/note", entry.get("note"))
    for i, store in enumerate(record.get("stores") or []):
        add(f"/stores/{i}/note", store.get("note"))
        add(f"/stores/{i}/erasure/note", (store.get("erasure") or {}).get("note"))
        for j, item in enumerate(store.get("fields") or []):
            add(f"/stores/{i}/fields/{j}/note", item.get("note"))
            add(f"/stores/{i}/fields/{j}/erasure/note", (item.get("erasure") or {}).get("note"))
    for i, item in enumerate(record.get("retention") or []):
        add(f"/retention/{i}/criteria", item.get("criteria"))
    return found
