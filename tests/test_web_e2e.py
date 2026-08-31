"""S10 through the website, start to finish: replay, the gate, the record, a citation.

`tests/test_web_server.py` holds the server's own surface -- the catalogue, the
refusals, the jail. This file walks the demo path once, on the hardest case, and
asserts the four things a judge watching the screen actually sees:

1. the verifier strikes the dead-helper claim and the reason names the line;
2. the run blocks at `--approve file` until a person answers, and the answer is
   recorded `by: human` with the recipient kind that person set;
3. the renderer's own `record.json`, `record.md` and `record.html` come back
   through the API, byte for byte off the child's directory (ADR 0007: nothing
   here renders anything);
4. the citation under the dead helper opens the source line, through the same
   jail the model's `read_file` uses.

No key and no socket to anywhere but 127.0.0.1: the cache the child replays from
is recorded in this file through the real `art30.llm.Cache`, with the fake SDK of
`tests/test_replay_roundtrip.py` standing where `anthropic.Anthropic()` would. A
subprocess cannot be monkeypatched, so a recorded cache is the only seam.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
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
from test_e2e_advanced import record_of
from test_replay_roundtrip import FakeClient, _message, _use
from test_web_server import call, raw, stream, traced

CASE, ARM, SEED = "S10", "advanced", 1
REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evals" / "fixtures" / "synthetic" / CASE
PAGE = REPO_ROOT / "art30" / "web" / "index.html"
HELPER = "cleanup_user_files"
# The claim the first submit makes and the verifier strikes: the dead helper is
# read as the erasure of the uploads bucket (evals/fixtures/manifests/S10.yaml).
LIE = {"verdict": "erased",
       "evidence": [{"file": "storage.py", "line": 30, "symbol": "delete_object"}],
       "timer_days": None, "note": HELPER + " removes the avatar"}
# `<file>.py:<line>` out of the verifier's own sentence, so the citation this test
# opens is the one the run produced rather than one copied into the test.
CITED = re.compile(re.escape(HELPER) + r" \((?P<file>[\w./-]+):(?P<line>\d+)\)")


# --- the recorded cache ------------------------------------------------------------------


@pytest.fixture(scope="module")
def recorded(tmp_path_factory) -> Path:
    """S10 on the advanced arm, recorded through the real cache with a fake SDK.

    Two scripted steps, which is the shape the case was built for: the dead-helper
    claim, then the record the verifier accepts (`tests/test_e2e_advanced.py`).
    """
    base = tmp_path_factory.mktemp("web-e2e")
    repo = base / "repos" / CASE
    shutil.copytree(FIXTURE, repo)
    cache = base / "cache"
    script = [
        _message([_use("t1", "submit_record",
                       {"record": record_of(CASE, edits={"uploads": LIE})})]),
        _message([_use("t2", "submit_record", {"record": record_of(CASE)})]),
    ]
    fake = FakeClient(script)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(llm, "_client", lambda max_retries: fake)
        cfg = Config(mode="live", record=True, approve="auto", cache_dir=cache,
                     out_dir=base / "out", trace_dir=base / "traces")
        result = run_loop(CaseRef(id=CASE, name=repo.name, root=repo), AdvancedArm(),
                          SEED, cfg, None)
    assert result.stop_condition == "accepted", result.note
    assert (result.submits, result.verify_rounds) == (2, 1)
    slot = cache / CASE / ARM / f"s{SEED}"
    assert sorted(path.name for path in slot.iterdir()) == ["01.json", "02.json"]
    return cache


@pytest.fixture()
def web(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded: Path):
    """The real server, over the recorded cache, writing under `tmp_path` alone.

    Every `ART30_*` the shell may carry is cleared first: four of them change the
    request the child builds, and a changed request is a replay miss rather than a
    run. `.env` is stubbed for the same reason, and because the key check reads it.
    """
    for name in [key for key in os.environ if key.startswith("ART30_")]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ART30_CACHE_DIR", str(recorded))
    monkeypatch.setenv("ART30_GATE_TIMEOUT", "60")
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


def submit_feedback(events: list[tuple[str, str]]) -> list[dict]:
    """Every `submit_record` result the model saw, in order, as the page reads them."""
    out = []
    for name, data in events:
        if name != "trace":
            continue
        line = json.loads(data)
        if line.get("type") != "step":
            continue
        calls = {c["id"]: c["name"] for c in line.get("tool_calls") or []}
        for result in line.get("tool_results") or []:
            if calls.get(result["call_id"]) == "submit_record":
                out.append(json.loads(result["output"]))
    return out


# --- the walk ------------------------------------------------------------------------------


def test_s10_replays_through_the_website_and_the_gate_reaches_the_record(web) -> None:
    status, started = call(web + "/api/runs",
                           {"repo": CASE, "arm": ARM, "mode": "replay", "seed": SEED})
    assert (status, started["status"]) == (201, "running"), started
    # the page prints paths relative to this; the run's own directory would be wrong
    assert Path(started["repo"]).is_absolute() and started["repo"].endswith(CASE), started
    run_id = started["run_id"]
    assert run_id.startswith(f"{ARM}-{CASE}-s{SEED}-")

    seen: list[dict] = []
    answered: list[tuple[int, dict]] = []

    def answer(name: str, data: str) -> None:
        """The page's own gate post: approve, and set the one recipient kind offered."""
        if name != "gate":
            return
        seen.append(json.loads(data))
        answered.append(call(f"{web}/api/runs/{run_id}/gate",
                             {"approved": True, "edits": {"stripe": "processor"}}))

    events = stream(f"{web}/api/runs/{run_id}/events", on_event=answer)

    # 1. the verifier struck the dead-helper claim, and said which line it read
    first, second = submit_feedback(events)
    assert first["accepted"] is False
    assert [claim["store"] for claim in first["rejected_claims"]] == ["uploads"]
    reason = first["rejected_claims"][0]["reason"]
    assert HELPER in reason and "no callers" in reason
    assert second == {"accepted": True}

    # 2. the gate blocked the child, and a person answered it
    assert len(seen) == 1 and seen[0]["risk"] == "high"
    assert seen[0]["summary"].startswith("RECORD READY FOR REVIEW")
    assert [party["store"] for party in seen[0]["third_party"]] == ["stripe"]
    assert answered == [(200, {"run_id": run_id, "approved": True,
                               "edits": {"stripe": "processor"}})]
    assert traced(events)[0] == "run_start" and traced(events)[-1] == "run_end"
    assert traced(events).count("step") == 2
    checkpoint = [json.loads(data) for name, data in events if name == "trace"
                  and json.loads(data)["type"] == "checkpoint"]
    assert len(checkpoint) == 1
    assert (checkpoint[0]["decision"], checkpoint[0]["by"]) == ("approved", "human")
    assert checkpoint[0]["risk"] == "high"
    assert checkpoint[0]["wait_s"] > 0, "a decision a person waited for took time"
    done = json.loads([data for name, data in events if name == "done"][-1])
    assert done == {"exit_code": 0, "stop_condition": "accepted", "status": "accepted"}

    # the child printed the gate as a terminal would, and the page relayed it
    printed = "\n".join(data for name, data in events if name == "stdout")
    assert "[gate] human checkpoint" in printed and "[render]" in printed

    # 3. the record, and the decision inside it
    status, record = call(f"{web}/api/runs/{run_id}/record")
    assert status == 200
    assert record["verification"]["accepted_on_attempt"] == 2
    assert record["provenance"]["gate"]["risk"] == "high"
    stores = {store["name"]: store for store in record["stores"]}
    assert set(stores) == {"users", "uploads", "stripe", "nightly_backup"}
    assert stores["uploads"]["erasure"]["verdict"] == "not_erased"
    assert stores["stripe"]["recipient_kind"] == "processor", \
        "the kind the person set at the gate belongs in the document they signed"

    status, content_type, html = raw(f"{web}/api/runs/{run_id}/record.html")
    assert (status, content_type.startswith("text/html")) == (200, True)
    assert "<table" in html and HELPER in html
    status, content_type, text = raw(f"{web}/api/runs/{run_id}/record.md")
    assert (status, content_type.startswith("text/markdown")) == (200, True)
    assert text.startswith("# ")
    directory = runs.get(run_id).dir
    assert html == (directory / "record.html").read_text(encoding="utf-8"), \
        "ADR 0007: the API hands back the renderer's file and renders nothing itself"
    assert json.loads((directory / "record.json").read_text(encoding="utf-8")) == record

    # 4. the citation under the dead helper opens the line
    found = CITED.search(reason)
    assert found is not None, reason
    status, payload = call(f"{web}/api/runs/{run_id}/source?path={found['file']}"
                           f"&line={found['line']}&context=3")
    assert status == 200
    line = int(found["line"])
    assert (payload["path"], payload["line"]) == (found["file"], line)
    assert HELPER in dict(payload["lines"])[line]
    assert dict(payload["lines"])[line].startswith("def "), \
        "the helper the record calls dead is a definition, and this is the line"

    # the runs list carries the finished run
    status, listing = call(web + "/api/runs")
    assert [(row["run_id"], row["status"], row["case"]) for row in listing["runs"]] \
        == [(run_id, "accepted", CASE)]


def record_link_urls(run_id: str) -> list[str]:
    """The two hrefs the record view offers, read out of `recordLinks` in the page.

    The record view draws `record.json` itself, so the renderer's own document would
    otherwise have no route off the page. The links are the route; a link that 404s
    is worse than no link, so they are built here exactly as the page builds them
    rather than copied, and then requested.
    """
    body = re.search(r"function recordLinks\(runId\) \{(.*?)\n\}", PAGE.read_text("utf-8"), re.S)
    assert body is not None, "recordLinks has changed shape"
    names = re.findall(r'\["(record\.[a-z]+)", "', body.group(1))
    href = re.search(r'href: "([^"]+)" \+ runId \+ "([^"]+)" \+ pair\[0\]', body.group(1))
    assert href is not None, "the href in recordLinks has changed shape"
    return [href.group(1) + run_id + href.group(2) + name for name in names]


def test_the_record_view_links_the_two_files_this_server_serves(web) -> None:
    status, started = call(web + "/api/runs",
                           {"repo": CASE, "arm": ARM, "mode": "replay", "seed": SEED})
    assert status == 201, started
    run_id = started["run_id"]

    def answer(name: str, data: str) -> None:
        if name == "gate":
            call(f"{web}/api/runs/{run_id}/gate", {"approved": True})

    stream(f"{web}/api/runs/{run_id}/events", on_event=answer)
    urls = record_link_urls(run_id)
    assert [url.rsplit("/", 1)[-1] for url in urls] == ["record.html", "record.md"]
    for url in urls:
        status, content_type, body = raw(web + url)
        assert status == 200, f"{url} answered {status}"
        assert body.strip(), url
    assert raw(web + urls[0])[1].startswith("text/html")
    assert raw(web + urls[1])[1].startswith("text/markdown")


def test_the_record_is_not_written_before_the_gate_is_answered(web) -> None:
    """The document exists because a person approved it, not because the loop ended."""
    status, started = call(web + "/api/runs",
                           {"repo": CASE, "arm": ARM, "mode": "replay", "seed": SEED})
    assert status == 201, started
    run_id = started["run_id"]
    before: list[tuple[int, dict]] = []

    def answer(name: str, data: str) -> None:
        if name != "gate":
            return
        before.append(call(f"{web}/api/runs/{run_id}/record"))
        call(f"{web}/api/runs/{run_id}/gate", {"approved": True})

    stream(f"{web}/api/runs/{run_id}/events", on_event=answer)
    assert before and before[0][0] == 404
    assert before[0][1] == {"error": "record.json has not been written yet"}
    assert call(f"{web}/api/runs/{run_id}/record")[0] == 200
    record = call(f"{web}/api/runs/{run_id}/record")[1]
    kinds = {store["name"]: store["recipient_kind"] for store in record["stores"]}
    assert kinds["stripe"] == "unknown", \
        "no kind was set, so the cell renders UNKNOWN and stays with the person"
