"""The symbol table and the raw call sites (03-verifier.md 1.2 and the 1.5 extraction).

One traversal per module records every definition under a qualified name that is
stable across runs, every import statement with the scope that owns it, every
`ast.Call` as written, and every assignment. Nothing here resolves a name: that is
1.5, and it lives in `callgraph.py`.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from art30.verify.astdata import (_assign, _assign_targets, _decorators, _for_assign,
                                  describe, dotted_of, field_decl)
from art30.verify.discovery import ParsedModule
from art30.verify.entities import Assign, CallSite, ClassInfo, FieldDecl, Symbol


@dataclass
class Extraction:
    symbols: dict[str, Symbol] = field(default_factory=dict)
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    calls: list[CallSite] = field(default_factory=list)
    imports: list[tuple[str, str | None, ast.stmt]] = field(default_factory=list)
    module_assigns: dict[str, list[Assign]] = field(default_factory=dict)
    name_refs: list[tuple[str, str, str, int]] = field(default_factory=list)
    ambiguous_names: set[str] = field(default_factory=set)


class _Walker(ast.NodeVisitor):
    def __init__(self, parsed: ParsedModule, out: Extraction) -> None:
        self.parsed = parsed
        self.out = out
        self.scope: list[str] = []      # qualname parts
        self.classes: list[str] = []
        self.in_function = 0
        self.lambda_depth = 0

    # -- naming ---------------------------------------------------------
    def qual(self, name: str) -> str:
        parts = [self.parsed.module] + self.scope + [name]
        return ".".join(p for p in parts if p)

    @property
    def owner(self) -> str | None:
        return self.classes[-1] if self.classes else None

    @property
    def current(self) -> str:
        parts = [self.parsed.module] + self.scope
        joined = ".".join(p for p in parts if p)
        return joined or self.parsed.module

    def caller(self) -> str:
        if self.in_function:
            return self.current
        return f"{self.parsed.module}.<module>" if self.parsed.module else "<module>"

    # -- definitions ----------------------------------------------------
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qual = self.qual(node.name)
        body: list[Assign] = []
        fields: list[FieldDecl] = []
        for stmt in node.body:
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                body += _assign(stmt, self.parsed.file)
                if isinstance(stmt.value, ast.Call):
                    for target in _assign_targets(stmt):
                        fields.append(field_decl(target, stmt.value, self.parsed.file))
        info = ClassInfo(
            name=qual, short=node.name, module=self.parsed.module, file=self.parsed.file,
            line=node.lineno, end_line=node.end_lineno or node.lineno,
            bases=[dotted_of(b) for b in node.bases],
            decorators=_decorators(node.decorator_list, self.parsed.file),
            body=body,
            fields=fields,
            keywords={k.arg: dotted_of(k.value) or describe(k.value).value
                      for k in node.keywords if k.arg},
        )
        if qual in self.out.classes:
            self.out.ambiguous_names.add(qual)
        self.out.classes[qual] = info
        self.scope.append(node.name)
        self.classes.append(qual)
        for stmt in node.body:
            self.visit(stmt)
        self.classes.pop()
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node, is_async=True)

    def _function(self, node, is_async: bool) -> None:
        qual = self.qual(node.name)
        decorators = _decorators(node.decorator_list, self.parsed.file)
        names = {d.name for d in decorators}
        kind = "function"
        if self.owner and not self.in_function:
            kind = "method"
            for special in ("classmethod", "staticmethod", "property"):
                if special in names:
                    kind = special
        symbol = Symbol(
            name=qual, short=node.name, module=self.parsed.module, kind=kind,
            file=self.parsed.file, line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            owner=self.owner, decorators=decorators,
            args=[a.arg for a in node.args.args + node.args.kwonlyargs],
            is_nested=bool(self.in_function), is_async=is_async,
        )
        if qual in self.out.symbols:
            self.out.ambiguous_names.add(qual)   # 1.2: a conditional redefinition
        self.out.symbols[qual] = symbol
        self.scope.append(node.name)
        self.in_function += 1
        for stmt in node.body:
            self.visit(stmt)
        self.in_function -= 1
        self.scope.pop()

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # 1.2: an inline lambda folds into its enclosing function; its calls are
        # attributed there and the fold is recorded so R11 can find it.
        self.lambda_depth += 1
        self.generic_visit(node)
        self.lambda_depth -= 1

    # -- statements -----------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        self.out.imports.append((self.parsed.module, self.current if self.in_function else None, node))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.out.imports.append((self.parsed.module, self.current if self.in_function else None, node))

    def visit_For(self, node: ast.For) -> None:
        self._store_assigns(_for_assign(node, self.parsed.file))
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._store_assigns(_for_assign(node, self.parsed.file))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self._record_assign(node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._record_assign(node)
        self.generic_visit(node)

    def _store_assigns(self, records: list[Assign]) -> None:
        if self.in_function:
            symbol = self.out.symbols.get(self.current)
            if symbol is not None:
                symbol.assigns += records
                return
        self.out.module_assigns.setdefault(self.parsed.module, []).extend(records)

    def _record_assign(self, node) -> None:
        records = _assign(node, self.parsed.file)
        self._store_assigns(records)
        # `f = lambda ...` is a symbol named f (1.2).
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Lambda):
            for target in _assign_targets(node):
                qual = self.qual(target)
                self.out.symbols[qual] = Symbol(
                    name=qual, short=target, module=self.parsed.module, kind="lambda",
                    file=self.parsed.file, line=node.lineno,
                    end_line=node.end_lineno or node.lineno, owner=self.owner,
                    args=[a.arg for a in node.value.args.args],
                )

    def visit_Call(self, node: ast.Call) -> None:
        site = CallSite(
            caller=self.caller(), file=self.parsed.file, line=node.lineno,
            form="other", name="", in_lambda=bool(self.lambda_depth),
            args=[describe(a) for a in node.args],
            keywords={k.arg: describe(k.value) for k in node.keywords if k.arg},
        )
        func = node.func
        if isinstance(func, ast.Name):
            site.form, site.name, site.dotted = "name", func.id, func.id
        elif isinstance(func, ast.Attribute):
            site.form, site.name = "attribute", func.attr
            site.receiver = dotted_of(func.value)
            site.dotted = dotted_of(func) or f"{site.receiver}.{func.attr}"
        else:
            site.dotted = dotted_of(func)
        self.out.calls.append(site)
        # CG-15: a callable named in argument position is a reference, not a call.
        for arg in list(node.args) + [k.value for k in node.keywords]:
            if isinstance(arg, ast.Name):
                self.out.name_refs.append((self.caller(), arg.id, self.parsed.file, node.lineno))
        self.generic_visit(node)


def extract(modules: list[ParsedModule]) -> Extraction:
    out = Extraction()
    for parsed in modules:
        walker = _Walker(parsed, out)
        for stmt in parsed.tree.body:
            walker.visit(stmt)
    return out
