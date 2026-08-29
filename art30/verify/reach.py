"""`path_exists` and the per-store verdicts (03-verifier.md 5 and 6).

Breadth-first over the state `(node, mode, passed)`, with the out-edges sorted, so
the first hit is a shortest path and the same repository always cites the same one.
The delete mode is carried in the search state and never in the signature (ADR 0004
P-15): `mode_of(entry)` is `none` for every entry point, SE12 sets a mode from the
primitive it names and SE10 sets the two admin modes, and every mode-bearing
synthetic edge stays inadmissible until one does (4.2, decision 19).

The search runs twice where it matters -- resolved edges only, then all edges. A
target reached in the first is evidence; one reached only in the second is
`unverified` (R26, decision 2), and that is the single mechanic that keeps a guessed
edge from ever producing `erased`.

Modules: `verdicts.py` owns the 6.1 ordering, `downgrades.py` the reasons a verdict
leaves row 4, `timers.py` 6.2 and 6.3, `anon.py` 4.7.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from art30.verify import anon
from art30.verify.entities import MODES, Edge
from art30.verify.findings import EntryPoint, Graph
from art30.verify.rules import RuleSet, load_rules
from art30.verify.timers import JOB_KINDS
from art30.verify.verdicts import Verdict, decide

# 4.2: what is admissible in mode `none`, enforced by `_search` rather than trusted
# from the edge builder. This table is the search's own state space and not data a
# rule set may vary (decision 17), and 4.2's sentence is categorical -- "SE1-SE9 all
# name a mode and stay inadmissible until a primitive edge has set one" -- while SE7's
# own row reads "all modes incl. bulk_dml". Reading that row as including `none` would
# make an `ondelete="CASCADE"` child reachable before any delete had been called.
# `reference` is deliberately absent: 1.5's promotion half -- a reference passed to a
# rule-set-known scheduler becoming an edge -- is not implemented, so no edge of that
# kind exists and naming it here would imply one that cannot. 1.5's other half, the
# downgrade to `unverified` where a reference is the only thing between the path and
# the store, is `downgrades._reference_only`.
ADMISSIBLE_IN_NONE = frozenset({"call", "entry", "SE10", "SE11", "SE12"})
ENTRY_RULE = "03-verifier.md 2.2"
# 00-contract.md, checkpoint risk: the verdicts that make a store's row `high`.
HIGH_RISK = frozenset({"not_erased", "pseudonymised", "external_manual",
                       "no_entry_point", "no_schedule_evidenced", "unverified"})


@dataclass(frozen=True)
class Step:
    """One step of a path: 5.1's `{from, to, kind, file, line, rule, ambiguous}`."""

    src: str
    dst: str
    kind: str
    file: str
    line: int
    rule: str
    ambiguous: bool = False
    note: str = ""

    def as_dict(self) -> dict:
        return {"from": self.src, "to": self.dst, "kind": self.kind, "file": self.file,
                "line": self.line, "rule": self.rule, "ambiguous": self.ambiguous}


@dataclass
class Path:
    steps: list[Step] = field(default_factory=list)
    mode: str = "none"

    @property
    def ambiguous(self) -> bool:
        return any(step.ambiguous for step in self.steps)

    @property
    def nodes(self) -> list[str]:
        return ([self.steps[0].src] if self.steps else []) + [s.dst for s in self.steps]

    def as_list(self) -> list[dict]:
        return [step.as_dict() for step in self.steps]

    def __iter__(self) -> "Iterator[Step]":
        return iter(self.steps)

    def __len__(self) -> int:
        return len(self.steps)

    def __getitem__(self, index: int) -> Step:
        return self.steps[index]


def mode_of(entry: EntryPoint | None) -> str:
    """4.2: `none` for every entry point; SE10 sets the two admin modes on traversal."""
    return getattr(entry, "mode", "none") or "none"


def _step(edge: Edge) -> Step:
    return Step(src=edge.src, dst=edge.dst, kind=edge.kind, file=edge.file,
                line=edge.line, rule=edge.rule, ambiguous=edge.ambiguous, note=edge.note)


def entry_edges(entries: Iterable[EntryPoint]) -> dict[str, list[Edge]]:
    """`entry:<name>` -> its symbol. The admin pair has no symbol; SE10 is their edge."""
    out: dict[str, list[Edge]] = {}
    for entry in entries:
        if not entry.symbol:
            continue
        out.setdefault(entry.node, []).append(
            Edge(src=entry.node, dst=entry.symbol, kind="entry", file=entry.file,
                 line=entry.line, rule=ENTRY_RULE, modes=MODES,
                 note=f"entry point {entry.name} ({entry.kind})"))
    return out


def _out(graph: Graph, extra: dict[str, list[Edge]], node: str, resolved_only: bool,
         blocked: frozenset[str]) -> list[Edge]:
    edges = [e for e in list(graph.out(node)) + list(extra.get(node, ()))
             if e.dst not in blocked and not (resolved_only and e.ambiguous)]
    return sorted(edges, key=lambda e: (e.to, e.kind, e.file, e.line, e.rule))


def _search(graph: Graph, extra: dict[str, list[Edge]], start: str, mode: str,
            targets: frozenset[str], target: str | None = None,
            resolved_only: bool = False,
            blocked: frozenset[str] = frozenset()) -> "Path | dict[str, Path] | None":
    """5.2's loop. `target=None` returns the first path to every reachable node."""
    state = (start, mode, not targets or start in targets)
    frontier: deque = deque([(state, ())])
    seen = {state}
    found: dict[str, Path] = {}
    while frontier:
        (node, mode, passed), path = frontier.popleft()
        if passed:
            if target is not None and node == target:
                return Path(list(path), mode)
            found.setdefault(node, Path(list(path), mode))
        for edge in _out(graph, extra, node, resolved_only, blocked):
            if mode not in edge.admissible_modes:
                continue
            if mode == "none" and edge.kind not in ADMISSIBLE_IN_NONE:
                continue
            nxt = (edge.to, edge.sets_mode or mode, passed or edge.to in targets)
            if nxt in seen:
                continue
            seen.add(nxt)
            frontier.append((nxt, path + (_step(edge),)))
    return None if target is not None else found


def path_exists(graph: Graph, entry: EntryPoint | str, target: str,
                must_pass_through: Iterable[str] | None = None) -> Path | None:
    """5.1: the first shortest path under a fixed edge ordering, or None."""
    extra = entry_edges(graph.entry_points)
    start = entry.node if isinstance(entry, EntryPoint) else str(entry)
    mode = mode_of(entry)
    if not isinstance(entry, EntryPoint):
        found = next((e for e in graph.entry_points if e.node == start), None)
        mode = mode_of(found) if found is not None else "none"
    return _search(graph, extra, start, mode, frozenset(must_pass_through or ()),
                   target=target)


class Reach:
    """One repository's reachable sets, memoised per (entry point, edge set) (5.3)."""

    def __init__(self, graph: Graph, rules: RuleSet | None = None,
                 entry_points: Iterable[EntryPoint] | None = None) -> None:
        self.graph = graph
        self.rules = rules or load_rules()
        source = graph.entry_points if entry_points is None else list(entry_points)
        self.entries = sorted(source, key=lambda e: e.key())
        self.extra = entry_edges(self.entries)
        # 6.2 requirement 3 / decision 20: a task decorator is not evidence that
        # anything runs the job, so an unscheduled job is never a start node for a
        # reaching verdict. Test 37a is the shape.
        self.starts = [e for e in self.entries if "unscheduled" not in e.flags]
        self.jobs = [e for e in self.starts if e.kind in JOB_KINDS]
        self.var_models = anon.propagate(graph)
        self._walks: dict[tuple, dict[str, Path]] = {}
        self._protect: set[str] | None = None

    def walk(self, entry: EntryPoint, resolved_only: bool = True,
             blocked: frozenset[str] = frozenset()) -> dict[str, Path]:
        key = (entry.node, resolved_only, blocked)
        if key not in self._walks:
            self._walks[key] = _search(self.graph, self.extra, entry.node,
                                       mode_of(entry), frozenset(),
                                       resolved_only=resolved_only, blocked=blocked)
        return self._walks[key]

    def reached(self, node: str, resolved_only: bool = True,
                exclude: Iterable[str] = (), only: EntryPoint | None = None,
                blocked: frozenset[str] = frozenset(),
                ignore_starts: bool = False) -> tuple[EntryPoint, Path] | None:
        """The first entry point, in sorted order, whose walk reaches `node`."""
        skip = set(exclude)
        pool = [only] if only is not None else (
            self.entries if ignore_starts else self.starts)
        for entry in pool:
            if entry.node in skip:
                continue
            path = self.walk(entry, resolved_only, blocked).get(node)
            if path is not None:
                return (entry, path)
        return None

    def from_symbol(self, symbol: str, target: str) -> Path | None:
        """A walk that starts at a bare symbol; 5.1 allows it, and R11 needs it."""
        return _search(self.graph, self.extra, symbol, "none", frozenset(), target=target)

    def path_symbols(self, entries: Iterable[EntryPoint] | None = None) -> set[str]:
        """Every symbol on a resolved walk from a start entry point (4.7's path).

        `entries` narrows the start set; 6.2 requirement 1 passes the non-job starts
        (`timers.markers`) so a marker written inside the purge job cannot stand in for
        the erasure entry point's own write.
        """
        found: set[str] = set()
        for entry in (self.starts if entries is None else entries):
            for node in self.walk(entry, True):
                if node in self.graph.symbols:
                    found.add(node)
        return found

    def protect_parents(self) -> set[str]:
        """6.1's second cap: the parents of a disqualified two-step PROTECT idiom."""
        from art30.verify import caps

        if self._protect is None:
            found: set[str] = set()
            for relation in self.graph.relations:
                child = self.graph.stores.get(relation.child)
                parent = self.graph.stores.get(relation.parent)
                if child is None or parent is None:
                    continue
                # 4.8 and 6.1's second cap. "absent" belongs here as much as
                # "disqualified" does: with no child delete at all the parent delete
                # raises `ProtectedError` while the children exist, so the parent row
                # -- and everything cascaded from it -- is not deleted either. Reading
                # only the disqualified branch produced a record that said in one row
                # that the delete raises and in the next that the account row is gone.
                if caps.protect_state(self, child) in {"disqualified", "absent"}:
                    found.add(parent.node)
            self._protect = found
        return self._protect


def verdicts(graph: Graph, rules: RuleSet | None = None,
             entry_points: Iterable[EntryPoint] | None = None,
             claimed: dict[str, list[str]] | None = None) -> dict[str, Verdict]:
    """6.1 over every detected store, sorted; per-field overrides where 4.7 yields them."""
    reach = Reach(graph, rules, entry_points)
    out: dict[str, Verdict] = {}
    for store_id in sorted(graph.stores):
        store = graph.stores[store_id]
        verdict = decide(reach, store, (claimed or {}).get(store_id))
        verdict.columns = len(store.fields)
        verdict.linked = store.subject_link is not None
        out[store_id] = verdict
    return out


def verdict_for(graph: Graph, store_id: str, rules: RuleSet | None = None,
                entry_points: Iterable[EntryPoint] | None = None,
                claimed: list[str] | None = None) -> Verdict:
    """One store's verdict, for a caller that wants a single claim checked (7.3)."""
    store = graph.stores[store_id]
    verdict = decide(Reach(graph, rules, entry_points), store, claimed)
    verdict.columns = len(store.fields)
    verdict.linked = store.subject_link is not None
    return verdict


def risk_flags(found: dict[str, Verdict]) -> dict:
    """6.4: the inputs to the checkpoint rating. The harness decides the rating.

    The verifier's own set is the cross-check carried beside the record's; 6.4 is
    explicit that the rating a human sees is computed from the accepted record, so
    what leaves here is evidence and a suggestion, never the decision.
    """
    # 6.4 asks for "with an identifier or contact field" and the verifier assigns no
    # categories (3.9 is guard-only), so three signals stand in: a guard match; a store
    # whose columns the detectors never saw (a bucket, an index, a queue), where such a
    # field cannot be ruled out; and a subject link, the citation tying the rows to a
    # person. Without the third, S03 rated `low` while `invoices` was `unverified` with
    # a `billing_name` -- 6.4's own "the gate would under-warn on exactly the divergence
    # the spec is proud of allowing". S07's `products` has neither and still does not
    # turn a rating; under-warning is the unsafe direction.
    high = sorted(v.store for v in found.values()
                  if v.verdict in HIGH_RISK
                  and (v.guard or v.linked or not v.columns))
    reaching = [v for v in found.values() if v.reaches_erasure]
    others = [v for v in found.values()
              if not v.reaches_erasure and v.verdict not in
              {"governed_by_retention", "no_schedule_evidenced"}]
    timer_only = bool(reaching) and not others and any(
        v.verdict == "erased_after_timer" for v in reaching)
    rating = "high" if high else ("medium" if timer_only else "low")
    return {"rating": rating, "high_stores": high, "timer_only": timer_only,
            "verdicts": {k: v.verdict for k, v in sorted(found.items())}}
