"""The skill package (ADR 0007 item 1): generated from the prompts, run offline.

The first tests are the ones that make the skill the baseline arm rather than a
paraphrase of it: `SKILL.md` after its marker is the spliced instruction text byte
for byte, and the Codex include carries the same text. Two more read the head each
surface gets, which is where the eval's wording is mapped onto tools that exist and
the named files are located. The rest drive the two scripts as a user does, on a copy
of S10, through `subprocess`: nothing is written under `results/`, `traces/` or the
committed package.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from art30 import llm
from tests.test_e2e_advanced import S10_LIE, record_of

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "skill" / "art30"
BUILD = REPO / "skill" / "build.py"
VERIFY = PKG / "scripts" / "verify.py"
RENDER = PKG / "scripts" / "render.py"
FIXTURE = REPO / "evals" / "fixtures" / "synthetic" / "S10"
GENERATED = ("SKILL.md", "AGENTS.md.include", "resources/record.schema.json")

MARKER = "<!-- art30 instruction text, generated from art30/prompts — do not edit here -->"
SPLICE = MARKER + "\n\n"
CODEX = "<!-- Codex reads AGENTS.md; append this file to yours. -->\n"
DEAD_HELPER = "cleanup_user_files (storage.py:29) is defined but has no callers"


def run(script: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args], cwd=cwd, capture_output=True, text=True
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def case(tmp_path: Path) -> Path:
    """A copy of the S10 fixture; the tests never read the committed one in place."""
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE, root)
    return root


def drafted(tmp_path: Path, record: dict) -> Path:
    target = tmp_path / "art30-record.json"
    target.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# the generated files
# ---------------------------------------------------------------------------
def test_skill_md_carries_the_instruction_text_byte_for_byte() -> None:
    text = (PKG / "SKILL.md").read_text(encoding="utf-8")
    assert text.count(MARKER) == 1
    head, body = text.split(SPLICE, 1)
    assert body == llm.system_prompt()
    assert head.startswith("---\nname: art30\n")
    assert "description:" in head.split("---\n")[1]


def test_the_codex_include_is_the_same_instruction_text_without_the_frontmatter() -> None:
    include = (PKG / "AGENTS.md.include").read_text(encoding="utf-8")
    skill = (PKG / "SKILL.md").read_text(encoding="utf-8")
    assert include.startswith(CODEX)
    assert "name: art30" not in include.split(SPLICE, 1)[0]
    assert include.split(SPLICE, 1)[1] == llm.system_prompt()
    assert include.split(MARKER, 1)[1] == skill.split(MARKER, 1)[1]


def test_the_include_locates_its_files_in_the_checkout_not_beside_itself() -> None:
    """Appended to someone's AGENTS.md, nothing is beside it and SKILL_DIR is elsewhere."""
    head = (PKG / "AGENTS.md.include").read_text(encoding="utf-8").split(SPLICE, 1)[0]
    assert CODEX.startswith("<!--")  # the line for the installer, not for the agent
    assert "beside this file" not in head
    assert "skill/art30/" in head
    assert "in Claude Code" not in head


def test_the_skill_head_maps_the_eval_wording_onto_this_surface() -> None:
    """The instruction text names tools this surface does not have; the head says so."""
    head = (PKG / "SKILL.md").read_text(encoding="utf-8").split(SPLICE, 1)[0]
    assert "beside this file" in head
    assert "Where it says `submit_record`" in head
    assert "Where it\nsays `read_file` and `grep`, use Read and Grep." in head
    assert "Bash runs the two scripts in steps 3 and 5" in head


def test_building_twice_is_byte_identical_and_the_committed_files_are_current(
    tmp_path: Path,
) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    for out in (first, second):
        assert run(BUILD, "--out", str(out)).returncode == 0
    for name in GENERATED:
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert (first / name).read_bytes() == (PKG / name).read_bytes()
    assert run(BUILD, "--check").returncode == 0


def test_the_schema_copy_hashes_equal_to_the_shipped_schema() -> None:
    assert digest(PKG / "resources" / "record.schema.json") == digest(
        REPO / "art30" / "schema" / "record.schema.json"
    )


# ---------------------------------------------------------------------------
# verify.py
# ---------------------------------------------------------------------------
def test_a_record_claiming_the_uploads_are_erased_is_rejected(case: Path, tmp_path: Path) -> None:
    """The S10 dead helper: the claim the CLI's own example rejects, from a file."""
    record = drafted(tmp_path, record_of("S10", edits={"uploads": S10_LIE}))
    done = run(VERIFY, "--repo", str(case), "--record", str(record), cwd=tmp_path)

    assert done.returncode == 1
    assert "REJECT   uploads · erasure.verdict=erased" in done.stdout
    assert DEAD_HELPER in done.stdout
    assert "expected: verdict not_erased, or cite the path" in done.stdout
    assert "attempts left" not in done.stdout


def test_the_corrected_record_is_accepted(case: Path, tmp_path: Path) -> None:
    record = drafted(tmp_path, record_of("S10"))
    done = run(VERIFY, "--repo", str(case), "--record", str(record), cwd=tmp_path)

    assert done.returncode == 0
    assert "accepted" in done.stdout


def test_the_json_output_carries_the_whole_feedback_object(case: Path, tmp_path: Path) -> None:
    record = drafted(tmp_path, record_of("S10", edits={"uploads": S10_LIE}))
    done = run(VERIFY, "--repo", str(case), "--record", str(record), "--json", cwd=tmp_path)
    payload = json.loads(done.stdout)

    assert done.returncode == 1
    assert payload["accepted"] is False
    assert [item["store"] for item in payload["rejected_claims"]] == ["uploads"]
    assert set(payload) == {
        "accepted", "schema_errors", "rejected_claims", "missing_stores",
        "missing_entry_points", "bad_citations", "unverified", "conservative_divergences",
    }


def test_a_record_that_does_not_validate_is_reported_as_schema_errors(
    case: Path, tmp_path: Path
) -> None:
    """Validation runs first: an invalid record never reaches the call graph."""
    broken = record_of("S10")
    broken["stores"][0]["erasure"]["verdict"] = "deleted"
    record = drafted(tmp_path, broken)
    done = run(VERIFY, "--repo", str(case), "--record", str(record), cwd=tmp_path)

    assert done.returncode == 1
    assert "SCHEMA   /stores/0/erasure/verdict" in done.stdout


def test_a_missing_repository_is_a_usage_error(tmp_path: Path) -> None:
    record = drafted(tmp_path, record_of("S10"))
    done = run(VERIFY, "--repo", str(tmp_path / "nope"), "--record", str(record), cwd=tmp_path)

    assert done.returncode == 2
    assert "not a directory" in done.stderr


# ---------------------------------------------------------------------------
# render.py
# ---------------------------------------------------------------------------
def test_render_writes_the_two_documents_and_leaves_the_record_alone(
    case: Path, tmp_path: Path
) -> None:
    record = drafted(tmp_path, record_of("S10"))
    before = record.read_bytes()
    done = run(RENDER, "--repo", str(case), "--record", str(record), cwd=tmp_path)

    assert done.returncode == 0, done.stderr
    markdown = (tmp_path / "art30-record.md").read_text(encoding="utf-8")
    page = (tmp_path / "art30-record.html").read_text(encoding="utf-8")
    assert markdown.startswith("# Record of processing — s10")
    assert "| Run | `skill run` |" in markdown
    assert "| Cost | USD n/a, no tool calls |" in markdown
    assert page.startswith("<!doctype html>")
    assert "not legal advice" in page
    assert record.read_bytes() == before
