"""The human checkpoint: the block, the two questions, the decision.

10-instructions.md section 5 owns the wording, 07-ui.md sections 3 and 4 own the
`[gate]` banner around it and the lines after the keystroke. The gate fires at every
rating, prints in both modes -- "a gate that becomes invisible under automation is a
gate nobody can audit" -- and reads nothing in `--approve auto`, where every
`recipient_kind` stays `unknown` and the decision is recorded `by: "simulated"`.

Rejecting is a run outcome, not a correction channel (`gate_rejected`); EOF at the
prompt is `n`, because silence is not approval (07-ui.md section 7).
"""

from __future__ import annotations

import time

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
        try:
            answer = input(f"  {name} ({where}): ").strip().lower()
        except EOFError:
            answer = ""
        if answer in KINDS and answer != "unknown":
            edits[f"stores.{name}.recipient_kind"] = answer
    return edits


def decide(record: dict, rating: str, summary: str, approve: str,
           say=print) -> Decision:
    """07-ui.md sections 3 and 4: the banner, the block, the questions, the keystroke."""
    auto = approve != "ask"
    say(f"\n[gate] human checkpoint · risk {rating.upper()}"
        + (" · --approve auto" if auto else ""))
    say("")
    say(summary)
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
