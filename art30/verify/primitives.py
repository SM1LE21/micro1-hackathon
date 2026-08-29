"""SE12: a rule-set deletion primitive becomes an edge to one store (03-verifier.md 4.2).

A keyed primitive is attributed by its **own literal** and never by the client
handle (3.10, decision 21): one Redis handle, one boto3 client and one
Elasticsearch client each serve several namespaces, and crediting the handle would
mark the siblings erased. The mode a relational primitive sets is what lets the
mode-bearing edges of SE1-SE9 become admissible at all (4.2).
"""

from __future__ import annotations

import re

from art30.verify import imports as importmap
from art30.verify.entities import Edge
from art30.verify.findings import Graph, Store
from art30.verify.rules import RuleSet, norm

ALL = ("none", "model_delete", "queryset_delete", "db_cascade", "session_delete",
       "bulk_dml", "raw_sql")
RAW_TABLE = re.compile(r"delete\s+from\s+[\"'`]?([A-Za-z_][\w]*)", re.IGNORECASE)


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
    module = symbol.module if symbol else site.caller.rsplit(".", 1)[0]
    dotted = imap.resolve_dotted(module, None, head)
    if dotted in graph.classes:
        return dotted
    local = f"{module}.{head}" if module else head
    if local in graph.classes:
        return local
    return None


def _relational_target(graph: Graph, imap: importmap.ImportMap, site, entry: dict) -> Store | None:
    if entry.get("arg0_call"):
        arg = site.args[0] if site.args else None
        if arg is None or arg.kind != "call":
            return None
        if arg.value.split(".")[-1] not in set(entry["arg0_call"]):
            return None
        if arg.value.split(".")[-1] == "text" or entry.get("mode") == "raw_sql":
            return _raw_target(graph, site)
        for name in arg.refs + arg.names + arg.keys:
            model = _model_of(graph, imap, site, name)
            if model:
                return graph.store_for_model(model)
        return None
    if entry.get("mode") == "raw_sql":
        return _raw_target(graph, site)
    receiver = site.receiver
    if site.name == "delete" and receiver.split(".")[-1] in {"session", "db"} or \
            receiver.endswith("session"):
        for arg in site.args:
            model = _model_of(graph, imap, site, str(arg.value))
            if model:
                return graph.store_for_model(model)
        return None
    if "." in receiver:
        # `instance.image.delete(save=False)` deletes the bytes, not the row (R8).
        return None
    model = _model_of(graph, imap, site, receiver)
    return graph.store_for_model(model) if model else None


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


def _keyed_target(graph: Graph, ctxconsts, site, kind: str, rules: RuleSet,
                  module: str) -> Store | None:
    """3.10: the store the primitive's own literal names, or none at all."""
    candidates = [s for s in graph.stores.values() if s.kind == kind]
    if kind == "object_storage":
        bucket = site.keywords.get("Bucket")
        literal = _literal(graph, module, bucket) if bucket else ""
        if literal:
            return next((s for s in candidates if norm(s.identity) == norm(literal)), None)
        return None
    if kind == "cache":
        arg = site.args[0] if site.args else None
        if arg is None:
            return None
        text = arg.prefix if arg.kind == "fstring" else _literal(graph, module, arg)
        for sep in (":", "/", "|", "-"):
            if sep in text:
                text = text.split(sep)[0]
                break
        return next((s for s in candidates if text and norm(s.identity) == norm(text)), None)
    if kind == "search_index":
        arg = site.keywords.get("index")
        literal = _literal(graph, module, arg) if arg else ""
        return next((s for s in candidates if literal and norm(s.identity) == norm(literal)), None)
    if kind == "queue":
        for key in ("queue", "routing_key", "queue_name", "QueueUrl"):
            arg = site.keywords.get(key)
            literal = _literal(graph, module, arg) if arg else ""
            if literal:
                return next((s for s in candidates if norm(s.identity) == norm(literal)), None)
    return None


def _literal(graph: Graph, module: str, arg) -> str:
    if arg is None:
        return ""
    if arg.kind == "literal":
        return str(arg.value)
    if arg.kind == "fstring":
        return arg.prefix
    name = str(arg.value).split(".")[-1]
    info = graph.modules.get(module)
    for source in ([info] if info else []) + list(graph.modules.values()):
        if source is None:
            continue
        for assign in source.assigns:
            if assign.target == name and assign.value_kind == "literal":
                return assign.value_repr
    return ""


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
                store = _relational_target(graph, imap, site, entry)
            elif kind in {"cache", "object_storage", "search_index", "queue"}:
                store = _keyed_target(graph, None, site, kind, rules, module)
            else:
                store = None
            if store is None:
                continue
            out.append(_edge(site, store, entry.get("rule", ""), entry.get("mode")))
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
