"""Tests for the fixture generator (docs/spec/fixture-generator.md section 8).

Offline by construction: the generator reads YAML specs and writes text. Nothing here
touches the network or an API key.
"""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"
sys.path.insert(0, str(FIXTURES))

import gen  # noqa: E402
import manifest  # noqa: E402
import naming  # noqa: E402
import render_sqlalchemy  # noqa: E402
import spec_model  # noqa: E402
from naming import IRREGULAR_PLURALS, line_tokens, norm, stems  # noqa: E402

VERDICTS = {
    "erased",
    "erased_after_timer",
    "anonymised",
    "pseudonymised",
    "not_erased",
    "external_manual",
    "no_entry_point",
    "governed_by_retention",
    "no_schedule_evidenced",
    "unverified",
}
BACKUP_VERDICTS = {"governed_by_retention", "no_schedule_evidenced"}
KINDS = {
    "relational",
    "object_storage",
    "cache",
    "search_index",
    "queue",
    "third_party",
    "log",
    "backup",
}
CATEGORIES = {"identifier", "contact", "financial", "behavioural", "free_text_may_contain", "technical"}

CASES = gen.all_cases()


@pytest.fixture(scope="module")
def cases() -> list:
    return [gen.generate(name) for name in CASES]


@pytest.fixture(scope="module")
def manifests() -> dict:
    return {
        case: yaml.safe_load((FIXTURES / "manifests" / f"{case}.yaml").read_text(encoding="utf-8"))
        for case in CASES
    }


def test_ten_cases():
    assert CASES == [f"S{n:02d}" for n in range(1, 11)]


def test_generation_is_byte_identical(cases):
    again = [gen.generate(name) for name in CASES]
    for first, second in zip(cases, again):
        assert first.files == second.files
        assert first.manifest_text == second.manifest_text
        assert first.index_entry == second.index_entry


def test_committed_fixtures_match_the_generator(cases):
    assert gen.differences(cases) == []


def test_files_are_lf_only_with_one_trailing_newline(cases):
    for case in cases:
        for path, text in case.files.items():
            assert "\r" not in text, f"{case.name}/{path}"
            assert "\t" not in text, f"{case.name}/{path}"
            assert not text.endswith("\n\n"), f"{case.name}/{path}"
            assert all(line == line.rstrip() for line in text.split("\n")), f"{case.name}/{path}"


def test_generated_python_parses(cases):
    for case in cases:
        for path, text in case.files.items():
            if path.endswith(".py"):
                ast.parse(text, filename=f"{case.name}/{path}")


def test_no_timestamp_or_absolute_path_leaks(cases):
    for case in cases:
        for path, text in case.files.items():
            assert str(ROOT) not in text, f"{case.name}/{path}"
            assert "2026-" not in text, f"{case.name}/{path}"


def test_manifests_load_and_verdicts_are_in_the_contract_enum(manifests):
    for case, manifest in manifests.items():
        assert manifest["case"] == case
        assert manifest["source"] == "synthetic"
        assert manifest["labelling_minutes"] is None
        for store in manifest["stores"]:
            assert store["kind"] in KINDS, f"{case} {store['name']}"
            verdict = store["erasure"]["verdict"]
            assert verdict in VERDICTS, f"{case} {store['name']}"
            if store["kind"] == "backup":
                assert verdict in BACKUP_VERDICTS, f"{case} {store['name']}"
            if store["kind"] == "third_party":
                assert store["recipient_kind"] == "unknown"
            for field in store["fields"]:
                assert field["category"] in CATEGORIES, f"{case} {store['name']}.{field['name']}"
                if "erasure" in field:
                    assert field["erasure"]["verdict"] in VERDICTS


def test_every_store_carries_a_subject_link(manifests):
    for case, manifest in manifests.items():
        for store in manifest["stores"]:
            link = store["subject_link"]
            assert link and link["file"] and link["line"] >= 1, f"{case} {store['name']}"


def test_spec_sha256_is_the_spec_file_digest(manifests):
    for case, manifest in manifests.items():
        digest = hashlib.sha256((FIXTURES / "specs" / f"{case}.yaml").read_bytes()).hexdigest()
        assert manifest["spec_sha256"] == digest, case


def test_norm_is_injective_over_store_names(manifests):
    """fixture-generator.md section 7 rule 2, on the committed manifests."""
    for case, manifest in manifests.items():
        prefixes = tuple(manifest["normalisation"]["prefixes"])
        names = [store["name"] for store in manifest["stores"]]
        known = stems(names, prefixes)
        keys = [norm(name, prefixes, known) for name in names]
        assert len(set(keys)) == len(keys), f"{case}: {sorted(names)} collide as {sorted(keys)}"
        for store in manifest["stores"]:
            fields = [field["name"] for field in store["fields"]]
            assert len({norm(f) for f in fields}) == len(fields), f"{case} {store['name']}"


def test_no_irregular_plurals_and_norm_is_idempotent(manifests):
    """Section 7 rule 3: an irregular plural does not collide, it never matches."""
    for case, manifest in manifests.items():
        names = [s["name"] for s in manifest["stores"]]
        names += [f["name"] for s in manifest["stores"] for f in s["fields"]]
        names += manifest["negatives"]
        for name in names:
            assert name.lower() not in IRREGULAR_PLURALS, f"{case} {name}"
            assert norm(norm(name)) == norm(name), f"{case} {name}"


def test_every_citation_resolves_to_a_line_that_names_it(manifests):
    """Section 8 assertion 5, re-run against the committed repositories."""
    for case, manifest in manifests.items():
        repo = FIXTURES / "synthetic" / case
        for store in manifest["stores"]:
            for field in store["fields"]:
                line = (repo / field["file"]).read_text(encoding="utf-8").split("\n")[field["line"] - 1]
                assert norm(field["name"]) in line_tokens(line), f"{case} {store['name']}.{field['name']}"
        for entry in manifest["entry_points"]:
            line = (repo / entry["file"]).read_text(encoding="utf-8").split("\n")[entry["line"] - 1]
            assert line.strip(), f"{case} {entry['name']}"


def test_retention_rows_carry_a_citation(manifests):
    """CASES.md errata: every submitted retention item carries file and line."""
    for case, manifest in manifests.items():
        for row in manifest["retention"]:
            assert row["file"] and row["line"] >= 1, f"{case} {row['store']}"
            assert ("days" in row) != ("criteria" in row), f"{case} {row['store']}"


def test_file_counts_match_the_spec_table(cases):
    expected = {"S01": 11, "S02": 10, "S03": 13, "S04": 12, "S05": 15,
                "S06": 15, "S07": 13, "S08": 15, "S09": 15, "S10": 15}
    assert {case.name: len(case.files) for case in cases} == expected


def test_naming_is_the_scorer_and_not_a_second_copy():
    """05-eval-harness.md section 2: one implementation, so the build-time assertions and the
    metric cannot drift. An identity check is the only version of this that cannot rot."""
    score = pytest.importorskip("evals.harness.score", reason="scorer not built yet")
    assert naming.norm is score.norm
    assert naming.stems is score.stems


def test_cascade_is_a_token_test_not_a_substring_test():
    """framework-behaviour.md section 6 R5: `delete-orphan` alone is not a delete cascade,
    and `all` is a synonym for a token list that contains `delete`."""
    assert spec_model.is_delete_cascade("all, delete")
    assert spec_model.is_delete_cascade("all")
    assert not spec_model.is_delete_cascade("delete-orphan")
    assert not spec_model.is_delete_cascade(spec_model.CASCADE_DEFAULT)


def test_a_bare_all_cascade_is_still_rendered():
    """The kwarg is emitted whenever the spec departs from SQLAlchemy's default, so a real
    delete cascade cannot be dropped from the fixture the manifest was derived from."""
    spec = spec_model.load_spec(FIXTURES / "specs" / "S01.yaml")
    child = next(m for m in spec["models"] if m["parent"])
    child["cascade"] = "all"
    assert 'cascade="all"' in render_sqlalchemy.render(spec).files["models.py"]


def test_a_purge_job_without_a_schedule_does_not_reach_erasure():
    """03-verifier.md section 6.2 requirement 3 and test 37a: a retention constant is a timer,
    not a registration. Without one nothing in the repository runs the job."""
    spec = spec_model.load_spec(FIXTURES / "specs" / "S03.yaml")
    subject = spec_model.subject_model(spec)
    assert manifest._relational_verdict(spec, subject) == "erased_after_timer"
    for job in spec["jobs"]:
        job["schedule"] = None
    assert manifest._relational_verdict(spec, subject) == "not_erased"


def test_erased_after_timer_cases_carry_a_schedule_registration():
    """The five requirements are only citable if the repository holds all of them."""
    for case in CASES:
        spec = spec_model.load_spec(FIXTURES / "specs" / f"{case}.yaml")
        rendered = render_sqlalchemy.render(spec) if spec["flavour"] == "sqlalchemy" else None
        if rendered is None:
            continue
        timers = [
            store
            for store in spec["expect"]["stores"].values()
            if store.get("verdict") == "erased_after_timer"
        ]
        if not timers:
            continue
        assert "CELERYBEAT_SCHEDULE" in rendered.files["config.py"], case
        purge = next(job for job in spec["jobs"] if job["kind"] == "purge")
        assert "@shared_task" in rendered.files[purge["module"]], case
