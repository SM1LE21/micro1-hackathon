"""Declared against discovered entry points (03-verifier.md 2.5, decision 5a).

A declared entry point the verifier cannot see registered as externally invocable
is kept as a start node and capped: every verdict derived from it is `unverified`.
Adding a start node makes more stores read `erased`, which is the unsafe direction,
and S10 falls in four lines without the cap.
"""

from __future__ import annotations

from art30.verify.entities import Symbol
from art30.verify.findings import Graph


def registration_shapes(graph: Graph, symbol: Symbol) -> list[str]:
    """2.5: is anything outside the process able to call this symbol at all?"""
    shapes: set[str] = set()
    for entry in graph.entry_points:
        if entry.symbol == symbol.name:
            shapes.update(entry.flags)
    for decorator in symbol.decorators:
        if decorator.name in {"route", "delete", "get", "post", "put", "patch", "api_view"}:
            shapes.add("route_decorator")
        if decorator.name in {"task", "shared_task", "periodic_task", "job"}:
            shapes.add("task_decorator")
        if decorator.name in {"command", "group"}:
            shapes.add("click_or_typer_command")
    if "/management/commands/" in symbol.file:
        shapes.add("BaseCommand_subclass")
    return sorted(shapes)


def reconcile(graph: Graph, declared: list[dict]) -> list[dict]:
    """2.5: declared against discovered, with the `declared_unregistered` cap."""
    out: list[dict] = []
    discovered = {(e.name, e.file, e.line): e for e in graph.entry_points}
    by_name = {e.name: e for e in graph.entry_points}
    for item in sorted(declared, key=lambda d: (d.get("file", ""), d.get("line", 0),
                                                d.get("name", ""))):
        name, file, line = item.get("name", ""), item.get("file", ""), int(item.get("line", 0))
        key = (name, file, line)
        if key in discovered or (name in by_name and by_name[name].file == file):
            out.append({"name": name, "file": file, "line": line, "status": "confirmed",
                        "capped": False})
            continue
        symbol = next((s for s in sorted(graph.symbols.values(), key=lambda s: s.name)
                       if s.short == name and s.file == file
                       and s.line <= line <= s.end_line), None)
        if symbol is None:
            out.append({"name": name, "file": file, "line": line, "status": "unresolved",
                        "capped": True})
            continue
        shapes = registration_shapes(graph, symbol)
        status = "declared_only" if shapes else "declared_unregistered"
        out.append({"name": name, "file": file, "line": symbol.line, "status": status,
                    "symbol": symbol.name, "shapes": shapes,
                    "capped": status == "declared_unregistered"})
    declared_keys = {(d.get("name", ""), d.get("file", "")) for d in declared}
    for entry in graph.entry_points:
        if (entry.name, entry.file) not in declared_keys:
            out.append({"name": entry.name, "file": entry.file, "line": entry.line,
                        "kind": entry.kind, "status": "missing", "capped": False})
    return sorted(out, key=lambda d: (d["file"], d["line"], d["name"], d["status"]))
