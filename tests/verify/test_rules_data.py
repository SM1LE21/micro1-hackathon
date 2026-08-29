"""The rule data: the five files, their split, and what every entry must carry.

`docs/spec/verifier-rules-draft.yaml` maps its sections to the five files under
`art30/verify/rules/`; two of its blocks (`path_modes` and `verdict_precedence`
with `reaches_erasure_true`) are deliberately not rule data and ship as constants
in `reach.py`, because a rule file that could reorder the precedence could put a
reaching verdict above a conservative one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from art30.verify.rules import (FILES, RULE_ID, RULES_DIR, SOURCE_ID, RuleError,
                                load_file, load_rules)

DRAFT = Path(__file__).resolve().parents[2] / "docs" / "spec" / "verifier-rules-draft.yaml"
CONSTANTS = {"path_modes", "verdict_precedence", "reaches_erasure_true"}
SKIP = {"version", "generated_for", "python_target", "section"}


def test_the_five_files_load_and_validate():
    rules = load_rules()
    assert sorted(FILES) == sorted(p.stem for p in RULES_DIR.glob("*.yaml"))
    assert rules.scan["max_file_bytes"] == 1048576
    assert rules.kinds.keys() >= {"relational", "object_storage", "cache", "search_index",
                                  "queue", "third_party", "log", "backup"}


def test_every_block_carries_its_rule_and_its_sources():
    for name in FILES:
        doc = load_file(name)
        for root, block in sorted(doc.items()):
            if root in SKIP:
                continue
            blocks = block.values() if root in {"store_kinds", "recipients", "entry_points"} else [block]
            for entry in blocks:
                assert RULE_ID.match(entry["rule"]), (name, root, entry["rule"])
                assert all(SOURCE_ID.match(s) for s in entry["source"]), (name, root)


def test_every_deletion_primitive_names_its_rule():
    rules = load_rules()
    for kind, entry in rules.all_primitives():
        assert RULE_ID.match(entry["rule"]), (kind, entry)
        assert entry["source"], (kind, entry)


def test_the_draft_sections_are_covered_exactly_once():
    draft = yaml.safe_load(DRAFT.read_text(encoding="utf-8"))
    wanted = {key for key in draft if key not in SKIP | CONSTANTS}
    shipped: dict[str, str] = {}
    for name in FILES:
        for key in load_file(name):
            if key in SKIP:
                continue
            assert key not in shipped, f"{key} is in both {shipped.get(key)} and {name}"
            shipped[key] = name
    assert wanted <= set(shipped), sorted(wanted - set(shipped))
    assert shipped["scan"] == "stores" and shipped["store_kinds"] == "stores"
    assert shipped["recipients"] == "recipients"
    assert shipped["entry_points"] == "entrypoints"
    assert shipped["django_on_delete"] == "primitives" and shipped["sqlalchemy"] == "primitives"
    assert shipped["soft_delete_markers"] == "patterns"
    assert shipped["personal_data_field_patterns"] == "patterns"


def test_the_search_state_and_the_precedence_are_not_rule_files():
    """03-verifier.md 5.2 and 6.1: both ship as constants in reach.py."""
    for name in FILES:
        assert not (CONSTANTS & set(load_file(name)))


def test_a_block_without_a_rule_id_is_refused(tmp_path):
    doc = yaml.safe_load((RULES_DIR / "patterns.yaml").read_text(encoding="utf-8"))
    doc["timers"].pop("rule")
    (tmp_path / "patterns.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    for name in ("stores", "recipients", "entrypoints", "primitives"):
        (tmp_path / f"{name}.yaml").write_text(
            (RULES_DIR / f"{name}.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(RuleError):
        load_rules(str(tmp_path))


def test_a_malformed_source_id_is_refused(tmp_path):
    doc = yaml.safe_load((RULES_DIR / "recipients.yaml").read_text(encoding="utf-8"))
    doc["recipients"]["stripe"]["source"] = ["stripe docs"]
    (tmp_path / "recipients.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    for name in ("stores", "entrypoints", "primitives", "patterns"):
        (tmp_path / f"{name}.yaml").write_text(
            (RULES_DIR / f"{name}.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(RuleError):
        load_rules(str(tmp_path))


# --------------------------------------------------------------------------
# what the data has to say, because a rule reads it
# --------------------------------------------------------------------------
def test_on_delete_tokens_match_r1_to_r4():
    rules = load_rules()
    assert rules.on_delete("CASCADE")["edge"] is True
    assert rules.on_delete("DB_CASCADE")["sets_mode"] == "db_cascade"
    assert rules.on_delete("DB_CASCADE")["signals"] is False
    for token in ("SET_NULL", "SET_DEFAULT", "SET", "DO_NOTHING", "PROTECT", "RESTRICT"):
        assert rules.on_delete(token)["edge"] is False


def test_cascade_token_parsing_is_exact():
    """R5 [S15]: `delete-orphan` contains `delete` and is not a delete cascade."""
    rules = load_rules()
    assert rules.cascade_is_delete("all, delete-orphan") is True
    assert rules.cascade_is_delete("save-update, merge, delete-orphan") is False
    assert rules.cascade_is_delete("delete") is True
    assert rules.cascade_is_delete("") is False


def test_the_vocabulary_excludes_the_four_bare_words():
    rules = load_rules()
    names = rules.entry["vocabulary"]["names"]
    assert "delete" not in names and "destroy" not in names
    assert set(rules.entry["excluded_vocabulary"]["names"]) == {
        "cleanup", "remove", "delete", "destroy", "deactivate"}
    assert rules.vocabulary_hit("delete_comment") is None
    assert rules.vocabulary_hit("close_account") == "close_account"


def test_guard_list_keeps_name_qualified():
    """Decision 24: with `name` strong the guard fires twice on FlaskBB."""
    rules = load_rules()
    assert "name" in rules.guard["qualified"] and "name" not in rules.guard["strong"]
    assert rules.guard_hit("email") == "strong" and rules.guard_hit("name") == "qualified"
    assert rules.guard_hit("sku") == ""


def test_r23_sentry_carries_its_default_fields():
    rules = load_rules()
    sentry = rules.recipient("sentry")
    assert [f["name"] for f in sentry["fields_by_default"]] == [
        "url", "query_string", "request_body", "stack_locals", "source_context"]
    assert sentry["upgrades_to_erased"] is False and sentry["verdict"] == "external_manual"


def test_r24_segment_is_the_only_upgrade_to_erased():
    rules = load_rules()
    upgrades = {name: rules.recipient(name)["upgrades_to_erased"]
                for name in rules.recipient_names()}
    assert upgrades["segment"] == "forwarding_types_only"
    assert all(value is False for name, value in upgrades.items() if name != "segment")
    assert rules.recipient("segment")["forwarding_types"] == ["SUPPRESS_WITH_DELETE", "DELETE_ONLY"]


def test_scan_surface_matches_the_skip_table():
    rules = load_rules()
    assert rules.skip_reason("tests/test_a.py") == "dir:tests"
    assert rules.skip_reason("app/conftest.py") == "file:conftest.py"
    assert rules.skip_reason("app/models.py") is None
    assert rules.always_scan("project/settings/base.py") is True
    assert rules.always_scan("app/management/commands/purge_users.py") is True
    assert rules.scan["r13_also_searches_python_as_text"] is True


def test_raw_sql_has_a_bare_string_literal_form():
    """R19 [S11]: 4.1's raw_sql example is `cursor.execute("DELETE ...")`.

    With every `raw_sql` entry gated on `arg0_call: [text]` the bare-string form matched
    nothing, and the mode's own example produced no primitive and no store edge.
    """
    rules = load_rules()
    raw = [entry for kind, entry in rules.all_primitives()
           if kind == "relational" and entry.get("mode") == "raw_sql"]
    assert raw, "no raw_sql primitive"
    bare = [entry for entry in raw
            if not entry.get("arg0_call") and any("execute" in call for call in entry["call"])]
    assert bare and all(entry["rule"] == "R19" for entry in bare)


def test_the_non_decorator_route_registration_is_rule_data():
    """2.2 route row: Flask's `add_url_rule` registers a handler no decorator names."""
    rules = load_rules()
    spec = rules.entry["route_registration"]
    assert spec["calls"] == ["add_url_rule"]
    assert spec["view_func_kwarg"] == "view_func" and spec["view_func_positional"] == 2
