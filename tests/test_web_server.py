"""`art30 serve`, offline: the catalogue, one real replayed run, the gate, cancel.

No key, no socket to anywhere but 127.0.0.1, nothing written outside `tmp_path`.
The one real child is the CLI itself in `--mode replay`, over a cache this file
records first through `art30.llm.Cache` with the fake SDK of
`tests/test_replay_roundtrip.py`: a subprocess cannot be monkeypatched, so the
seam has to be a recorded cache.

The gate runs the same way: the advanced arm of D01, replayed, blocking on
`<out>/gate/request.json` until this server writes the decision beside it. Only
the cancel test scripts its child, because a run that ends needs no killing.
"""

from __future__ import annotations

import json
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from advanced.arm import AdvancedArm
from art30 import config as config_mod
from art30 import llm
from art30.config import Config
from art30.loop import CaseRef
from art30.loop import run as run_loop
from art30.web import runs
from art30.web import server as server_mod
from art30.web import sse
from baseline.arm import BaselineArm
from test_e2e_advanced import record_of
from test_replay_roundtrip import FakeClient, _message, _use

CASE, ARM, SEED = "D01", "baseline", 1
REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evals" / "fixtures" / "synthetic" / CASE

BLOCKING_CHILD = "import time\nprint('waiting', flush=True)\ntime.sleep(60)\n"


# --- the recorded cache, the server ------------------------------------------------------


@pytest.fixture(scope="module")
def recorded(tmp_path_factory) -> tuple[Path, Path]:
    """Both arms of D01, recorded through the real cache with a fake SDK below `llm.call`.

    One scripted step each: the manifest submitted as a record, which the verifier
    accepts on the first attempt (`tests/test_e2e_advanced.py`).
    """
    base = tmp_path_factory.mktemp("web")
    repo = base / "repos" / CASE
    shutil.copytree(FIXTURE, repo)
    cache = base / "cache"
    for arm in (BaselineArm(), AdvancedArm()):
        fake = FakeClient([_message([_use("t1", "submit_record", {"record": record_of(CASE)})])])
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(llm, "_client", lambda max_retries: fake)
            cfg = Config(mode="live", record=True, approve="auto", cache_dir=cache,
                         out_dir=base / "out", trace_dir=base / "traces")
            result = run_loop(CaseRef(id=CASE, name=repo.name, root=repo), arm, SEED, cfg, None)
        assert result.stop_condition == "accepted", result.note
        assert (cache / CASE / arm.name / f"s{SEED}" / "01.json").is_file()
    return repo, cache


@pytest.fixture()
def web(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded):
    _, cache = recorded
    monkeypatch.setenv("ART30_CACHE_DIR", str(cache))
    monkeypatch.setenv("ART30_GATE_TIMEOUT", "30")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(config_mod, "read_dotenv", lambda *a, **k: {})
    monkeypatch.setattr(runs, "RUNS_ROOT", tmp_path / "web")
    monkeypatch.setattr(runs, "_runs", {})
    httpd = server_mod.build("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    for run in runs.listing():
        if run.proc.poll() is None:
            run.proc.kill()
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def call(url: str, body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return answer.status, json.loads(answer.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def raw(url: str) -> tuple[int, str, str]:
    try:
        with urllib.request.urlopen(url, timeout=30) as answer:
            return answer.status, answer.headers.get("Content-Type", ""), \
                answer.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read().decode("utf-8")


def stream(url: str, on_event=None, timeout: int = 90) -> list[tuple[str, str]]:
    """Read the event stream to `done`, calling back on each event as it arrives."""
    events: list[tuple[str, str]] = []
    name = None
    with urllib.request.urlopen(url, timeout=timeout) as answer:
        for raw_line in answer:
            line = raw_line.decode("utf-8").rstrip("\n")
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: ") and name is not None:
                events.append((name, line[len("data: "):]))
                if on_event is not None:
                    on_event(name, events[-1][1])
                if name == "done":
                    return events
                name = None
    return events


def wait_for(predicate, seconds: float = 20.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def traced(events: list[tuple[str, str]]) -> list[str]:
    return [json.loads(data)["type"] for name, data in events if name == "trace"]


# --- the catalogue -----------------------------------------------------------------------


def test_the_catalogue_lists_every_case_with_its_split_and_kind(web) -> None:
    status, payload = call(web + "/api/cases")
    assert status == 200
    rows = {row["id"]: row for row in payload["cases"]}
    assert [f"S{n:02d}" for n in range(1, 11)] == [c for c in rows if c.startswith("S")]
    assert {"D01", "D02"} <= set(rows)
    assert rows["S01"]["split"] == "dev" and rows["S10"]["split"] == "test"
    assert rows["D01"]["kind"] == "demo" and rows["S01"]["kind"] == "synthetic"
    assert rows["R01"]["kind"] == "real"
    assert rows["R01"]["path"] == "evals/fixtures/real/full-stack-fastapi-template"
    assert rows["D01"]["replayable"] is True
    assert rows["D01"]["replay_arms"] == ["baseline", "advanced"]
    assert rows["S01"]["replayable"] is False
    assert payload["live_enabled"] is False, "no key here, and the catalogue must say so"


def test_a_repository_that_is_neither_a_case_nor_a_directory_is_refused(web) -> None:
    status, payload = call(web + "/api/runs", {"repo": "nope", "arm": "baseline",
                                               "mode": "replay"})
    assert status == 400
    assert payload == {"error": "no case and no directory called nope"}


def test_live_is_refused_without_a_key_and_the_test_split_is_named(web) -> None:
    status, payload = call(web + "/api/runs", {"repo": "S02", "arm": "baseline", "mode": "live"})
    assert status == 400 and "ANTHROPIC_API_KEY" in payload["error"]
    status, payload = call(web + "/api/runs", {"repo": "S10", "arm": "advanced",
                                               "mode": "replay"})
    assert status == 400 and "no recorded responses for S10/advanced" in payload["error"]


def test_a_test_split_case_is_refused_live_and_the_reason_names_the_split(
    web, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lock evals/split.yaml holds: live on `test` goes through the harness ledger."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-key-and-never-read")
    status, payload = call(web + "/api/runs", {"repo": "S10", "arm": "advanced", "mode": "live"})
    assert status == 400 and "test split" in payload["error"]
    assert "Replay is allowed" in payload["error"]


# --- one real run, replayed --------------------------------------------------------------


def test_a_recorded_case_replays_through_the_cli_and_every_citation_opens(web) -> None:
    status, started = call(web + "/api/runs", {"repo": str(FIXTURE), "case": "relabelled",
                                               "arm": ARM, "mode": "replay", "seed": SEED})
    assert (status, started["status"]) == (201, "running")
    run_id = started["run_id"]
    assert run_id.startswith(f"{ARM}-{CASE}-s{SEED}-")

    events = stream(f"{web}/api/runs/{run_id}/events")
    assert traced(events) == ["run_start", "step", "run_end"]
    end = json.loads([d for n, d in events if n == "trace"][-1])
    assert end["stop_condition"] == "accepted"
    done = json.loads([d for n, d in events if n == "done"][-1])
    assert done == {"exit_code": 0, "stop_condition": "accepted", "status": "accepted"}
    printed = "\n".join(d for n, d in events if n == "stdout")
    assert "art30" in printed and "accepted" in printed and "[render]" in printed

    status, payload = call(web + "/api/runs")
    assert [(r["run_id"], r["status"]) for r in payload["runs"]] == [(run_id, "accepted")]
    assert call(f"{web}/api/runs/{run_id}")[1]["case"] == CASE
    status, record = call(f"{web}/api/runs/{run_id}/record")
    assert status == 200 and record["provenance"]["arm"] == "baseline"
    assert [s["name"] for s in record["stores"]][:1] == ["members_member"]
    status, content_type, text = raw(f"{web}/api/runs/{run_id}/record.md")
    assert status == 200 and content_type.startswith("text/markdown")
    assert text.startswith("# ")
    status, content_type, html = raw(f"{web}/api/runs/{run_id}/record.html")
    assert status == 200 and content_type.startswith("text/html") and "<table" in html

    status, payload = call(f"{web}/api/runs/{run_id}/source"
                           "?path=members/models.py&line=14&context=2")
    assert status == 200
    assert payload["path"] == "members/models.py" and payload["start"] == 12
    assert [n for n, _ in payload["lines"]] == [12, 13, 14, 15, 16]
    assert "avatar" in dict(payload["lines"])[14]
    status, payload = call(f"{web}/api/runs/{run_id}/source?path=../../../etc/passwd&line=1")
    assert status == 403 and "escapes the repository root" in payload["error"]
    status, payload = call(f"{web}/api/runs/{run_id}/source?path=passwd%00&line=1")
    assert status == 403, "a NUL byte never reaches the jail, so the jail never rules on it"
    status, payload = call(f"{web}/api/runs/{run_id}/source?path=nothing.py&line=1")
    assert status == 404
    status, payload = call(f"{web}/api/runs/{run_id}/source?path=members/models.py&line=9999")
    assert status == 404 and "there is no line 9999" in payload["error"]


# --- the gate and the cancel -------------------------------------------------------------


def test_the_gate_is_answered_mid_stream_and_the_decision_reaches_the_child(web) -> None:
    """The advanced arm of D01, replayed: the real `--approve file` gate blocks in the
    child and this server answers it, which is the demo path end to end."""
    status, started = call(web + "/api/runs", {"repo": CASE, "arm": "advanced",
                                               "mode": "replay"})
    assert status == 201, started
    run_id = started["run_id"]
    answered: list[tuple[int, dict]] = []
    seen: list[dict] = []

    def answer(name: str, data: str) -> None:
        if name != "gate":
            return
        request = json.loads(data)
        seen.append(request)
        answered.append(call(f"{web}/api/runs/{run_id}/gate",
                             {"approved": True, "edits": {"members_member": "sold"}}))
        answered.append(call(f"{web}/api/runs/{run_id}/gate", {"approved": True}))
        answered.append(call(f"{web}/api/runs/{run_id}/gate", {"approved": True}))

    events = stream(f"{web}/api/runs/{run_id}/events", on_event=answer)

    assert seen and seen[0]["risk"] in ("low", "medium", "high")
    assert seen[0]["summary"].startswith("RECORD READY FOR REVIEW")
    assert seen[0]["human_cells"] and "retention justification" in seen[0]["human_cells"][-1]
    assert answered[0][0] == 400 and "recipient kind" in answered[0][1]["error"]
    assert answered[1][0] == 200 and answered[2][0] == 410
    assert "gate" in [name for name, _ in events]
    assert traced(events)[0] == "run_start" and traced(events)[-1] == "run_end"
    checkpoint = [json.loads(d) for n, d in events if n == "trace"
                  and json.loads(d)["type"] == "checkpoint"]
    assert checkpoint and checkpoint[0]["decision"] == "approved"
    assert checkpoint[0]["by"] == "human", "a decision a person wrote is not a simulated one"
    done = json.loads([d for n, d in events if n == "done"][-1])
    assert done == {"exit_code": 0, "stop_condition": "accepted", "status": "accepted"}


def test_cancel_kills_a_child_that_is_waiting_and_the_gate_refuses_before_the_request(
    web, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runs, "command", lambda *argv, **named: [
        sys.executable, "-c", BLOCKING_CHILD])
    status, started = call(web + "/api/runs", {"repo": CASE, "arm": "advanced",
                                               "mode": "replay"})
    assert status == 201, started
    run_id = started["run_id"]
    run = runs.get(run_id)
    assert wait_for(lambda: runs.status(run) == "running")

    status, payload = call(f"{web}/api/runs/{run_id}/gate", {"approved": True})
    assert status == 409 and payload["error"] == "this run has not reached the gate yet"

    status, payload = call(f"{web}/api/runs/{run_id}/cancel", {})
    assert (status, payload["status"]) == (200, "cancelling")
    assert wait_for(lambda: run.proc.poll() is not None), "SIGTERM did not end the child"
    assert runs.status(run) == "failed:cancelled"
    status, payload = call(f"{web}/api/runs/{run_id}/cancel", {})
    assert status == 409


# --- what the server refuses ---------------------------------------------------------------


def test_a_directory_outside_the_project_is_refused_and_a_fixture_keeps_its_own_case(
    web, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two ways to walk around the split lock, both closed: the jail root is picked by
    the caller, and the case label is a separate field from the repository."""
    status, payload = call(web + "/api/runs", {"repo": str(tmp_path), "arm": "baseline",
                                               "mode": "replay"})
    assert status == 400 and "outside" in payload["error"]
    status, payload = call(web + "/api/runs", {"repo": "/etc", "case": CASE,
                                               "arm": "baseline", "mode": "replay"})
    assert status == 400 and "outside" in payload["error"]
    for inside in (".", str(REPO_ROOT), "evals/.."):
        status, payload = call(web + "/api/runs", {"repo": inside, "arm": "baseline",
                                                   "mode": "replay"})
        assert status == 400, inside
        assert payload["error"] == ("name a case or a repository inside the project,"
                                    " not the project root"), inside
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-key-and-never-read")
    status, payload = call(web + "/api/runs", {"repo": "evals/fixtures/synthetic/S10",
                                               "case": "sneaky", "arm": "advanced",
                                               "mode": "live"})
    assert status == 400 and "test split" in payload["error"]


def test_the_secrets_file_is_not_readable_as_source(web, tmp_path: Path) -> None:
    """`.env` holds the API key the Settings view writes, and `source` is not the way
    back out: refused under any root, before the file is opened."""
    canary = "sk-ant-api03-CANARY-not-a-real-key-0123456789"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text(f"ANTHROPIC_API_KEY={canary}\n", encoding="utf-8")
    (repo / "README.md").write_text("a line\n", encoding="utf-8")
    run_id = "baseline-D01-s1-abcdef"
    directory = tmp_path / "web" / run_id
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps(
        {"run_id": run_id, "case": CASE, "arm": ARM, "mode": "replay", "seed": SEED,
         "repo": str(repo), "started_at": "2026-08-30T09:00:00Z"}), encoding="utf-8")

    ok, _type, body = raw(f"{web}/api/runs/{run_id}/source?path=README.md&line=1")
    assert ok == 200 and "a line" in body, "an ordinary file in the same root still opens"
    for path in (".env", "./.env", "sub/../.env"):
        status, _type, body = raw(f"{web}/api/runs/{run_id}/source?path={path}&line=1&context=3")
        assert status == 403, path
        assert canary not in body, path
        assert json.loads(body)["error"] == "the secrets file is not source", path


def test_another_host_and_another_origin_are_both_refused(web) -> None:
    """A name someone else controls can be pointed at 127.0.0.1; the page it serves
    cannot then read this server, because the `Host` it sends is not ours."""
    rebound = urllib.request.Request(web + "/api/cases", headers={"Host": "evil.example.com"})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(rebound, timeout=10)
    assert caught.value.code == 403
    cross = urllib.request.Request(web + "/api/runs", data=b'{"repo": "D01"}',
                                   headers={"Content-Type": "text/plain",
                                            "Origin": "https://evil.example.com"})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(cross, timeout=10)
    assert caught.value.code == 403
    assert call(web + "/api/cases")[0] == 200, "the page's own requests still pass"


def test_the_child_never_records_and_reads_the_cache_the_catalogue_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ART30_RECORD", "1")
    monkeypatch.setenv("ART30_CACHE_DIR", str(tmp_path / "cache"))
    env = runs.environment(tmp_path, "replay")
    assert env["ART30_RECORD"] == "0", "a recording run clears the slot it writes"
    assert env["ART30_CACHE_DIR"] == str(tmp_path / "cache")
    assert env["ART30_TRACE_DIR"] == str(tmp_path / "traces")


def test_a_character_split_across_two_polls_survives_the_tail(tmp_path: Path) -> None:
    path = tmp_path / "stdout.log"
    path.write_bytes(b"art30 \xc2")
    tail = sse.Tail(lambda: path)
    assert tail.lines() == [], "half of a separator is not a line"
    with path.open("ab") as handle:
        handle.write(b"\xb7 case D01\n")
    assert tail.lines() == ["art30 \u00b7 case D01"]
    tail.close()
