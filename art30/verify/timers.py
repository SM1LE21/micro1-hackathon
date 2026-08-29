"""Timers: `erased_after_timer` and the retention numbers (03-verifier.md 6.2, 6.3).

Five conditions, all required, or the verdict falls back to row 9 of the 6.1 table:
a soft-delete marker written by the erasure entry point (R25), a job entry point with
a resolved path to a hard delete for that store, **a schedule registration citation**
for that job, an integer number of days, and a `file:line` for all four.

Requirement 3 is the one the decorator does not supply (decision 20). `@shared_task`
makes a function a candidate; it is never on its own evidence that anything runs it,
and without the join an unscheduled purge job renders `erased_after_timer` while the
rows survive for ever. Row 1's backup schedule is read the same way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from art30.verify.entities import Symbol
from art30.verify.findings import EntryPoint, Graph, Store
from art30.verify.registration import schedule_evidence

if TYPE_CHECKING:                       # `reach.py` owns the walk this module reads
    from art30.verify.entities import Assign
    from art30.verify.reach import Reach
    from art30.verify.rules import RuleSet

HOURS_PER_DAY = 24
# 2.2, 6.2: the two entry-point kinds a scheduled job can have. `reach.py` reads it
# from here so the row-4 walk and 6.2 never disagree about what a job is.
JOB_KINDS = ("cli", "task")


@dataclass
class Timer:
    """What 6.2 found, with every half citable (requirement 5)."""

    days: int | None = None
    job: EntryPoint | None = None
    cites: list[dict] = field(default_factory=list)
    note: str = ""
    criteria: str = ""             # 6.3: a cadence that is not a number of days


def _cite(file: str, line: int, symbol: str = "") -> dict:
    return {"file": file, "line": int(line), "symbol": symbol}


# ---------------------------------------------------------------------------
# 6.3 timer parsing
# ---------------------------------------------------------------------------
def _int(text: str) -> int | None:
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def _day_kwargs(rules: "RuleSet") -> tuple[tuple[str, int], ...]:
    """6.3's day-bearing keywords: `days`, `hours` rounded down, and the S3 lifecycle
    keys the rule data names (`Days`, `NoncurrentDays`), which are already in days."""
    patterns = rules.patterns["timers"]["day_patterns"]
    keys = [n for p in patterns for n in (p.get("s3_lifecycle_keys") or ())]
    return (("days", 1), ("hours", HOURS_PER_DAY)) + tuple((k, 1) for k in sorted(keys))


def parse_days(reach: "Reach", symbol: Symbol) -> tuple[int | None, dict | None]:
    """6.3: `timedelta(days=N)`, `days=N`, `timedelta(hours=N)`, a module constant,
    a `settings.X` that resolves to a module-level integer, or an S3 lifecycle `Days`.

    A cadence is deliberately not a number here: a job that runs every seven days and
    deletes rows older than thirty has a thirty-day timer, and reading the schedule as
    the retention period would understate it. 6.3 renders a cadence as a `criteria`
    string instead, which `_criteria` builds.
    """
    graph, rules = reach.graph, reach.rules
    patterns = rules.patterns["timers"]["day_patterns"]
    constants = {n for p in patterns for n in (p.get("constant_names") or ())}
    sites = sorted((c for c in graph.calls if c.caller == symbol.name),
                   key=lambda c: (c.line, c.dotted or c.name))
    for site in sites:
        for kwarg, divisor in _day_kwargs(rules):
            arg = site.keywords.get(kwarg)
            if arg is None:
                continue
            direct = _int(arg.value) if arg.kind == "literal" else None
            if direct is not None:
                return (max(1, direct // divisor), _cite(site.file, site.line, kwarg))
            if arg.kind in {"name", "attribute"}:
                found = _constant(graph, symbol.module, str(arg.value))
                if found is not None:
                    value = _int(found[0].value_repr)
                    if value is not None:
                        return (max(1, value // divisor),
                                _cite(found[1], found[0].line, found[0].target))
    for name in sorted(constants):           # a retention constant beside the job
        found = _constant(graph, symbol.module, name, exact=True)
        value = _int(found[0].value_repr) if found else None
        if value is not None:
            return (value, _cite(found[1], found[0].line, found[0].target))
    return (None, None)


def _constant(graph: Graph, module: str, name: str,
              exact: bool = False) -> "tuple[Assign, str] | None":
    """A module-level literal: the job's own module first, then a unique repo match.

    `exact` keeps a retention constant to the module that declares the job, so a
    `RETENTION_DAYS` belonging to another feature never becomes this job's timer.
    """
    short = str(name).split(".")[-1]
    order = [module] if exact else (
        ([module] if module in graph.modules else []) + sorted(graph.modules))
    for candidate in order:
        info = graph.modules.get(candidate)
        for assign in info.assigns if info else []:
            if assign.target == short and assign.value_kind == "literal":
                return (assign, info.file)
    return None


# ---------------------------------------------------------------------------
# 6.2 erased_after_timer
# ---------------------------------------------------------------------------
def markers(reach: "Reach", store: Store) -> list[dict]:
    """Requirement 1 (R25): *the erasure entry point* writes a soft-delete marker.

    Scoped to the non-job starts on purpose. `writes_for` walks every start node, the
    purge job included, so a marker written inside the job itself -- or by an unrelated
    task -- satisfied requirement 1 and could open the `erased_after_timer` row for a
    store whose user-facing path never marks anything. 6.2 requirement 1 names the
    erasure entry point, and a job is the *other* half of the shape (requirement 2).
    """
    from art30.verify import anon

    out = []
    entries = [e for e in reach.starts if e.kind not in JOB_KINDS]
    for write in anon.writes_for(reach, store, entries).values():
        if write.kind == anon.MARKER:
            out.append(_cite(write.file, write.line, write.field))
    return sorted(out, key=lambda c: (c["file"], c["line"]))


def schedule_for(reach: "Reach", entry: EntryPoint) -> tuple[str, str, int] | None:
    """Requirement 3: the registration citation, from the graph's own two halves.

    A module interface rather than a private call: 6.1's row-4 walk has to ask the same
    question of every job entry point, not only of the one a `Timer` was built for.
    """
    symbol = reach.graph.symbols.get(entry.symbol or "")
    if symbol is None:
        return None
    for decorator in symbol.decorators:
        found = schedule_evidence(reach.graph, reach.rules, symbol, decorator)
        if found:
            return found
    return None


def erased_after_timer(reach: "Reach", store: Store) -> Timer | None:
    """6.2: requirements 1 to 3, with `days` set only where 4 and 5 also hold.

    A `Timer` with `days=None` is the fourth requirement failing on a job that does
    satisfy the first three, and it is returned rather than swallowed because 6.2 says
    the verdict then "falls back to row 9": the job's own path has to leave row 4 too,
    or a purge whose retention period is an environment variable renders `erased` and
    the record says the data is gone today when it survives an unknown number of days.
    """
    marks = markers(reach, store)
    if not marks:                                            # requirement 1
        return None
    for entry in reach.jobs:                                 # requirement 2, sorted
        hit = reach.reached(store.node, resolved_only=True, only=entry)
        if hit is None or entry.symbol is None:
            continue
        found = schedule_for(reach, entry)                   # requirement 3
        if found is None:
            continue
        symbol = reach.graph.symbols[entry.symbol]
        days, cite = parse_days(reach, symbol)               # requirement 4
        if days is None or cite is None:
            _how, file, line = found
            return Timer(days=None, job=entry, cites=list(marks),
                         criteria=f"the schedule cited at {file}:{line}",
                         note=(f"{entry.name} ({entry.file}:{entry.line}) purges on a "
                               f"schedule registered at {file}:{line}, and no retention "
                               "period in the repository resolves to a number of days "
                               "(6.3); the record renders no_timer_evidenced"))
        _how, file, line = found
        path = hit[1]
        last = path.steps[-1] if path.steps else None
        cites = list(marks) + [_cite(file, line, entry.name), cite]
        if last is not None:
            cites.append(_cite(last.file, last.line, entry.name))
        return Timer(days=days, job=entry, cites=sorted(
            cites, key=lambda c: (c["file"], c["line"], c["symbol"])),
            note=(f"soft delete at {marks[0]['file']}:{marks[0]['line']}; "
                  f"{entry.name} purges after {days} days, scheduled at {file}:{line}"))
    return None


def unscheduled_note(reach: "Reach", store: Store) -> str:
    """6.2's negative twin: the job exists and nothing in the repository runs it.

    Asked of every job entry point and not only of the ones `_tasks` flagged, because
    the flag is written by the task branch of discovery alone: a `BaseCommand` under
    `management/commands/` and a `@click.command` are kind `cli` and carry no flag, and
    a purge reached only from one of those had to fall back to row 9's generic "defined
    but no entry point reaches it" -- which reads as a helper nobody wired up rather
    than as the thing 6.2 requirement 3 actually found.
    """
    for entry in reach.entries:
        if entry.kind not in JOB_KINDS:
            continue
        if "unscheduled" not in entry.flags and schedule_for(reach, entry) is not None:
            continue
        if reach.reached(store.node, resolved_only=False, only=entry, ignore_starts=True):
            return (f"purge job defined at {entry.file}:{entry.line}, "
                    "nothing in the repository schedules it (6.2 requirement 3)")
    return ""


# ---------------------------------------------------------------------------
# 6.1 row 1: the backup schedule
# ---------------------------------------------------------------------------
def backup_retention(reach: "Reach", store: Store) -> Timer:
    """Row 1: `governed_by_retention` with a cited schedule, else `no_schedule_evidenced`.

    A cron expression or a `crontab(...)` is a schedule that parses but is not a number
    of days, so 6.3's last row applies: no number, and a `criteria` string quoting the
    source line. The verdict still turns on whether anything was cited at all.
    """
    graph, rules = reach.graph, reach.rules
    file = store.declared_at.file if store.declared_at else ""
    module = next((m.module for m in graph.modules.values() if m.file == file), "")
    cites: list[dict] = []
    criteria = ""
    days = None
    names = {n for p in rules.patterns["timers"]["day_patterns"]
             for n in (p.get("constant_names") or ())}
    info = graph.modules.get(module)
    for name in sorted(names):
        for assign in info.assigns if info else []:
            if assign.target != name or assign.value_kind != "literal":
                continue
            value = _int(assign.value_repr)
            if value is not None and days is None:
                days = value
                cites.append(_cite(file, assign.line, name))
    for entry in sorted(graph.settings.get("schedules") or [],
                        key=lambda s: (s["file"], s["line"])):
        if entry["file"] == file or module in set(entry.get("names") or ()):
            cites.append(_cite(entry["file"], entry["line"], str(entry.get("how", ""))))
            criteria = criteria or _criteria(graph, entry)
    note = "a dump is governed by its retention schedule, not by erasure"
    if days is None and criteria:
        note = f"{note}; {criteria}"
    return Timer(days=days, criteria=criteria, note=note,
                 cites=sorted(cites, key=lambda c: (c["file"], c["line"], c["symbol"])))


def _criteria(graph: Graph, entry: dict) -> str:
    """6.3's last row: a `criteria` string quoting the source line, never a number."""
    info = next((m for m in graph.modules.values() if m.file == entry["file"]), None)
    lines = info.source.splitlines() if info else []
    index = int(entry["line"]) - 1
    text = lines[index].strip() if 0 <= index < len(lines) else ""
    where = f'{entry["file"]}:{entry["line"]}'
    return f'the schedule at {where} reads "{text}"' if text else f"a schedule at {where}"
