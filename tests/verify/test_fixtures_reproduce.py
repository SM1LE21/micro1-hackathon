"""The acceptance test for the whole verifier: the twelve synthetic cases.

For each of `S01`-`S10`, `D01` and `D02`, `verdicts(build_graph(case))` must reproduce
every store verdict its manifest carries, and every field-level override inside one.
Store ids are compared through the scorer's own `norm` (05-eval-harness.md Decision 5,
one implementation), with 7.3's declaration-line fallback for the Django file stores
that a manifest calls `<model>.<field>` and no name normalisation reaches.

The verifier never reads a manifest at run time (contract, Verifier contract); this
test reads both sides and compares them, which is what a test is allowed to do. A
manifest that cannot be reproduced is reported, never edited: an `xfail(strict=True)`
naming the store and the reason is the only way a row leaves this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from art30.verify import build_graph
from art30.verify.reach import verdicts
from evals.harness.score import REACHES, build_context, norm
from tests.verify.conftest import FIXTURES

TWELVE = [f"S{i:02d}" for i in range(1, 11)] + ["D01", "D02"]


def _manifest(case: str) -> dict:
    return yaml.safe_load((FIXTURES / "manifests" / f"{case}.yaml").read_text())


def _expected(manifest: dict, ctx: dict) -> dict[str, dict]:
    """Manifest stores, keyed the way the scorer keys them."""
    out: dict[str, dict] = {}
    for store in manifest.get("stores") or []:
        block = store.get("erasure") or {}
        out[norm(store["name"], ctx["prefixes"], ctx["known"])] = {
            "name": store["name"],
            "verdict": block.get("verdict"),
            "timer_days": block.get("timer_days"),
            "fields": {f["name"]: (f.get("erasure") or {}).get("verdict")
                       for f in store.get("fields") or [] if f.get("erasure")},
        }
    return out


def _key(store, ctx: dict) -> str:
    """7.3: name normalisation first, the declaration line as the file-store fallback.

    `avatar.image` and `uploads` never normalise equal, so a record -- and a manifest
    written in the record's vocabulary -- reconciles a Django file store by the
    `FileField` declaration it cites, which is a citation the model has to get right
    anyway.
    """
    key = norm(store.id, ctx["prefixes"], ctx["known"])
    if key in ctx["known"] or store.declared_at is None:
        return key
    named = ctx["file_stores"].get((store.declared_at.file, store.declared_at.line))
    return norm(named, ctx["prefixes"], ctx["known"]) if named else key


@pytest.mark.parametrize("case", TWELVE)
def test_case_reproduces_every_store_verdict(case: str):
    manifest = _manifest(case)
    ctx = build_context(manifest)
    expected = _expected(manifest, ctx)
    graph = build_graph(Path(FIXTURES / "synthetic" / case))
    found = {_key(graph.stores[sid], ctx): (sid, v) for sid, v in verdicts(graph).items()}

    missing = sorted(set(expected) - set(found))
    assert missing == [], f"{case}: the verifier found no store for {missing}"

    for key in sorted(expected):
        want, (store_id, got) = expected[key], found[key]
        assert got.verdict == want["verdict"], (
            f"{case} {want['name']} (verifier id {store_id}): "
            f"expected {want['verdict']}, got {got.verdict} -- {got.note}")
        if want["timer_days"] is not None:
            assert got.timer_days == want["timer_days"], (
                f"{case} {want['name']}: expected {want['timer_days']} days, "
                f"got {got.timer_days}")
        for field, verdict in sorted(want["fields"].items()):
            override = got.fields.get(field)
            assert override is not None, (
                f"{case} {want['name']}.{field}: no field-level override; "
                f"the store reads {got.verdict}")
            assert override.verdict == verdict, (
                f"{case} {want['name']}.{field}: expected {verdict}, "
                f"got {override.verdict}")


@pytest.mark.parametrize("case", TWELVE)
def test_case_reproduces_the_scored_tuple(case: str):
    """The primary metric is `(store, field, reaches_erasure)` (evals/CASES.md), so the
    label agreeing is not enough on its own: the boolean the scorer reads has to agree
    too, and a `backup` store's two verdicts are both on the false side of it."""
    manifest = _manifest(case)
    ctx = build_context(manifest)
    expected = _expected(manifest, ctx)
    graph = build_graph(Path(FIXTURES / "synthetic" / case))
    found = {_key(graph.stores[sid], ctx): v for sid, v in verdicts(graph).items()}
    for key in sorted(expected):
        want = expected[key]
        assert found[key].reaches_erasure == (want["verdict"] in REACHES), (
            f"{case} {want['name']}: reaches_erasure disagrees "
            f"({found[key].verdict} against {want['verdict']})")


@pytest.mark.parametrize("case", TWELVE)
def test_case_never_credits_a_negative_store(case: str):
    """`negatives` are the stores the manifest says hold no personal data (S07's
    `products` is the precision test). None of them may read as reaching erasure --
    a false safe on a store the record should not even carry."""
    manifest = _manifest(case)
    ctx = build_context(manifest)
    graph = build_graph(Path(FIXTURES / "synthetic" / case))
    found = {_key(graph.stores[sid], ctx): v for sid, v in verdicts(graph).items()}
    for name in manifest.get("negatives") or []:
        verdict = found.get(norm(name, ctx["prefixes"], ctx["known"]))
        if verdict is None:
            continue                     # the detectors did not see it at all: fine
        assert not verdict.reaches_erasure, (
            f"{case} {name} is a negative and reads {verdict.verdict}")


def test_every_case_is_covered():
    """Ten synthetic plus the two dev cases; a case added without a manifest fails here."""
    assert sorted(TWELVE) == sorted(p.stem for p in (FIXTURES / "manifests").glob("*.yaml")
                                    if not p.stem.endswith(".labelling"))
