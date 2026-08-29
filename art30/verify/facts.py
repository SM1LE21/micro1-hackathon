"""The framework facts the synthetic edges rest on (03-verifier.md 4.4, 4.5, R9-R12).

`INSTALLED_APPS` and the django-cleanup mode with 4.4's split-settings routing, the
schedule registrations 6.2 requirement 3 asks for, the receivers of R9 to R12 with
their sender and their connection, and the enforcing-engine evidence of R6 bound to
the engine the delete's session is built from and never to the repository.
"""

from __future__ import annotations

import re

from art30.verify import imports as importmap
from art30.verify.findings import Graph, Receiver
from art30.verify.rules import RuleSet, norm


def settings_facts(graph: Graph, rules: RuleSet) -> None:
    """R10 [S13] and R6: INSTALLED_APPS, AUTH_USER_MODEL, engines and schedules."""
    apps: dict[str, list[str]] = {}
    facts: dict[str, object] = {}
    engines: list[dict] = []
    schedules: list[dict] = []
    for module in sorted(graph.modules):
        info = graph.modules[module]
        for assign in info.assigns:
            if assign.target == "INSTALLED_APPS":
                apps[module] = sorted(assign.keys)
            elif assign.target == "AUTH_USER_MODEL" and assign.value_kind == "literal":
                facts["AUTH_USER_MODEL"] = assign.value_repr
            elif assign.target == "DATABASES":
                for key in assign.keys:
                    if key.startswith("django.db.backends."):
                        engines.append({"file": info.file, "line": assign.line,
                                        "url": key, "var": "DATABASES"})
            elif assign.target in {"CELERYBEAT_SCHEDULE", "beat_schedule",
                                   "CELERY_BEAT_SCHEDULE"}:
                schedules.append({"file": info.file, "line": assign.line,
                                  "names": sorted(assign.keys), "how": assign.target})
            elif assign.value_kind == "literal" and re.fullmatch(
                r"([-*/,0-9]+\s+){4}[-*/,0-9]+", assign.value_repr or ""
            ):
                schedules.append({"file": info.file, "line": assign.line,
                                  "names": [module], "how": "cron_literal"})
    for site in sorted(graph.calls, key=lambda c: (c.file, c.line)):
        if site.name in {"create_engine"}:
            engines.append({"file": site.file, "line": site.line,
                            "url": _engine_url(graph, site), "var": ""})
        if site.name in {"crontab", "add_periodic_task"}:
            schedules.append({"file": site.file, "line": site.line, "names": [],
                              "how": site.name})
    facts["installed_apps"] = {k: v for k, v in sorted(apps.items())}
    facts["engines"] = engines
    facts["schedules"] = schedules
    facts["cleanup"] = _cleanup_mode(rules, apps)
    graph.settings.update(facts)


def _engine_url(graph: Graph, site) -> str:
    if site.args and site.args[0].kind == "literal":
        return str(site.args[0].value)
    if site.args and site.args[0].kind in {"name", "attribute"}:
        name = str(site.args[0].value).split(".")[-1]
        for module in graph.modules.values():
            for assign in module.assigns:
                if assign.target == name and assign.value_kind == "literal":
                    return assign.value_repr
    return ""


def _cleanup_mode(rules: RuleSet, apps: dict[str, list[str]]) -> str:
    """R10 [S13], with 4.4's split-settings routing: intersection for a reaching verdict."""
    data = rules.primitives["django_cleanup"]
    modes: set[str] = set()
    for labels in apps.values():
        if data["select_mode_label"] in labels:
            modes.add("SELECT")
        elif set(labels) & set(data["active_labels"]):
            modes.add("ALL")
        else:
            modes.add("OFF")
    if not modes:
        return "OFF"
    if len(modes) > 1:
        return "DISAGREE"
    return modes.pop()


def _loaded_modules(graph: Graph) -> set[str]:
    """R12 [S6]: the modules Django loads on its own, plus what they import."""
    apps = graph.settings.get("installed_apps") or {}
    labels = {label.split(".")[0] for labels in apps.values() for label in labels}
    seeds = {f"{label}.models" for label in labels} | {f"{label}.apps" for label in labels}
    if not apps:                       # not a Django settings tree: anything imported
        seeds = {m for m in graph.modules}
    loaded = {m for m in seeds if m in graph.modules}
    frontier = list(loaded)
    while frontier:
        current = frontier.pop()
        info = graph.modules.get(current)
        if info is None:
            continue
        for kind, dotted in list(info.imports.values()):
            if dotted in graph.modules and dotted not in loaded:
                loaded.add(dotted)
                frontier.append(dotted)
        for scope, bindings in graph.settings.get("_local_imports", {}).items():
            if scope.startswith(f"{current}."):
                for dotted in bindings:
                    if dotted in graph.modules and dotted not in loaded:
                        loaded.add(dotted)
                        frontier.append(dotted)
    return loaded


def _receivers(graph: Graph, rules: RuleSet, imap: importmap.ImportMap) -> None:
    """R9, R11, R12: the decorator form and the `.connect()` form, read the same way."""
    data = rules.primitives["django_signals"]
    signals = set(data["delete_signals"])
    loaded = _loaded_modules(graph)
    for symbol in sorted(graph.symbols.values(), key=lambda s: s.name):
        for decorator in symbol.decorators:
            if decorator.name != data["receiver_decorator"]:
                continue
            signal = decorator.args[0].split(".")[-1] if decorator.args else ""
            if signal not in signals:
                continue
            sender = decorator.keywords.get(data["sender_kwarg"])
            graph.receivers.append(_receiver(graph, imap, symbol, signal, sender,
                                             decorator.file, decorator.line,
                                             decorator.keywords.get(data["weak_kwarg"]),
                                             loaded, data))
    for site in sorted(graph.calls, key=lambda c: (c.file, c.line)):
        if site.name != data["connect_call"] or site.receiver.split(".")[-1] not in signals:
            continue
        module = _module_of(graph, site.file)
        target = site.args[0].value if site.args else ""
        symbol = _symbol_named(graph, imap, module, str(target))
        if symbol is None:
            continue
        sender = site.keywords[data["sender_kwarg"]].value if data["sender_kwarg"] in site.keywords else None
        weak = site.keywords["weak"].value if "weak" in site.keywords else None
        graph.receivers.append(_receiver(graph, imap, symbol,
                                         site.receiver.split(".")[-1], sender,
                                         site.file, site.line, weak, loaded, data))
    graph.receivers.sort(key=lambda r: (r.file, r.line, r.symbol))


def _receiver(graph: Graph, imap: importmap.ImportMap, symbol, signal: str,
              sender: str | None, file: str, line: int, weak, loaded: set[str],
              data: dict) -> Receiver:
    model = None
    if sender:
        dotted = imap.resolve_dotted(symbol.module, None, str(sender))
        model = dotted if dotted in graph.classes else (
            f"{symbol.module}.{sender}" if f"{symbol.module}.{sender}" in graph.classes else str(sender))
    guards = False
    if model is None:
        info = graph.modules.get(symbol.module)
        body = "\n".join((info.source.splitlines() if info else [])[symbol.line: symbol.end_line])
        guards = any(token in body for token in data["no_sender_body_guards"])
    return Receiver(symbol=symbol.name, signal=signal, sender=model, file=file, line=line,
                    weak=(norm(str(weak)) != "false") if weak is not None else True,
                    nested=symbol.is_nested, guards_on_sender=guards,
                    connected=symbol.module in loaded,
                    reason="" if symbol.module in loaded else
                    f"receiver defined at {symbol.file}:{symbol.line}, module imported by nothing")


def _module_of(graph: Graph, file: str) -> str:
    for module in graph.modules.values():
        if module.file == file:
            return module.module
    return ""


def _symbol_named(graph: Graph, imap: importmap.ImportMap, module: str, written: str):
    dotted = imap.resolve_dotted(module, None, written)
    for candidate in (dotted, f"{module}.{written}" if module else written):
        if candidate in graph.symbols:
            return graph.symbols[candidate]
    matches = [s for s in graph.symbols.values() if s.short == written.split(".")[-1]]
    return matches[0] if len(matches) == 1 else None


def _enforcing_engine(graph: Graph, rules: RuleSet) -> bool | None:
    """4.5: True where the bound engine is shown to enforce foreign keys, else None.

    `ondelete` is DDL and nothing more [S19]; a repository-wide URL match would let an
    unrelated analytics engine bless SE7 for a session bound to sqlite:///app.db.
    """
    data = rules.primitives["sqlalchemy"]["enforcing_engine_evidence"]
    engines = list(graph.settings.get("engines") or [])
    if not engines:
        return None
    urls = [str(e["url"]) for e in engines]
    non_sqlite = [u for u in urls if any(u.startswith(p) or f"backends.{p}" in u
                                         for p in data["non_sqlite_url_prefixes"])]
    django = [u for u in urls if u in set(data["django_engines"])]
    if len(engines) > 1 and (non_sqlite or django) and len(non_sqlite + django) != len(engines):
        return None                     # several engines, binding not resolved by name
    if non_sqlite or django:
        return True
    pragma = any(
        data["sqlite_pragma_literal"].replace(" ", "") in line.replace(" ", "")
        for module in graph.modules.values()
        for line in module.source.splitlines()
    )
    return True if pragma else None
