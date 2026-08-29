"""What the store detectors share: the graph, the rules and the name lookups.

Module-level constants resolved by name, the calls of one module, whether a module
imports an SDK at all -- the plumbing 03-verifier.md 3.1 to 3.8 all need and none
of them owns.
"""

from __future__ import annotations

from typing import NamedTuple

from art30.verify import imports as importmap
from art30.verify.findings import Graph, Store
from art30.verify.imports import ImportMap
from art30.verify.rules import RuleSet


class Const(NamedTuple):
    """A module-level constant, with the file that declares it (R28: no guessed line)."""

    value: str
    line: int
    file: str


def owner_module(graph: Graph, imap: importmap.ImportMap, module: str,
                 name: str) -> str | None:
    """The intra-repo module a written name belongs to, or None (03-verifier.md 1.3).

    `from config import BUCKET` and `import config` + `config.BUCKET` alike. The one
    module-scoped resolver the detectors share: R6's engine URL and 3.2's bucket
    constant both used to scan the whole tree by tail name, first alphabetical match
    winning, which attributed a literal to a sibling module.
    """
    head = name.split(".")[0]
    target = imap.lookup(module, None, head)
    if target is None:
        return None
    kind, dotted = target
    owner = dotted if kind == importmap.MODULE else dotted.rsplit(".", 1)[0]
    return owner if owner in graph.modules else None


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
        self.consts: dict[str, dict[str, Const]] = {}
        for module in graph.modules.values():
            found: dict[str, Const] = {}
            for assign in module.assigns:
                if assign.value_kind in {"literal", "fstring"} and "." not in assign.target:
                    found[assign.target] = Const(assign.value_repr, assign.line, module.file)
                elif assign.value_kind == "sequence" and assign.keys:
                    found[assign.target] = Const("|".join(assign.keys), assign.line, module.file)
            self.consts[module.module] = found
        self.declarative = _declarative_bases(graph, imap)
        self.core_tables: dict[str, str] = {}
        self.by_kind: dict[tuple[str, str], Store] = {}

    def file_of(self, module: str) -> str:
        info = self.graph.modules.get(module)
        return info.file if info else ""

    def constant(self, module: str, name: str) -> Const | None:
        """A module-level constant: this module's, or the intra-repo one it imports.

        3.2 names the store after "bucket names from `Bucket=` kwargs and from module
        constants they resolve to". Reading only the calling module's own assignments
        lost every `from config import BUCKET` layout -- no literal, no store, and a
        bucket the record names then has no verifier store to corroborate it (7.3).
        The constant keeps its own file, so the citation is the declaring line (R28).

        R28: the lookup is ordered by what the name itself says. A *qualified* name
        (`config.BUCKET`) names its own module and is read there and nowhere else;
        reading the calling module first let an unrelated local `BUCKET` of the same
        tail win, which named the store after the wrong bucket and cited a line that
        does not carry it -- and 7.3 then matches the record's correct name against
        nothing. A bare name is this module's first, then the module it is imported
        from.
        """
        tail = name.split(".")[-1]
        if "." in name:
            owner = owner_module(self.graph, self.imap, module, name)
            if owner is not None:
                return self.consts.get(owner, {}).get(tail)
            return self.consts.get(module, {}).get(tail)
        found = self.consts.get(module, {}).get(tail)
        if found is not None:
            return found
        owner = owner_module(self.graph, self.imap, module, name)
        if owner is None:
            return None
        return self.consts.get(owner, {}).get(tail)

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
            return found.value if found else ""
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
        """One store per (kind, id). Two kinds sharing an identifier are never merged.

        Keyed on the id alone, a `sessions` table and a `session`-prefixed cache
        namespace became one store, so the relational SE12 edge marked the cache
        erased and the emails in it survived -- a false safe of exactly the shape 3.10
        forbids for a client handle. The second kind is kept as its own store under
        `<id>#<kind>`, with the conflict recorded on both (6.1 row 8 reads the flag).
        """
        existing = self.by_kind.get((store.kind, store.id))
        if existing is None:
            other = self.graph.stores.get(store.id)
            if other is not None:
                key = (store.kind, store.id)
                store.flags.append("store_id_conflict")
                store.note = (f"{store.note} " if store.note else "") + (
                    f"identifier shared with the {other.kind} store {other.id}; "
                    "kept separate, never merged (3.10)")
                other.flags.append("store_id_conflict")
                store.id = f"{store.id}#{store.kind}"
                self.by_kind[key] = store
                self.graph.stores[store.id] = store
                return store
            self.by_kind[(store.kind, store.id)] = store
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
