"""What the repository says can invoke a symbol from outside (03-verifier.md 2.2, 6.2).

Two registrations that entry-point discovery has to ask about and that are too big to
live beside it: the Django admin of R16 [S8] [S9], where the `ModelAdmin` of *one*
model may deny deletion for that model alone, and the schedule registration 6.2
requirement 3 demands before a `@shared_task` is allowed to be evidence that anything
ever runs the job.
"""

from __future__ import annotations

from art30.verify import imports as importmap
from art30.verify.entities import Decorator, Symbol
from art30.verify.findings import EntryPoint, Graph
from art30.verify.rules import RuleSet

ADMIN_NAMES = ("admin_delete_model", "admin_delete_selected")


# ---------------------------------------------------------------------------
# 6.2 requirement 3: a schedule registration, cited
# ---------------------------------------------------------------------------
def _task_names(graph: Graph, symbol: Symbol) -> set[str]:
    """2.4: every task-name string that resolves to this symbol, plus its own names."""
    named = {name for name, target in graph.task_table.items() if target == symbol.name}
    return named | {symbol.short, symbol.name}


def schedule_evidence(graph: Graph, rules: RuleSet, symbol: Symbol,
                      decorator: Decorator) -> tuple[str, str, int] | None:
    """6.2 requirement 3: what in the repository says this job ever runs, and where.

    "The `task` decorator makes a function an entry-point *candidate*; it is never on
    its own evidence that anything runs it" (2.2). The graph holds both halves --
    `task_table` and `settings["schedules"]` -- and joining them here is what lets a
    verdict honour requirement 3 mechanically: an unscheduled `@shared_task
    purge_closed_accounts` otherwise reaches 6.1 row 4 (a hard-delete primitive on a
    resolved path) and renders `erased` before requirement 3 is ever consulted, which
    is test 37a's expected `not_erased` inverted into a false safe.
    """
    names = _task_names(graph, symbol)
    for key in ("run_every", "schedule", "crontab"):
        if key in decorator.keywords:
            return (key, decorator.file, decorator.line)
    for entry in sorted(graph.settings.get("schedules") or [],
                        key=lambda s: (s["file"], s["line"])):
        if names & set(entry.get("names") or []):
            return (str(entry.get("how", "schedule")), entry["file"], entry["line"])
    dispatch = set(rules.entry["celery_task_names"]["dispatch_calls"]) | {"add_periodic_task"}
    for site in sorted(graph.calls, key=lambda c: (c.file, c.line)):
        if site.name not in dispatch:
            continue
        written = {str(arg.value) for arg in site.args}
        written |= {str(value.value) for value in site.keywords.values()}
        if site.receiver:
            written |= {site.receiver, site.receiver.split(".")[-1]}
        if names & written:
            return (site.name, site.file, site.line)
    return None


# ---------------------------------------------------------------------------
# R16: the admin, per model
# ---------------------------------------------------------------------------
def _registrations(graph: Graph, rules: RuleSet,
                   imap: importmap.ImportMap) -> list[tuple[str, str, int]]:
    """The registered models, each with the citation the registration carries."""
    registers = set(rules.entry["django"]["admin"]["register_calls"])
    file_to_module = {m.file: m.module for m in graph.modules.values()}
    found: list[tuple[str, str, int]] = []
    for site in sorted(graph.calls, key=lambda c: (c.file, c.line)):
        dotted = site.dotted or site.name
        if dotted not in registers and site.name != "register":
            continue
        module = file_to_module.get(site.file, "")
        for arg in site.args[:1]:
            found.append((imap.resolve_dotted(module, None, str(arg.value)),
                          site.file, site.line))
    for symbol in sorted(graph.symbols.values(), key=lambda s: s.name):
        for decorator in symbol.decorators:
            if decorator.name != "register" or not decorator.args:
                continue
            found.append((imap.resolve_dotted(symbol.module, None, decorator.args[0]),
                          decorator.file, decorator.line))
    return found


def _class_named(graph: Graph, imap: importmap.ImportMap, module: str,
                 written: str) -> str:
    """A class as written -> its qualified name: imported, or defined right here."""
    for candidate in (imap.resolve_dotted(module, None, written),
                      f"{module}.{written}" if module else written):
        if candidate in graph.classes:
            return candidate
    return ""


def _admin_classes(graph: Graph, rules: RuleSet,
                   imap: importmap.ImportMap) -> dict[str, str]:
    """model qualname -> the `ModelAdmin` registered for it, from either shape."""
    registers = set(rules.entry["django"]["admin"]["register_calls"])
    file_to_module = {m.file: m.module for m in graph.modules.values()}
    found: dict[str, str] = {}
    for site in sorted(graph.calls, key=lambda c: (c.file, c.line)):
        dotted = site.dotted or site.name
        if (dotted not in registers and site.name != "register") or len(site.args) < 2:
            continue
        module = file_to_module.get(site.file, "")
        model = imap.resolve_dotted(module, None, str(site.args[0].value))
        admin = _class_named(graph, imap, module, str(site.args[1].value))
        if model and admin:
            found.setdefault(model, admin)
    for qual, cls in sorted(graph.classes.items()):
        for decorator in cls.decorators:
            if decorator.name == "register" and decorator.args:
                model = imap.resolve_dotted(cls.module, None, decorator.args[0])
                if model:
                    found.setdefault(model, qual)
    return found


def _denies_deletion(graph: Graph, admin_class: str) -> bool:
    """2.2: a `ModelAdmin` whose `has_delete_permission` is a bare `return False`.

    Scoped to the one admin class, and restricted to a method whose *only* return is
    `return False`: the repository-wide text scan took both admin entry points away for
    every registered model as soon as one unrelated `ModelAdmin` denied deletion for one
    model, or a conditional `if obj.is_locked: return False` appeared anywhere. The text
    test stays the documented approximation.
    """
    for symbol in sorted(graph.symbols.values(), key=lambda s: s.name):
        if symbol.short != "has_delete_permission" or symbol.owner != admin_class:
            continue
        module = graph.modules.get(symbol.module)
        if module is None:
            continue
        body = module.source.splitlines()[symbol.line - 1: symbol.end_line]
        returns = [line.strip() for line in body if line.strip().startswith("return")]
        if len(returns) == 1 and returns[0] == "return False":
            return True
    return False


def admin_entry_points(graph: Graph, rules: RuleSet,
                       imap: importmap.ImportMap) -> list[EntryPoint]:
    """R16 [S8] [S9]: two admin entry points, over the models the admin still deletes."""
    admin = rules.entry["django"]["admin"]
    classes = _admin_classes(graph, rules, imap)
    models: list[str] = []
    cite: tuple[str, int] | None = None
    for model, file, line in _registrations(graph, rules, imap):
        store = graph.store_for_model(model)
        if store is None or not (store.guard or store.subject_link):
            continue
        admin_class = classes.get(model)
        if admin_class and _denies_deletion(graph, admin_class):
            continue                     # 2.2: this model only, never the repository
        models.append(model)
        if cite is None:
            cite = (file, line)
    if not models or cite is None:
        return []
    modes = {entry["name"]: entry["mode"] for entry in admin["entry_points"]}
    return [
        EntryPoint(name=name, kind="admin", file=cite[0], line=cite[1], admin_only=True,
                   sets_mode=modes[name], models=sorted(set(models)),
                   flags=["admin_registration"])
        for name in ADMIN_NAMES
    ]
