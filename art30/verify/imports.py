"""The import map of 03-verifier.md 1.3.

Per module, a dict from a local name to a target that is an intra-repo symbol, an
intra-repo module, or an external dotted path. A function-body import is recorded
with the same binding, scoped to that function, and shadows the module-level one.
`from x import *` flags the module; its unbound names fall through to CG-3/CG-4.
`importlib.import_module` and `__import__` bind nothing (1.5, CG-12).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

SYMBOL, MODULE, EXTERNAL = "symbol", "module", "external"
Target = tuple[str, str]


@dataclass
class ImportMap:
    modules: dict[str, dict[str, Target]] = field(default_factory=dict)
    local: dict[str, dict[str, Target]] = field(default_factory=dict)
    wildcard: set[str] = field(default_factory=set)

    def lookup(self, module: str, scope: str | None, name: str) -> Target | None:
        if scope:
            for owner in _enclosing_scopes(scope):
                if name in self.local.get(owner, {}):
                    return self.local[owner][name]
        return self.modules.get(module, {}).get(name)

    def resolve_dotted(self, module: str, scope: str | None, written: str) -> str:
        """`models.CASCADE` -> the dotted path its head is bound to, else as written."""
        if not written:
            return ""
        head, _, tail = written.partition(".")
        target = self.lookup(module, scope, head)
        if target is None:
            return written
        base = target[1]
        return f"{base}.{tail}" if tail else base


def _enclosing_scopes(scope: str) -> list[str]:
    parts = scope.split(".")
    return [".".join(parts[: i + 1]) for i in range(len(parts) - 1, 0, -1)]


def package_of(module: str, is_package: bool) -> str:
    if is_package:
        return module
    return ".".join(module.split(".")[:-1])


def _absolute(package: str, level: int, module: str | None) -> str:
    parts = [p for p in package.split(".") if p]
    if level > 1:
        parts = parts[: max(0, len(parts) - (level - 1))]
    base = ".".join(parts)
    if module:
        return f"{base}.{module}" if base else module
    return base


def build(records, packages: dict[str, bool], symbols: set[str],
          module_names: set[str]) -> ImportMap:
    """`records` is `Extraction.imports`: (module, scope or None, the statement)."""
    imap = ImportMap()
    for module in sorted(packages):
        imap.modules.setdefault(module, {})
    for module, scope, node in records:
        into = imap.modules.setdefault(module, {}) if scope is None else imap.local.setdefault(scope, {})
        if isinstance(node, ast.Import):
            for alias in node.names:
                into[alias.asname or alias.name] = _target(alias.name, symbols, module_names)
                if not alias.asname:
                    head = alias.name.split(".")[0]
                    into.setdefault(head, _target(head, symbols, module_names))
        elif isinstance(node, ast.ImportFrom):
            package = package_of(module, packages.get(module, False))
            base = _absolute(package, node.level, node.module) if node.level else (node.module or "")
            for alias in node.names:
                if alias.name == "*":
                    imap.wildcard.add(module)
                    continue
                dotted = f"{base}.{alias.name}" if base else alias.name
                into[alias.asname or alias.name] = _target(dotted, symbols, module_names)
    return imap


def _target(dotted: str, symbols: set[str], module_names: set[str]) -> Target:
    if dotted in symbols:
        return (SYMBOL, dotted)
    if dotted in module_names:
        return (MODULE, dotted)
    return (EXTERNAL, dotted)
