"""Entry-point discovery and reconciliation (03-verifier.md section 2).

An entry point is where a person's account deletion begins, and a deletion
primitive no entry point reaches is not erasure (AMBIGUITIES row 2 reading B).
The HTTP method is never the qualification: a DELETE route is an erasure entry
point only when its name matches the 2.1 vocabulary, the model it deletes is the
subject root, or its terminal path segment names the subject (decision 6a).
"""

from __future__ import annotations

from art30.verify import imports as importmap
from art30.verify.entities import Symbol
from art30.verify.findings import EntryPoint, Graph
from art30.verify.registration import (ADMIN_NAMES, admin_entry_points,
                                       schedule_evidence)
from art30.verify.rules import RuleSet

__all__ = ["ADMIN_NAMES", "discover_entry_points", "task_table"]


def task_table(graph: Graph, rules: RuleSet) -> dict[str, str]:
    """2.4: task name string -> symbol. Celery defaults to `module.function`."""
    names = {d["name"] for d in rules.entry["decorators"]["task"]}
    override = rules.entry["celery_task_names"]["override_kwarg"]
    table: dict[str, str] = {}
    for symbol in sorted(graph.symbols.values(), key=lambda s: s.name):
        for decorator in symbol.decorators:
            if decorator.name not in names:
                continue
            given = decorator.keywords.get(override, "")
            table[given or f"{symbol.module}.{symbol.short}"] = symbol.name
    return table


def _methods(decorator, keys: list[str]) -> set[str]:
    text = ",".join([decorator.keywords.get("methods", "")] + list(decorator.args))
    return {part.strip().upper() for part in text.split(",") if part.strip()}


def _deletes_subject_root(graph: Graph, symbol: Symbol) -> bool:
    """Qualifier 2: the model the handler deletes resolves to a subject root."""
    roots = {s.model for s in graph.stores.values() if s.subject_root and s.model}
    for var, model in sorted(symbol.var_models.items()):
        if model in roots:
            return True
    return False


def _qualifies(graph: Graph, rules: RuleSet, symbol: Symbol, path: str) -> bool:
    if rules.vocabulary_hit(symbol.short):
        return True
    if _deletes_subject_root(graph, symbol):
        return True
    return rules.subject_path_segment(path)


def discover_entry_points(graph: Graph, rules: RuleSet,
                          imap: importmap.ImportMap) -> list[EntryPoint]:
    found: list[EntryPoint] = []
    claimed: set[str] = set()
    found += _routes(graph, rules, claimed)
    found += _url_rules(graph, rules, imap, claimed)
    found += _viewsets(graph, rules, imap, claimed)
    found += _urlpatterns(graph, rules, imap, claimed)
    found += _commands(graph, rules, claimed)
    found += _tasks(graph, rules, claimed)
    found += admin_entry_points(graph, rules, imap)
    found += _unclaimed(graph, rules, claimed)
    return sorted(found, key=lambda e: e.key())


def _routes(graph: Graph, rules: RuleSet, claimed: set[str]) -> list[EntryPoint]:
    specs = rules.entry["decorators"]["route"]
    out: list[EntryPoint] = []
    for symbol in sorted(graph.symbols.values(), key=lambda s: s.name):
        for decorator in symbol.decorators:
            spec = next((s for s in specs if s["name"] == decorator.name), None)
            if spec is None:
                continue
            wanted = {m.upper() for m in (spec.get("kwarg_methods") or [])}
            if wanted and not (wanted & _methods(decorator, [])):
                continue
            path = decorator.args[0] if decorator.args else ""
            if not _qualifies(graph, rules, symbol, path):
                continue
            claimed.add(symbol.name)
            out.append(EntryPoint(name=symbol.short, kind="route", file=symbol.file,
                                  line=symbol.line, symbol=symbol.name, path=path,
                                  flags=["route_decorator"]))
            break
    return out


def _url_rules(graph: Graph, rules: RuleSet, imap: importmap.ImportMap,
               claimed: set[str]) -> list[EntryPoint]:
    """2.2 route row, the non-decorator form: Flask's `add_url_rule`.

    `app.add_url_rule("/account", "delete_user", delete_user, methods=["DELETE"])`
    registers a handler no decorator scan can see. Without it the function is an entry
    point only where its name happens to hit the vocabulary, and a record that declares
    one whose name does not is capped `declared_unregistered` under 2.5 with the
    registration in plain sight. The subject qualification of decision 6a binds this
    shape exactly as it binds a decorated route.
    """
    spec = rules.entry["route_registration"]
    calls, index = set(spec["calls"]), int(spec["view_func_positional"])
    file_to_module = {m.file: m.module for m in graph.modules.values()}
    out: list[EntryPoint] = []
    for site in sorted(graph.calls, key=lambda c: (c.file, c.line)):
        if site.name not in calls:
            continue
        given = site.keywords.get(spec["view_func_kwarg"])
        written = str(given.value) if given is not None else (
            str(site.args[index].value) if len(site.args) > index else "")
        target = _view_symbol(graph, imap, file_to_module.get(site.file, ""), written)
        if target is None or target.name in claimed:
            continue
        methods = site.keywords.get(spec["methods_kwarg"])
        wanted = {m.strip().upper() for m in (methods.keys if methods else [])}
        if "DELETE" not in wanted:
            continue
        path = str(site.args[0].value) if site.args else ""
        if not _qualifies(graph, rules, target, path):
            continue
        claimed.add(target.name)
        out.append(EntryPoint(name=target.short, kind="route", file=target.file,
                              line=target.line, symbol=target.name, path=path,
                              flags=["route_registration"]))
    return out


def _viewsets(graph: Graph, rules: RuleSet, imap: importmap.ImportMap,
              claimed: set[str]) -> list[EntryPoint]:
    """DRF: `destroy` on a viewset whose queryset names the user model (2.2)."""
    bases = set(rules.entry["drf"]["viewset_bases"])
    destroy = set(rules.entry["drf"]["destroy_methods"])
    roots = {s.model for s in graph.stores.values() if s.subject_root and s.model}
    out: list[EntryPoint] = []
    for qual, cls in sorted(graph.classes.items()):
        if not any(base.split(".")[-1] in bases or base.split(".")[-1].endswith("ViewSet")
                   for base in cls.bases):
            continue
        model = ""
        for assign in cls.body:
            if assign.target in set(rules.entry["drf"]["queryset_attrs"]):
                for ref in assign.refs:
                    dotted = imap.resolve_dotted(cls.module, None, ref)
                    if dotted in roots:
                        model = dotted
        for symbol in sorted(graph.symbols.values(), key=lambda s: s.name):
            if symbol.owner != qual:
                continue
            is_destroy = symbol.short in destroy
            action = any(d.name == "action" and "DELETE" in _methods(d, [])
                         for d in symbol.decorators)
            if not (is_destroy or action):
                continue
            if not model and not rules.vocabulary_hit(symbol.short):
                continue
            claimed.add(symbol.name)
            out.append(EntryPoint(name=symbol.short, kind="route", file=symbol.file,
                                  line=symbol.line, symbol=symbol.name,
                                  models=[model] if model else [], flags=["drf_viewset"]))
    return out


def _urlpatterns(graph: Graph, rules: RuleSet, imap: importmap.ImportMap,
                 claimed: set[str]) -> list[EntryPoint]:
    """CG-17: a view named in `urlpatterns` is a declaration, not a call edge."""
    calls = set(rules.entry["django"]["urlconf_calls"])
    out: list[EntryPoint] = []
    file_to_module = {m.file: m.module for m in graph.modules.values()}
    for site in sorted(graph.calls, key=lambda c: (c.file, c.line)):
        if site.name not in calls or len(site.args) < 2:
            continue
        module = file_to_module.get(site.file, "")
        path = str(site.args[0].value)
        written = site.args[1].value
        target = _view_symbol(graph, imap, module, written)
        if target is None or target.name in claimed:
            continue
        # 2.2 `view` row: the name or the URL pattern matches the vocabulary. The
        # subject-path qualifier belongs to a DELETE route, where the method is known;
        # a urlpattern carries no method, and `/accounts/<pk>/profile/` is a GET view.
        if not (rules.vocabulary_hit(target.short) or rules.vocabulary_hit(path)):
            continue
        claimed.add(target.name)
        out.append(EntryPoint(name=target.short, kind="view", file=target.file,
                              line=target.line, symbol=target.name, path=path,
                              flags=["urlpatterns_reference"]))
    out += _delete_views(graph, rules, claimed)
    return out


def _view_symbol(graph: Graph, imap: importmap.ImportMap, module: str,
                 written: str) -> Symbol | None:
    if not written:
        return None
    dotted = imap.resolve_dotted(module, None, written)
    for candidate in (dotted, f"{module}.{written}" if module else written):
        if candidate in graph.symbols:
            return graph.symbols[candidate]
    short = written.split(".")[-1]
    matches = [s for s in graph.symbols.values() if s.short == short and not s.owner]
    return matches[0] if len(matches) == 1 else None


def _delete_views(graph: Graph, rules: RuleSet, claimed: set[str]) -> list[EntryPoint]:
    bases = set(rules.entry["django"]["delete_view_bases"])
    out: list[EntryPoint] = []
    for qual, cls in sorted(graph.classes.items()):
        if not any(base.split(".")[-1] in bases for base in cls.bases):
            continue
        # The base already says this view deletes; the subject is the qualification
        # (decision 6a), and `AccountDeleteView` names it.
        if not (rules.vocabulary_hit(cls.short) or rules.subject_word(cls.short)):
            continue
        methods = [s for s in sorted(graph.symbols.values(), key=lambda s: s.name)
                   if s.owner == qual and s.short in {"delete", "form_valid"}]
        for symbol in methods or []:
            claimed.add(symbol.name)
            out.append(EntryPoint(name=symbol.short, kind="view", file=symbol.file,
                                  line=symbol.line, symbol=symbol.name,
                                  flags=["delete_view"]))
        if not methods:
            out.append(EntryPoint(name=cls.short, kind="view", file=cls.file,
                                  line=cls.line, flags=["delete_view"]))
    return out


def _commands(graph: Graph, rules: RuleSet, claimed: set[str]) -> list[EntryPoint]:
    base = rules.entry["django"]["management_command_base"]
    click = set(rules.entry["cli_frameworks"]["click"]["decorators"])
    out: list[EntryPoint] = []
    for qual, cls in sorted(graph.classes.items()):
        if not any(b.split(".")[-1] == base for b in cls.bases):
            continue
        command = cls.file.rsplit("/", 1)[-1][:-3]
        handle = graph.symbols.get(f"{qual}.handle")
        qualifies = bool(rules.vocabulary_hit(command))
        if not qualifies and handle is not None:
            qualifies = any(rules.vocabulary_hit(call.name)
                            for call in graph.calls if call.caller == handle.name)
        if not qualifies:
            continue
        target = handle or None
        claimed.add(target.name if target else qual)
        out.append(EntryPoint(name=command, kind="cli",
                              file=target.file if target else cls.file,
                              line=target.line if target else cls.line,
                              symbol=target.name if target else None,
                              flags=["BaseCommand_subclass"]))
    for symbol in sorted(graph.symbols.values(), key=lambda s: s.name):
        for decorator in symbol.decorators:
            if decorator.name not in click:
                continue
            name = decorator.args[0] if decorator.args else symbol.short
            if not (rules.vocabulary_hit(name) or rules.vocabulary_hit(symbol.short)):
                continue
            claimed.add(symbol.name)
            out.append(EntryPoint(name=symbol.short, kind="cli", file=symbol.file,
                                  line=symbol.line, symbol=symbol.name,
                                  flags=["click_or_typer_command"]))
            break
    return out


def _tasks(graph: Graph, rules: RuleSet, claimed: set[str]) -> list[EntryPoint]:
    """A task decorator makes a candidate; the 2.1 vocabulary decides (6.2 req. 4).

    The decorator is never on its own evidence that anything runs the job (2.2), so the
    start node carries the 6.2 requirement 3 join beside it: `schedule_registered` with
    the citation, or `unscheduled` with the note. Both halves were already in the graph
    -- `task_table` and `settings["schedules"]` -- and nothing joined them.
    """
    names = {d["name"] for d in rules.entry["decorators"]["task"]}
    out: list[EntryPoint] = []
    for symbol in sorted(graph.symbols.values(), key=lambda s: s.name):
        if symbol.name in claimed:
            continue
        for decorator in symbol.decorators:
            if decorator.name not in names or not rules.vocabulary_hit(symbol.short):
                continue
            claimed.add(symbol.name)
            found = schedule_evidence(graph, rules, symbol, decorator)
            flags = ["task_decorator", "schedule_registered" if found else "unscheduled"]
            note = (f"schedule registered at {found[1]}:{found[2]} ({found[0]})"
                    if found else
                    "task decorator only; nothing in the repository schedules it "
                    "(6.2 requirement 3)")
            out.append(EntryPoint(name=symbol.short, kind="task", file=symbol.file,
                                  line=symbol.line, symbol=symbol.name,
                                  flags=flags, note=note))
            break
    return out


def _unclaimed(graph: Graph, rules: RuleSet, claimed: set[str]) -> list[EntryPoint]:
    """2.2 last row: a module-level function nothing else claimed, kind `unknown`."""
    out: list[EntryPoint] = []
    for symbol in sorted(graph.symbols.values(), key=lambda s: s.name):
        if symbol.name in claimed or symbol.owner or symbol.is_nested:
            continue
        if not rules.vocabulary_hit(symbol.short):
            continue
        out.append(EntryPoint(name=symbol.short, kind="unknown", file=symbol.file,
                              line=symbol.line, symbol=symbol.name))
    return out
