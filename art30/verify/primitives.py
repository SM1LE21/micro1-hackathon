"""SE12: a rule-set deletion primitive becomes an edge to one store (03-verifier.md 4.2).

A keyed primitive is attributed by its **own literal** and never by the client
handle (3.10, decision 21): one Redis handle, one boto3 client and one
Elasticsearch client each serve several namespaces, and crediting the handle would
mark the siblings erased. The mode a relational primitive sets is what lets the
mode-bearing edges of SE1-SE9 become admissible at all (4.2).
"""

from __future__ import annotations

import re
from typing import NamedTuple

from art30.verify import imports as importmap
from art30.verify.context import Ctx
from art30.verify.entities import Edge
from art30.verify.findings import Graph, Store
from art30.verify.keyed import keyed_target
from art30.verify.rules import RuleSet, norm

ALL = ("none", "model_delete", "queryset_delete", "db_cascade", "session_delete",
       "bulk_dml", "raw_sql")
RAW_TABLE = re.compile(r"delete\s+from\s+[\"'`]?([A-Za-z_][\w]*)", re.IGNORECASE)
# R15 [S3], 4.8: the chain segments that say a delete is a queryset delete. A chain
# carrying one of these never runs `Model.delete()` [S3], so the mode is forced.
QUERYSET_SEGMENTS = frozenset({"objects", "all", "filter", "exclude", "query",
                               "get_queryset", "_default_manager", "none"})


class Hit(NamedTuple):
    """The store a primitive was attributed to, with what the shape overrides."""

    store: Store
    mode: str | None = None        # the shape decides the mode, not the rule entry
    rule: str | None = None


def _segments(dotted: str) -> list[str]:
    return [part.replace("()", "") for part in (dotted or "").split(".")]


def matches(site, pattern: str) -> bool:
    """`.delete`, `session.delete`, `objects.filter.delete`, `delete_object`."""
    dotted = site.dotted or site.name
    if pattern.startswith("."):
        return site.name == pattern[1:]
    if "." not in pattern:
        return site.name == pattern
    head, _, tail = pattern.rpartition(".")
    if site.name != tail:
        return False
    parts = set(_segments(dotted)[:-1])
    return all(part in parts for part in head.split("."))


def _model_of(graph: Graph, imap: importmap.ImportMap, site, written: str) -> str | None:
    """The variable to model table of the spike's finding 2, then the class index."""
    if not written:
        return None
    symbol = graph.symbols.get(site.caller)
    head = written.split(".")[0]
    if symbol is not None and head in symbol.var_models:
        return symbol.var_models[head]
    if head in {"self", "cls"} and symbol is not None and symbol.owner:
        # A deletion inside a model method (`self.delete()`, `self.image.delete()`)
        # names its own class; without the binding the call was attributed to no store
        # at all and R8's and R14's own shapes went unrecorded (11, finding 2).
        return symbol.owner
    module = symbol.module if symbol else site.caller.rsplit(".", 1)[0]
    dotted = imap.resolve_dotted(module, None, head)
    if dotted in graph.classes:
        return dotted
    local = f"{module}.{head}" if module else head
    if local in graph.classes:
        return local
    return None


def _hit(store: Store | None, mode: str | None = None, rule: str | None = None) -> Hit | None:
    return Hit(store, mode, rule) if store is not None else None


def _relational_target(graph: Graph, imap: importmap.ImportMap, site, entry: dict) -> Hit | None:
    if entry.get("arg0_call"):
        arg = site.args[0] if site.args else None
        if arg is None or arg.kind != "call":
            return None
        if arg.value.split(".")[-1] not in set(entry["arg0_call"]):
            return None
        if arg.value.split(".")[-1] == "text" or entry.get("mode") == "raw_sql":
            return _hit(_raw_target(graph, site))
        for name in arg.refs + arg.names + arg.keys:
            model = _model_of(graph, imap, site, name)
            if model:
                return _hit(graph.store_for_model(model))
        return None
    if entry.get("mode") == "raw_sql":
        return _hit(_raw_target(graph, site))
    receiver = site.receiver
    if site.name == "delete" and receiver.split(".")[-1] in {"session", "db"} or \
            receiver.endswith("session"):
        for arg in site.args:
            model = _model_of(graph, imap, site, str(arg.value))
            if model:
                return _hit(graph.store_for_model(model))
        return None
    if "." in receiver:
        return _chained_target(graph, imap, site)
    model = _model_of(graph, imap, site, receiver)
    if model is None:
        return None
    store = graph.store_for_model(model)
    if store is None:
        return None
    # R14 [S3]: a name bound to a queryset is not an instance -- `qs = M.objects.filter(...)`
    # then `qs.delete()` never runs `M.delete()`, so SE8 must stay inadmissible. The
    # receiver carries no dot, so `_chained_target` never sees it and the rule entry's
    # `model_delete` stood: 4.2's own worked example, written over two lines, credited
    # the `Model.delete()` override and read `erased` for bytes still on disk.
    symbol = graph.symbols.get(site.caller)
    for assign in (symbol.assigns if symbol else ()):
        if assign.target == receiver and set(_segments(assign.value_repr)) & QUERYSET_SEGMENTS:
            return Hit(store, "queryset_delete", "R15")
    return Hit(store)


def _chained_target(graph: Graph, imap: importmap.ImportMap, site) -> Hit | None:
    """R15 [S3], 4.8: the two chained deletes, attributed to the rows they remove.

    `Model.objects.filter(...).delete()` and `<subject>.<relation>.all().delete()` were
    refused outright because the receiver carries a dot, so a repository whose only
    account-closure code is a queryset delete had no SE12 edge and every row store on
    it read `not_erased`. Both are queryset deletes: the mode is forced to
    `queryset_delete` whatever entry matched, so SE8 stays inadmissible and the
    `Model.delete()` override is never credited on this path (R14 [S3]).
    Anything else with a dotted receiver -- `instance.image.delete(save=False)` --
    deletes the bytes and not the row (R8), and still gets no relational edge.
    """
    segments = _segments(site.receiver)
    if len(segments) < 2 or not set(segments) & QUERYSET_SEGMENTS:
        return None
    model = _model_of(graph, imap, site, segments[0])
    if model is None:
        return None
    store = graph.store_for_model(model)
    if store is None:
        return None
    if segments[1] in QUERYSET_SEGMENTS:
        return Hit(store, "queryset_delete", "R15")
    related = _related_store(graph, store, segments[1])
    return Hit(related, "queryset_delete", "R15") if related is not None else None


def _related_store(graph: Graph, parent: Store, accessor: str) -> Store | None:
    """4.8: which rows `<subject>.<relation>.all().delete()` removes.

    Never the subject's own: crediting `rows:user` for a call that deletes the user's
    posts is the false safe 3.10 forbids one kind-level up. The accessor has to
    resolve -- a `relationship()` attribute, a Django `related_name`, or the default
    `<model>_set` -- and where it does not, there is no edge (R26).
    """
    wanted = norm(accessor)
    for relation in sorted(graph.relations, key=lambda r: (r.file, r.line, r.child)):
        if relation.parent != parent.id:
            continue
        child = graph.stores.get(relation.child)
        if child is None:
            continue
        names = {norm(relation.related_name)} if relation.related_name else set()
        if relation.kind == "relationship" and relation.field_name:
            names.add(norm(relation.field_name))
        if relation.kind == "fk" and child.model:
            names.add(norm(f"{child.model.split('.')[-1]}_set"))
        if wanted in names:
            return child
    return None


def _raw_target(graph: Graph, site) -> Store | None:
    """R19 [S11]: the table is read from the string literal and nowhere else."""
    for arg in site.args:
        for text in [arg.value] + list(arg.keys):
            found = RAW_TABLE.search(str(text) or "")
            if not found:
                continue
            table = found.group(1)
            for store in sorted(graph.stores.values(), key=lambda s: s.id):
                if store.kind == "relational" and norm(store.id) == norm(table):
                    return store
    return None


def _file_field_target(graph: Graph, imap: importmap.ImportMap, site) -> Store | None:
    """`instance.avatar.delete(save=False)`: the field the receiver binds to (R8)."""
    if site.name != "delete" or "." not in site.receiver:
        return None
    head, _, field = site.receiver.rpartition(".")
    model = _model_of(graph, imap, site, head)
    if model is None:
        return None
    cls = graph.classes.get(model)
    if cls is None:
        return None
    return graph.stores.get(f"{norm(cls.short)}.{field}")


def primitive_edges(graph: Graph, rules: RuleSet, imap: importmap.ImportMap) -> list[Edge]:
    out: list[Edge] = []
    # 3.10: the keyed literal is read through the one module-scoped name resolver.
    # Read-only -- `ctx.add` is never called here; the stores already exist.
    ctx = Ctx(graph, rules, imap)
    file_to_module = {m.file: m.module for m in graph.modules.values()}
    for site in sorted(graph.calls, key=lambda c: (c.file, c.line, c.dotted)):
        module = file_to_module.get(site.file, "")
        claimed = False
        file_store = _file_field_target(graph, imap, site)
        if file_store is not None:
            out.append(_edge(site, file_store, "R8", None))
            claimed = True
        for kind, entry in rules.all_primitives():
            if claimed:
                break
            if not any(matches(site, pattern) for pattern in entry.get("call") or []):
                continue
            if entry.get("receiver_is_file_field"):
                continue
            if kind == "relational":
                hit = _relational_target(graph, imap, site, entry)
            elif kind in {"cache", "object_storage", "search_index", "queue"}:
                hit = _hit(keyed_target(ctx, graph, site, kind, module))
            else:
                hit = None
            if hit is None:
                continue
            out.append(_edge(site, hit.store, hit.rule or entry.get("rule", ""),
                             hit.mode or entry.get("mode")))
            claimed = True
    out += _recipient_edges(graph, rules, file_to_module)
    return out


def _edge(site, store: Store, rule: str, mode: str | None) -> Edge:
    """The edge, and the primitive recorded on the store it was attributed to."""
    store.primitives.append({"call": site.dotted or site.name, "file": site.file,
                             "line": site.line, "rule": rule or "R26",
                             "caller": site.caller, "mode": mode or ""})
    return Edge(src=site.caller, dst=store.node, kind="SE12", file=site.file,
                line=site.line, rule=rule or "R26", modes=ALL, sets_mode=mode,
                note=f"{site.dotted or site.name} -> {store.id}")


def _recipient_edges(graph: Graph, rules: RuleSet, file_to_module: dict[str, str]) -> list[Edge]:
    """R22-R24: a deletion request reaches the recipient store; the verdict is reach.py's."""
    out: list[Edge] = []
    for name in rules.recipient_names():
        store = graph.stores.get(name)
        if store is None:
            continue
        data = rules.recipient(name)
        wanted = list(data.get("deletion_requests") or [])
        if data.get("deletion_call"):
            wanted.append(data["deletion_call"])
        for site in sorted(graph.calls, key=lambda c: (c.file, c.line)):
            dotted = site.dotted or site.name
            if not any(dotted == call or dotted.endswith(f".{call}") or site.name == call
                       for call in wanted):
                continue
            kwarg = data.get("regulation_type_kwarg")
            note = f"{dotted} on {name}"
            if kwarg and kwarg in site.keywords:
                note += f" regulation_type={site.keywords[kwarg].value}"
            store.primitives.append({"call": dotted, "file": site.file, "line": site.line,
                                     "rule": data.get("rule", "R24"),
                                     "caller": site.caller, "mode": ""})
            out.append(Edge(src=site.caller, dst=store.node, kind="SE12", file=site.file,
                            line=site.line, rule=data.get("rule", "R24"), modes=ALL,
                            note=note))
    return out
