"""What the detectors and the discovery pass found: stores, entry points, the graph.

The record half of `entities.py` (which holds the syntax half). 03-verifier.md 2
(entry points), 3 (stores), 1.6 (what the graph is) and 7.5 (every collection that
leaves a module is sorted).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from art30.verify.entities import CallSite, ClassInfo, Edge, ModuleInfo, Reference, Symbol


@dataclass
class Cite:
    file: str
    line: int

    def as_dict(self) -> dict:
        return {"file": self.file, "line": self.line}


@dataclass
class StoreField:
    name: str
    file: str
    line: int
    declared: str = ""             # the field call as written, where there is one
    flags: list[str] = field(default_factory=list)
    category: str | None = None    # only where the rule data carries one (R23)

    def as_dict(self) -> dict:
        return {"name": self.name, "file": self.file, "line": self.line,
                "declared": self.declared, "flags": sorted(self.flags),
                "category": self.category}


@dataclass
class Store:
    id: str
    kind: str
    name: str
    declared_at: Cite | None = None
    subject_link: Cite | None = None
    model: str | None = None       # the class this store was detected from
    identity: str = ""             # 3.10: the literal a keyed primitive must match
    client_vars: list[str] = field(default_factory=list)
    fields: list[StoreField] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    primitives: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    subject_root: bool = False
    guard: str = ""                # "" | strong | qualified (3.9, guard only)
    note: str = ""

    @property
    def node(self) -> str:
        return f"store:{self.id}"

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "name": self.name,
                "declared_at": self.declared_at.as_dict() if self.declared_at else None,
                "subject_link": self.subject_link.as_dict() if self.subject_link else None,
                "model": self.model, "identity": self.identity,
                "client_vars": sorted(self.client_vars),
                "fields": [f.as_dict() for f in self.fields],
                "primitives": sorted(self.primitives, key=lambda p: (p.get("file", ""), p.get("line", 0), p.get("call", ""))),
                "evidence": self.evidence, "flags": sorted(self.flags),
                "subject_root": self.subject_root, "guard": self.guard, "note": self.note}


@dataclass
class EntryPoint:
    name: str
    kind: str                      # route | view | cli | admin | task | signal | unknown
    file: str
    line: int
    symbol: str | None = None
    admin_only: bool = False
    mode: str = "none"             # 4.2: mode_of(entry). Always `none`: no entry point
                                   # starts a walk in a delete mode; a primitive or SE10
                                   # sets one, which is what keeps SE8 off a queryset path.
    sets_mode: str | None = None   # what SE10 sets for the two admin entry points [S8] [S9]
    path: str = ""                 # the route string where there is one
    models: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def node(self) -> str:
        return f"entry:{self.name}"

    def key(self) -> tuple:
        return (self.name, self.file, self.line, self.kind)

    def as_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "file": self.file, "line": self.line,
                "symbol": self.symbol, "admin_only": self.admin_only, "mode": self.mode,
                "sets_mode": self.sets_mode,
                "path": self.path, "models": sorted(self.models),
                "flags": sorted(self.flags), "note": self.note}


@dataclass
class Relation:
    """A foreign key or a relationship, read as written (R1-R7)."""

    parent: str                    # store id of the referenced table
    child: str                     # store id of the declaring table
    kind: str                      # fk | relationship | secondary
    token: str = ""                # on_delete token, or the cascade string
    ondelete: str = ""             # SQLAlchemy ForeignKey(ondelete=...)
    passive_deletes: bool = False
    file: str = ""
    line: int = 0
    field_name: str = ""           # the attribute as written on the declaring class
    related_name: str = ""         # Django `related_name=`: the accessor from the parent


@dataclass
class Receiver:
    """A pre_delete / post_delete receiver, from the decorator or from .connect()."""

    symbol: str
    signal: str
    sender: str | None
    file: str
    line: int
    weak: bool = True
    nested: bool = False
    guards_on_sender: bool = False
    connected: bool = False
    reason: str = ""

    def as_dict(self) -> dict:
        return {"symbol": self.symbol, "signal": self.signal, "sender": self.sender,
                "file": self.file, "line": self.line, "weak": self.weak,
                "nested": self.nested, "guards_on_sender": self.guards_on_sender,
                "connected": self.connected, "reason": self.reason}


@dataclass
class Graph:
    root: Path
    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    symbols: dict[str, Symbol] = field(default_factory=dict)
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    calls: list[CallSite] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    unresolved: list[CallSite] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    stores: dict[str, Store] = field(default_factory=dict)
    entry_points: list[EntryPoint] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    receivers: list[Receiver] = field(default_factory=list)
    task_table: dict[str, str] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    versioning: list[dict] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    unparsed: list[dict] = field(default_factory=list)
    _out: dict[str, list[Edge]] = field(default_factory=dict, repr=False)

    @property
    def nodes(self) -> dict[str, dict]:
        found: dict[str, dict] = {}
        for symbol in self.symbols.values():
            found[symbol.name] = {"id": symbol.name, "kind": "symbol",
                                  "file": symbol.file, "line": symbol.line}
        for store in self.stores.values():
            found[store.node] = {"id": store.node, "kind": f"store:{store.kind}",
                                 "file": store.declared_at.file if store.declared_at else "",
                                 "line": store.declared_at.line if store.declared_at else 0}
        for entry in self.entry_points:
            found[entry.node] = {"id": entry.node, "kind": f"entry:{entry.kind}",
                                 "file": entry.file, "line": entry.line}
        return dict(sorted(found.items()))

    def index(self) -> None:
        self.edges.sort(key=lambda e: e.key())
        self._out = {}
        for edge in self.edges:
            self._out.setdefault(edge.src, []).append(edge)

    def out(self, node: str) -> list[Edge]:
        """Out-edges, already in the sorted order 03-verifier.md 5.2 walks."""
        return list(self._out.get(node, ()))

    def store_for_model(self, model: str, kind: str = "relational") -> Store | None:
        """The row store for a model. A `FileField` store shares the class (R8) and is
        found by id, never by this lookup, or `account.delete()` would resolve to the
        bytes rather than to the row."""
        for store in sorted(self.stores.values(), key=lambda s: s.id):
            if store.model == model and store.kind == kind:
                return store
        return None

    def to_dict(self) -> dict:
        return {
            "nodes": [self.nodes[key] for key in sorted(self.nodes)],
            "edges": [e.as_dict() for e in sorted(self.edges, key=lambda e: e.key())],
            "symbols": [self.symbols[k].as_dict() for k in sorted(self.symbols)],
            "classes": [self.classes[k].as_dict() for k in sorted(self.classes)],
            "stores": [self.stores[k].as_dict() for k in sorted(self.stores)],
            "entry_points": [e.as_dict() for e in sorted(self.entry_points, key=lambda e: e.key())],
            "receivers": [r.as_dict() for r in sorted(self.receivers, key=lambda r: (r.file, r.line, r.symbol))],
            "references": [r.as_dict() for r in sorted(self.references, key=lambda r: (r.file, r.line, r.target))],
            "unresolved": [c.as_dict() for c in sorted(self.unresolved, key=lambda c: (c.file, c.line, c.dotted or c.name))],
            "task_table": dict(sorted(self.task_table.items())),
            "versioning": sorted(self.versioning, key=lambda v: (v["file"], v["line"])),
            "settings": _sorted_settings(self.settings),
            "skipped": dict(sorted(self.skipped.items())),
            "unparsed": sorted(self.unparsed, key=lambda u: u["file"]),
        }


def _sorted_settings(settings: dict[str, Any]) -> dict:
    out: dict[str, Any] = {}
    for key in sorted(settings):
        value = settings[key]
        out[key] = sorted(value, key=repr) if isinstance(value, (set, frozenset)) else value
    return out
