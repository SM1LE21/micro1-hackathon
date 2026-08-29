"""The two caps of 6.1, and the 4.8 reading they rest on (03-verifier.md 4.8, 6.1).

"Two caps sit above the table and are applied after it. A store whose only path starts
at a `declared_unregistered` entry point (2.5) is `unverified` whatever row fired. A
store reached only through the parent delete of a disqualified two-step `PROTECT` idiom
(4.8) is `unverified` likewise. Both replace a reaching verdict with a conservative one
and never the other way round."

Split from `downgrades.py`, which owns row 8's reasons and row 9's note, to keep both
files inside the 300-line rule. Nothing here can raise a verdict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from art30.verify.downgrades import call_at, restrict_with_cascade_sibling
from art30.verify.findings import EntryPoint, Store
from art30.verify.rules import norm

if TYPE_CHECKING:                       # `verdicts.py` owns 6.1, `reach.py` the walk
    from art30.verify.reach import Path, Reach
    from art30.verify.verdicts import Verdict


def blocking_relations(reach: "Reach", store: Store) -> list:
    """The relations whose parent delete raises while this child still has rows.

    `PROTECT` always. `RESTRICT` "behaves as `PROTECT` with one documented exception"
    (R3b [S1]) -- deletion is allowed where the child also references a different
    object being deleted in the same operation via `CASCADE` -- so it joins the list
    only where that shape is absent. Where it is present R3b's own `unverified` row in
    `unverified_reason` decides the child and the parent delete is not shown to raise.
    """
    out = [r for r in reach.graph.relations
           if r.child == store.id and norm(r.token) == "protect"]
    restrict = [r for r in reach.graph.relations
                if r.child == store.id and norm(r.token) == "restrict"]
    if restrict and not restrict_with_cascade_sibling(reach, store):
        out += restrict
    return sorted(out, key=lambda r: (r.file, r.line, r.field_name))   # 7.5


def error_name(reach: "Reach", store: Store) -> str:
    """The exception Django raises for the token that blocks: R3a's or R3b's [S1]."""
    tokens = {norm(r.token) for r in blocking_relations(reach, store)}
    return "RestrictedError" if tokens == {"restrict"} else "ProtectedError"


def protect_state(reach: "Reach", store: Store) -> str:
    """4.8: the two-step PROTECT idiom, read through the child delete's predicate."""
    relations = blocking_relations(reach, store)
    if not relations:
        return ""
    hit = reach.reached(store.node, resolved_only=True)
    if hit is None:
        return "absent"
    last = hit[1].steps[-1]
    for name in ("filter", "exclude"):
        site = call_at(reach, last.file, last.line, name)
        if site is not None and any(arg.kind == "literal"
                                    for arg in site.keywords.values()):
            return "disqualified"           # drafts only: paid invoices survive
    return "qualified"


def only_declared(reach: "Reach", evidence: list[str]) -> "EntryPoint | None":
    """2.5: the evidence is reachable only from a `declared_unregistered` start node.

    `hit` is None for every verdict 4.7 or 6.2 decided, so a cap read off `hit` alone
    did not apply to rows 5, 6 and 7 and a record that declares an unregistered helper
    -- `blank_user`, called by nothing, registered by nothing -- was handed back
    `anonymised` with `reaches_erasure = true`. 2.5 is categorical ("every verdict
    derived from it is `unverified`, never `erased`, `erased_after_timer` or
    `anonymised`") and 6.1 says the cap holds "whatever row fired".
    """
    if not evidence:
        return None
    capped = [e for e in reach.starts if "declared_unregistered" in (e.flags or [])]
    if not capped:
        return None
    for entry in reach.starts:
        if "declared_unregistered" in (entry.flags or []):
            continue
        if any(symbol in reach.walk(entry, True) for symbol in evidence):
            return None                  # an uncorroborated start reaches it too
    for entry in capped:
        if any(symbol in reach.walk(entry, True) for symbol in evidence):
            return entry
    return None


def cap(reach: "Reach", store: Store, verdict: "Verdict",
        hit: "tuple[EntryPoint, Path] | None",
        evidence: list[str] | None = None) -> "Verdict":
    """The two caps of 6.1, applied after the table and only downwards."""
    from art30.verify.verdicts import REACHES_ERASURE

    if verdict.verdict not in REACHES_ERASURE:
        return verdict
    declared = (hit[0] if hit is not None and "declared_unregistered" in (hit[0].flags or [])
                else None)
    if declared is None and hit is None:
        declared = only_declared(reach, list(evidence or ()))
    if declared is not None:                              # 2.5, whatever row fired
        verdict.verdict, verdict.timer_days = "unverified", None
        verdict.reasons = sorted(set(verdict.reasons) | {"03-verifier.md 2.5"})
        verdict.note = (f"the only path starts at {declared.name}, declared but not seen "
                        "registered as externally invocable")
        return verdict
    through = {step.dst for step in (hit[1].steps if hit else ())} | {store.node}
    blocked = reach.protect_parents() & through
    branch = protect_state(reach, store)
    if branch != "disqualified" and not blocked:
        return verdict
    note, rule = _cap_reason(reach, store, branch, blocked)
    verdict.verdict, verdict.timer_days = "unverified", None
    verdict.reasons = sorted(set(verdict.reasons) | {rule, "03-verifier.md 4.8"})
    verdict.note = note
    return verdict


def _cap_reason(reach: "Reach", store: Store, branch: str,
                blocked: set[str]) -> tuple[str, str]:
    """4.8's two branches read differently, so the note has to say which one fired.

    `disqualified` is the filtered child delete ("drafts only"); `absent` is the bare
    parent delete with nothing emptying the child at all, and it is the branch
    `protect_parents` used not to collect -- which produced a record saying in one row
    that the delete raises and in the next that the account row is gone.
    """
    if branch == "disqualified":
        error = error_name(reach, store)
        rule = "R3b" if error == "RestrictedError" else "R3a"
        return (f"a filtered child delete leaves rows behind, so the parent delete may "
                f"raise {error}", rule)
    for child in _blocked_children(reach, blocked):
        error = error_name(reach, child)
        rule = "R3b" if error == "RestrictedError" else "R3a"
        token = norm(blocking_relations(reach, child)[0].token).upper()
        return (f"nothing empties the {token} child {child.id} first, so the parent "
                f"delete may raise {error}", rule)
    return ("a child the parent cannot be deleted past is not emptied first, so the "
            "parent delete may raise ProtectedError", "R3a")


def _blocked_children(reach: "Reach", blocked: set[str]) -> list[Store]:
    """The un-emptied children of the parents this store's path runs through, sorted."""
    out: list[Store] = []
    for relation in sorted(reach.graph.relations, key=lambda r: (r.file, r.line)):
        parent = reach.graph.stores.get(relation.parent)
        child = reach.graph.stores.get(relation.child)
        if parent is None or child is None or parent.node not in blocked:
            continue
        if protect_state(reach, child) == "absent":
            out.append(child)
    return out
