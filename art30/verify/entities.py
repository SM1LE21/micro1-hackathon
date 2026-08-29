"""The data the verifier's four modules pass to each other.

One dataclass per thing 03-verifier.md names: a symbol (1.2), a class (1.2), a
decorator read as data (1.4, R27), a call site and its resolution (1.5), an edge
of the graph (1.6), a store (3), an entry point (2) and the `Graph` itself.

Nothing here parses, matches or decides. Every collection that leaves the graph
is sorted before it is emitted (03-verifier.md 7.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 03-verifier.md 4.1. The names only; the search state and its admissibility
# table ship as a constant in reach.py, which owns the walk.
MODES: tuple[str, ...] = (
    "none",
    "model_delete",
    "queryset_delete",
    "db_cascade",
    "session_delete",
    "bulk_dml",
    "raw_sql",
)


@dataclass
class Decorator:
    """R27 [S35]: every decorator_list entry recorded, none interpreted."""

    name: str
    dotted: str
    args: list[str] = field(default_factory=list)
    keywords: dict[str, str] = field(default_factory=dict)
    file: str = ""
    line: int = 0

    def as_dict(self) -> dict:
        return {"name": self.name, "dotted": self.dotted, "args": list(self.args),
                "keywords": dict(sorted(self.keywords.items())), "file": self.file,
                "line": self.line}


@dataclass
class Assign:
    """An assignment kept for R25 (soft delete) and 4.7 (anonymised vs pseudonymised)."""

    target: str
    value_kind: str
    value_repr: str
    file: str
    line: int
    refs: list[str] = field(default_factory=list)   # every Name in the value
    keys: list[str] = field(default_factory=list)   # literal strings in the value

    def as_dict(self) -> dict:
        return {"target": self.target, "value_kind": self.value_kind,
                "value_repr": self.value_repr, "file": self.file, "line": self.line,
                "refs": list(self.refs), "keys": list(self.keys)}


@dataclass
class Arg:
    """One argument of a call site, described without evaluating it."""

    kind: str                      # literal | name | attribute | call | fstring | other
    value: str = ""                # literal text, dotted name, or callee
    prefix: str = ""               # fstring literal prefix up to the first placeholder
    names: list[str] = field(default_factory=list)   # attribute tails seen inside
    keys: list[str] = field(default_factory=list)    # dict-literal keys seen inside
    refs: list[str] = field(default_factory=list)    # bare names seen inside


@dataclass
class CallSite:
    caller: str
    file: str
    line: int
    form: str                      # name | attribute | other
    name: str                      # bare name, or the attribute tail
    receiver: str = ""             # dotted receiver as written
    dotted: str = ""               # the whole callee as written
    args: list[Arg] = field(default_factory=list)
    keywords: dict[str, Arg] = field(default_factory=dict)
    in_lambda: bool = False
    outcome: str = "unresolved"    # resolved | ambiguous | unresolved
    rule: str = ""                 # CG-1 .. CG-20
    targets: list[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        return {"caller": self.caller, "file": self.file, "line": self.line,
                "dotted": self.dotted or self.name, "outcome": self.outcome,
                "rule": self.rule, "targets": sorted(self.targets), "reason": self.reason}


@dataclass
class Reference:
    """CG-15: a callable named in argument position. Not a call, not an edge."""

    caller: str
    target: str
    file: str
    line: int
    promoted_by: str = ""

    def as_dict(self) -> dict:
        return {"caller": self.caller, "target": self.target, "file": self.file,
                "line": self.line, "promoted_by": self.promoted_by}


@dataclass
class Symbol:
    name: str                      # module.qualname (1.2)
    short: str
    module: str
    kind: str                      # function | method | classmethod | staticmethod | property | lambda
    file: str
    line: int
    end_line: int
    owner: str | None = None       # the class that owns a method
    decorators: list[Decorator] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    is_nested: bool = False
    is_async: bool = False
    dynamic: bool = False                          # CG-12
    wrapped_by_unmodelled_decorator: bool = False  # R27
    assigns: list[Assign] = field(default_factory=list)
    var_models: dict[str, str] = field(default_factory=dict)  # spike finding 2

    def as_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "file": self.file, "line": self.line,
                "end_line": self.end_line, "owner": self.owner, "is_nested": self.is_nested,
                "dynamic": self.dynamic,
                "wrapped_by_unmodelled_decorator": self.wrapped_by_unmodelled_decorator,
                "decorators": [d.as_dict() for d in self.decorators],
                "var_models": dict(sorted(self.var_models.items()))}


@dataclass
class FieldDecl:
    """A class-body declaration read as written: `email = models.EmailField(...)`."""

    target: str
    call: str
    file: str
    line: int
    args: list["Arg"] = field(default_factory=list)
    keywords: dict[str, "Arg"] = field(default_factory=dict)
    raw: list[str] = field(default_factory=list)          # positional args, dotted
    kwraw: dict[str, str] = field(default_factory=dict)   # keywords, dotted
    nested: list["FieldDecl"] = field(default_factory=list)

    @property
    def short_call(self) -> str:
        return self.call.split(".")[-1]

    def find(self, name: str) -> "FieldDecl | None":
        for item in self.nested:
            if item.short_call == name:
                return item
        return None


@dataclass
class ClassInfo:
    name: str                      # module.Qualname
    short: str
    module: str
    file: str
    line: int
    end_line: int
    bases: list[str] = field(default_factory=list)
    decorators: list[Decorator] = field(default_factory=list)
    body: list[Assign] = field(default_factory=list)
    fields: list[FieldDecl] = field(default_factory=list)
    keywords: dict[str, str] = field(default_factory=dict)   # SQLModel table=True

    def as_dict(self) -> dict:
        return {"name": self.name, "file": self.file, "line": self.line,
                "bases": list(self.bases),
                "decorators": [d.as_dict() for d in self.decorators]}


@dataclass
class ModuleInfo:
    module: str
    file: str
    source: str = ""
    is_package: bool = False
    wildcard: bool = False
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)
    local_imports: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    assigns: list[Assign] = field(default_factory=list)


@dataclass
class Edge:
    src: str
    dst: str
    kind: str                      # call | reference | SE1 .. SE12
    file: str
    line: int
    rule: str
    ambiguous: bool = False
    modes: tuple[str, ...] = MODES
    sets_mode: str | None = None
    note: str = ""

    @property
    def to(self) -> str:            # the search reads edge.to (03-verifier.md 5.2)
        return self.dst

    @property
    def admissible_modes(self) -> tuple[str, ...]:
        return self.modes

    def key(self) -> tuple:
        return (self.src, self.dst, self.kind, self.file, self.line, self.rule)

    def as_dict(self) -> dict:
        return {"src": self.src, "dst": self.dst, "kind": self.kind, "file": self.file,
                "line": self.line, "rule": self.rule, "ambiguous": self.ambiguous,
                "modes": list(self.modes), "sets_mode": self.sets_mode, "note": self.note}
