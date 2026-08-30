"""The MCP server, over a real pipe, with the advanced arm behind it.

Every test here spawns `python -m art30.brains.mcp_server` and speaks JSON-RPC to
it the way `claude` does. What is being checked is that the tool a local brain sees
is the tool the API brain sees -- `art30.tools.SPEC[3]`, name, description and
input schema -- and that the answer behind it is the arm's, so S10's dead helper
comes back with the verifier's own sentence rather than a schema error.

The fixture is copied first: ADR 0006 item 3 allows offline runs against fixture
copies and nothing else, and nothing here writes under `results/` or `traces/`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from art30 import tools
from tests.fakes.mcp_client import McpClient, server_argv
from tests.test_e2e_advanced import S10_LIE, S10_REASON, record_of

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "evals" / "fixtures" / "synthetic"


@pytest.fixture
def s10(tmp_path: Path) -> Path:
    target = tmp_path / "repos" / "S10"
    shutil.copytree(FIXTURES / "S10", target)
    return target


@pytest.fixture
def client(s10: Path, tmp_path: Path):
    with McpClient(server_argv("advanced", s10, tmp_path / "spool"), cwd=tmp_path) as talker:
        yield talker


def _lie() -> dict:
    """The record S10 is built to catch: `uploads` erased by a helper nothing calls."""
    return record_of("S10", edits={"uploads": S10_LIE}, drop=("nightly_backup",),
                     retention=False)


def test_initialize_answers_with_the_tool_capability_and_our_server_name(client) -> None:
    answer = client.initialize("2025-11-05")

    result = answer["result"]
    assert answer["id"] == 1 and answer["jsonrpc"] == "2.0"
    assert result["protocolVersion"] == "2025-11-05"   # the client's version is echoed
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == "art30"


def test_tools_list_serves_the_submit_record_spec_verbatim(client) -> None:
    client.initialize()

    served = client.tools()

    assert [tool["name"] for tool in served] == ["submit_record"]
    assert served[0]["description"] == tools.SPEC[3]["description"]
    assert served[0]["inputSchema"] == tools.SPEC[3]["input_schema"]


def test_the_dead_helper_claim_is_rejected_with_the_verifiers_own_reason(
    client, tmp_path: Path
) -> None:
    """The arm is the handler: a claim the verifier refuses is a tool error, not a schema one."""
    client.initialize()

    text, is_error = client.submit(_lie())

    payload = json.loads(text)
    assert is_error is True and payload["accepted"] is False
    assert payload["attempt"] == 1 and payload["attempts_left"] == 4
    claim = payload["rejected_claims"][0]
    assert (claim["store"], claim["claim"]) == ("uploads", "erasure.verdict=erased")
    assert claim["reason"] == S10_REASON
    assert [m["store"] for m in payload["missing_stores"]] == ["nightly_backup"]
    assert not (tmp_path / "spool" / "accepted.json").exists()


def test_the_corrected_record_is_accepted_once_and_spooled(client, tmp_path: Path) -> None:
    client.initialize()
    client.submit(_lie())

    text, is_error = client.submit(record_of("S10"))

    assert (text, is_error) == ('{"accepted":true}', False)
    accepted = json.loads((tmp_path / "spool" / "accepted.json").read_text(encoding="utf-8"))
    assert {store["name"] for store in accepted["stores"]} >= {"uploads", "nightly_backup"}
    lines = [json.loads(line) for line in
             (tmp_path / "spool" / "submissions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [line["attempt"] for line in lines] == [1, 2]
    assert lines[0]["feedback"]["accepted"] is False
    assert lines[0]["feedback"]["rejected_claims"][0]["store"] == "uploads"
    assert lines[1]["feedback"]["accepted"] is True

    again, error_again = client.submit(record_of("S10"))
    assert error_again is True and json.loads(again)["reason"] == "already accepted"
    assert [line["attempt"] for line in lines] == [1, 2]   # nothing was appended


def test_the_submit_budget_is_the_servers_and_leaves_a_marker(s10: Path, tmp_path: Path) -> None:
    """A sixth attempt cannot be bought from the CLI: the server counts, not the model."""
    spool = tmp_path / "spool"
    with McpClient(server_argv("advanced", s10, spool, submit_budget=2), cwd=tmp_path) as client:
        client.initialize()
        first, _ = client.submit(_lie())
        second, _ = client.submit(_lie())
        third, is_error = client.submit(_lie())

    assert json.loads(first)["attempts_left"] == 1
    assert json.loads(second)["attempts_left"] == 0
    assert is_error is True and json.loads(third)["reason"] == "no attempts left"
    assert (spool / "exhausted").is_file()
    assert len((spool / "submissions.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_a_notification_an_unknown_method_and_a_garbage_line_leave_the_server_up(
    client
) -> None:
    client.initialize()
    client.notify("notifications/cancelled", {"requestId": 99})   # answered with silence

    unknown = client.request("tools/nope")
    client.send_raw("{not json at all")
    parse_error = client.read()
    client.send_raw("[1, 2, 3]")
    not_object = client.read()

    assert unknown["error"]["code"] == -32601
    assert parse_error["error"]["code"] == -32700 and parse_error["id"] is None
    assert not_object["error"]["code"] == -32600
    assert client.request("ping")["result"] == {}   # still serving


def test_the_two_lists_codex_probes_on_connect_are_answered_empty(client) -> None:
    """This server advertises neither capability, and the spec leaves a server that
    does not free to refuse. Refusing cost something measurable: the real D02 codex run
    logged `resources/list failed` to stderr and the model then spent one of its 60
    tool calls on `list_mcp_resources` trying to recover. An empty list costs nothing.
    """
    client.initialize()

    resources = client.request("resources/list")
    templates = client.request("resources/templates/list")
    prompts = client.request("prompts/list")

    assert resources["result"] == {"resources": []}
    # `resourceTemplates` is the spec's key for this one. Answering with `resources`
    # put `resources/templates/list failed ... Unexpected response type` back on
    # codex's stderr and the model back on `list_mcp_resource_templates`.
    assert templates["result"] == {"resourceTemplates": []}
    assert prompts["result"] == {"prompts": []}
    assert client.request("tools/nope")["error"]["code"] == -32601   # still not a catch-all


def test_a_call_without_a_record_and_a_call_to_another_tool_are_errors(client) -> None:
    client.initialize()

    missing = client.call("submit_record", {})
    other = client.call("read_file", {"path": "app.py"})

    assert missing["isError"] is True
    assert "record object" in missing["content"][0]["text"]
    assert other["isError"] is True and "unknown tool" in other["content"][0]["text"]


def test_a_hostile_line_is_answered_and_the_server_keeps_serving(client) -> None:
    """The docstring promises "never fatal", and two shapes used to break it.

    `json.loads` raises `RecursionError` on a deeply nested line, not the
    `JSONDecodeError` the loop caught: 100k deep killed the process, took
    `submit_record` away for the rest of the run, and left the run ending
    `no_submission` with nothing saying why. Bytes that are not UTF-8 raised out of
    the read itself. Both are parse errors now, and the session survives them.
    """
    client.initialize()

    client.send_raw("[" * 100_000 + "]" * 100_000)
    deep = client.read()
    client.send_bytes(b"\xff\xfe\x80 not utf-8 and not json")
    undecodable = client.read()

    assert deep["error"]["code"] == -32700 and deep["id"] is None
    assert undecodable["error"]["code"] == -32700
    assert client.request("ping")["result"] == {}   # still serving
    assert client.submit(record_of("S10"))[1] is False
