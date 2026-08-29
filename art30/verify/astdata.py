"""AST nodes read as data (03-verifier.md 1.4, R27 [S35]).

Dotted names as written, one argument described without evaluating it, a decorator
list kept verbatim, a class-body field declaration with its nested calls, and the
assignments R25 and 4.7 read. Nothing here interprets what it records.
"""

from __future__ import annotations

import ast
from art30.verify.entities import Arg, Assign, Decorator, FieldDecl

DYNAMIC_CALLS = frozenset({"getattr", "eval", "exec", "globals", "locals",
                           "__import__", "import_module"})


def dotted_of(node: ast.AST) -> str:
    """`a.b.c` as written; "" for anything that is not a Name/Attribute chain."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = dotted_of(node.value)
        return f"{head}.{node.attr}" if head else ""
    if isinstance(node, ast.Call):
        head = dotted_of(node.func)
        return f"{head}()" if head else ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return repr(node.value)
    return ""


def describe(node: ast.AST) -> Arg:
    """One argument, described without evaluating it."""
    if isinstance(node, ast.Constant):
        return Arg(kind="literal", value=str(node.value))
    if isinstance(node, ast.Name):
        return Arg(kind="name", value=node.id)
    if isinstance(node, ast.Attribute):
        dotted = dotted_of(node)
        return Arg(kind="attribute", value=dotted, names=[node.attr])
    if isinstance(node, ast.JoinedStr):
        prefix = ""
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                prefix += part.value
            else:
                break
        names = [n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)]
        return Arg(kind="fstring", value=_fstring_repr(node), prefix=prefix, names=names)
    if isinstance(node, ast.Dict):
        keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        names = [n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)]
        return Arg(kind="dict", value="{...}", keys=keys, names=names)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        keys = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        return Arg(kind="sequence", value="[...]", keys=keys)
    if isinstance(node, ast.Call):
        names = [n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)]
        keys = [k.value for k in ast.walk(node)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        refs = [n.id for n in ast.walk(node.args and node or node) if isinstance(n, ast.Name)]
        return Arg(kind="call", value=dotted_of(node.func), names=names, keys=keys, refs=refs)
    names = [n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)]
    return Arg(kind="other", value=ast.dump(node)[:40], names=names)


def _fstring_repr(node: ast.JoinedStr) -> str:
    out = ""
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            out += part.value
        elif isinstance(part, ast.FormattedValue):
            out += "{" + dotted_of(part.value) + "}"
    return out


def _dec_text(node: ast.AST) -> str:
    """A decorator argument as text; a literal list keeps its members (`["DELETE"]`)."""
    written = dotted_of(node)
    if written:
        return written.strip("'\"")
    arg = describe(node)
    return ",".join(arg.keys) if arg.keys else arg.value


def _decorators(nodes: list[ast.expr], file: str) -> list[Decorator]:
    """R27 [S35]: recorded, never interpreted."""
    out: list[Decorator] = []
    for node in nodes:
        call = node if isinstance(node, ast.Call) else None
        target = call.func if call else node
        written = dotted_of(target)
        name = written.split(".")[-1] if written else ""
        args = [_dec_text(a) for a in (call.args if call else [])]
        keywords = {k.arg: _dec_text(k.value) for k in (call.keywords if call else []) if k.arg}
        out.append(Decorator(name=name, dotted=written, args=args, keywords=keywords,
                             file=file, line=node.lineno))
    return out


def _assign_targets(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Assign):
        return [dotted_of(t) for t in node.targets if dotted_of(t)]
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        return [dotted_of(node.target)] if dotted_of(node.target) else []
    return []


def _assign(node: ast.Assign | ast.AnnAssign, file: str) -> list[Assign]:
    value = node.value
    if value is None:
        return []
    arg = describe(value)
    kind = arg.kind
    if isinstance(value, ast.Constant) and value.value is None:
        kind = "none"
    refs = sorted({n.id for n in ast.walk(value) if isinstance(n, ast.Name)})
    keys = [k.value for k in ast.walk(value)
            if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    return [Assign(target=t, value_kind=kind, value_repr=arg.value, file=file,
                   line=node.lineno, refs=refs, keys=keys)
            for t in _assign_targets(node)]


def _for_assign(node: ast.For | ast.AsyncFor, file: str) -> list[Assign]:
    """`for row in session.query(User).all()` binds row the way an assignment does."""
    target = dotted_of(node.target)
    if not target:
        return []
    refs = sorted({n.id for n in ast.walk(node.iter) if isinstance(n, ast.Name)})
    return [Assign(target=target, value_kind="for", value_repr=dotted_of(node.iter),
                   file=file, line=node.lineno, refs=refs)]


def field_decl(target: str, node: ast.Call, file: str) -> FieldDecl:
    """A class-body call, with its nested calls kept (a ForeignKey inside a Column)."""
    decl = FieldDecl(
        target=target, call=dotted_of(node.func), file=file, line=node.lineno,
        args=[describe(a) for a in node.args],
        keywords={k.arg: describe(k.value) for k in node.keywords if k.arg},
        raw=[dotted_of(a) for a in node.args],
        kwraw={k.arg: dotted_of(k.value) for k in node.keywords if k.arg},
    )
    for child in list(node.args) + [k.value for k in node.keywords]:
        if isinstance(child, ast.Call):
            decl.nested.append(field_decl(target, child, file))
    return decl
