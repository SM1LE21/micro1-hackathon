"""Enforcing-foreign-key evidence, bound to the engine (03-verifier.md 4.5, R6).

`ondelete` emits DDL and nothing more [S19]; the cascade runs only where the
connection enforces foreign keys [S15]. Enforcement is a property of the engine the
deleting session is built from, so the evidence is bound to that engine and never to
the repository: a `postgresql://` analytics engine must not bless SE7 for a session
bound to `sqlite:///app.db`, and a `PRAGMA foreign_keys=ON` in a module nothing on
the engine's own import chain loads never runs at all.

Split out of `facts.py` to keep both files inside the 300-line rule.
"""

from __future__ import annotations

from art30.verify.findings import Graph
from art30.verify.rules import RuleSet, norm

CONNECT_EVENT = "connect"
LISTENS_FOR = "listens_for"
LISTEN_CALL = "listen"
# 4.5 [S46]: the SQLAlchemy class a listener may be registered on to cover every
# engine. Compared case-sensitively, so a variable literally named `engine` is matched
# by the engine's own name and never by this.
ENGINE_CLASS = "Engine"


def enforcing_engine(graph: Graph, rules: RuleSet) -> bool | None:
    """4.5: True where the bound engine is shown to enforce foreign keys, else None."""
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
    return True if pragma_listener(graph, rules, engines) else None


def pragma_listener(graph: Graph, rules: RuleSet, engines: list[dict]) -> dict | None:
    """R6 [S46]: a connect listener emitting the PRAGMA, on the engine's own modules.

    Two halves, and the second is the one a repository-wide string scan skipped: the
    call has to be a `connect` listener (`@event.listens_for(Engine, "connect")` or
    `event.listen(...)`), and it has to live in a module the engine construction
    reaches -- the module that builds the engine, or one it imports. A `PRAGMA` in a
    module nobody loads is a string in a file, and SQLite's foreign keys stay inert.
    """
    data = rules.primitives["sqlalchemy"]["enforcing_engine_evidence"]
    literals = [str(data["sqlite_pragma_literal"]), str(data.get("sqlite_pragma_alt") or "")]
    wanted = {text.replace(" ", "") for text in literals if text}
    allowed = _engine_modules(graph, engines)
    named = _engine_vars(graph, engines)
    for listener in _listeners(graph, rules):
        symbol = graph.symbols.get(listener["symbol"])
        if symbol is None or symbol.module not in allowed:
            continue
        target = str(listener.get("target") or "").split(".")[-1]
        if target != ENGINE_CLASS and target not in named:
            continue                    # 4.5: registered on *that* engine [S46]
        if target != ENGINE_CLASS and len(engines) > 1:
            continue                    # several engines, binding not resolved by name
        if _emits(graph, symbol, wanted):
            return listener
    return None


def _engine_vars(graph: Graph, engines: list[dict]) -> set[str]:
    """The names the engines are bound to, so a listener can be tied to one of them.

    `facts.settings_facts` records `create_engine` with an empty `var`; the assignment
    that carries it is the module-level one on the call site's own line, which is the
    same name-following 4.5 asks for at the `sessionmaker(bind=...)` end and needs no
    type inference.
    """
    by_file: dict[str, object] = {}
    for info in graph.modules.values():
        by_file.setdefault(info.file, info)
    found: set[str] = set()
    for engine in engines:
        var = str(engine.get("var") or "")
        if var:
            found.add(var.split(".")[-1])
            continue
        info = by_file.get(str(engine.get("file") or ""))
        for assign in getattr(info, "assigns", []) or []:
            if assign.line == engine.get("line") and assign.target:
                found.add(assign.target.split(".")[-1])
    return found


def _emits(graph: Graph, symbol, wanted: set[str]) -> bool:
    """R6 [S46]: the listener body *calls* something with the PRAGMA as a literal.

    Read off the call sites and never off the raw source span. A text scan accepted
    `# TODO: emit PRAGMA foreign_keys=ON here one day` over a body of `pass` as
    enforcement, and 4.5 requires a listener that emits the statement -- the file is
    already parsed, so the argument is there to be read.
    """
    for site in graph.calls:
        if site.caller != symbol.name:
            continue
        for arg in list(site.args) + list(site.keywords.values()):
            if arg.kind != "literal":
                continue
            if any(text in str(arg.value).replace(" ", "") for text in wanted):
                return True
    return False


def _listeners(graph: Graph, rules: RuleSet) -> list[dict]:
    """The two spellings [S46]: the decorator and the `event.listen(...)` call."""
    out: list[dict] = []
    for symbol in sorted(graph.symbols.values(), key=lambda s: s.name):
        for decorator in symbol.decorators:
            if decorator.name != LISTENS_FOR or len(decorator.args) < 2:
                continue
            if norm(decorator.args[1]) != CONNECT_EVENT:
                continue
            out.append({"symbol": symbol.name, "target": decorator.args[0],
                        "file": decorator.file, "line": decorator.line})
    file_to_module = {m.file: m.module for m in graph.modules.values()}
    for site in sorted(graph.calls, key=lambda c: (c.file, c.line)):
        if site.name != LISTEN_CALL or len(site.args) < 3:
            continue
        if norm(str(site.args[1].value)) != CONNECT_EVENT:
            continue
        module = file_to_module.get(site.file, "")
        name = str(site.args[2].value)
        for candidate in (f"{module}.{name}" if module else name, name):
            if candidate in graph.symbols:
                out.append({"symbol": candidate, "target": str(site.args[0].value),
                            "file": site.file, "line": site.line})
                break
    return out


def _engine_modules(graph: Graph, engines: list[dict]) -> set[str]:
    """The modules that construct an engine, plus what they import (4.5)."""
    file_to_module = {m.file: m.module for m in graph.modules.values()}
    seeds = {file_to_module[e["file"]] for e in engines if e.get("file") in file_to_module}
    reached = set(seeds)
    frontier = sorted(seeds)
    while frontier:
        current = frontier.pop()
        info = graph.modules.get(current)
        if info is None:
            continue
        for _kind, dotted in sorted(info.imports.values()):
            if dotted in graph.modules and dotted not in reached:
                reached.add(dotted)
                frontier.append(dotted)
        for scope, bindings in sorted((graph.settings.get("_local_imports") or {}).items()):
            if not scope.startswith(f"{current}."):
                continue
            for dotted in bindings:
                if dotted in graph.modules and dotted not in reached:
                    reached.add(dotted)
                    frontier.append(dotted)
    return reached
