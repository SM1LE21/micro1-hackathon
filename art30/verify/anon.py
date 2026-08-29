"""Anonymised versus pseudonymised, and the soft-delete marker (03-verifier.md 4.7, R25).

Read the assignments performed on a store's own columns on the erasure path. A
constant or `None` is an `anonymised` candidate; a hash, a token, a UUID, a mask or
an id-bearing template is `pseudonymised` -- reversible or still linked [S12] -- and
a call the verifier cannot resolve is `unverified` (R26).

The column list is the verifier's own, union whatever the record claims, minus the
primary key (4.7, decision 22): reading it off the record alone would let the model
shrink the list until "every field is overwritten" is true while the name and the
phone number survive. A soft-delete marker is neither an overwrite nor a column of
its own here: writing it is R25's `not_erased`, and the timer half is `timers.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from art30.verify.entities import Assign, Symbol
from art30.verify.findings import EntryPoint, Graph, Store

if TYPE_CHECKING:                       # `reach.py` owns the walk 4.7 reads over
    from art30.verify.reach import Reach
    from art30.verify.rules import RuleSet

CONSTANT, PSEUDO, MARKER, OPAQUE = "constant", "pseudonymous", "marker", "opaque"
# 4.7: the field verdict each write kind yields when it differs from the store's.
FIELD_VERDICT = {CONSTANT: "anonymised", PSEUDO: "pseudonymised", OPAQUE: "unverified"}
SELF_NAMES = ("self", "instance")


@dataclass
class Write:
    """One assignment to one column of one store, classified (4.7)."""

    field: str
    kind: str
    file: str
    line: int
    symbol: str
    value: str = ""


@dataclass
class Anon:
    verdict: str | None = None            # anonymised | pseudonymised | None
    writes: dict[str, Write] = field(default_factory=dict)
    fields: dict[str, str] = field(default_factory=dict)   # column -> field verdict
    evidence: list[dict] = field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------------------
# the variable-to-model table, followed across one resolved call edge
# ---------------------------------------------------------------------------
def propagate(graph: Graph) -> dict[str, dict[str, str]]:
    """The spike's finding 2, one hop further: a parameter bound at the call site.

    `close_account` binds `user` to `User` and hands it to `anonymize_user(user)`;
    without following that argument the callee's `user.email = ...` belongs to no
    store and S07's whole 4.7 reading is invisible. Still no type inference: the
    binding is the caller's own table, carried over a *resolved* call edge only.
    """
    table = {name: dict(symbol.var_models) for name, symbol in graph.symbols.items()}
    calls = sorted((c for c in graph.calls if c.outcome == "resolved" and c.targets),
                   key=lambda c: (c.file, c.line, c.dotted or c.name))
    for _ in range(4):                       # bounded fixpoint; deep chains are rare
        changed = False
        for site in calls:
            source = table.get(site.caller, {})
            for target in sorted(site.targets):
                callee = graph.symbols.get(target)
                if callee is None:
                    continue
                names = [a for a in callee.args if a not in SELF_NAMES]
                for index, arg in enumerate(site.args):
                    if arg.kind != "name" or index >= len(names):
                        continue
                    model = source.get(str(arg.value))
                    if model and table.setdefault(target, {}).get(names[index]) != model:
                        table[target][names[index]] = model
                        changed = True
        if not changed:
            break
    return table


def _module_constant(graph: Graph, module: str, name: str) -> Assign | None:
    """A module-level literal, the declaring module first, then a unique repo match."""
    short = name.split(".")[-1]
    order = ([module] if module in graph.modules else []) + sorted(graph.modules)
    for candidate in order:
        for assign in graph.modules[candidate].assigns:
            if assign.target == short and assign.value_kind in {"literal", "none"}:
                return assign
    return None


# ---------------------------------------------------------------------------
# 4.7 classification
# ---------------------------------------------------------------------------
def _pseudonymous(rules: "RuleSet", assign: Assign) -> bool:
    data = rules.patterns["anonymisation"]["pseudonymised_rhs"]
    text = assign.value_repr or ""
    if any(call in text for call in data["calls"]):
        return True
    if any(call.split(".")[-1] == text.replace("()", "").split(".")[-1]
           for call in data["calls"]):
        return True
    joined = text + " " + " ".join(assign.keys)
    return any(token in joined for token in
               list(data["templates_retaining_key"]) + list(data["masks"]))


def classify_write(graph: Graph, rules: "RuleSet", symbol: Symbol, assign: Assign,
                   column: str) -> str:
    """4.7's table, one right-hand side at a time; R25's marker is neither branch."""
    markers = rules.patterns["soft_delete_markers"]
    text = assign.value_repr or ""
    is_marker = rules.soft_delete_field(column)
    if is_marker and (assign.value_kind in {"literal", "none"}
                      or any(call.split(".")[-1] == text.split(".")[-1]
                             for call in markers["timestamp_calls"])):
        return MARKER
    if _pseudonymous(rules, assign):
        return PSEUDO
    if assign.value_kind in {"literal", "none"}:
        return CONSTANT
    if assign.value_kind == "name":
        found = _module_constant(graph, symbol.module, assign.value_repr)
        return CONSTANT if found is not None else OPAQUE
    return OPAQUE                            # an unresolvable call: R26, never a guess


def writes_for(reach: "Reach", store: Store,
               entries: "list[EntryPoint] | None" = None) -> dict[str, Write]:
    """Every assignment to a column of this store made on the erasure path.

    `entries` narrows the walk to a subset of the start nodes. 4.7 wants all of them --
    an anonymisation routine is an erasure path wherever it is reached from -- while
    6.2 requirement 1 names *the erasure entry point* and so passes the non-job starts
    (`timers.markers`), or a marker written inside the purge job itself would satisfy
    the requirement that the user-facing path is supposed to satisfy.
    """
    graph, rules = reach.graph, reach.rules
    found: dict[str, Write] = {}
    for name in sorted(reach.path_symbols(entries)):
        symbol = graph.symbols.get(name)
        if symbol is None:
            continue
        bound = reach.var_models.get(name, {})
        for assign in symbol.assigns:
            head, _, column = assign.target.rpartition(".")
            if not head or not column:
                continue
            model = bound.get(head)
            if model is None and head in SELF_NAMES and symbol.owner == store.model:
                model = store.model
            if model is None or model != store.model:
                continue
            kind = classify_write(graph, rules, symbol, assign, column)
            found.setdefault(column, Write(field=column, kind=kind, file=assign.file,
                                           line=assign.line, symbol=name,
                                           value=assign.value_repr))
    return dict(sorted(found.items()))


def _columns(reach: "Reach", store: Store, claimed: list[str] | None) -> list[str]:
    """4.7: the verifier's own columns, union the record's claims, minus the key.

    Nothing else is removed. An earlier draft also dropped the soft-delete markers,
    which made `anonymised` *easier*: a routine that blanks the contact columns and
    writes `deleted_at` would have satisfied "every detected column" without the
    marker column ever being read. 4.7 says every column the verifier detected, and
    a marker write is not an overwrite (R25), so the store stays `pseudonymised` --
    the conservative direction 4.7 names as the one this project pays for.
    """
    keys = _primary_keys(reach.graph, store)
    names = {f.name for f in store.fields} | set(claimed or ())
    return sorted(n for n in names if n not in keys)


def _primary_keys(graph: Graph, store: Store) -> set[str]:
    keys = {"id", "pk"}
    cls = graph.classes.get(store.model or "")
    for decl in (cls.fields if cls else []):
        if "primary_key" in decl.kwraw or "primary_key" in decl.keywords:
            keys.add(decl.target)
    return keys


def classify(reach: "Reach", store: Store,
             claimed: list[str] | None = None) -> Anon:
    """4.7 over one store: rows 5 and 7 of the 6.1 table, plus the field overrides."""
    out = Anon(writes=writes_for(reach, store))
    columns = _columns(reach, store, claimed)
    overwritten = {c: w for c, w in out.writes.items() if w.kind != MARKER}
    if not overwritten:
        return out
    out.evidence = [{"file": w.file, "line": w.line, "symbol": w.field}
                    for w in sorted(overwritten.values(), key=lambda w: (w.file, w.line))]
    kinds = {c: overwritten[c].kind if c in overwritten else "" for c in columns}
    if columns and all(kinds[c] == CONSTANT for c in columns) and not _key_survives(reach, store, overwritten):
        out.verdict = "anonymised"
    elif any(w.kind == PSEUDO for w in overwritten.values()):
        out.verdict = "pseudonymised"
    elif any(w.kind == OPAQUE for w in overwritten.values()):
        out.note = "an assignment the verifier cannot resolve (R26)"
    elif columns:
        out.verdict = "pseudonymised"        # a partial constant overwrite is masking
    for column in columns:
        out.fields[column] = FIELD_VERDICT.get(kinds[column], "not_erased")
    return out


def _key_survives(reach: "Reach", store: Store,
                  overwritten: dict[str, Write]) -> bool:
    """4.7: a surviving foreign key to a subject root makes it pseudonymisation."""
    roots = {s.id for s in reach.graph.stores.values() if s.subject_root}
    for relation in reach.graph.relations:
        if relation.child != store.id or relation.parent not in roots:
            continue
        if relation.field_name and relation.field_name not in overwritten:
            return True
    return False
