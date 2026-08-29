"""One record and one manifest into one number (docs/spec/05-eval-harness.md sections 1-4).

The tuple is (store, field, reaches_erasure) (evals/CASES.md, Primary metric). Normalisation
lives here and nowhere else: the verifier imports `norm` from this module so the metric and the
tool cannot drift apart (05 Decision 5).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from art30.naming import (  # noqa: F401 - re-exported: one implementation, imported from here by the fixtures
    E_STEM, SUFFIX_KEEP, _base, _singular, _strip_prefix, norm, stems,
)

REACHES = frozenset({"erased", "erased_after_timer", "anonymised"})
BACKUP_VERDICTS = frozenset({"governed_by_retention", "no_schedule_evidenced"})

Tuples = dict[tuple[str, str], dict[str, Any]]


def _citation(value: Any) -> tuple[str, int] | None:
    """A declared_at as either {file, line} or the manifest's "file:line" string."""
    if isinstance(value, dict) and value.get("file") and value.get("line") is not None:
        return (str(value["file"]), int(value["line"]))
    if isinstance(value, str) and ":" in value:
        head, _, tail = value.rpartition(":")
        if tail.isdigit():
            return (head, int(tail))
    return None


def build_context(manifest: dict) -> dict[str, Any]:
    """Everything the prediction side needs from the manifest before any comparison."""
    prefixes = tuple((manifest.get("normalisation") or {}).get("prefixes") or ())
    manifest_stores = manifest.get("stores") or []
    names = [s["name"] for s in manifest_stores]
    file_stores: dict[tuple[str, int], str] = {}
    for store in manifest_stores:
        cite = _citation(store.get("declared_at"))
        if cite is None:  # a manifest with no declared_at: the file store's one field cites it
            first = (store.get("fields") or [None])[0]
            cite = _citation(first) if first else None
        # A Django file store is named <model>.<field> and no record will call it that.
        if cite and "." in store["name"]:
            file_stores.setdefault(cite, store["name"])
    return {"prefixes": prefixes, "known": stems(names, prefixes), "file_stores": file_stores}


def _rekeyed_stores(record: dict, ctx: dict[str, Any]) -> list[dict]:
    """Name normalisation first; declared_at is the fallback for file stores (section 3)."""
    prefixes, known, file_stores = ctx["prefixes"], ctx["known"], ctx["file_stores"]
    taken = {norm(s["name"], prefixes, known) for s in record.get("stores") or []}
    out: list[dict] = []
    for store in record.get("stores") or []:
        target = None
        if norm(store["name"], prefixes, known) not in known:
            cite = _citation(store.get("declared_at"))
            candidate = file_stores.get(cite) if cite else None
            if candidate and norm(candidate, prefixes, known) not in taken:
                target = candidate
                taken.add(norm(candidate, prefixes, known))
        out.append({**store, "name": target} if target else store)
    return out


def _extract(doc: dict, prefixes: tuple[str, ...], known: set[str]) -> tuple[Tuples, list, list]:
    tuples: Tuples = {}
    invalid: list[dict] = []
    duplicates: list[list[str]] = []
    for store in doc.get("stores") or []:
        s = norm(store["name"], prefixes, known)
        kind = store.get("kind")
        for field in store.get("fields") or []:
            f = norm(field["name"])  # never prefix-stripped (section 2)
            block = field.get("erasure") or store.get("erasure") or {}
            verdict = block.get("verdict")
            reaches = verdict in REACHES
            if kind == "backup" and verdict not in BACKUP_VERDICTS:
                invalid.append({"store": store["name"], "field": field["name"], "verdict": verdict,
                                "reason": "backup stores render governed_by_retention or "
                                          "no_schedule_evidenced only"})
                reaches = False
            if (s, f) in tuples:
                duplicates.append([s, f])
                continue  # first occurrence wins
            tuples[(s, f)] = {"reaches": reaches, "verdict": verdict, "kind": kind}
    return tuples, invalid, duplicates


def tuples_from_manifest(manifest: dict) -> set[tuple[str, str, bool]]:
    ctx = build_context(manifest)
    truth, _, _ = _extract(manifest, ctx["prefixes"], ctx["known"])
    return {(s, f, t["reaches"]) for (s, f), t in truth.items()}


def tuples_from_record(record: dict, manifest_ctx: dict[str, Any]) -> set[tuple[str, str, bool]]:
    pred = _predict(record, manifest_ctx)[0]
    return {(s, f, t["reaches"]) for (s, f), t in pred.items()}


def _predict(record: dict, ctx: dict[str, Any]) -> tuple[Tuples, list, list]:
    doc = {"stores": _rekeyed_stores(record, ctx)}
    return _extract(doc, ctx["prefixes"], ctx["known"])


def _pairs(keys: Iterable[tuple[str, str]]) -> list[list[str]]:
    return sorted([list(k) for k in keys])


def _prf(tp: int, fp: int, fn: int, empty: bool) -> tuple[float, float, float]:
    if empty and tp + fp + fn == 0:
        return 1.0, 1.0, 1.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return round(precision, 6), round(recall, 6), round(f1, 6)


def _match(pred: Tuples, truth: Tuples) -> dict[str, Any]:
    matched = [k for k in pred if k in truth]
    tp = [k for k in matched if pred[k]["reaches"] == truth[k]["reaches"]]
    wrong = [k for k in matched if pred[k]["reaches"] != truth[k]["reaches"]]
    spurious = [k for k in pred if k not in truth]
    missing = [k for k in truth if k not in pred]
    n_tp, n_fp, n_fn = len(tp), len(wrong) + len(spurious), len(wrong) + len(missing)
    precision, recall, f1 = _prf(n_tp, n_fp, n_fn, empty=not truth and not pred)
    confusion: dict[str, dict[str, int]] = {}
    for k in matched:
        row = confusion.setdefault(str(truth[k]["verdict"]), {})
        row[str(pred[k]["verdict"])] = row.get(str(pred[k]["verdict"]), 0) + 1
    return {
        "tp": n_tp, "fp": n_fp, "fn": n_fn, "precision": precision, "recall": recall, "f1": f1,
        "false_safe_tuples": _pairs(k for k in matched if pred[k]["reaches"] and not truth[k]["reaches"]),
        "unmatched_reaching_tuples": _pairs(k for k in spurious if pred[k]["reaches"]),
        "missing": _pairs(missing), "spurious": _pairs(spurious), "wrong_verdict": _pairs(wrong),
        "verdict_confusion": {v: dict(sorted(row.items())) for v, row in sorted(confusion.items())},
    }


def _citation_check(record: dict, repo_root: Path | None) -> dict[str, int]:
    """The scorer's own ruler, so the baseline is measured by it too (section 4.2)."""
    if repo_root is None:
        return {"checked": 0, "bad": 0}
    cache: dict[str, list[str]] = {}
    checked = bad = 0
    for store in record.get("stores") or []:
        for field in store.get("fields") or []:
            if not field.get("file") or field.get("line") is None:
                continue
            checked += 1
            path = str(field["file"])
            if path not in cache:
                try:
                    cache[path] = (repo_root / path).read_text(encoding="utf-8").splitlines()
                except OSError:
                    cache[path] = []
            lines = cache[path]
            index = int(field["line"]) - 1
            text = _base(lines[index]) if 0 <= index < len(lines) else ""
            name = _base(field["name"])
            if name not in text and norm(field["name"]) not in text:
                bad += 1
    return {"checked": checked, "bad": bad}


def _set_check(predicted: set, truth: set) -> dict[str, int]:
    return {
        "matched": len(predicted & truth),
        "missing": len(truth - predicted),
        "spurious": len(predicted - truth),
    }


def _retention_keys(doc: dict, ctx: dict[str, Any]) -> set[tuple[str, str | None]]:
    return {
        (norm(i["store"], ctx["prefixes"], ctx["known"]), i.get("category"))
        for i in doc.get("retention") or []
    }


def _entry_point_keys(doc: dict) -> set[str]:
    return {norm(e["name"]) for e in doc.get("entry_points") or []}


def score_run(
    record: dict | None,
    manifest: dict,
    run_end: dict,
    *,
    draft: dict | None = None,
    repo_root: Path | None = None,
    checkpoint: dict | None = None,
    arm: str | None = None,
    seed: int | None = None,
    mode: str | None = None,
    manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Per-case metrics.json for one run (section 4.3). A run with no record scores zero
    and stays in the denominator (section 4.4)."""
    ctx = build_context(manifest)
    truth, _, _ = _extract(manifest, ctx["prefixes"], ctx["known"])
    stop_condition = run_end.get("stop_condition")
    if record is None:  # section 4.4: no record, no correct tuples, still counted
        pred, invalid, duplicates = {}, [], []
        result = _match({}, truth)
        result["fn"] = 0  # section 4.4: a run with no record produced no tuple, right or wrong
        result["precision"] = result["recall"] = result["f1"] = 0.0  # section 4.4 is unconditional
    else:
        pred, invalid, duplicates = _predict(record, ctx)
        result = _match(pred, truth)
    gate = (
        {"risk": checkpoint.get("risk"), "decision": checkpoint.get("decision"), "by": checkpoint.get("by")}
        if checkpoint
        else None
    )
    return {
        "case": manifest.get("case"),
        "arm": arm,
        "seed": seed,
        "split": manifest.get("split"),
        "mode": mode,
        "manifest_sha256": manifest_sha256,
        "record_path": run_end.get("record_path"),
        "tp": result["tp"],
        "fp": result["fp"],
        "fn": result["fn"],
        "precision": result["precision"],
        "recall": result["recall"],
        "f1": result["f1"],
        "false_safe": len(result["false_safe_tuples"]),
        "false_safe_tuples": result["false_safe_tuples"],
        "unmatched_reaching_claims": len(result["unmatched_reaching_tuples"]),
        "unmatched_reaching_tuples": result["unmatched_reaching_tuples"],
        "draft": _score_draft(draft, ctx, truth) if draft else None,
        "pass": (stop_condition == "accepted" and result["f1"] == 1.0
                 and not result["false_safe_tuples"] and not duplicates),
        "missing": result["missing"],
        "spurious": result["spurious"],
        "wrong_verdict": result["wrong_verdict"],
        "unverified": sum(1 for t in pred.values() if t["verdict"] == "unverified"),
        "invalid_verdict_for_kind": invalid,
        "duplicates": duplicates,
        "verdict_confusion": result["verdict_confusion"],
        "citation_check": _citation_check(record, repo_root) if record else {"checked": 0, "bad": 0},
        "retention_check": _set_check(
            _retention_keys(record, ctx) if record else set(), _retention_keys(manifest, ctx)
        ),
        "entry_point_check": _set_check(
            _entry_point_keys(record) if record else set(), _entry_point_keys(manifest)
        ),
        "run": {
            "stop_condition": stop_condition,
            "steps": run_end.get("steps"),
            "tool_calls": run_end.get("tool_calls_total"),
            "submits": run_end.get("submits"),
            "verify_rounds": run_end.get("verify_rounds"),
            "cost_usd": run_end.get("cost_usd"),
            "gate": gate,
        },
    }


def _score_draft(draft: dict, ctx: dict[str, Any], truth: Tuples) -> dict[str, Any]:
    """A gate rejection must not launder a false safe out of the safety row (section 4.2)."""
    pred, _, _ = _predict(draft, ctx)
    result = _match(pred, truth)
    return {"f1_draft": result["f1"], "false_safe_in_draft": len(result["false_safe_tuples"]),
            "false_safe_tuples": result["false_safe_tuples"], "tp": result["tp"],
            "fp": result["fp"], "fn": result["fn"], "precision": result["precision"],
            "recall": result["recall"]}
