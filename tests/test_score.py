"""Scorer unit tests (docs/spec/05-eval-harness.md sections 2-4).

The eleven normalisation tests named in section 2 come first, by name, because a bug in `norm`
moves the metric and the verifier the same way and is invisible in the comparison between arms.
"""

from __future__ import annotations

from typing import Any

from evals.harness.score import (
    build_context,
    norm,
    score_run,
    stems,
    tuples_from_manifest,
    tuples_from_record,
)


def _erasure(verdict: str, timer_days: int | None = None) -> dict[str, Any]:
    return {"verdict": verdict, "evidence": [], "timer_days": timer_days, "note": None}


def _field(name: str, category: str = "contact", file: str = "models.py", line: int = 1,
           erasure: dict | None = None) -> dict[str, Any]:
    return {"name": name, "category": category, "file": file, "line": line, "note": None,
            "erasure": erasure}


def _store(name: str, verdict: str = "erased", kind: str = "relational",
           fields: list | None = None, declared_at: dict | None = None) -> dict[str, Any]:
    return {"name": name, "kind": kind, "declared_at": declared_at, "subject_link": None,
            "fields": [_field("email")] if fields is None else fields,
            "erasure": _erasure(verdict), "recipient_kind": None, "note": None}


def _manifest(stores: list, prefixes: tuple[str, ...] = (), **extra: Any) -> dict[str, Any]:
    return {"case": "S01", "split": "dev", "normalisation": {"prefixes": list(prefixes)},
            "stores": stores, **extra}


def _record(stores: list, **extra: Any) -> dict[str, Any]:
    return {"schema_version": "1", "repository": "tidewharf", "stores": stores, **extra}


def _run_end(stop: str = "accepted", **extra: Any) -> dict[str, Any]:
    return {"stop_condition": stop, "steps": 4, "tool_calls_total": 6, "submits": 1,
            "verify_rounds": 0, "wall_s": 12.0, "cost_usd": 0.11,
            "record_path": "results/runs/advanced/S01/s1/record.json", "note": None, **extra}


# --- the eleven normalisation tests of section 2 ---------------------------------------------


def test_norm_case_and_punctuation() -> None:
    assert norm("Users") == norm("user") == "user"
    assert norm("  User-Profile  ") == norm("user__profile") == "user_profile"


def test_norm_plural_s() -> None:
    assert norm("orders") == norm("order") == "order"


def test_norm_ies() -> None:
    assert norm("companies") == norm("company") == "company"


def test_norm_suffix_keep() -> None:
    assert norm("ip_address") == "ip_address"
    assert norm("status") == "status"
    assert norm("analysis") == "analysis"


def test_norm_addresses() -> None:
    assert norm("addresses") == norm("address") == "address"


def test_norm_boxes() -> None:
    assert norm("boxes") == norm("box") == "box"


def test_norm_classes() -> None:
    assert norm("classes") == norm("class") == "class"


def test_norm_response_not_over_stripped() -> None:
    assert norm("responses") == norm("response") == "response"


def test_norm_idempotent() -> None:
    # "user_s" is the shape the first implementation lost: _singular strips the "s" and leaves
    # the separator, so norm("user_s") was "user_" and norm("user_") "user".
    for name in ("Users", "companies", "addresses", "boxes", "classes", "responses", "status",
                 "user_s", "gallery_photos", "audit_es"):
        assert norm(norm(name)) == norm(name)


def test_prefix_stripped_only_for_known_stem() -> None:
    known = stems(["address"], ("accounts",))
    assert norm("accounts_address", ("accounts",), known) == "address"
    # accounts_ledger is not a known store, so the prefix is part of the name.
    assert norm("accounts_ledger", ("accounts",), known) == "accounts_ledger"


def test_field_names_are_never_prefix_stripped() -> None:
    manifest = _manifest([_store("photo", fields=[_field("gallery_title")])], prefixes=("gallery",))
    ctx = build_context(manifest)
    assert tuples_from_record(_record(manifest["stores"]), ctx) == {("photo", "gallery_title", True)}


# --- tuple extraction ------------------------------------------------------------------------


def test_manifest_tuples_carry_reaches_erasure() -> None:
    manifest = _manifest([_store("users", "erased_after_timer"), _store("uploads", "not_erased")])
    assert tuples_from_manifest(manifest) == {("user", "email", True), ("upload", "email", False)}


def test_extra_predicted_store_is_a_false_positive() -> None:
    manifest = _manifest([_store("users")])
    record = _record([_store("users"), _store("sessions", kind="cache", verdict="not_erased")])
    metrics = score_run(record, manifest, _run_end())
    assert (metrics["tp"], metrics["fp"], metrics["fn"]) == (1, 1, 0)
    assert metrics["spurious"] == [["session", "email"]]


def test_missing_store_is_a_false_negative() -> None:
    manifest = _manifest([_store("users"), _store("uploads", "not_erased")])
    metrics = score_run(_record([_store("users")]), manifest, _run_end())
    assert (metrics["tp"], metrics["fp"], metrics["fn"]) == (1, 0, 1)
    assert metrics["missing"] == [["upload", "email"]]


def test_store_with_no_fields_yields_no_tuples() -> None:
    manifest = _manifest([_store("users"), _store("products", fields=[])])
    assert tuples_from_manifest(manifest) == {("user", "email", True)}


def test_field_level_erasure_overrides_the_store() -> None:
    store = _store("users", "pseudonymised", fields=[
        _field("email"), _field("full_name", erasure=_erasure("anonymised"))])
    assert tuples_from_manifest(_manifest([store])) == {
        ("user", "email", False), ("user", "full_name", True)}


def test_backup_verdicts_are_forced_to_the_false_side() -> None:
    manifest = _manifest([_store("nightly_backup", "governed_by_retention", kind="backup")])
    record = _record([_store("nightly_backup", "erased", kind="backup")])
    metrics = score_run(record, manifest, _run_end())
    assert metrics["false_safe"] == 0
    assert metrics["tp"] == 1  # both sides are false; the contradiction is a secondary row
    assert metrics["invalid_verdict_for_kind"][0]["verdict"] == "erased"


def test_duplicate_key_keeps_the_first_occurrence() -> None:
    record = _record([_store("users", "erased"), _store("user", "not_erased")])
    ctx = build_context(_manifest([_store("users")]))
    assert tuples_from_record(record, ctx) == {("user", "email", True)}
    metrics = score_run(record, _manifest([_store("users")]), _run_end())
    assert metrics["duplicates"] == [["user", "email"]]


def test_file_store_matched_by_declared_at() -> None:
    cite = {"file": "gallery/models.py", "line": 14, "symbol": "image"}
    manifest = _manifest([_store("photo.image", "not_erased", kind="object_storage",
                                 fields=[_field("image")], declared_at=cite)])
    record = _record([_store("uploads", "not_erased", kind="object_storage",
                             fields=[_field("image")], declared_at=cite)])
    metrics = score_run(record, manifest, _run_end())
    assert (metrics["tp"], metrics["fp"], metrics["fn"]) == (1, 0, 0)


def test_file_store_matched_by_the_field_citation_when_declared_at_is_absent() -> None:
    # evals/CASES.md's manifest shape does not require declared_at; a file store's one field
    # cites the same FileField line (03-verifier.md section 3.1, fixture-generator.md 6.1).
    manifest = _manifest([_store("photo.image", "not_erased", kind="object_storage",
                                 fields=[_field("image", file="gallery/models.py", line=21)])])
    record = _record([_store("uploads", "not_erased", kind="object_storage",
                             fields=[_field("image", file="gallery/models.py", line=21)],
                             declared_at={"file": "gallery/models.py", "line": 21})])
    metrics = score_run(record, manifest, _run_end())
    assert (metrics["tp"], metrics["fp"], metrics["fn"]) == (1, 0, 0)


def test_file_store_unmatched_when_line_differs() -> None:
    manifest = _manifest([_store("photo.image", "not_erased", kind="object_storage",
                                 fields=[_field("image")],
                                 declared_at={"file": "gallery/models.py", "line": 14})])
    record = _record([_store("uploads", "not_erased", kind="object_storage",
                             fields=[_field("image")],
                             declared_at={"file": "gallery/models.py", "line": 15})])
    metrics = score_run(record, manifest, _run_end())
    assert (metrics["tp"], metrics["fp"], metrics["fn"]) == (0, 1, 1)


# --- scoring one run -------------------------------------------------------------------------


def test_perfect_record_passes() -> None:
    manifest = _manifest([_store("users", "erased_after_timer"), _store("uploads", "not_erased")])
    metrics = score_run(_record(manifest["stores"]), manifest, _run_end(), arm="advanced", seed=1)
    assert (metrics["precision"], metrics["recall"], metrics["f1"]) == (1.0, 1.0, 1.0)
    assert metrics["pass"] is True
    assert metrics["false_safe"] == 0
    assert metrics["verdict_confusion"] == {"erased_after_timer": {"erased_after_timer": 1},
                                            "not_erased": {"not_erased": 1}}
    assert metrics["run"]["stop_condition"] == "accepted"
    assert metrics["case"] == "S01" and metrics["arm"] == "advanced" and metrics["seed"] == 1


def test_false_safe_is_counted_and_blocks_pass() -> None:
    manifest = _manifest([_store("uploads", "not_erased", kind="object_storage")])
    metrics = score_run(_record([_store("uploads", "erased", kind="object_storage")]),
                        manifest, _run_end())
    assert metrics["false_safe"] == 1
    assert metrics["false_safe_tuples"] == [["upload", "email"]]
    assert (metrics["tp"], metrics["fp"], metrics["fn"]) == (0, 1, 1)
    assert metrics["f1"] == 0.0 and metrics["pass"] is False


def test_reaching_claim_on_an_unknown_store_is_unmatched_not_false_safe() -> None:
    manifest = _manifest([_store("users")])
    record = _record([_store("users"), _store("avatars", "erased", kind="object_storage")])
    metrics = score_run(record, manifest, _run_end())
    assert metrics["false_safe"] == 0
    assert metrics["unmatched_reaching_claims"] == 1
    assert metrics["unmatched_reaching_tuples"] == [["avatar", "email"]]


def test_accepted_run_with_a_perfect_record_but_no_acceptance_does_not_pass() -> None:
    manifest = _manifest([_store("users")])
    metrics = score_run(_record(manifest["stores"]), manifest, _run_end(stop="timeout"))
    assert metrics["f1"] == 1.0 and metrics["pass"] is False


def test_failed_run_scores_zero_and_keeps_the_manifest_in_view() -> None:
    manifest = _manifest([_store("users"), _store("uploads", "not_erased")])
    metrics = score_run(None, manifest, _run_end(stop="budget_exhausted", record_path=None))
    assert (metrics["tp"], metrics["fp"], metrics["fn"]) == (0, 0, 0)
    assert metrics["f1"] == 0.0 and metrics["pass"] is False and metrics["false_safe"] == 0
    assert metrics["missing"] == [["upload", "email"], ["user", "email"]]
    assert metrics["run"]["stop_condition"] == "budget_exhausted"


def test_gate_rejected_run_scores_its_draft() -> None:
    manifest = _manifest([_store("uploads", "not_erased", kind="object_storage")])
    draft = _record([_store("uploads", "erased", kind="object_storage")])
    metrics = score_run(None, manifest, _run_end(stop="gate_rejected"), draft=draft)
    assert metrics["f1"] == 0.0 and metrics["false_safe"] == 0
    assert metrics["draft"]["false_safe_in_draft"] == 1
    assert metrics["draft"]["f1_draft"] == 0.0


def test_unverified_and_the_gate_block_are_reported() -> None:
    manifest = _manifest([_store("orders", "not_erased")])
    record = _record([_store("orders", "unverified")])
    checkpoint = {"risk": "high", "decision": "approved", "by": "simulated", "wait_s": 0.0}
    metrics = score_run(record, manifest, _run_end(), checkpoint=checkpoint)
    assert metrics["unverified"] == 1
    assert metrics["run"]["gate"] == {"risk": "high", "decision": "approved", "by": "simulated"}


def test_retention_and_entry_point_rows() -> None:
    manifest = _manifest([_store("users")],
                         retention=[{"store": "users", "category": "contact", "days": 30}],
                         entry_points=[{"name": "close_account", "file": "api.py", "line": 12,
                                        "kind": "route"}])
    record = _record(manifest["stores"], retention=[], entry_points=manifest["entry_points"])
    metrics = score_run(record, manifest, _run_end())
    assert metrics["retention_check"] == {"matched": 0, "missing": 1, "spurious": 0}
    assert metrics["entry_point_check"] == {"matched": 1, "missing": 0, "spurious": 0}


def test_citation_check_reads_the_cited_line(tmp_path: Any) -> None:
    (tmp_path / "models.py").write_text("class User(Base):\n    email = Column(String)\n")
    manifest = _manifest([_store("users")])
    record = _record([_store("users", fields=[_field("email", line=2), _field("full_name", line=1)])])
    metrics = score_run(record, manifest, _run_end(), repo_root=tmp_path)
    assert metrics["citation_check"] == {"checked": 2, "bad": 1}


def test_a_run_with_no_record_never_scores_a_perfect_f1() -> None:
    # section 4.4 is unconditional; the empty-manifest branch of _prf must not reach it.
    metrics = score_run(None, _manifest([]), _run_end(stop="crashed"))
    assert (metrics["precision"], metrics["recall"], metrics["f1"]) == (0.0, 0.0, 0.0)
    assert metrics["pass"] is False


def test_two_spellings_of_one_store_cannot_pass_in_either_order() -> None:
    # `_extract` keeps the first occurrence, so without the duplicates clause the order of the
    # two rows decided whether a record claiming both verdicts passed.
    manifest = _manifest([_store("users", "not_erased")])
    safe = _store("users", "erased")
    unsafe = _store("user", "not_erased")
    for stores in ([unsafe, safe], [safe, unsafe]):
        metrics = score_run(_record(stores), manifest, _run_end())
        assert metrics["duplicates"] == [["user", "email"]]
        assert metrics["pass"] is False
