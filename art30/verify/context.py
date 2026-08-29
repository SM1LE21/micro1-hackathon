"""What the store detectors share: the graph, the rules and the name lookups.

Module-level constants resolved by name, the calls of one module, whether a module
imports an SDK at all -- the plumbing 03-verifier.md 3.1 to 3.8 all need and none
of them owns.
"""

from __future__ import annotations

from art30.verify import imports as importmap
from art30.verify.findings import Graph, Store
from art30.verify.imports import ImportMap
from art30.verify.rules import RuleSet


def _declarative_bases(graph: Graph, imap: importmap.ImportMap) -> set[str]:
    """`Base = declarative_base()` is a base; the class `Base` itself is not a store."""
    found: set[str] = set()
    for module in graph.modules.values():
        for assign in module.assigns:
            if assign.value_kind == "call" and assign.value_repr.split(".")[-1] in {
                "declarative_base", "automap_base"
            }:
                found.add(f"{module.module}.{assign.target}" if module.module else assign.target)
    return found


class Ctx:
    """Everything the detectors share: the graph, the rules and the name lookups."""

    def __init__(self, graph: Graph, rules: RuleSet, imap: importmap.ImportMap) -> None:
        self.graph = graph
        self.rules = rules
        self.imap = imap
        self.calls_by_module: dict[str, list] = {}
        file_to_module = {m.file: m.module for m in graph.modules.values()}
        for site in graph.calls:
            module = file_to_module.get(site.file, "")
            self.calls_by_module.setdefault(module, []).append(site)
        self.consts: dict[str, dict[str, tuple[str, int]]] = {}
        for module in graph.modules.values():
            found: dict[str, tuple[str, int]] = {}
            for assign in module.assigns:
                if assign.value_kind in {"literal", "fstring"} and "." not in assign.target:
                    found[assign.target] = (assign.value_repr, assign.line)
                elif assign.value_kind == "sequence" and assign.keys:
                    found[assign.target] = ("|".join(assign.keys), assign.line)
            self.consts[module.module] = found
        self.declarative = _declarative_bases(graph, imap)
        self.core_tables: dict[str, str] = {}

    def file_of(self, module: str) -> str:
        info = self.graph.modules.get(module)
        return info.file if info else ""

    def constant(self, module: str, name: str) -> tuple[str, int] | None:
        return self.consts.get(module, {}).get(name.split(".")[-1])

    def literal(self, module: str, arg) -> str:
        """A literal argument, or the module constant a name resolves to."""
        if arg is None:
            return ""
        if arg.kind == "literal":
            return str(arg.value)
        if arg.kind == "fstring":
            return arg.prefix
        if arg.kind in {"name", "attribute"}:
            found = self.constant(module, arg.value)
            return found[0] if found else ""
        return ""

    def imports_any(self, module: str, names: list[str]) -> bool:
        bindings = self.imap.modules.get(module, {})
        for target_kind, dotted in bindings.values():
            if target_kind != importmap.EXTERNAL:
                continue
            for name in names:
                if dotted == name or dotted.startswith(f"{name}."):
                    return True
        return False

    def external_head(self, module: str, site, names: list[str]) -> bool:
        head = (site.receiver or site.name).split(".")[0]
        target = self.imap.lookup(module, None, head)
        if target is None or target[0] != importmap.EXTERNAL:
            return False
        return any(target[1] == n or target[1].startswith(f"{n}.") for n in names)

    def add(self, store: Store) -> Store:
        existing = self.graph.stores.get(store.id)
        if existing is None:
            self.graph.stores[store.id] = store
            return store
        for extra in store.fields:                      # merge, never duplicate
            if all(f.name != extra.name for f in existing.fields):
                existing.fields.append(extra)
        existing.client_vars = sorted(set(existing.client_vars) | set(store.client_vars))
        existing.flags = sorted(set(existing.flags) | set(store.flags))
        return existing


def personal_names(ctx, site) -> list[str]:
    """The guard-list names a call carries in its arguments (3.9, guard use only)."""
    seen: list[str] = []
    for arg in list(site.args) + [site.keywords[k] for k in sorted(site.keywords)]:
        for name in list(arg.names) + list(arg.keys):
            if ctx.rules.guard_hit(name) and name not in seen:
                seen.append(name)
    return seen
