"""Call resolution and the graph itself (03-verifier.md 1.5 and 1.6).

Every `ast.Call` recorded by `symbols.py` is resolved here under CG-1 to CG-20 into
one of three outcomes: resolved (one intra-repo target, an edge that can carry
`erased`), ambiguous (several candidates, edges flagged, a path through one can
only be `unverified`, R26), or unresolved (no intra-repo candidate; no edge, and
the rules match SDK primitives against it in `synthetic.py`).

`build_graph(root)` is the entry point the reach and check builders call. It runs
discovery, the symbol pass, the import map, this resolution, store detection,
entry-point discovery and the synthetic edges, and returns a `Graph` whose every
collection is sorted.
"""

from __future__ import annotations

import ast
from pathlib import Path

from art30.verify import binding
from art30.verify import imports as importmap
from art30.verify import synthetic
from art30.verify.discovery import parse_all, versioning_search
from art30.verify.entities import CallSite, Edge, ModuleInfo
from art30.verify.findings import Graph
from art30.verify.entrypoints import discover_entry_points, task_table
from art30.verify.facts import settings_facts
from art30.verify.rules import RuleSet, load_rules
from art30.verify.stores import detect_stores
from art30.verify.astdata import DYNAMIC_CALLS
from art30.verify.symbols import Extraction, extract

MODULE_CALLER = "<module>"


class Resolver:
    """CG-1 to CG-20 over one repository."""

    def __init__(self, extraction: Extraction, imap: importmap.ImportMap,
                 modules: dict[str, ModuleInfo]) -> None:
        self.ex = extraction
        self.imap = imap
        self.modules = modules
        self.by_short: dict[str, list[str]] = {}
        for qual, symbol in extraction.symbols.items():
            self.by_short.setdefault(symbol.short, []).append(qual)
        for name in self.by_short:
            self.by_short[name].sort()
        self.classes = extraction.classes
        self.classes_by_short: dict[str, list[str]] = {}
        for qual, info in sorted(extraction.classes.items()):
            self.classes_by_short.setdefault(info.short, []).append(qual)

    # -- helpers -----------------------------------------------------------
    def _scope(self, site: CallSite) -> tuple[str, str | None]:
        caller = site.caller
        if caller.endswith(f".{MODULE_CALLER}") or caller == MODULE_CALLER:
            module = caller[: -len(MODULE_CALLER) - 1] if "." in caller else ""
            return module, None
        symbol = self.ex.symbols.get(caller)
        return (symbol.module if symbol else "", caller)

    def _short(self, name: str) -> list[str]:
        return list(self.by_short.get(name, ()))

    def _method(self, cls: str, attr: str, seen: set[str] | None = None) -> str | None:
        """CG-8/CG-9/CG-10: `C.attr`, then intra-repo bases depth first, left to right."""
        seen = seen or set()
        if cls in seen or cls not in self.classes:
            return None
        seen.add(cls)
        qual = f"{cls}.{attr}"
        if qual in self.ex.symbols:
            return qual
        info = self.classes[cls]
        for base in info.bases:
            for target in self._base_classes(info.module, base):
                candidate = self._method(target, attr, seen)
                if candidate:
                    return candidate
        return None

    def _base_classes(self, module: str, base: str) -> list[str]:
        """A base as written, resolved to intra-repo classes, left to right."""
        found: list[str] = []
        for candidate in (self.imap.resolve_dotted(module, None, base),
                          f"{module}.{base}" if module else base):
            if candidate in self.classes and candidate not in found:
                found.append(candidate)
        if not found:
            found = list(self.classes_by_short.get(base.split(".")[-1], ()))
        return found

    def _owner_class(self, scope: str | None) -> str | None:
        if not scope:
            return None
        symbol = self.ex.symbols.get(scope)
        return symbol.owner if symbol else None

    # -- resolution --------------------------------------------------------
    def resolve(self, site: CallSite) -> CallSite:
        module, scope = self._scope(site)
        if site.form == "name":
            self._resolve_name(site, module, scope)
        elif site.form == "attribute":
            self._resolve_attribute(site, module, scope)
        else:
            site.outcome, site.rule, site.reason = "unresolved", "CG-5", "callee is not a name"
        # 1.2: two definitions sharing a qualified name in one module are both kept
        # and *every* call to the name is ambiguous. `symbols.py` records the collision
        # and the last body wins the table, so a resolved edge would credit the
        # surviving symbol with the dead body's primitive; forcing the outcome (targets
        # and rule unchanged) keeps any path through it at `unverified` (R26).
        if site.outcome == "resolved" and any(t in self.ex.ambiguous_names
                                              for t in site.targets):
            site.outcome = "ambiguous"
            site.reason = f"conditional redefinition of {sorted(site.targets)[0]} (1.2)"
        if site.name in DYNAMIC_CALLS or site.receiver.endswith("importlib"):
            site.outcome, site.rule = "unresolved", "CG-12"
            site.reason = f"dynamic dispatch through {site.name}"
            site.targets = []
            symbol = self.ex.symbols.get(site.caller)
            if symbol is not None:
                symbol.dynamic = True
        return site

    def _resolve_name(self, site: CallSite, module: str, scope: str | None) -> None:
        target = self.imap.lookup(module, scope, site.name)
        if target and target[0] == importmap.SYMBOL:
            site.outcome, site.rule, site.targets = "resolved", "CG-1", [target[1]]
            return
        if target and target[0] == importmap.EXTERNAL:
            site.outcome, site.rule = "unresolved", "CG-5"
            site.reason = f"external {target[1]}"
            return
        local = f"{module}.{site.name}" if module else site.name
        owner = self._owner_class(scope)
        if owner:                                  # a name from the enclosing class
            found = self._method(owner, site.name)
            if found:
                site.outcome, site.rule, site.targets = "resolved", "CG-2", [found]
                return
        if local in self.ex.symbols:
            site.outcome, site.rule, site.targets = "resolved", "CG-2", [local]
            return
        candidates = self._short(site.name)
        rule_suffix = "CG-20" if module in self.imap.wildcard else ""
        if len(candidates) == 1:
            site.outcome, site.rule, site.targets = "resolved", rule_suffix or "CG-3", candidates
            site.reason = "by_short_name"
        elif len(candidates) > 1:
            site.outcome, site.rule, site.targets = "ambiguous", rule_suffix or "CG-4", candidates
            site.reason = f"{len(candidates)} definitions of {site.name}"
        else:
            site.outcome, site.rule = "unresolved", "CG-5"
            site.reason = "no intra-repo definition"

    def _resolve_attribute(self, site: CallSite, module: str, scope: str | None) -> None:
        receiver, attr = site.receiver, site.name
        owner = self._owner_class(scope)
        if receiver in {"self", "cls"} and owner:
            found = self._method(owner, attr)
            rule = "CG-8" if receiver == "self" else "CG-9"
            if found:
                site.outcome, site.rule, site.targets = "resolved", rule, [found]
            else:
                external_base = any(
                    not self._base_classes(self.classes[owner].module, base)
                    for base in self.classes[owner].bases
                ) if owner in self.classes else False
                site.outcome = "ambiguous" if external_base else "unresolved"
                site.rule, site.reason = rule, "receiver is self with an external base"
            return
        if receiver.startswith("super()"):
            found = None
            if owner and owner in self.classes:
                for base in self.classes[owner].bases:
                    for target in self._base_classes(self.classes[owner].module, base):
                        found = self._method(target, attr) or found
                        if found:
                            break
                    if found:
                        break
            site.rule = "CG-10"
            if found:
                site.outcome, site.targets = "resolved", [found]
            else:
                site.outcome, site.reason = "unresolved", "no intra-repo base defines it"
            return
        head = receiver.split(".")[0] if receiver else ""
        bound = self.imap.lookup(module, scope, head) if head else None
        if bound and bound[0] == importmap.MODULE:
            dotted = self.imap.resolve_dotted(module, scope, site.dotted)
            if dotted in self.ex.symbols:
                site.outcome, site.rule, site.targets = "resolved", "CG-6", [dotted]
                return
        if (bound and bound[0] == importmap.SYMBOL and bound[1] in self.classes
                and receiver == head):
            # CG-6, and only where the receiver *is* the class: `Avatar.delete(obj)`.
            # A chain that merely starts with it -- `Avatar.objects.filter(...).delete()`
            # -- is a queryset delete, which never runs the model's `delete()` override
            # [S3]. Resolving it to `Avatar.delete` gave 4.2's own worked example and
            # test 27 a non-ambiguous call edge admissible in every mode, so the bytes
            # read `erased` while SE8's `model_delete` gate was bypassed (R14). The
            # chain falls through to CG-11 instead: ambiguous at worst, never `erased`.
            found = self._method(bound[1], attr)
            if found:
                site.outcome, site.rule, site.targets = "resolved", "CG-6", [found]
                return
        candidates = self._short(attr)
        if bound and bound[0] == importmap.EXTERNAL:
            # CG-7: an external module. The rules match `m.f` against their
            # primitives in synthetic.py; nothing here invents an edge.
            site.outcome, site.rule = "unresolved", "CG-7"
            site.reason = f"external {self.imap.resolve_dotted(module, scope, site.dotted)}"
            return
        if candidates:
            site.outcome, site.rule, site.targets = "ambiguous", "CG-11", candidates
            site.reason = f"receiver {receiver or '?'} is not a known module"
        else:
            site.outcome, site.rule = "unresolved", "CG-11"
            site.reason = f"no definition of {attr}"


def build_graph(root: Path, rules: RuleSet | None = None) -> Graph:
    """The one entry point: repository path in, `Graph` out (03-verifier.md 1.6)."""
    root = Path(root)
    rules = rules or load_rules()
    parsed, skipped, unparsed = parse_all(root, rules)
    extraction = extract(parsed)
    packages = {p.module: p.is_package for p in parsed}
    module_names = set(packages)
    known = set(extraction.symbols) | set(extraction.classes)
    imap = importmap.build(extraction.imports, packages, known, module_names)
    modules = {
        p.module: ModuleInfo(module=p.module, file=p.file, source=p.source,
                             is_package=p.is_package,
                             wildcard=p.module in imap.wildcard,
                             imports=imap.modules.get(p.module, {}),
                             assigns=extraction.module_assigns.get(p.module, []))
        for p in parsed
    }
    resolver = Resolver(extraction, imap, modules)
    calls = [resolver.resolve(site) for site in extraction.calls]
    binding.var_models(extraction, imap)

    graph = Graph(root=root, modules=modules, symbols=extraction.symbols,
                  classes=extraction.classes, calls=calls,
                  skipped=skipped, unparsed=unparsed)
    # 1.5: an ambiguous call with no candidate produces no edge (`_call_edges` walks
    # `targets`), so without this it appeared nowhere at all and the store an opaque
    # `self.f()` dispatch plausibly touches read `not_erased` instead of 6.1 row 8's
    # `unverified` (R26). CG-8/CG-9 against an external base is that shape.
    graph.unresolved = [c for c in calls
                        if c.outcome == "unresolved"
                        or (c.outcome == "ambiguous" and not c.targets)]
    _unmodelled_decorators(graph, rules)
    graph.edges = _call_edges(calls)
    graph.references = binding.references(extraction, imap, resolver._short)
    graph.versioning = versioning_search(root, rules, {p.file: p.source for p in parsed})
    graph.task_table = task_table(graph, rules)
    settings_facts(graph, rules, imap)
    detect_stores(graph, rules, imap)
    graph.entry_points = discover_entry_points(graph, rules, imap)
    synthetic.add_edges(graph, rules, imap)
    graph.index()
    return graph


def _unmodelled_decorators(graph: Graph, rules: RuleSet) -> None:
    """R27: a primitive reachable only through a decorator the rules do not model
    is `unverified`; the flag is what reach.py reads to say so."""
    modelled = rules.modelled_decorators()
    for symbol in graph.symbols.values():
        symbol.wrapped_by_unmodelled_decorator = any(
            decorator.name not in modelled for decorator in symbol.decorators)


def _call_edges(calls: list[CallSite]) -> list[Edge]:
    edges: list[Edge] = []
    for site in calls:
        if site.outcome not in {"resolved", "ambiguous"}:
            continue
        for target in sorted(site.targets):
            edges.append(Edge(src=site.caller, dst=target, kind="call", file=site.file,
                              line=site.line, rule=site.rule,
                              ambiguous=site.outcome == "ambiguous"))
    return edges
