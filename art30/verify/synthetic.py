"""Synthetic edges SE0-SE12 and the framework facts behind them (03-verifier.md 4).

Django `on_delete` tokens, SQLAlchemy cascade strings, receivers, django-cleanup,
enforcing foreign keys and the deletion primitives of the rule data become edges
here, each carrying the modes it is admissible in and the mode it sets, so that
R4, R14, R15, R17 and R18 are mechanical in the search rather than prose. SE0 is
the entry point's own edge into the function it names, without which the walk of
5.2 starts on a node with no out-edge and reaches nothing.
"""

from __future__ import annotations

import re

from art30.verify import imports as importmap
from art30.verify.entities import Edge
from art30.verify.engines import enforcing_engine
from art30.verify.facts import _module_of, _receivers, _symbol_named
from art30.verify.findings import Graph
from art30.verify.rules import RuleSet, norm

ALL = ("none", "model_delete", "queryset_delete", "db_cascade", "session_delete",
       "bulk_dml", "raw_sql")
PY_DELETE = re.compile(r"delete\s+from\s+([A-Za-z_][\w]*)", re.IGNORECASE)


def _store_node(graph: Graph, store_id: str) -> str | None:
    store = graph.stores.get(store_id)
    return store.node if store else None


def _relation_edges(graph: Graph, rules: RuleSet) -> list[Edge]:
    """SE1, SE4, SE5, SE6, SE7 -- R1 to R7, each with the modes it is admissible in."""
    out: list[Edge] = []
    enforcing = enforcing_engine(graph, rules)
    for relation in graph.relations:
        parent, child = _store_node(graph, relation.parent), _store_node(graph, relation.child)
        if parent is None or child is None:
            continue
        if relation.kind == "fk" and relation.token:
            token = rules.on_delete(relation.token)
            if token.get("edge"):
                out.append(Edge(src=parent, dst=child,
                                kind="SE4" if token.get("sets_mode") else "SE1",
                                file=relation.file, line=relation.line,
                                rule="R4" if token.get("sets_mode") else "R1",
                                modes=tuple(token.get("modes") or ("model_delete", "queryset_delete")),
                                sets_mode=token.get("sets_mode"),
                                note=f"on_delete={relation.token}"))
        elif relation.kind == "fk" and relation.ondelete:
            # R6 [S15] [S19] [S46]: DDL is not enforcement; the bound engine decides.
            if norm(relation.ondelete) == "cascade" and enforcing is True:
                out.append(Edge(src=parent, dst=child, kind="SE7", file=relation.file,
                                line=relation.line, rule="R6", modes=ALL,
                                note=f'ondelete="{relation.ondelete}" on an enforcing engine'))
            elif norm(relation.ondelete) == "cascade":
                store = graph.stores.get(relation.child)
                passive = any(r.passive_deletes and r.child in {relation.child, relation.parent}
                              for r in graph.relations)
                if store is not None:
                    # No enforcement evidence: unverified, and not_erased only where the
                    # ORM has also been told not to emit the child DELETE (R6 [S15]).
                    store.flags.append("r6_not_erased" if passive else "r6_unverified")
        elif relation.kind == "relationship" and rules.cascade_is_delete(relation.token):
            out.append(Edge(src=parent, dst=child, kind="SE5", file=relation.file,
                            line=relation.line, rule="R5", modes=("session_delete",),
                            note=f'cascade="{relation.token}"'))
        elif relation.kind == "secondary":
            out.append(Edge(src=parent, dst=child, kind="SE6", file=relation.file,
                            line=relation.line, rule="R7", modes=("session_delete",),
                            note=f"secondary={relation.token}"))
    return out


def _signal_edges(graph: Graph, rules: RuleSet) -> list[Edge]:
    """SE2 (R8a, R9, R15) and SE3 (R8b, R10): the row reaches the cleanup, or not."""
    out: list[Edge] = []
    for receiver in graph.receivers:
        if not receiver.connected or receiver.guards_on_sender:
            continue
        if receiver.nested and receiver.weak:      # R11 [S6]
            continue
        targets = []
        if receiver.sender:
            store = graph.store_for_model(receiver.sender)
            targets = [store] if store else []
        else:
            targets = [s for s in graph.stores.values() if s.kind == "relational"]
        for store in targets:
            out.append(Edge(src=store.node, dst=receiver.symbol, kind="SE2",
                            file=receiver.file, line=receiver.line, rule="R9",
                            modes=("model_delete", "queryset_delete"),
                            note=f"{receiver.signal} receiver, sender={receiver.sender or 'any'}"))
    mode = graph.settings.get("cleanup")
    if mode in {"ALL", "SELECT"}:
        for store in sorted(graph.stores.values(), key=lambda s: s.id):
            if "django_file_field" not in store.flags or not store.model:
                continue
            owner = graph.store_for_model(store.model)
            cls = graph.classes.get(store.model)
            if owner is None or cls is None:
                continue
            names = {d.dotted for d in cls.decorators}
            if mode == "ALL" and any(n.endswith("cleanup.ignore") for n in names):
                continue
            if mode == "SELECT" and not any(n.endswith("cleanup.select") for n in names):
                continue
            out.append(Edge(src=owner.node, dst=store.node, kind="SE3",
                            file=cls.file, line=cls.line, rule="R10",
                            modes=("model_delete", "queryset_delete"),
                            note="django-cleanup active"))
    return out


def _override_edges(graph: Graph, rules: RuleSet) -> list[Edge]:
    """SE8 (R14, model_delete only) and SE9 (R18, session_delete only)."""
    out: list[Edge] = []
    for symbol in sorted(graph.symbols.values(), key=lambda s: s.name):
        if symbol.short == "delete" and symbol.owner:
            store = graph.store_for_model(symbol.owner)
            if store is not None:
                out.append(Edge(src=store.node, dst=symbol.name, kind="SE8",
                                file=symbol.file, line=symbol.line, rule="R14",
                                modes=("model_delete",), note="Model.delete() override"))
        for decorator in symbol.decorators:
            if decorator.name == "listens_for" and len(decorator.args) >= 2:
                if decorator.args[1] in set(rules.primitives["sqlalchemy"]["mapper_delete_events"]):
                    store = _model_store(graph, decorator.args[0])
                    if store is not None:
                        out.append(Edge(src=store.node, dst=symbol.name, kind="SE9",
                                        file=decorator.file, line=decorator.line,
                                        rule="R18", modes=("session_delete",),
                                        note=f"{decorator.args[1]} listener"))
    for site in sorted(graph.calls, key=lambda c: (c.file, c.line)):
        if site.name == "listen" and len(site.args) >= 3:
            if str(site.args[1].value) in set(rules.primitives["sqlalchemy"]["mapper_delete_events"]):
                store = _model_store(graph, str(site.args[0].value))
                target = _symbol_named(graph, importmap.ImportMap(), _module_of(graph, site.file),
                                       str(site.args[2].value))
                if store is not None and target is not None:
                    out.append(Edge(src=store.node, dst=target.name, kind="SE9",
                                    file=site.file, line=site.line, rule="R18",
                                    modes=("session_delete",), note="event.listen"))
    return out


def _model_store(graph: Graph, written: str):
    short = str(written).split(".")[-1]
    for qual, cls in graph.classes.items():
        if cls.short == short:
            return graph.store_for_model(qual)
    return None


def _admin_edges(graph: Graph) -> list[Edge]:
    """SE10 [S8] [S9]: the two admin paths, each setting its own mode."""
    out: list[Edge] = []
    for entry in graph.entry_points:
        if not entry.admin_only:
            continue
        for model in entry.models:
            store = graph.store_for_model(model)
            if store is None:
                continue
            if entry.sets_mode == "model_delete":
                override = graph.symbols.get(f"{model}.delete")
                dst = override.name if override else store.node
            else:
                dst = store.node
            out.append(Edge(src=entry.node, dst=dst, kind="SE10", file=entry.file,
                            line=entry.line, rule="R16", modes=("none",),
                            sets_mode=entry.sets_mode,
                            note=f"admin registration of {model}"))
    return out


def _entry_edges(graph: Graph) -> list[Edge]:
    """SE0: `entry:<name>` -> the symbol the entry point names (2.2, 5.2's start node).

    Only the two admin entry points had an out-edge (SE10), so a walk from
    `entry:close_account` left the start node with nowhere to go: `path_exists`
    returned None for every store in every non-admin repository, and S01, S04 and S06
    all read `not_erased` however plainly the body deletes. The edge is admissible in
    every mode and sets none -- it carries the search into the body, and the mode is
    still set by the primitive it finds there (4.2, decision 19).
    """
    out: list[Edge] = []
    for entry in sorted(graph.entry_points, key=lambda e: e.key()):
        if not entry.symbol or entry.symbol not in graph.symbols:
            continue
        out.append(Edge(src=entry.node, dst=entry.symbol, kind="entry", file=entry.file,
                        line=entry.line, rule="SE0", modes=ALL,
                        note=f"entry point {entry.name} ({entry.kind})"))
    return out


def _task_edges(graph: Graph, rules: RuleSet) -> list[Edge]:
    """SE11 / CG-16: `.delay`, `.apply_async` and `send_task` through the task table."""
    dispatch = set(rules.entry["celery_task_names"]["dispatch_calls"])
    out: list[Edge] = []
    for site in sorted(graph.calls, key=lambda c: (c.file, c.line)):
        if site.name not in dispatch:
            continue
        target = None
        if site.args and site.args[0].kind == "literal":
            target = graph.task_table.get(str(site.args[0].value))
        if target is None and site.receiver:
            short = site.receiver.split(".")[-1]
            matches = [s for name, s in sorted(graph.task_table.items())
                       if s.split(".")[-1] == short]
            target = matches[0] if len(matches) == 1 else None
        if target:
            out.append(Edge(src=site.caller, dst=target, kind="SE11", file=site.file,
                            line=site.line, rule="CG-16", modes=ALL,
                            note=f"dispatch through {site.name}"))
    return out


def add_edges(graph: Graph, rules: RuleSet, imap: importmap.ImportMap) -> None:
    from art30.verify import primitives

    graph.settings["_local_imports"] = {
        scope: sorted({dotted for _kind, dotted in bindings.values()})
        for scope, bindings in sorted(imap.local.items())
    }
    _receivers(graph, rules, imap)
    for receiver in graph.receivers:
        symbol = graph.symbols.get(receiver.symbol)
        if symbol is not None and receiver.sender:
            symbol.var_models.setdefault("instance", receiver.sender)
    edges: list[Edge] = []
    edges += _relation_edges(graph, rules)
    edges += _signal_edges(graph, rules)
    edges += _override_edges(graph, rules)
    edges += _admin_edges(graph)
    edges += _entry_edges(graph)
    edges += _task_edges(graph, rules)
    edges += primitives.primitive_edges(graph, rules, imap)
    graph.edges += edges
    if graph.versioning:
        for store in graph.stores.values():
            if store.kind == "object_storage":
                store.flags.append("versioning_declared")
