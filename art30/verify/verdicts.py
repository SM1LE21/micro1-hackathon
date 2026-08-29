"""The verdict decision procedure, one store at a time (03-verifier.md 6.1).

Nine rows applied in order, the first that fires deciding, with the two caps of 6.1
applied after the table. The ordering is itself the safety property -- the
conservative labels sit above the reaching ones wherever the evidence is weaker --
so, like the mode table, it lives in code beside the search and never in a rule file
a rule set could reorder (decision 17).

`reach.py` owns the walk and hands this module a context with the paths already
found; this module owns which row fires and why, and every branch names its rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from art30.verify import anon, caps, downgrades, timers
from art30.verify.findings import EntryPoint, Store

if TYPE_CHECKING:                       # the walk owns `Reach`; this module owns 6.1
    from art30.verify.anon import Anon
    from art30.verify.reach import Path, Reach
    from art30.verify.timers import Timer


REACHES_ERASURE = frozenset({"erased", "erased_after_timer", "anonymised"})


@dataclass
class Verdict:
    """What 6.1 decided for one store, with the evidence a record has to cite."""

    store: str
    verdict: str
    kind: str = ""
    guard: str = ""
    columns: int = 0               # how many columns the detectors saw (6.4's proxy)
    linked: bool = False           # 6.4: the store carries a subject_link citation
    timer_days: int | None = None
    evidence: list[dict] = field(default_factory=list)
    path: list[dict] = field(default_factory=list)
    note: str = ""
    reasons: list[str] = field(default_factory=list)
    fields: dict[str, "Verdict"] = field(default_factory=dict)

    @property
    def reaches_erasure(self) -> bool:
        return self.verdict in REACHES_ERASURE

    def as_dict(self) -> dict:
        return {"store": self.store, "verdict": self.verdict, "kind": self.kind,
                "timer_days": self.timer_days, "evidence": self.evidence,
                "path": self.path, "note": self.note, "reasons": sorted(self.reasons),
                "fields": {k: v.as_dict() for k, v in sorted(self.fields.items())}}


def _cite(file: str, line: int, symbol: str = "") -> dict:
    return {"file": file, "line": int(line), "symbol": symbol}


def _verdict(store: Store, name: str, **kwargs) -> Verdict:
    return Verdict(store=store.id, verdict=name, kind=store.kind, guard=store.guard,
                   **kwargs)


# ---------------------------------------------------------------------------
# rows 1 and 2: the two kinds that never take an ordinary erasure verdict
# ---------------------------------------------------------------------------
def _backup(reach: "Reach", store: Store) -> Verdict:
    """Row 1 (AMBIGUITIES 6, gdpr-sources.md 3.1 [S10] [S11]): never an erasure verdict."""
    found = timers.backup_retention(reach, store)
    if found.cites:
        return _verdict(store, "governed_by_retention", timer_days=found.days,
                        evidence=found.cites, reasons=["03-verifier.md 6.1 row 1"],
                        note=found.note)
    return _verdict(store, "no_schedule_evidenced", reasons=["03-verifier.md 6.1 row 1"],
                    note="no schedule, cron expression or retention constant names this dump")


def _literal_type(reach: "Reach", step, kwarg: str) -> bool:
    """R24 [S47] and 4.3: the `regulation_type` **string literal at the call site**.

    The edge note carries the argument as written whatever kind it is, so a module
    constant `SUPPRESS_WITH_DELETE = "DELETE_INTERNAL"` handed to `create_regulation`
    matched the forwarding list on the name of a variable bound to the value R24
    explicitly refuses -- the one route by which a `third_party` store can reach
    erasure, taken on a name. "`DELETE_INTERNAL`, a variable, or an absent type ->
    `external_manual`", so the call site is re-read and the kind is required to be
    `literal` (`Arg.kind`, entities.py).
    """
    if not kwarg:
        return False
    for site in reach.graph.calls:
        if site.file != step.file or site.line != step.line:
            continue
        arg = site.keywords.get(kwarg)
        if arg is not None and arg.kind == "literal":
            return True
    return False


def _third_party(reach: "Reach", store: Store) -> Verdict:
    """Row 2: `external_manual` (R22, R23), with R24's single upgrade shape."""
    data = reach.rules.recipient(store.id) if store.id in set(
        reach.rules.recipient_names()) else {}
    wanted = {str(t) for t in (data.get("forwarding_types") or ())}
    hit = reach.reached(store.node, resolved_only=True)
    kwarg = str(data.get("regulation_type_kwarg") or "")
    if hit and wanted:
        for step in hit[1].steps:
            value = step.note.partition("regulation_type=")[2]
            if value and value in wanted and _literal_type(reach, step, kwarg):
                return _verdict(store, "erased", evidence=[_cite(step.file, step.line, store.id)],
                                path=hit[1].as_list(), reasons=["R24"],
                                note=f"Segment regulation {value} forwards downstream [S47]")
    note = str(data.get("note") or "").strip() or (
        "a deletion request to a processor is not an erasure this repository can show")
    cites = [_cite(p["file"], p["line"], store.id) for p in sorted(
        store.primitives, key=lambda p: (p["file"], p["line"]))]
    declared = [_cite(store.declared_at.file, store.declared_at.line, store.id)] if store.declared_at else []
    return _verdict(store, "external_manual", evidence=cites or declared,
                    reasons=[data.get("rule", "R24")], note=note)


# ---------------------------------------------------------------------------
# rows 3 to 9
# ---------------------------------------------------------------------------
def decide(reach: "Reach", store: Store,
           claimed: list[str] | None = None) -> Verdict:
    """6.1, applied in order; the first row that fires decides."""
    if store.kind == "backup":
        return _backup(reach, store)
    if store.kind == "third_party":
        return _third_party(reach, store)
    if not reach.entries:                                            # row 3
        return _verdict(store, "no_entry_point", reasons=["03-verifier.md 2.3"],
                        note="no route, command, task or admin registration deletes a user")
    timer = timers.erased_after_timer(reach, store)
    exclude = {timer.job.node} if timer and timer.job else set()
    # 6.2 requirement 3, enforced for every job kind and not only for `task`.
    # `_tasks` flags an unscheduled celery job and `Reach.starts` drops it, but a
    # `BaseCommand` under `management/commands/` and a `@click.command` are kind `cli`
    # and carry no flag: a soft delete plus a purge command named in no cron file, no
    # beat schedule and nothing else read `erased` from row 4, with the record saying
    # the rows are gone today when nothing has been scheduled to remove them at all.
    # This is 6.2's own S10-shape argument with `cli` substituted for `task`. Gated on
    # requirement 1 so a plain `delete_user` command in a repository with no soft-delete
    # marker anywhere -- the manual-DSR shape -- is untouched.
    if timers.markers(reach, store):
        exclude |= {e.node for e in reach.jobs
                    if timers.schedule_for(reach, e) is None}
    hit = reach.reached(store.node, resolved_only=True, exclude=exclude)
    loose = reach.reached(store.node, resolved_only=False, exclude=exclude)
    marks = anon.classify(reach, store, claimed)
    verdict = _rows(reach, store, hit, loose, timer, marks)
    verdict.fields = _field_overrides(store, verdict, marks)
    # 2.5's cap holds "whatever row fired" (6.1), so rows 5, 6 and 7 need the symbols
    # their evidence was read off: `hit` is None for every verdict 4.7 or 6.2 decided,
    # and reading the cap off `hit` alone let a record declare an unregistered helper
    # and be handed back `anonymised`.
    evidence = sorted({w.symbol for w in marks.writes.values()}
                      | ({timer.job.symbol} if timer and timer.job and timer.job.symbol
                         else set()))
    return caps.cap(reach, store, verdict, hit, evidence)


def _rows(reach: "Reach", store: Store,
          hit: "tuple[EntryPoint, Path] | None",
          loose: "tuple[EntryPoint, Path] | None",
          timer: "Timer | None", marks: "Anon") -> Verdict:
    if hit is not None:                                              # row 4
        entry, path = hit
        down = downgrades.on_path(reach, store, entry, path)
        if down is not None:
            return down
        last = path.steps[-1] if path.steps else None
        return _verdict(store, "erased", path=path.as_list(),
                        evidence=[_cite(last.file, last.line, store.id)] if last else [],
                        reasons=sorted({s.rule for s in path.steps} | {"03-verifier.md 6.1 row 4"}),
                        note=f"reached from entry point {entry.name} ({entry.file}:{entry.line})")
    if marks.verdict == "anonymised":                                # row 5
        return _verdict(store, "anonymised", evidence=marks.evidence, reasons=["03-verifier.md 4.7"],
                        note="every detected column is overwritten with a constant on the path")
    if timer is not None and timer.days is not None:                 # row 6
        return _verdict(store, "erased_after_timer", timer_days=timer.days,
                        evidence=timer.cites, reasons=["R25", "03-verifier.md 6.2"],
                        note=timer.note)
    if marks.verdict == "pseudonymised":                             # row 7
        return _verdict(store, "pseudonymised", evidence=marks.evidence,
                        reasons=["03-verifier.md 4.7"],
                        note="the value is replaced by a reversible or still-linked token [S12]")
    reason = downgrades.unverified_reason(reach, store, hit, loose, marks)
    if reason is not None:                                           # row 8
        note, rules_hit, cites = reason
        return _verdict(store, "unverified", note=note, reasons=rules_hit, evidence=cites)
    # 6.2: "All five required, or the verdict falls back to row 9." A timer that got
    # as far as a scheduled job and no number is that fallback, and its note is the
    # one a reader needs -- not row 9's generic "nothing reaches this store".
    note = timer.note if timer is not None else downgrades.not_erased_note(reach, store)
    return _verdict(store, "not_erased", reasons=["03-verifier.md 6.1 row 9"],  # row 9
                    evidence=timer.cites if timer is not None else [], note=note)


def _field_overrides(store: Store, verdict: Verdict,
                     marks: "Anon") -> dict[str, Verdict]:
    """00-contract.md: a field whose fate differs from its store carries its own block.

    Only where 4.7 decided the store (rows 5 and 7): a store that is `erased` takes its
    columns with it, and a store nothing reaches leaves them all where they are.
    """
    if verdict.verdict not in {"anonymised", "pseudonymised"}:
        return {}
    out: dict[str, Verdict] = {}
    for column, name in sorted(marks.fields.items()):
        if name == verdict.verdict:
            continue
        write = marks.writes.get(column)
        out[column] = Verdict(store=store.id, verdict=name, kind=store.kind,
                              guard=store.guard, reasons=["03-verifier.md 4.7"],
                              evidence=[_cite(write.file, write.line, column)] if write else [],
                              note="" if write else "no assignment on the path touches this column")
    return out
