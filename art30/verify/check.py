"""Claim-by-claim checking of a submitted record (03-verifier.md 7).

Input: the record (already schema-valid), the repository path and the rule sets.
Output: the feedback object of 00-contract.md, exactly its seven list keys. The
verifier reads no manifest, here or anywhere below.

The four documents this file answers to: 7.1 for what blocks acceptance, 7.2 for the
citation re-read (`citations.py`), 7.3 for the verdict-consistency table -- one branch
per row, in the table's order -- and 7.4 for the completeness guard
(`completeness.py`). Every string is `feedback.py`'s except the row sentences below,
which belong to the rows that produce them.

Two directions are never symmetrical here. A record safer than the evidence is
recorded and accepted (`conservative_divergences`); a record safer than the code is
rejected. Nothing in this module can turn a model's conservative verdict into a
reaching one.
"""

from __future__ import annotations

from pathlib import Path

from art30.arm import Feedback
from art30.verify import completeness, feedback
from art30.verify.callgraph import build_graph
from art30.verify.citations import check_citations
from art30.verify.declared import reconcile
from art30.verify.findings import EntryPoint, Graph, Store
from art30.verify.reach import Reach
from art30.verify.rules import RuleSet, load_rules, norm
from art30.verify.verdicts import REACHES_ERASURE, Verdict, decide

BACKUP_ONLY = frozenset({"governed_by_retention", "no_schedule_evidenced"})

# 7.3's own rows, in the terms of the row that fires. 10-instructions.md 4.1 owns the
# no-path sentence (`feedback.no_path_reason`); these are the other four.
UNCORROBORATED = ("no store this scan detected corresponds to {store}, so a claim that "
                  "it reaches erasure rests on nothing the verifier can read")
# 7.3's row 10 is the same store and the other direction: the claim does not reach
# erasure, so the reaching sentence above would be false on an informational list.
UNCORROBORATED_SAFE = ("no store this scan detected corresponds to {store}; the "
                       "verifier cannot corroborate or contradict this row")
UNRESOLVED = "{note}; the path cannot be decided from the source"
TIMER_FIRST = ("the rows survive the erasure entry point and are removed later by a "
               "scheduled job: {note}")
OFF_PATH = ("the cited evidence at {file}:{line} is on no path the verifier found; the "
            "path it found ends at {end}")
# The row fires only where the verifier reached the same verdict the record claims, so
# 4.1's `EXPECT_VERDICT` would read "verdict erased, or cite the path" to a record that
# already says `erased`. The single edit that resolves it is the citation.
EXPECT_ON_PATH = "cite a line on the path above, or drop the claim"
WRONG_KIND = "{verdict} is not a verdict a store of kind {kind} takes"
EXPECT_BACKUP = ("verdict governed_by_retention or no_schedule_evidenced, the only two "
                 "a backup store takes")
EXPECT_KIND = "a verdict for kind {kind}, or kind backup where this store is a dump"
EXPECT_KEEP = "keep the verdict, or cite the line that declares this store"


def _verdict_of(block: dict | None) -> str:
    return str((block or {}).get("verdict") or "")


def _reaches(verdict: str) -> bool:
    return verdict in REACHES_ERASURE


def _claim(verdict: str) -> str:
    return f"erasure.verdict={verdict}"


class Check:
    """One record against one repository. Every list is built, then sorted (7.5)."""

    def __init__(self, record: dict, root: Path, rules: RuleSet | None = None,
                 graph: Graph | None = None) -> None:
        self.record = record
        self.root = Path(root)
        self.rules = rules or load_rules()
        self.graph = graph if graph is not None else build_graph(self.root)
        # 2.5: "Verdicts are computed over D union E_valid, with `declared_unregistered`
        # nodes contributing only capped verdicts." Walking only `D` left `caps.cap`'s
        # 2.5 branch unreachable and let the no-path sentence say "no entry point exists
        # in this repository" about a symbol the verifier's own registration scan can
        # see is externally invocable. `E_valid` is the two resolving statuses;
        # `unresolved` is a bad citation and is dropped as a start node.
        self.declared = reconcile(self.graph, completeness.declarations(record))
        self.reach = Reach(self.graph, self.rules,
                           list(self.graph.entry_points) + self._declared_starts(record))
        self.matched = completeness.matched(record, self.graph)
        self.found = self._verdicts()
        self.rejected: list[dict] = []
        self.unverified: list[dict] = []
        self.divergences: list[dict] = []

    def _declared_starts(self, record: dict) -> list[EntryPoint]:
        """2.5's `E \\ D`, as start nodes; `declared_unregistered` carries the cap flag.

        The kind is the record's own -- the verifier did not classify a node it never
        discovered -- and `unknown` where the record left it out.
        """
        kinds = {(e.get("name", ""), e.get("file", "")): str(e.get("kind") or "unknown")
                 for e in record.get("entry_points") or []}
        # `EntryPoint.node` is `entry:<name>`, so two entry points of one name share a
        # node and share a memoised walk. Where a declared row collides with a name
        # already in `D` (or with an earlier declared row) it is dropped rather than
        # merged: a merged node would carry one row's `flags` over the other's edges,
        # and an uncapped `declared_only` flag standing in front of a
        # `declared_unregistered` walk is the unsafe direction 2.5's cap exists for.
        # Dropping removes a start node, which is the conservative direction (deviation).
        seen = {entry.name for entry in self.graph.entry_points}
        out: list[EntryPoint] = []
        for row in self.declared:
            if row["status"] not in ("declared_only", "declared_unregistered"):
                continue
            if row["name"] in seen:
                continue
            seen.add(row["name"])
            out.append(EntryPoint(name=row["name"],
                                  kind=kinds.get((row["name"], row["file"]), "unknown"),
                                  file=row["file"], line=row["line"],
                                  symbol=row.get("symbol"), flags=[row["status"]]))
        return out

    def _verdicts(self) -> dict[str, Verdict]:
        """6.1 over every detected store, with the record's own columns as `claimed`.

        `reach.verdicts()` is the same loop; it is repeated here so the walk is built
        once and the 4.1 detail probes can ask the same `Reach` what it found.
        """
        claimed: dict[str, list[str]] = {}
        for index, store in self.matched.items():
            item = (self.record.get("stores") or [])[index]
            claimed[store.id] = sorted({f.get("name", "") for f in item.get("fields") or []})
        out: dict[str, Verdict] = {}
        for key in sorted(self.graph.stores):
            store = self.graph.stores[key]
            verdict = decide(self.reach, store, claimed.get(key))
            verdict.columns = len(store.fields)
            verdict.linked = store.subject_link is not None
            out[key] = verdict
        return out

    # -- 7.3 ---------------------------------------------------------------
    def run(self) -> None:
        for index, item in enumerate(self.record.get("stores") or []):
            self._store(index, item)

    def _store(self, index: int, item: dict) -> None:
        name = str(item.get("name") or "")
        kind = str(item.get("kind") or "")
        claimed = _verdict_of(item.get("erasure"))
        if self._wrong_kind(name, kind, claimed):
            return                                  # 7.3: a verdict reserved for a kind
        store = self.matched.get(index)
        if store is None:                           # 7.3: not in the verifier's store set
            self._uncorroborated(name, claimed)
            return
        verdict = self.found[store.id]
        if kind and verdict.kind and kind != verdict.kind:
            self.unverified.append(feedback.unverified(
                name, f"kind={kind}",
                f"the verifier detected kind {verdict.kind} for this store, not {kind}",
                f"kind {verdict.kind}, or say in the store note what the code shows"))
        before = len(self.rejected)
        self._compare(name, None, claimed, verdict, store)
        if len(self.rejected) == before:   # one rejection per claim, never two
            self._evidence(name, item, verdict, store)
        for field in item.get("fields") or []:
            override = field.get("erasure")
            if override:
                self._compare(name, str(field.get("name") or ""), _verdict_of(override),
                              self._field_verdict(verdict, str(field.get("name") or "")),
                              store)

    def _field_verdict(self, verdict: Verdict, name: str) -> Verdict:
        """A per-field override is checked against the field's own verdict where 4.7
        produced one, and against the store's where it did not."""
        for column, found in sorted(verdict.fields.items()):
            if norm(column) == norm(name):
                return found
        return verdict

    def _wrong_kind(self, name: str, kind: str, claimed: str) -> bool:
        if kind == "backup" and claimed not in BACKUP_ONLY:
            self._reject(name, None, claimed, WRONG_KIND.format(verdict=claimed, kind=kind),
                         [], EXPECT_BACKUP)
            return True
        if kind != "backup" and claimed in BACKUP_ONLY:
            self._reject(name, None, claimed, WRONG_KIND.format(verdict=claimed, kind=kind),
                         [], EXPECT_KIND.format(kind=kind))
            return True
        return False

    def _uncorroborated(self, name: str, claimed: str) -> None:
        """7.3's two rows for a store the detectors never saw."""
        if _reaches(claimed):
            self._reject(name, None, claimed, UNCORROBORATED.format(store=name), [],
                         feedback.EXPECT_UNVERIFIED)
            return
        self.unverified.append(feedback.unverified(          # 7.3 row 10, not reaching
            name, _claim(claimed), UNCORROBORATED_SAFE.format(store=name), EXPECT_KEEP))

    def _compare(self, name: str, field: str | None, claimed: str, verdict: Verdict,
                 store: Store) -> None:
        """The verdict-consistency rows, in 7.3's order; the first that fires decides."""
        found = verdict.verdict
        if _reaches(claimed) and not _reaches(found):
            if found == "unverified":               # row 2: a safe claim with no evidence
                self._reject(name, field, claimed, UNRESOLVED.format(note=verdict.note),
                             feedback.path_cites(verdict), feedback.EXPECT_UNVERIFIED)
                return
            self._reject(name, field, claimed,      # row 1: the false-safe direction
                         feedback.no_path_reason(self.reach, store, verdict),
                         feedback.path_cites(verdict),
                         feedback.EXPECT_VERDICT.format(suggested=found))
            return
        if claimed == "erased" and found == "erased_after_timer":       # row 3
            self._reject(name, field, claimed, TIMER_FIRST.format(note=verdict.note),
                         feedback.path_cites(verdict),
                         feedback.EXPECT_VERDICT.format(suggested=found))
            return
        if claimed == "erased_after_timer" and found == "erased":       # row 4
            self._diverge(name, claimed, verdict)
            return
        if not _reaches(claimed) and _reaches(found):                   # row 5
            self._diverge(name, claimed, verdict)
            return
        if not _reaches(claimed) and found == "unverified":
            self.unverified.append(feedback.unresolved(name, _claim(claimed), verdict))

    def _evidence(self, name: str, item: dict, verdict: Verdict, store: Store) -> None:
        """7.3's last row: a citation that points at the right file and the wrong reason."""
        claimed = _verdict_of(item.get("erasure"))
        if claimed != verdict.verdict:
            # The row is "a citation that points at the right file and the wrong
            # reason": a claim the verifier corroborates, cited wrongly. Where the two
            # labels differ, 7.3 has already decided the store -- rows 4 and 6 accept it
            # -- and a rejection here would contradict the divergence the same pass
            # recorded ("conservative_divergences are accepted, never rejected").
            return
        cited = [(c.get("file"), c.get("line")) for c in
                 (item.get("erasure") or {}).get("evidence") or []]
        if not (cited and verdict.path and _reaches(claimed) and _reaches(verdict.verdict)):
            return
        allowed = {(step["file"], step["line"]) for step in verdict.path}
        allowed |= {(c["file"], c["line"]) for c in verdict.evidence}
        allowed |= {(p["file"], p["line"]) for p in store.primitives}
        allowed |= {(r.file, r.line) for r in self.graph.relations
                    if store.id in (r.child, r.parent)}
        if any(pair in allowed for pair in cited):
            return
        end = verdict.path[-1]
        self._reject(name, None, claimed,
                     OFF_PATH.format(file=cited[0][0], line=cited[0][1],
                                     end=f"{end['file']}:{end['line']}"),
                     feedback.path_cites(verdict), EXPECT_ON_PATH)

    def _reject(self, store: str, field: str | None, claimed: str, reason: str,
                path: list[dict], expected: str) -> None:
        self.rejected.append(
            feedback.rejected(store, field, _claim(claimed), reason, path, expected))

    def _diverge(self, store: str, claimed: str, verdict: Verdict) -> None:
        self.divergences.append(feedback.divergence(
            store, _claim(claimed), feedback.verifier_phrase(self.reach, verdict)))

    # -- 7.1 ---------------------------------------------------------------
    def build(self) -> Feedback:
        self.run()
        bad = check_citations(self.record, self.graph, self.root)
        missing = completeness.missing_stores(self.record, self.graph, self.rules)
        entries = completeness.missing_entry_points(self.record, self.graph, self.declared)
        rejected = feedback.ordered("rejected_claims", self.rejected)
        accepted = not (rejected or missing or bad)
        return Feedback(
            accepted=accepted,
            rejected_claims=rejected,
            missing_stores=missing,
            missing_entry_points=entries,
            bad_citations=bad,
            unverified=feedback.ordered("unverified", self.unverified),
            conservative_divergences=feedback.ordered("conservative_divergences",
                                                      self.divergences),
        )


def check(record: dict, root: Path, rules: RuleSet | None = None,
          graph: Graph | None = None) -> Feedback:
    """7.1: `accepted` iff no rejected claim, no missing store and no bad citation."""
    return Check(record, root, rules, graph).build()
