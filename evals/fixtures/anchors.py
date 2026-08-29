"""Anchor resolution (fixture-generator.md section 4).

`<relpath>::<symbol>` in four forms, resolved against the files the generator has just
rendered by re-parsing them with `ast`. `ast.walk` does not preserve source order, so both
search forms sort by `(lineno, col_offset)` before taking the first match.
"""

from __future__ import annotations

import ast

from emit import SpecError


def _last_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _last_name(node.func)
    return None


def _find_def(tree: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return node
    raise SpecError(f"no definition of {name!r}")


def _find_class(tree: ast.AST, name: str) -> ast.ClassDef:
    node = _find_def(tree, name)
    if not isinstance(node, ast.ClassDef):
        raise SpecError(f"{name!r} is not a class")
    return node


def _assignments(node: ast.AST) -> list[ast.AST]:
    return [n for n in ast.walk(node) if isinstance(n, (ast.Assign, ast.AnnAssign))]


def _targets(stmt: ast.AST) -> list[ast.AST]:
    if isinstance(stmt, ast.Assign):
        return list(stmt.targets)
    return [stmt.target]


def _assigns_to(stmt: ast.AST, attr: str) -> bool:
    if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
        return False
    return any(_last_name(t) == attr for t in _targets(stmt))


def resolve(anchor: str, files: dict[str, str]) -> tuple[str, int]:
    """Return `(path, line)` for one anchor, or raise SpecError naming it."""
    if "::" not in anchor:
        raise SpecError(f"{anchor}: not an anchor (expected <path>::<symbol>)")
    path, symbol = anchor.split("::", 1)
    if path not in files:
        raise SpecError(f"{anchor}: no rendered file {path}")
    tree = ast.parse(files[path])
    try:
        if "@" in symbol:
            holder, attr = symbol.split("@", 1)
            node = _find_def(tree, holder)
            for stmt in sorted(_assignments(node), key=lambda n: (n.lineno, n.col_offset)):
                if _assigns_to(stmt, attr):
                    return path, stmt.lineno
            raise SpecError(f"{anchor}: no assignment to {attr} inside {holder}")
        if "!" in symbol:
            holder, callee = symbol.split("!", 1)
            node = _find_def(tree, holder)
            calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
            for call in sorted(calls, key=lambda n: (n.lineno, n.col_offset)):
                if _last_name(call.func) == callee:
                    return path, call.lineno
            raise SpecError(f"{anchor}: no call to {callee} inside {holder}")
        if "." in symbol:
            cls, attr = symbol.split(".", 1)
            node = _find_class(tree, cls)
            for stmt in node.body:
                if _assigns_to(stmt, attr):
                    return path, stmt.lineno
            raise SpecError(f"{anchor}: no assignment to {attr} inside class {cls}")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol:
                return path, node.lineno
        for stmt in tree.body:
            if _assigns_to(stmt, symbol):
                return path, stmt.lineno
        raise SpecError(f"{anchor}: no definition or module-level assignment named {symbol}")
    except SpecError as exc:
        raise SpecError(f"{anchor}: {exc}" if not str(exc).startswith(anchor) else str(exc)) from None


def interpolate(text: str, files: dict[str, str]) -> str:
    """Replace every `{<anchor>}` in a manifest note with `path:line`."""
    out, rest = [], text
    while "{" in rest:
        head, _, tail = rest.partition("{")
        anchor, close, rest = tail.partition("}")
        if not close:
            raise SpecError(f"unclosed anchor brace in note: {text!r}")
        path, line = resolve(anchor, files)
        out.append(head + f"{path}:{line}")
    out.append(rest)
    return "".join(out)
