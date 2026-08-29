"""The feedback object's strings, and the order it leaves in.

`10-instructions.md` section 4 owns every sentence here and `03-verifier.md` 7.5
owns every sort key; nothing in this module invents a phrase or reads a rule file.
`check.py` decides which item to build, this module decides how it reads, so a
wording change is one file and a rule change is the other.

The `{detail}` clause of 4.1 is a closed set, one entry per rule the check failed,
and every probe below is guarded on the fact that actually decided the store: a
probe that fired on a store the search did reach would put a false sentence in
front of the model, which costs an attempt for the tool's own mistake. Where no
probe applies the verifier's own note is used verbatim rather than a guess.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from art30.verify.findings import Store

if TYPE_CHECKING:                       # `check.py` owns 7.1-7.4, this module the strings
    from art30.verify.reach import Reach
    from art30.verify.verdicts import Verdict

# 10-instructions.md 4.1: the store kind's deletion primitive, in the contract's own
# words. `log` and `backup` are outside that closed set of six, so they take a phrase
# that names no primitive rather than one this file made up (reported as a deviation).
PRIMITIVE = {
    "relational": "any relational row-deletion primitive",
    "object_storage": "any object-storage deletion primitive",
    "cache": "any cache deletion primitive",
    "search_index": "any search-index deletion primitive",
    "queue": "any queue purge",
    "third_party": "any vendor deletion call",
}
DEFAULT_PRIMITIVE = "any deletion primitive for this store"

# 10-instructions.md 4.1, 4.2, 4.2a, 4.4, 4.4a: the templates, verbatim.
NO_PATH = "no path from entry point {name} ({file}:{line}) to {primitive}; {detail}"
NO_ENTRY = ("no entry point exists in this repository, so nothing reaches "
            "{primitive}; {detail}")
EXPECT_VERDICT = "verdict {suggested}, or cite the path"
EXPECT_UNVERIFIED = "verdict unverified, or cite the path"
MISSING_STORE = ("add store {store} (kind {kind}) with its personal-data fields "
                 "and an erasure verdict")
MISSING_ENTRY = "declare {name} as an entry point, or say in its note why it is not one"
UNVERIFIED_REASON = ("{symbol} at {file}:{line} resolves through {mechanism}; the path "
                     "cannot be decided from the source")
UNVERIFIED_EXPECT = ("verdict unverified for {store}, or cite a path that does not pass "
                     "through {mechanism}")
DIVERGENCE_NOTE = "accepted; the record is more conservative than the evidence"

# 10-instructions.md 4.2: the verb the evidence phrase uses, per store kind.
VERB = {"relational": "writes", "object_storage": "uploads", "cache": "writes",
        "search_index": "indexes", "queue": "enqueues", "third_party": "sends",
        "log": "logs", "backup": "backs up"}

# 10-instructions.md 4.4: `{mechanism}` is a closed set. Only the rules that name one
# unambiguously are mapped; anything else keeps the verifier's own sentence.
MECHANISM = {"R27": "an unmodelled decorator", "R19": "raw SQL",
             "03-verifier.md 1.5": "a callable passed as an argument"}
# R27, R19 and 1.5 each name one shape; R26 names two, and both are `downgrades.py`'s
# most frequent rows, so they are told apart on the note that file already fixed
# (`downgrades.py:86` and `:114`) rather than on the bare rule id. Both replacements are
# inside 4.4's closed set, which the three above leave two members short.
NOTE_MECHANISM = (("ambiguous call", "two definitions of the same name"),
                  ("opaque call", "getattr"))


def _short(name: str) -> str:
    return str(name).rsplit(":", 1)[-1].rsplit(".", 1)[-1]


def primitive_words(kind: str) -> str:
    return PRIMITIVE.get(kind, DEFAULT_PRIMITIVE)


def path_cites(verdict: "Verdict") -> list[dict]:
    """7.3: the structured walk, each element `{file, line, symbol}`, order preserved."""
    return [{"file": step["file"], "line": step["line"], "symbol": _short(step["to"])}
            for step in verdict.path]


# ---------------------------------------------------------------------------
# 4.1's `{detail}`: one probe per rule, in the table's own order
# ---------------------------------------------------------------------------
def _reached(reach: "Reach", store: Store) -> bool:
    return reach.reached(store.node, resolved_only=True) is not None


def _r26(reach: "Reach", store: Store, verdict: "Verdict") -> str:
    """R26: the primitive exists and its owner is called by nothing (the S10 shape)."""
    if _reached(reach, store):
        return ""
    called = {edge.dst for edge in reach.graph.edges if edge.kind == "call"}
    for primitive in sorted(store.primitives, key=lambda p: (p["file"], p["line"])):
        owner = str(primitive.get("caller") or "")
        symbol = reach.graph.symbols.get(owner)
        if symbol is None or owner in called:
            continue
        return f"{symbol.short} ({symbol.file}:{symbol.line}) is defined but has no callers"
    return ""


def _r25(reach: "Reach", store: Store, verdict: "Verdict") -> str:
    """R25: a soft-delete marker is the only write the erasure path makes."""
    from art30.verify import timers

    if verdict.verdict == "erased_after_timer":
        return ""                       # the marker is half of a verdict, not a failure
    marks = timers.markers(reach, store)
    if not marks:
        return ""
    first = marks[0]
    return (f"the only write on the path is {first['symbol']} "
            f"({first['file']}:{first['line']}), which sets a flag")


def _r9(reach: "Reach", store: Store, verdict: "Verdict") -> str:
    """R9 [S6]: every receiver names a different sender than this store's model."""
    if not store.model or _reached(reach, store):
        return ""
    receivers = sorted(reach.graph.receivers, key=lambda r: (r.file, r.line, r.symbol))
    if not receivers or any(r.sender is None or r.sender == store.model for r in receivers):
        return ""
    first = receivers[0]
    return (f"the receiver at {first.file}:{first.line} has sender="
            f"{_short(first.sender)}, not {_short(store.model)}")


def _r8(reach: "Reach", store: Store, verdict: "Verdict") -> str:
    """R8 [S1] [S2]: a file field behind a row cascade; the row goes, the file stays."""
    if "django_file_field" not in store.flags or store.declared_at is None:
        return ""
    return (f"{store.id} ({store.declared_at.file}:{store.declared_at.line}) is a file "
            "field; a row cascade does not delete the file")


def _relations(reach: "Reach", store: Store) -> list:
    row = reach.graph.store_for_model(store.model or "") if store.model else None
    wanted = {store.id} | ({row.id} if row is not None else set())
    return sorted((r for r in reach.graph.relations if r.child in wanted),
                  key=lambda r: (r.file, r.line))


def _r4(reach: "Reach", store: Store, verdict: "Verdict") -> str:
    """R4 [S1] [S3]: DB_CASCADE removes the row and sends no delete signal."""
    for relation in _relations(reach, store):
        if relation.token.upper() == "DB_CASCADE":
            return (f"{_short(relation.child)}.{relation.field_name} ({relation.file}:"
                    f"{relation.line}) is DB_CASCADE, so no delete signal is sent")
    return ""


def _r5(reach: "Reach", store: Store, verdict: "Verdict") -> str:
    """R5 [S15]: a `cascade=` string with no `delete` and no `all` token."""
    if _reached(reach, store):
        return ""
    for relation in _relations(reach, store):
        if relation.kind != "relationship" or not relation.token:
            continue
        if not reach.rules.cascade_is_delete(relation.token):
            return (f'cascade at {relation.file}:{relation.line} is "{relation.token}": '
                    "no delete token")
    return ""


def _r2(reach: "Reach", store: Store, verdict: "Verdict") -> str:
    """R2 [S1]: a non-cascading `on_delete`; the row survives with its columns."""
    if _reached(reach, store):
        return ""
    for relation in _relations(reach, store):
        token = relation.token.upper()
        if token in {"SET_NULL", "SET_DEFAULT", "SET", "DO_NOTHING"}:
            return (f"{_short(relation.child)}.{relation.field_name} ({relation.file}:"
                    f"{relation.line}) is {token}; the row survives")
    return ""


def _r22(reach: "Reach", store: Store, verdict: "Verdict") -> str:
    """R22 [S28] [S29]: a deleted Stripe customer is still retrievable."""
    if store.kind != "third_party" or "recipient:stripe" not in store.flags:
        return ""
    return "a Stripe customer delete does not erase the customer at Stripe"


PROBES = (_r26, _r25, _r9, _r8, _r4, _r5, _r2, _r22)


def detail(reach: "Reach", store: Store, verdict: "Verdict") -> str:
    """4.1's closed set, first match wins; the verifier's own note where none fires."""
    for probe in PROBES:
        found = probe(reach, store, verdict)
        if found:
            return found
    return verdict.note or "nothing in the repository shows this store being erased"


# ---------------------------------------------------------------------------
# the items
# ---------------------------------------------------------------------------
def no_path_reason(reach: "Reach", store: Store, verdict: "Verdict") -> str:
    """4.1: the template the contract's own example renders, filled in."""
    words = primitive_words(store.kind)
    text = detail(reach, store, verdict)
    entry = reach.starts[0] if reach.starts else (reach.entries[0] if reach.entries else None)
    if entry is None:
        return NO_ENTRY.format(primitive=words, detail=text)
    return NO_PATH.format(name=entry.name, file=entry.file, line=entry.line,
                          primitive=words, detail=text)


def rejected(store: str, field: str | None, claim: str, reason: str,
             path: list[dict], expected: str) -> dict:
    return {"store": store, "field": field, "claim": claim, "reason": reason,
            "path": path, "expected": expected}


def missing_store(store: str, kind: str, evidence: str) -> dict:
    return {"store": store, "kind": kind, "evidence": evidence,
            "expected": MISSING_STORE.format(store=store, kind=kind)}


def missing_entry(name: str, file: str, line: int, kind: str) -> dict:
    return {"name": name, "file": file, "line": int(line), "kind": kind,
            "expected": MISSING_ENTRY.format(name=name)}


def unverified(store: str, claim: str, reason: str, expected: str) -> dict:
    return {"store": store, "claim": claim, "reason": reason, "expected": expected}


def unresolved(store: str, claim: str, verdict: "Verdict") -> dict:
    """4.4, where a rule names the mechanism; the verifier's own note where none does."""
    note = verdict.note or ""
    mechanism = next((words for phrase, words in NOTE_MECHANISM if phrase in note), "")
    if not mechanism:
        mechanism = next((MECHANISM[r] for r in sorted(verdict.reasons)
                          if r in MECHANISM), "")
    cite = verdict.evidence[0] if verdict.evidence else None
    if mechanism and cite:
        return unverified(store, claim,
                          UNVERIFIED_REASON.format(symbol=cite.get("symbol") or store,
                                                   file=cite["file"], line=cite["line"],
                                                   mechanism=mechanism),
                          UNVERIFIED_EXPECT.format(store=store, mechanism=mechanism))
    return unverified(store, claim, note,
                      f"keep the verdict, or cite a path the verifier can resolve for {store}")


def divergence(store: str, claim: str, verifier: str) -> dict:
    return {"store": store, "claim": claim, "verifier": verifier, "note": DIVERGENCE_NOTE}


def verifier_phrase(reach: "Reach", verdict: "Verdict") -> str:
    """4.4a's `"{verdict} via {mechanism} {file}:{line}"`, read off the walk."""
    step = verdict.path[-1] if verdict.path else None
    if step is not None:
        for relation in reach.graph.relations:
            if relation.file == step["file"] and relation.line == step["line"] and relation.token:
                return (f"{verdict.verdict} via on_delete={relation.token} "
                        f"{step['file']}:{step['line']}")
        return f"{verdict.verdict} via {step['rule']} {step['file']}:{step['line']}"
    if verdict.evidence:
        cite = verdict.evidence[0]
        return (f"{verdict.verdict} via {cite.get('symbol') or verdict.store} "
                f"{cite['file']}:{cite['line']}")
    return f"{verdict.verdict}, with no citable line"


# ---------------------------------------------------------------------------
# 7.5: every list leaves in one order
# ---------------------------------------------------------------------------
SORT = {
    "rejected_claims": lambda i: (i["store"], i["field"] or "", i["claim"]),
    "unverified": lambda i: (i["store"], i["claim"]),
    "missing_stores": lambda i: (i["store"],),
    "missing_entry_points": lambda i: (i["file"], i["line"], i["name"]),
    "bad_citations": lambda i: (i["file"], i["line"], i["symbol"]),
    "conservative_divergences": lambda i: (i["store"], i["claim"]),
}


def ordered(name: str, items: list[dict]) -> list[dict]:
    return sorted(items, key=SORT[name])
