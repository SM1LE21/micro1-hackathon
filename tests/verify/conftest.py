"""Shared fixtures for the verifier tests (03-verifier.md section 10).

Every fixture is an inline repository written to `tmp_path` by `mkrepo(files)`, so
each test reads in one screen and pins the rule it names.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from art30.verify import build_graph, load_rules

MODELS = "from django.db import models\n"


@pytest.fixture
def mkrepo(tmp_path: Path):
    """`mkrepo({"a/b.py": "..."})` -> the repository root."""

    def _make(files: dict[str, str], name: str = "repo") -> Path:
        root = tmp_path / name
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
        return root

    return _make


@pytest.fixture
def graph_of(mkrepo):
    """The graph of an inline repository."""

    def _graph(files: dict[str, str], name: str = "repo"):
        return build_graph(mkrepo(files, name))

    return _graph


@pytest.fixture(scope="session")
def rules():
    return load_rules()


def edges(graph, kind: str) -> list:
    return sorted((e for e in graph.edges if e.kind == kind),
                  key=lambda e: (e.src, e.dst, e.line))


def edge_between(graph, src: str, dst: str, kind: str | None = None):
    for edge in graph.edges:
        if edge.src == src and edge.dst == dst and (kind is None or edge.kind == kind):
            return edge
    return None


def call(graph, line: int, file: str = "app.py"):
    for site in graph.calls:
        if site.file == file and site.line == line:
            return site
    raise AssertionError(f"no call recorded at {file}:{line}")


def call_named(graph, name: str, index: int = 0):
    found = [s for s in graph.calls if s.name == name or s.dotted == name]
    assert found, f"no call to {name}"
    return found[index]


def store_ids(graph) -> list[str]:
    return sorted(graph.stores)


def entry_names(graph) -> list[str]:
    return sorted(e.name for e in graph.entry_points)


CASES = [f"S{i:02d}" for i in range(1, 11)]
FIXTURES = Path(__file__).resolve().parents[2] / "evals" / "fixtures"
