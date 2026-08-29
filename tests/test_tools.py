"""Golden tool output, the jail, and the caps.

The golden strings are the bytes that go into a `tool_result` block and so into
the hash of every later request; a change here is a replay miss everywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from art30.tools import (
    SPEC,
    ToolCtx,
    ToolError,
    dispatch,
    format_schema_errors,
    grep,
    list_tree,
    read_file,
    resolve,
)
from conftest import mkrepo

GOLDEN_TREE = (
    "README.md  (7 B)\n"
    "alpha.py  (10 B)\n"
    "api/\n"
    "  __init__.py  (0 B)\n"
    "  account.py  (61 B)\n"
    "billing.py  (40 B)\n"
    "models.py  (51 B)\n"
    "storage.py  (74 B)\n"
    "zeta.py  (43 B)"
)

GOLDEN_GREP = (
    "api/account.py:2:     return delete_later(user_id)\n"
    "models.py:3:     deleted_at = None\n"
    "storage.py:5:     delete(user_id)\n"
)


def test_list_tree_is_sorted_and_golden(ctx: ToolCtx) -> None:
    assert list_tree(ctx) == GOLDEN_TREE


def test_list_tree_excludes_the_five_directories(ctx: ToolCtx) -> None:
    assert "__pycache__" not in list_tree(ctx)


def test_list_tree_respects_max_depth(ctx: ToolCtx) -> None:
    assert "account.py" not in list_tree(ctx, ".", 1)


def test_grep_is_recursive_sorted_and_golden(ctx: ToolCtx) -> None:
    assert grep(ctx, "delete") == GOLDEN_GREP


def test_grep_glob_cannot_walk_out_of_the_root(ctx: ToolCtx, tmp_path: Path) -> None:
    sibling = mkrepo(tmp_path / "sibling", {"other.py": "SECRET_FROM_ANOTHER_CASE = 1\n"})
    assert sibling.is_dir()
    assert grep(ctx, "SECRET", ".", "../sibling/*.py") == "no matches\n"


def test_grep_glob_cannot_follow_a_symlinked_directory(ctx: ToolCtx, tmp_path: Path) -> None:
    outside = mkrepo(tmp_path / "outside", {"secret.py": "SECRET_TOKEN = 1\n"})
    (ctx.root / "link").symlink_to(outside, target_is_directory=True)
    assert grep(ctx, "SECRET", ".", "link/*.py") == "no matches\n"
    assert grep(ctx, "SECRET", ".", "*/*.py") == "no matches\n"


def test_grep_never_emits_a_path_outside_the_root(ctx: ToolCtx, tmp_path: Path) -> None:
    mkrepo(tmp_path / "outside", {"secret.py": "delete\n"})
    (ctx.root / "link").symlink_to(tmp_path / "outside", target_is_directory=True)
    for glob in ("*.py", "*/*.py", "../outside/*.py", "link/*.py"):
        for line in grep(ctx, "delete", ".", glob).splitlines():
            assert not line.startswith("..") and not line.startswith("/")


def test_grep_rejects_an_absolute_glob_without_raising(ctx: ToolCtx) -> None:
    output, is_error = dispatch(
        "grep", {"pattern": "x", "path": ".", "glob": "/etc/*.py", "max_results": 5}, ctx
    )
    assert is_error and "must be relative" in output


def test_grep_glob_selects_non_python_files(ctx: ToolCtx) -> None:
    assert grep(ctx, "delete", glob="*.md") == "README.md:1: delete\n"


def test_grep_sorts_before_the_max_results_cut(tmp_path: Path) -> None:
    root = mkrepo(tmp_path / "fx", {"zeta.py": "hit\n", "alpha.py": "hit\n"})
    ctx = ToolCtx(root=root.resolve())
    assert grep(ctx, "hit", max_results=1) == "alpha.py:1: hit\n"


def test_grep_never_returns_more_than_a_hundred(tmp_path: Path) -> None:
    root = mkrepo(tmp_path / "fx", {"many.py": "hit\n" * 150})
    ctx = ToolCtx(root=root.resolve())
    assert len(grep(ctx, "hit", max_results=1000).splitlines()) == 100


def test_grep_reports_no_matches_rather_than_an_empty_result(ctx: ToolCtx) -> None:
    assert grep(ctx, "nothing_matches_this") == "no matches\n"


def test_read_file_on_an_empty_file_is_not_an_error(ctx: ToolCtx) -> None:
    output, is_error = dispatch(
        "read_file", {"path": "api/__init__.py", "start_line": 1, "end_line": None}, ctx
    )
    assert not is_error
    assert output == "(empty file)\n"


def test_read_file_strips_a_trailing_carriage_return(tmp_path: Path) -> None:
    root = mkrepo(tmp_path / "fx", {"crlf.py": "one\r\ntwo\r\n"})
    ctx = ToolCtx(root=root.resolve())
    assert read_file(ctx, "crlf.py") == "1: one\n2: two\n"


def test_read_file_caps_at_four_hundred_lines(tmp_path: Path) -> None:
    root = mkrepo(tmp_path / "fx", {"long.py": "".join(f"line{n}\n" for n in range(1, 501))})
    ctx = ToolCtx(root=root.resolve())
    lines = read_file(ctx, "long.py").splitlines()
    assert len(lines) == 400
    assert lines[-1] == "400: line400"
    assert read_file(ctx, "long.py", 101, 600).splitlines()[-1] == "500: line500"


def test_read_file_clamps_a_meaningless_end_line(tmp_path: Path) -> None:
    root = mkrepo(tmp_path / "fx", {"short.py": "a\nb\nc\n"})
    ctx = ToolCtx(root=root.resolve())
    to_end = read_file(ctx, "short.py", 1, None)
    assert read_file(ctx, "short.py", 1, 0) == to_end
    assert read_file(ctx, "short.py", 2, 1) == "2: b\n3: c\n"


def test_jail_rejects_a_relative_escape(ctx: ToolCtx) -> None:
    with pytest.raises(ToolError):
        resolve(ctx.root, "../secrets.txt")


def test_jail_rejects_an_absolute_path(ctx: ToolCtx) -> None:
    with pytest.raises(ToolError):
        resolve(ctx.root, "/etc/passwd")


def test_jail_resolves_symlinks_before_the_containment_check(ctx: ToolCtx, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n", encoding="utf-8")
    (ctx.root / "link.txt").symlink_to(outside)
    with pytest.raises(ToolError):
        resolve(ctx.root, "link.txt")


def test_dispatch_returns_errors_rather_than_raising(ctx: ToolCtx) -> None:
    output, is_error = dispatch("read_file", {"path": "../x", "start_line": 1, "end_line": None}, ctx)
    assert is_error and "escapes" in output
    unknown, unknown_error = dispatch("rm_rf", {}, ctx)
    assert unknown_error and "unknown tool" in unknown


def test_dispatch_emits_no_absolute_path(ctx: ToolCtx) -> None:
    for name, args in (
        ("list_tree", {"path": ".", "max_depth": 4}),
        ("grep", {"pattern": "delete", "path": ".", "glob": "*.py", "max_results": 100}),
    ):
        output, is_error = dispatch(name, args, ctx)
        assert not is_error
        assert str(ctx.root) not in output


def test_spec_order_and_strictness() -> None:
    assert [tool["name"] for tool in SPEC] == ["list_tree", "read_file", "grep", "submit_record"]
    for tool in SPEC:
        schema = tool["input_schema"]
        assert tool["strict"] is True
        assert schema["additionalProperties"] is False
        assert sorted(schema["required"]) == sorted(schema["properties"])
    end_line = SPEC[1]["input_schema"]["properties"]["end_line"]
    assert end_line == {"anyOf": [{"type": "integer"}, {"type": "null"}]}
    assert "end_line" in SPEC[1]["input_schema"]["required"]


def test_submit_record_schema_is_self_contained() -> None:
    schema = SPEC[3]["input_schema"]
    assert "$defs" in schema, "hoisted so every #/$defs reference resolves"
    Draft202012Validator.check_schema(schema)
    assert "$id" not in json.dumps(schema["properties"]["record"])


def test_format_schema_errors_sorts_and_names_the_allowed_values() -> None:
    schema = {
        "type": "object",
        "properties": {"verdict": {"enum": ["erased", "not_erased"]}, "line": {"type": "integer"}},
        "required": ["line"],
    }
    errors = Draft202012Validator(schema).iter_errors({"verdict": "deleted"})
    rendered = format_schema_errors(errors)
    assert rendered == [
        "/: 'line' is a required property",
        "/verdict: 'deleted' is not one of the allowed values; allowed: erased, not_erased",
    ]
