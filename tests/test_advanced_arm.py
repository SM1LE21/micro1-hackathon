"""The advanced arm: the four lines of `handle_submit`, the rating, and the gate.

01-architecture.md section 3 is the shape under test; 00-contract.md's Trace contract
is the rating; 10-instructions.md section 5 and 07-ui.md sections 3 and 4 are the
block. Offline, with no model and no repository beyond the inline one.

The rating is the number the checkpoint line carries, and `trace_check.py` recomputes
it from the accepted record on every run: `test_the_rating_is_the_one_the_trace
_validator_recomputes` asserts the two readings agree, so a change to either fails
here rather than in a sweep.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from advanced import gate as terminal
from advanced.arm import AdvancedArm, cross_check, risk_rating
from art30.arm import RunCtx
from art30.config import Config
from art30.tools import ToolCtx
from art30.trace import Trace
from art30.verify import build_graph
from art30.verify.reach import verdicts
from evals.harness.trace_checks import _risk
from test_gate_file import write_after     # the website's side of the file exchange
from tests.verify.test_check import (  # the record builder, one implementation
    ENTRY, USER_STORE, child, cite, erasure, field, record, repo, store)


def mkrepo(root: Path, files: dict[str, str]) -> Path:
    """`tests/verify/conftest.py`'s writer, repeated here: that conftest is not on
    this directory's path and the record builder it feeds is imported, not inherited."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return root


@pytest.fixture
def ctx_of(tmp_path: Path):
    def _make(files: dict[str, str], **overrides) -> RunCtx:
        root = mkrepo(tmp_path / "repo", files)
        cfg = Config(trace_dir=tmp_path / "traces", out_dir=tmp_path / "out",
                     cache_dir=tmp_path / "cache", **overrides)
        return RunCtx(case="T01", arm="advanced", seed=1, root=root,
                      tools=ToolCtx(root=root), trace=Trace(tmp_path / "t.jsonl"),
                      cfg=cfg)
    return _make


def post_store(verdict: str, evidence=()) -> dict:
    return store("post", "relational", cite("app/models.py", 8, "Post"),
                 {"file": "app/models.py", "line": 9},
                 [field("body", "free_text_may_contain", "app/models.py", 10)],
                 erasure(verdict, evidence))


# ---------------------------------------------------------------------------
# handle_submit
# ---------------------------------------------------------------------------
def test_a_schema_invalid_record_returns_schema_errors_only(ctx_of):
    """01-architecture.md section 3: the verifier never sees a malformed record."""
    ctx = ctx_of(repo())
    ctx.submits = 1
    found = AdvancedArm().handle_submit({"schema_version": "1"}, ctx)

    assert found.accepted is False and found.schema_errors
    assert (found.attempt, found.attempts_left) == (1, 4)
    assert (found.rejected_claims, found.missing_stores, found.bad_citations) == ([], [], [])
    assert (found.unverified, found.conservative_divergences) == ([], [])


def test_a_rejected_claim_carries_the_attempt_counters(ctx_of):
    """The four lines under test: `check` decides, `replace` fills the counters."""
    ctx = ctx_of(repo(child("SET_NULL")))
    ctx.submits = 2
    claim = post_store("erased", [cite("app/models.py", 9, "user")])
    found = AdvancedArm().handle_submit(record([USER_STORE, claim]), ctx)

    assert found.accepted is False and len(found.rejected_claims) == 1
    assert (found.attempt, found.attempts_left) == (2, 3)


def test_an_accepted_record_keeps_the_three_lists_that_do_not_block(ctx_of):
    """07-ui.md section 2 rule 3: SAFER prints on an accepted record too."""
    ctx = ctx_of(repo(child("CASCADE")))
    ctx.submits = 1
    found = AdvancedArm().handle_submit(record([USER_STORE, post_store("not_erased")]), ctx)

    assert found.accepted is True and found.conservative_divergences
    assert json.loads(found.to_tool_result()) == {"accepted": True}


def test_the_graph_is_built_once_per_repository(ctx_of):
    """Five attempts on one repository parse it once (5.3's query budget)."""
    ctx = ctx_of(repo())
    arm = AdvancedArm()
    first = arm.graph(ctx.root)

    assert arm.graph(ctx.root) is first


# ---------------------------------------------------------------------------
# the risk rating (00-contract.md, Trace contract)
# ---------------------------------------------------------------------------
def _record(*stores, entry_points=(ENTRY,)) -> dict:
    return record(list(stores), entry_points)


def test_risk_is_high_when_a_contact_field_does_not_reach_erasure():
    found = _record(USER_STORE, post_store("not_erased"))
    found["stores"][1]["fields"][0]["category"] = "contact"

    assert risk_rating(found) == "high"


def test_risk_is_high_when_no_entry_point_was_found():
    """ADR 0004 P-09: `no_entry_point` is in the `high` list, and S08 is why."""
    blind = json.loads(json.dumps(USER_STORE))
    blind["erasure"] = erasure("no_entry_point")
    found = _record(blind, entry_points=())

    assert risk_rating(found) == "high"
    assert terminal.risk_reason(found, "high") == (
        "no deletion entry point was found; no store in this record reaches erasure")


def test_risk_is_medium_when_every_store_reaches_erasure_only_after_a_timer():
    timed = json.loads(json.dumps(USER_STORE))
    timed["erasure"] = erasure("erased_after_timer",
                               [cite("app/views.py", 6, "delete")], 30)

    assert risk_rating(_record(timed)) == "medium"
    assert terminal.risk_reason(_record(timed), "medium") == (
        "every store reaches erasure, at least one only after a timer")


def test_risk_is_low_when_every_store_reaches_erasure_directly():
    assert risk_rating(_record(USER_STORE)) == "low"
    assert terminal.risk_reason(_record(USER_STORE), "low") == (
        "every store reaches erasure directly and an entry point was found")


def test_a_high_verdict_on_a_store_with_no_identifying_field_does_not_raise_the_rating():
    """The contract's clause is `with an identifier or contact field`, not `any`."""
    assert risk_rating(_record(USER_STORE, post_store("not_erased"))) == "low"


@pytest.mark.parametrize("verdict", sorted(
    {"not_erased", "pseudonymised", "external_manual", "no_entry_point",
     "no_schedule_evidenced", "unverified", "erased", "erased_after_timer",
     "anonymised", "governed_by_retention"}))
def test_the_rating_is_the_one_the_trace_validator_recomputes(verdict: str):
    """Check 11 recomputes the checkpoint's rating from the record; they must agree."""
    item = json.loads(json.dumps(USER_STORE))
    item["erasure"] = erasure(verdict, [cite("app/views.py", 6, "delete")],
                              30 if verdict in ("erased_after_timer",
                                                "governed_by_retention") else None)
    found = _record(item)

    assert risk_rating(found) == _risk(found)


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------
def test_the_gate_in_auto_mode_is_a_simulated_approval(ctx_of, capsys):
    """07-ui.md section 4: the banner still prints, nothing is read, `wait_s` is 0.0."""
    ctx = ctx_of(repo(), approve="auto")
    decision = AdvancedArm().gate(record([USER_STORE]), ctx)
    printed = capsys.readouterr().out

    assert (decision.approved, decision.by, decision.wait_s) == (True, "simulated", 0.0)
    assert decision.risk == "low" and decision.edits == {}
    assert decision.human_completions() is None      # check 17: null when simulated
    assert "[gate] human checkpoint · risk LOW · --approve auto" in printed
    assert "RECORD READY FOR REVIEW - app" in printed
    assert "You are approving a document you will sign. Render it? [y/N]: (auto)" in printed
    assert "Approved without a human. Recorded as by: simulated." in printed


def test_the_file_gate_is_routed_to_the_run_s_own_directory(ctx_of, capsys, monkeypatch):
    """ADR 0007: `--approve file` exchanges its two files under the run's own `--out`.

    Routed anywhere else -- the module default is `results/web/unrouted`, resolved
    against the child's working directory -- `art30/web/runs.py` never sees the
    request, nobody can answer, and the run ends `gate_rejected` on the timeout.
    """
    monkeypatch.setenv(terminal.TIMEOUT_VAR, "10")
    ctx = ctx_of(repo(), approve="file")
    folder = Path(ctx.cfg.out_dir) / terminal.GATE_DIR
    thread = write_after(folder / terminal.DECISION_NAME, 0.25, ['{"approved": true}'])
    decision = AdvancedArm().gate(record([USER_STORE]), ctx)
    thread.join(timeout=5)
    capsys.readouterr()

    assert (folder / terminal.REQUEST_NAME).is_file(), "the gate wrote its request elsewhere"
    assert json.loads((folder / terminal.REQUEST_NAME).read_text())["risk"] == "low"
    assert (decision.approved, decision.by) == (True, "human")


def test_the_gate_block_names_the_stores_that_do_not_reach_erasure(ctx_of, capsys):
    """10-instructions.md section 5: the block, filled in from the record."""
    ctx = ctx_of(repo(child("SET_NULL")), approve="auto")
    item = post_store("not_erased")
    item["fields"][0]["category"] = "contact"
    item["erasure"]["note"] = "the SET_NULL foreign key leaves the row"
    decision = AdvancedArm().gate(record([USER_STORE, item]), ctx)

    assert decision.risk == "high"
    assert "Risk: HIGH. post holds a contact field and does not reach erasure." in decision.summary
    assert "Stores: 2   reaching erasure: 1   not reaching: 1   unverified: 0" in decision.summary
    assert "Entry points: close_account (route, app/views.py:4)" in decision.summary
    assert "  post (relational)" in decision.summary
    assert "NOT ERASED" in decision.summary
    assert "the SET_NULL foreign key leaves the row" in decision.summary
    assert "Left for you, and rendered as requires human completion:" in decision.summary
    capsys.readouterr()


def test_a_third_party_store_is_listed_as_left_unknown_under_auto(ctx_of, capsys):
    """07-ui.md section 4: `--approve auto` reads nothing and says what it left."""
    ctx = ctx_of(repo(), approve="auto")
    vendor = store("stripe", "third_party", cite("app/models.py", 4, "User"),
                   {"file": "app/models.py", "line": 4},
                   [field("email", "contact", "app/models.py", 5)],
                   erasure("external_manual"))
    decision = AdvancedArm().gate(record([USER_STORE, vendor]), ctx)
    printed = capsys.readouterr().out

    assert decision.risk == "high"
    assert "Recipient kinds left unknown: stripe" in printed
    assert decision.edits == {}


def test_the_gate_shows_both_ratings_when_the_two_readings_differ(ctx_of, capsys):
    """6.4: the record's rating is the one shown; the verifier's is carried beside it."""
    ctx = ctx_of(repo(child("CASCADE")), approve="auto")
    item = post_store("not_erased")
    item["fields"][0]["category"] = "identifier"
    submitted = record([USER_STORE, item])
    cross = cross_check(submitted, build_graph(ctx.root))

    assert cross == {"rating": "low", "stores": ["post"]}
    decision = AdvancedArm().gate(submitted, ctx)
    assert decision.risk == "high"
    assert "The verifier's own rating is LOW." in decision.summary
    assert "Stores the two readings differ on: post." in decision.summary
    capsys.readouterr()


def test_the_gate_shows_one_rating_when_only_a_store_differs(ctx_of, capsys):
    """6.4 shows the block "where the two ratings differ", and 7.3 accepts a
    conservative divergence by design: on a per-store trigger every conservative record
    printed "The verifier's own rating is LOW." on a screen already rating LOW."""
    ctx = ctx_of(repo(child("CASCADE")), approve="auto")
    submitted = record([USER_STORE, post_store("not_erased")])

    assert cross_check(submitted, build_graph(ctx.root)) is None
    decision = AdvancedArm().gate(submitted, ctx)
    assert decision.risk == "low"
    assert "The verifier's own rating" not in decision.summary
    capsys.readouterr()


PROPERTY_MODEL = """
from django.db import models


class User(models.Model):
    email = models.EmailField()
    nickname = property(lambda self: self.email)
"""
BLANK_ROUTE = """
from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    user.email = ""
    user.save()
"""


def test_the_cross_check_reads_the_record_s_own_columns(ctx_of):
    """6.4: the cross-check is computed from the verdict set the record was checked
    against. 4.7 unions the record's claimed columns into the set that must all be
    overwritten, so a second walk without them reads `anonymised` where `check` read
    `pseudonymised` -- and the gate would then stay silent on the divergence."""
    ctx = ctx_of(repo(PROPERTY_MODEL, view=BLANK_ROUTE))
    item = json.loads(json.dumps(USER_STORE))
    item["fields"] = [field("email", "contact", "app/models.py", 5),
                      field("nickname", "contact", "app/models.py", 6)]
    item["erasure"] = erasure("anonymised", [cite("app/views.py", 6, "email")])
    submitted = record([item])
    graph = build_graph(ctx.root)

    assert risk_rating(submitted) == "low"
    assert {key: value.verdict for key, value in verdicts(graph).items()} == {
        "user": "anonymised"}, "the columns the record adds are what change it"
    assert cross_check(submitted, graph) == {"rating": "high", "stores": ["user"]}


def test_the_ask_path_reads_the_recipient_kind_and_then_one_keystroke(monkeypatch, capsys):
    """10-instructions.md section 5: the recipient block sits above the keystroke."""
    answers = iter(["processor", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    vendor = store("stripe", "third_party", cite("app/models.py", 4, "User"),
                   {"file": "app/models.py", "line": 4},
                   [field("email", "contact", "app/models.py", 5)],
                   erasure("external_manual"))
    submitted = record([USER_STORE, vendor])
    decision = terminal.decide(submitted, "high", terminal.gate_summary(submitted, "high"),
                               "ask")

    assert (decision.approved, decision.by) == (True, "human")
    assert decision.edits == {"stores.stripe.recipient_kind": "processor"}
    assert decision.human_completions() == {"recipient_kind": {"stripe": "processor"}}
    capsys.readouterr()


def test_the_ask_path_cannot_address_a_store_whose_name_carries_a_dot(monkeypatch, capsys):
    """One key shape, both modes: the file gate drops the same edit with the same note.

    `apply_edits` and `Decision.human_completions` split the key and take the middle,
    so a kind recorded for `sentry.io` would name a store `sentry`, which the record
    does not have and `trace_check` check 17 rejects. The gate never offers the cell.
    """
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    vendor = store("sentry.io", "third_party", cite("app/models.py", 4, "User"),
                   {"file": "app/models.py", "line": 4},
                   [field("email", "contact", "app/models.py", 5)],
                   erasure("external_manual"))
    submitted = record([USER_STORE, vendor])
    decision = terminal.decide(submitted, "high", terminal.gate_summary(submitted, "high"),
                               "ask")

    assert decision.edits == {} and decision.human_completions() is None
    assert ("  sentry.io: a store name with a dot cannot be addressed at the gate"
            in capsys.readouterr().out)


def test_silence_at_the_prompt_is_not_approval(monkeypatch, capsys):
    """07-ui.md section 7: EOF is `n`, and the run ends `gate_rejected`."""
    def eof(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    submitted = record([USER_STORE])
    decision = terminal.decide(submitted, "low", terminal.gate_summary(submitted, "low"),
                               "ask")

    assert (decision.approved, decision.by) == (False, "human")
    capsys.readouterr()
