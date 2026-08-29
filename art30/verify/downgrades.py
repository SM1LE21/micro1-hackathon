"""What takes a verdict away from row 4, and row 8's and row 9's reasons.

Split from `verdicts.py`, which owns the 6.1 ordering: this module owns the reasons
a store that looks reached is not, or is not *shown* to be. Every branch names its
rule -- 1.5's reference, R6, R10, R11, R13, R19, R26, R27, R28 -- and every one of
them moves a verdict from a reaching label to a conservative one, never the other way
round. The two caps that sit *above* the table, and the 4.8 `PROTECT`/`RESTRICT`
reading they rest on, are `caps.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from art30.verify.findings import EntryPoint, Graph, Store
from art30.verify.rules import norm

if TYPE_CHECKING:                       # `verdicts.py` owns 6.1, `reach.py` the walk
    from art30.verify.anon import Anon
    from art30.verify.entities import CallSite
    from art30.verify.reach import Path, Reach
    from art30.verify.verdicts import Verdict

VERSION_KWARG = "VersionId"


def _cite(file: str, line: int, symbol: str = "") -> dict:
    return {"file": file, "line": int(line), "symbol": symbol}


def call_at(reach: "Reach", file: str, line: int, name: str) -> "CallSite | None":
    for site in reach.graph.calls:
        if site.file == file and site.line == line and site.name == name:
            return site
    return None


# ---------------------------------------------------------------------------
# on the path: R13 and R27
# ---------------------------------------------------------------------------
def on_path(reach: "Reach", store: Store, entry: EntryPoint,
            path: "Path") -> "Verdict | None":
    """Row 4's own downgrades, read off the path the search returned."""
    from art30.verify.verdicts import Verdict

    def make(name: str, note: str, rules: list[str], cites: list[dict]) -> Verdict:
        return Verdict(store=store.id, verdict=name, kind=store.kind, guard=store.guard,
                       note=note, reasons=rules, evidence=cites, path=path.as_list())

    unmodelled = sorted({s.dst for s in path.steps
                         if getattr(reach.graph.symbols.get(s.dst),
                                    "wrapped_by_unmodelled_decorator", False)})
    if unmodelled and reach.reached(store.node, resolved_only=True, blocked=frozenset(unmodelled)) is None:
        symbol = reach.graph.symbols[unmodelled[0]]
        return make("unverified",                                        # R27 [S35]
                    f"the primitive is reachable only through {symbol.short}, "
                    "wrapped by a decorator the rules do not model",
                    ["R27"], [_cite(symbol.file, symbol.line, symbol.short)])
    if store.kind == "object_storage" and "versioning_declared" in store.flags:
        last = path.steps[-1]
        site = call_at(reach, last.file, last.line, last.note.split(".")[-1].split(" ")[0])
        if site is None or VERSION_KWARG not in site.keywords:           # R13 [S22] [S23]
            declared = sorted(reach.graph.versioning, key=lambda v: (v["file"], v["line"]))[0]
            return make("not_erased",
                        "the bucket declares versioning and the delete passes no "
                        "VersionId; S3 behaves as though the object has been deleted "
                        "even though it has not been erased [S22]",
                        ["R13"], [_cite(last.file, last.line, store.id),
                                  _cite(declared["file"], declared["line"], declared["literal"])])
    return None


# ---------------------------------------------------------------------------
# row 8: the reasons the tool cannot tell
# ---------------------------------------------------------------------------
def unverified_reason(reach: "Reach", store: Store,
                      hit: "tuple[EntryPoint, Path] | None",
                      loose: "tuple[EntryPoint, Path] | None",
                      marks: "Anon") -> tuple[str, list[str], list[dict]] | None:
    """Row 8, in a fixed order so two rules never race for one store."""
    graph = reach.graph
    if store.declared_at and any(u["file"] == store.declared_at.file for u in graph.unparsed):
        return ("the store is declared in a file that does not parse", ["R28"], [])
    if hit is None and loose is not None:                                # R26 [S35]
        step = next((s for s in loose[1].steps if s.ambiguous), loose[1].steps[-1])
        return (f"reached only through an ambiguous call at {step.file}:{step.line}",
                ["R26"], [_cite(step.file, step.line, store.id)])
    if hit is None:
        split = _cleanup_disagreement(reach, store)                  # R10, 4.4
        if split is not None:
            return ("the settings modules disagree about django_cleanup, so whether "
                    "the file is deleted depends on which one runs in production",
                    ["R10", "03-verifier.md 4.4"], split)
    if hit is None and "r6_unverified" in store.flags and _parent_reached(reach, store):
        cite = _relation_cite(graph, store, ondelete=True)                # R6 [S15] [S19]
        return ('ondelete="CASCADE" is DDL only; no evidence that the engine the '
                "session is bound to enforces foreign keys", ["R6"], cite)
    if hit is None and restrict_with_cascade_sibling(reach, store):     # R3b [S1]
        return ("on_delete=RESTRICT with a CASCADE relation deleted in the same "
                "operation is the documented exception the AST cannot settle",
                ["R3b"], _relation_cite(graph, store))
    if hit is None:
        raw = _raw_downstream(reach, store)                              # R19 [S11]
        if raw is not None:
            return ("the parent row is removed by raw SQL; nothing downstream of it "
                    "is visible to the verifier", ["R19"], [raw])
        weak = _weak_receiver(reach, store)                              # R11 [S6]
        if weak is not None:
            return (f"the only cleanup is a receiver defined inside {weak[0]} and "
                    "connected without weak=False; it may be collected before it fires",
                    ["R11"], [weak[1]])
        opaque = _opaque_call(reach, store)                              # 1.5, CG-12
        if opaque is not None:
            return (f"an opaque call at {opaque['file']}:{opaque['line']} plausibly "
                    "touches this store", ["R26"], [opaque])
        handed = _reference_only(reach, store)                       # 1.5, CG-15
        if handed is not None:
            symbol, cite = handed
            return (f"{symbol} is handed to something as a reference at "
                    f"{cite['file']}:{cite['line']} and reaches this store, but no "
                    "resolved call edge does; the verifier cannot say the scheduler "
                    "ever runs it", ["03-verifier.md 1.5", "R26"], [cite])
    if hit is None and marks.note:
        return (marks.note, ["R26"], marks.evidence)
    return None


def _cleanup_disagreement(reach: "Reach", store: Store) -> list[dict] | None:
    """4.4: several `INSTALLED_APPS`, disagreeing about django_cleanup.

    "Where they disagree about `django_cleanup` specifically, the file store is
    `unverified`, with both settings lines cited." Reading their union would let a
    `django_cleanup` present only in the development module make SE3 admissible for
    the whole repository; `facts.py` already refuses the union and returns DISAGREE,
    and this is the verdict that refusal owes the store.
    """
    if store.kind != "object_storage" or "django_file_field" not in store.flags:
        return None
    if reach.graph.settings.get("cleanup") != "DISAGREE":
        return None
    owner = reach.graph.store_for_model(store.model or "")
    if owner is None or reach.reached(owner.node, resolved_only=True) is None:
        return None                      # 4.4 only bites where the row is reached (R8)
    cites: list[dict] = []
    for module in sorted(reach.graph.settings.get("installed_apps") or {}):
        info = reach.graph.modules.get(module)
        for assign in info.assigns if info else []:
            if assign.target == "INSTALLED_APPS":
                cites.append(_cite(info.file, assign.line, "INSTALLED_APPS"))
    return sorted(cites, key=lambda c: (c["file"], c["line"])) or None


def _parent_reached(reach: "Reach", store: Store) -> bool:
    for relation in reach.graph.relations:
        if relation.child != store.id or not relation.ondelete:
            continue
        parent = reach.graph.stores.get(relation.parent)
        if parent is not None and reach.reached(parent.node, resolved_only=True):
            return True
    return False


def _relation_cite(graph: Graph, store: Store, ondelete: bool = False) -> list[dict]:
    for relation in sorted(graph.relations, key=lambda r: (r.file, r.line)):
        if relation.child != store.id:
            continue
        if ondelete and not relation.ondelete:
            continue
        return [_cite(relation.file, relation.line, relation.field_name or store.id)]
    return []


def restrict_with_cascade_sibling(reach: "Reach", store: Store) -> bool:
    graph = reach.graph
    mine = [r for r in graph.relations if r.child == store.id and norm(r.token) == "restrict"]
    if not mine:
        return False
    parents = {r.parent for r in mine}
    return any(norm(r.token) == "cascade" and r.parent in parents for r in graph.relations)


def _raw_downstream(reach: "Reach", store: Store) -> dict | None:
    for relation in sorted(reach.graph.relations, key=lambda r: (r.file, r.line)):
        if relation.child != store.id:
            continue
        parent = reach.graph.stores.get(relation.parent)
        if parent is None or reach.reached(parent.node, resolved_only=True) is None:
            continue
        for primitive in sorted(parent.primitives, key=lambda p: (p["file"], p["line"])):
            if primitive.get("mode") == "raw_sql":
                return _cite(primitive["file"], primitive["line"], parent.id)
    return None


def _weak_receiver(reach: "Reach", store: Store) -> tuple[str, dict] | None:
    """R11 [S6]: a receiver defined in a function body and connected weakly."""
    for receiver in reach.graph.receivers:
        if not (receiver.nested and receiver.weak):
            continue
        if reach.from_symbol(receiver.symbol, store.node) is None:
            continue
        symbol = reach.graph.symbols.get(receiver.symbol)
        owner = symbol.name.rsplit(".", 1)[0] if symbol else receiver.symbol
        return (owner, _cite(receiver.file, receiver.line, receiver.symbol.split(".")[-1]))
    return None


def _reference_only(reach: "Reach", store: Store) -> tuple[str, dict] | None:
    """1.5, CG-15: a reference is the only thing between the path and the store.

    "The store stays `unverified` rather than `not_erased` if that reference is the
    only thing standing between the store and a primitive." `my_queue.push(
    cleanup_user_files, request.user)` in `close_account` is the shape: the helper is
    named, never called, and whether the queue runs it is outside the AST. The mirror
    half of 1.5 -- promoting a reference passed to a *known* scheduler to a real edge --
    is not implemented, which is a recall loss in the safe direction.
    """
    on_path = reach.path_symbols()
    for reference in sorted(reach.graph.references,
                            key=lambda r: (r.file, r.line, r.target)):
        if reference.promoted_by or reference.caller not in on_path:
            continue
        if reference.target in on_path:
            continue                     # something already calls it: not a reference-only
        if reach.from_symbol(reference.target, store.node) is None:
            continue
        short = reference.target.rsplit(".", 1)[-1]
        return (short, _cite(reference.file, reference.line, short))
    return None


def _opaque_call(reach: "Reach", store: Store) -> dict | None:
    """1.5 narrowed: an opaque call only downgrades the store it plausibly touches."""
    clients = set(store.client_vars)
    files = {p["file"] for p in store.primitives}
    if store.declared_at:
        files.add(store.declared_at.file)
    for site in sorted(reach.graph.unresolved, key=lambda c: (c.file, c.line)):
        if site.rule != "CG-12":
            continue
        head = (site.receiver or "").split(".")[0]
        if head in clients or (clients and site.file in files):
            return _cite(site.file, site.line, site.dotted or site.name)
    return None


# ---------------------------------------------------------------------------
# row 9's note (6.1's two caps are `caps.py`)
# ---------------------------------------------------------------------------
def not_erased_note(reach: "Reach", store: Store) -> str:
    from art30.verify import caps, timers

    if caps.protect_state(reach, store) == "absent":
        cite = _relation_cite(reach.graph, store)
        where = f" ({cite[0]['file']}:{cite[0]['line']})" if cite else ""
        error = caps.error_name(reach, store)
        return (f"deleting the parent raises {error} while children exist"
                f"{where}; nothing deletes this table first")
    if "r6_not_erased" in store.flags:
        return ('passive_deletes=True tells the ORM not to emit the child DELETE and '
                "no enforcing engine is shown, so nothing removes these rows")
    unscheduled = timers.unscheduled_note(reach, store)
    if unscheduled:
        return unscheduled
    for primitive in sorted(store.primitives, key=lambda p: (p["file"], p["line"])):
        caller = primitive.get("caller", "")
        short = caller.rsplit(".", 1)[-1]
        return (f"{short} ({primitive['file']}:{primitive['line']}) is defined but no "
                "entry point reaches it")
    return "no deletion primitive for this store is on any path from an entry point"
