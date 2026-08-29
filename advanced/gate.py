"""The human checkpoint: the block, the two questions, the decision.

10-instructions.md section 5 owns the wording, 07-ui.md sections 3 and 4 own the
`[gate]` banner around it and the lines after the keystroke. The gate fires at every
rating, prints in both modes -- "a gate that becomes invisible under automation is a
gate nobody can audit" -- and reads nothing in `--approve auto`, where every
`recipient_kind` stays `unknown` and the decision is recorded `by: "simulated"`.

Rejecting is a run outcome, not a correction channel (`gate_rejected`); EOF at the
prompt is `n`, because silence is not approval (07-ui.md section 7).

`--approve file` (ADR 0007) is the same gate with the terminal replaced by two files
under `<out_dir>/gate/`: the request this module writes, the decision it waits for.
The banner and the block still print, because the website relays this stdout and a
gate nobody can read is the one the auto mode was warned about. A decision that never
arrives is a rejection, and its note says so rather than quoting the record's title. A
decision an earlier gate left in the folder is stamped and moved aside, because an
approval belongs to the run that asked for it.
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from art30.arm import REACHING, Decision

VERDICT_COLUMN = 38
LABEL_COLUMN = 23
KINDS = ("unknown", "internal", "processor", "external_controller")
HUMAN_CELLS = (
    "  controller identity and contact, DPO, purposes, legal basis, categories of\n"
    "  data subject, transfers and safeguards, activity grouping, retention justification."
)
APPROVE = "You are approving a document you will sign. Render it? [y/N]: "
RECIPIENTS = (
    "Third-party recipients. Set a kind for each, or press enter to leave it unknown\n"
    "(unknown | internal | processor | external_controller):"
)
# 10-instructions.md section 5: `{risk_reason}` in its four shapes.
NO_ENTRY_REASON = ("no deletion entry point was found; no store in this record reaches "
                   "erasure")
HIGH_REASON = "{store} holds {article} {category} field and does not reach erasure."
MEDIUM_REASON = "every store reaches erasure, at least one only after a timer"
LOW_REASON = "every store reaches erasure directly and an entry point was found"

# ADR 0007: the file exchange. `UNROUTED` is where a caller that passes no directory
# lands, so a misrouted gate leaves its request beside the website's own runs instead
# of inside an evaluation result.
GATE_DIR = "gate"
REQUEST_NAME = "request.json"
DECISION_NAME = "decision.json"
UNROUTED = Path("results/web/unrouted")
POLL_S = 0.25
DEFAULT_TIMEOUT_S = 1800.0
TIMEOUT_VAR = "ART30_GATE_TIMEOUT"
WAITING = "[gate] waiting for {path}"
TIMED_OUT = "No decision arrived within {timeout:g} s; {path} was never written."
EDIT_KEY = "stores.<name>.recipient_kind"
# `apply_edits` (art30/render) and `Decision.human_completions` (art30/arm) both take
# the key's middle part, so a name that carries a dot has no edit key here.
DOTTED = "a store name with a dot cannot be addressed at the gate"
STALE = "  a decision was already here; moved to {path}, so this gate waits for its own"
BAD_TIMEOUT = "  {var} must be a positive number of seconds ({raw}); waiting {seconds:g} s"


def _verdict(store: dict) -> str:
    return str((store.get("erasure") or {}).get("verdict") or "")


def _words(verdict: str) -> str:
    """00-contract.md, writing contract: verdicts render as words in capitals."""
    return verdict.replace("_", " ").upper()


def risk_reason(record: dict, rating: str) -> str:
    """The rating's own trigger, quoted from 00-contract.md, Trace contract."""
    from advanced.arm import HIGH_CATEGORIES, high_store

    if rating == "high" and not (record.get("entry_points") or []):
        return NO_ENTRY_REASON
    if rating == "high":
        store = high_store(record) or {}
        field = next((f for f in store.get("fields") or []
                      if f.get("category") in HIGH_CATEGORIES), {})
        category = str(field.get("category") or "identifier")
        article = "an" if category[:1] in "aeiou" else "a"
        return HIGH_REASON.format(store=store.get("name", ""), article=article,
                                  category=category)
    return MEDIUM_REASON if rating == "medium" else LOW_REASON


def _entry_points(record: dict) -> str:
    found = [f"{e.get('name')} ({e.get('kind')}, {e.get('file')}:{e.get('line')})"
             for e in record.get("entry_points") or []]
    return ", ".join(found) if found else "none"


def _detail(store: dict) -> str:
    block = store.get("erasure") or {}
    if block.get("note"):
        return str(block["note"])
    cites = block.get("evidence") or []
    return f"{cites[0]['file']}:{cites[0]['line']}" if cites else ""


def _not_reaching(record: dict) -> list[str]:
    lines = []
    for store in record.get("stores") or []:
        if _verdict(store) in REACHING:
            continue
        head = f"  {store.get('name')} ({store.get('kind')})".ljust(VERDICT_COLUMN)
        lines.append((head + _words(_verdict(store)).ljust(LABEL_COLUMN)
                      + _detail(store)).rstrip())
    return lines


def third_party(record: dict) -> list[tuple[str, str]]:
    """`(store name, evidence)` per third-party recipient, in the record's order."""
    out = []
    for store in record.get("stores") or []:
        if store.get("kind") != "third_party":
            continue
        cite = store.get("declared_at") or {}
        where = f"{cite.get('file')}:{cite.get('line')}" if cite else "no single line"
        out.append((str(store.get("name") or ""), where))
    return out


def gate_summary(record: dict, rating: str, cross: dict | None = None) -> str:
    """The block of 10-instructions.md section 5, filled in; the trace carries it."""
    stores = record.get("stores") or []
    reaching = [s for s in stores if _verdict(s) in REACHING]
    unverified = [s for s in stores if _verdict(s) == "unverified"]
    lines = [f"RECORD READY FOR REVIEW - {record.get('repository', '')}",
             f"Risk: {rating.upper()}. {risk_reason(record, rating)}"]
    if cross is not None:                # 6.4: both ratings, and the stores that differ
        named = ", ".join(cross["stores"]) if cross["stores"] else "none"
        lines.append(f"The verifier's own rating is {cross['rating'].upper()}."
                     f" Stores the two readings differ on: {named}.")
    lines += ["",
              f"Stores: {len(stores)}   reaching erasure: {len(reaching)}"
              f"   not reaching: {len(stores) - len(reaching)}"
              f"   unverified: {len(unverified)}",
              f"Entry points: {_entry_points(record)}"]
    missing = _not_reaching(record)
    if missing:
        lines += ["", "Does not reach erasure:"] + missing
    lines += ["", "Left for you, and rendered as requires human completion:", HUMAN_CELLS]
    return "\n".join(lines)


def _ask_recipients(record: dict, say) -> dict[str, str]:
    edits: dict[str, str] = {}
    stores = third_party(record)
    if not stores:
        return edits
    say("")
    say(RECIPIENTS)
    for name, where in stores:
        if "." in name:                  # the file gate drops it too; one rule, two modes
            say(f"  {name}: {DOTTED}")
            continue
        try:
            answer = input(f"  {name} ({where}): ").strip().lower()
        except EOFError:
            answer = ""
        if answer in KINDS and answer != "unknown":
            edits[f"stores.{name}.recipient_kind"] = answer
    return edits


def human_cells() -> list[str]:
    """The cells of `HUMAN_CELLS`, one per item, for a reader that is not a terminal."""
    return [" ".join(cell.split())
            for cell in HUMAN_CELLS.strip().rstrip(".").split(",")]


def gate_request(record: dict, rating: str, summary: str) -> dict:
    """What `<out_dir>/gate/request.json` carries: the screen, in fields.

    `summary` is the text the terminal prints, verbatim, so the page, the trace and
    the terminal quote one rendering of the record rather than three.
    """
    return {
        "risk": rating,
        "summary": summary,
        "third_party": [{"store": name, "where": where, "kinds": list(KINDS)}
                        for name, where in third_party(record)],
        "human_cells": human_cells(),
        "written_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _timeout(say) -> float:
    """A wait a run can reach: `nan` fails every deadline comparison and `inf` passes
    none, so either turns the poll below into a run that never ends; zero and negative
    return before a person can answer, with a wait in the trace nobody waited."""
    raw = os.environ.get(TIMEOUT_VAR)
    if not raw:
        return DEFAULT_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        value = float("nan")
    if not math.isfinite(value) or value <= 0:
        say(BAD_TIMEOUT.format(var=TIMEOUT_VAR, raw=raw, seconds=DEFAULT_TIMEOUT_S))
        return DEFAULT_TIMEOUT_S
    return value


def _read_decision(path: Path) -> dict | None:
    """The decision, or None while the file is absent, half-written or not a decision.

    A writer mid-flush leaves bytes that do not parse; polling again is the whole
    handling, which is why malformed input is not an error here.
    """
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(found, dict) or not isinstance(found.get("approved"), bool):
        return None
    return found


def validate_edits(record: dict, raw: object, say) -> dict[str, str]:
    """The decision's `edits`, keeping only what this record can carry: an edit naming
    a store that is not a third-party recipient, or a kind outside the enum, is dropped
    with a note. The record a person signs takes no value the gate never offered them.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        say(f"  ignored edits: expected an object of {EDIT_KEY}, got {type(raw).__name__}")
        return {}
    names = {name for name, _ in third_party(record)}
    edits: dict[str, str] = {}
    head, tail = "stores.", ".recipient_kind"
    for key, value in sorted(raw.items()):
        # Prefix and suffix, not a dot count: a store is named after the identifier
        # the code carries, and a bucket constant like `s3.avatars` is a valid name.
        text = str(key)
        name = text[len(head):-len(tail)] if (
            text.startswith(head) and text.endswith(tail)) else ""
        if not name:
            say(f"  ignored {key}: the gate sets {EDIT_KEY} and nothing else")
        elif "." in name:
            say(f"  ignored {key}: {DOTTED}")
        elif name not in names:
            say(f"  ignored {key}: no third-party store named {name} in this record")
        elif value not in KINDS:
            say(f"  ignored {key}: {value} is not one of {' | '.join(KINDS)}")
        elif value != "unknown":         # the default; the ask path drops it too
            edits[f"stores.{name}.recipient_kind"] = value
    return edits


def _file_gate(record: dict, rating: str, summary: str, out_dir, say) -> Decision:
    """ADR 0007: write the request, wait for the decision, record `by: human` either way."""
    folder = Path(out_dir) / GATE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    decision_path = folder / DECISION_NAME
    if decision_path.exists():
        # `art30 scan` without `--out` resolves to a stable path per case: a second run
        # would read the first run's answer and record it `by: human`. Nothing is
        # deleted, the old decision is stamped and kept.
        stale = folder / f"{DECISION_NAME}.{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.stale"
        decision_path.replace(stale)
        say(STALE.format(path=stale))
    (folder / REQUEST_NAME).write_text(
        json.dumps(gate_request(record, rating, summary), indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    say("")
    say(WAITING.format(path=decision_path))
    timeout = _timeout(say)
    clock = time.monotonic()
    while True:
        found = _read_decision(decision_path)
        if found is not None:
            return Decision(risk=rating, approved=found["approved"], by="human",
                            summary=summary,
                            wait_s=round(time.monotonic() - clock, 3),
                            edits=validate_edits(record, found.get("edits"), say))
        if time.monotonic() - clock >= timeout:
            # The loop's `gate_rejected` note is the summary's first line, so the
            # reason a run ended without a person is the first thing in it.
            note = TIMED_OUT.format(timeout=timeout, path=decision_path)
            say(f"  {note}")
            return Decision(risk=rating, approved=False, by="human",
                            summary=f"{note}\n\n{summary}",
                            wait_s=round(time.monotonic() - clock, 3))
        time.sleep(POLL_S)


def decide(record: dict, rating: str, summary: str, approve: str,
           say=print, out_dir=UNROUTED) -> Decision:
    """07-ui.md sections 3 and 4: the banner, the block, the questions, the keystroke."""
    auto = approve not in ("ask", "file")
    say(f"\n[gate] human checkpoint · risk {rating.upper()}"
        + (" · --approve auto" if auto else ""))
    say("")
    say(summary)
    if approve == "file":
        return _file_gate(record, rating, summary, out_dir, say)
    if auto:
        say("")
        say(APPROVE + "(auto)")
        say("")
        say("  Approved without a human. Recorded as by: simulated.")
        left = ", ".join(name for name, _ in third_party(record))
        if left:
            say(f"  Recipient kinds left unknown: {left}")
        return Decision(risk=rating, approved=True, by="simulated", summary=summary,
                        wait_s=0.0, edits={})
    clock = time.monotonic()
    edits = _ask_recipients(record, say)
    say("")
    try:
        answer = input(APPROVE).strip().lower()
    except EOFError:                     # silence is not approval (07-ui.md section 7)
        answer = "n"
    return Decision(risk=rating, approved=answer in ("y", "yes"), by="human",
                    summary=summary, wait_s=round(time.monotonic() - clock, 3),
                    edits=edits)
