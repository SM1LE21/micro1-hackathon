"""The two name-binding tables the graph carries beside its edges (03-verifier.md 1.5).

The variable-to-model table of the spike's finding 2 -- `user = User.objects.get(...)`
then `user.delete()`, three lines of assignment tracking and no type inference -- and
the reference records of CG-15, a callable named in argument position that makes no
edge on its own. Split out of `callgraph.py`, which owns CG-1 to CG-20 and the graph.
"""

from __future__ import annotations

from typing import Callable

from art30.verify import imports as importmap
from art30.verify.entities import Reference
from art30.verify.symbols import Extraction


def var_models(extraction: Extraction, imap: importmap.ImportMap) -> None:
    """The spike's finding 2: a variable to model table, and no type inference."""
    for symbol in extraction.symbols.values():
        found: dict[str, str] = {}
        for assign in symbol.assigns:
            models = _models_in(assign.refs, symbol.module, symbol.name, imap, extraction)
            if len(models) == 1 and "." not in assign.target:
                found[assign.target] = models[0]
        symbol.var_models = found


def _models_in(refs: list[str], module: str, scope: str | None,
               imap: importmap.ImportMap, extraction: Extraction) -> list[str]:
    out: list[str] = []
    for ref in refs:
        target = imap.lookup(module, scope, ref)
        if target and target[0] == importmap.SYMBOL and target[1] in extraction.classes:
            out.append(target[1])
            continue
        local = f"{module}.{ref}" if module else ref
        if local in extraction.classes:
            out.append(local)
    return sorted(set(out))


def references(extraction: Extraction, imap: importmap.ImportMap,
               short_names: Callable[[str], list[str]]) -> list[Reference]:
    """CG-15: a callable in argument position makes a reference, never an edge."""
    out: list[Reference] = []
    for caller, name, file, line in extraction.name_refs:
        symbol = extraction.symbols.get(caller)
        module = symbol.module if symbol else caller.rsplit(".", 1)[0]
        scope = caller if symbol else None
        target = imap.lookup(module, scope, name)
        resolved = None
        if target and target[0] == importmap.SYMBOL and target[1] in extraction.symbols:
            resolved = target[1]
        else:
            local = f"{module}.{name}" if module else name
            if local in extraction.symbols:
                resolved = local
            else:
                candidates = short_names(name)
                resolved = candidates[0] if len(candidates) == 1 else None
        if resolved:
            out.append(Reference(caller=caller, target=resolved, file=file, line=line))
    return out
