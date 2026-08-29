"""Record then replay one baseline run through the real `art30.llm.Cache`.

`tests/test_loop.py` and `tests/test_e2e_advanced.py` script the model by
replacing `llm.call`, which is exactly the function that owns the cache: those
tests never execute a line of record/replay. Here only the SDK is replaced --
the fake stands where `anthropic.Anthropic()` would, one step below
`llm.call` -- so `request_hash`, `Cache.write`, `Cache.read` and the
`ReplayMiss` path all run for real, on a copy of `evals/fixtures/synthetic/S02`
under `tmp_path` with `ART30_RECORD=1` and `ART30_CACHE_DIR` pointed at
`tmp_path` (ADR 0006 item 3: no key, no socket, nothing under results/ or
traces/).

What the two tests hold to: a replayed run reproduces the recorded
`record.json` byte for byte apart from the two provenance timestamps, with the
same per-step request hashes and the same cost and without touching the
client; and one changed byte in the fixture ends the replay at `replay_miss`
on the first step whose request that byte reaches -- step 2, because the
mutated file arrives in the request as a step-1 tool result.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest

from art30 import config as config_mod
from art30 import llm
from art30.config import Config, load
from art30.loop import CaseRef, run
from baseline.arm import BaselineArm
from evals.harness.trace_check import check_trace

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evals" / "fixtures" / "synthetic" / "S02"
CASE, ARM, SEED = "S02", "baseline", 1
# API-side token names: `usage_of` maps them, and a cache entry keeps both.
RAW_USAGE = {
    "input_tokens": 2314,
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 4180,
    "output_tokens": 188,
}
# The byte the second test moves: `phone` is on models.py line 17 and nothing
# in the submitted record cites it, so the mutation changes the tool result
# and no citation, which keeps the miss about hashing and not about rendering.
MUTATED_FROM, MUTATED_TO = b"    phone = ", b"    phonE = "


def _cite(path: str, line: int, symbol: str) -> dict:
    return {"file": path, "line": line, "symbol": symbol}


def _field(name: str, category: str, line: int) -> dict:
    return {"name": name, "category": category, "file": "models.py", "line": line,
            "note": None, "erasure": None}


def _human() -> dict:
    """Every human-owned key, present and empty (04-output-schema.md section 5)."""
    human: dict = {key: None for key in (
        "purposes", "legal_basis", "data_subject_categories_confirmed",
        "data_categories_outside_code", "special_categories",
        "retention_justification", "security_organisational")}
    for key in ("controller", "joint_controller", "representative", "dpo"):
        human[key] = {"name": None, "contact": None}
    human["transfers"] = {"occurs": None, "countries": None, "safeguards": None}
    return human


def record_for(repository: str) -> dict:
    """S02 as a record the baseline accepts and the renderer can cite.

    Soft delete only: `close_account` writes `deleted_at` and no code removes
    the row, so the store's verdict is `not_erased` (manifest S02).
    """
    return {
        "schema_version": "1",
        "repository": repository,
        "unscanned": [{"path": "README.md", "reason": "not_python"}],
        "data_subjects": [
            {"label": "account holders", "basis": "model_name", "file": "models.py", "line": 12}
        ],
        "entry_points": [
            {"name": "close_account", "kind": "route", "file": "api/account.py", "line": 12,
             "admin_only": False, "note": None}
        ],
        "stores": [
            {
                "name": "users",
                "kind": "relational",
                "declared_at": _cite("models.py", 12, "User"),
                "subject_link": {"file": "models.py", "line": 12},
                "fields": [_field("email", "contact", 15), _field("deleted_at", "technical", 19)],
                "erasure": {
                    "verdict": "not_erased",
                    "evidence": [],
                    "timer_days": None,
                    "note": "close_account sets deleted_at at api/account.py:15;"
                            " no code path removes the row",
                },
                "recipient_kind": None,
                "note": None,
            }
        ],
        "retention": [],
        "activities": [],
        "hints": {"observed_module_names": [], "observed_region_hints": [], "security_evidence": []},
        "human": _human(),
    }


def _message(blocks: list[dict]) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": [{"type": "thinking", "thinking": "reading the models"}] + blocks,
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": dict(RAW_USAGE),
    }


def _use(call_id: str, name: str, payload: dict) -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": payload}


def _read(call_id: str, path: str) -> dict:
    return _use(call_id, "read_file", {"path": path, "start_line": 1, "end_line": None})


def script_for(repository: str) -> list[dict]:
    """Two reads, then a valid submit: the shortest accepted baseline run."""
    return [
        _message([_read("t1", "models.py"), _read("t2", "api/account.py")]),
        _message([_use("t3", "submit_record", {"record": record_for(repository)})]),
    ]


# --- the fake SDK: one step below llm.call, so the cache runs for real -------


class _Final:
    """What `stream.get_final_message()` returns: a message with `to_dict`."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return copy.deepcopy(self._data)


class _Stream:
    def __init__(self, data: dict, request_id: str) -> None:
        self._data, self.request_id = data, request_id

    def __enter__(self) -> "_Stream":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def get_final_message(self) -> _Final:
        return _Final(self._data)


class _Messages:
    def __init__(self, client: "FakeClient") -> None:
        self._client = client

    def stream(self, **request: object) -> _Stream:
        self._client.requests.append(request)
        index = len(self._client.requests) - 1
        assert index < len(self._client.script), "the fake model ran out of scripted steps"
        return _Stream(self._client.script[index], f"req_{index + 1:02d}")


class FakeClient:
    """Counts every stream call: replay must leave the count where it was."""

    def __init__(self, script: list[dict]) -> None:
        self.script = script
        self.requests: list[dict] = []
        self.constructions = 0
        self.messages = _Messages(self)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    target = tmp_path / "repos" / CASE
    shutil.copytree(FIXTURE, target)
    return target


@pytest.fixture()
def client(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeClient]:
    fake = FakeClient(script_for(repo.name))

    def _fake_client(max_retries: int) -> FakeClient:
        assert max_retries == 4
        fake.constructions += 1
        return fake

    monkeypatch.setattr(llm, "_client", _fake_client)
    yield fake


def _config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **env: str) -> Config:
    """`load()` from the environment: ART30_CACHE_DIR is the relocation knob.

    Both runs write to the same two directories, so nothing that lands in the
    record can differ because the test asked for a different path. Every other
    input `load()` reads is cleared first: an `ART30_*` variable in the
    caller's shell or a `.env` in the cwd would otherwise be a live input to a
    test whose whole subject is determinism, and `load()` re-injects `.env`
    with `setdefault` after any `delenv`, so the file has to be stubbed too.
    """
    monkeypatch.setattr(config_mod, "read_dotenv", lambda *a, **k: {})
    for name in [key for key in os.environ if key.startswith("ART30_")]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ART30_CACHE_DIR", str(tmp_path / "cache"))
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    cfg = load()
    assert cfg.cache_dir == tmp_path / "cache"
    return replace(cfg, out_dir=tmp_path / "out", trace_dir=tmp_path / "traces")


def _run(repo: Path, cfg: Config):
    case = CaseRef(id=CASE, name=repo.name, root=repo, kind="synthetic")
    return run(case, BaselineArm(), SEED, cfg)


def _record_path(cfg: Config) -> Path:
    return Path(cfg.out_dir) / "record.json"


def _trace_path(cfg: Config) -> Path:
    return Path(cfg.trace_dir) / ARM / f"{CASE}-s{SEED}.jsonl"


def _hashes(path: Path) -> list[str]:
    assert check_trace(path) == []
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [line["request_hash"] for line in lines if line["type"] == "step"]


def _steps(path: Path) -> list[dict]:
    """Every step line with its wall-clock `ts` dropped: the rest must replay."""
    assert check_trace(path) == []
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [{k: v for k, v in ln.items() if k != "ts"} for ln in lines if ln["type"] == "step"]


def _lines_minus(path: Path, keys: tuple[str, ...]) -> list[str]:
    """The file's lines with the named provenance fields dropped.

    `record.json` is written one key per line, so this is a byte comparison
    with the two wall-clock stamps and the mode label taken out of it.
    """
    text = path.read_text(encoding="utf-8")
    return [line for line in text.splitlines() if not any(f'"{k}":' in line for k in keys)]


@pytest.fixture()
def recorded(tmp_path: Path, repo: Path, client: FakeClient, monkeypatch: pytest.MonkeyPatch):
    """The live arm of the round trip: one recorded run, asserted accepted."""
    cfg = _config(tmp_path, monkeypatch, ART30_RECORD="1")
    assert (cfg.mode, cfg.record) == ("live", True)
    result = _run(repo, cfg)
    assert result.stop_condition == "accepted", result.note
    assert (result.steps, result.tool_calls_total, result.submits) == (2, 3, 1)
    assert len(client.requests) == 2  # the SDK was reached once per step
    # The replay run writes to the same two paths; keep the recorded pair.
    archive = tmp_path / "recorded"
    (archive / ARM).mkdir(parents=True)
    shutil.copy2(_record_path(cfg), archive / "record.json")
    # Same layout, because check 13 reads the arm folder and the file name.
    shutil.copy2(_trace_path(cfg), archive / ARM / f"{CASE}-s{SEED}.jsonl")
    return cfg, result, archive


def test_replay_reproduces_the_recorded_run_without_touching_the_client(
    tmp_path: Path, repo: Path, client: FakeClient, monkeypatch: pytest.MonkeyPatch, recorded
) -> None:
    live_cfg, live, archive = recorded
    slot_dir = tmp_path / "cache" / CASE / ARM / f"s{SEED}"
    assert sorted(p.name for p in slot_dir.iterdir()) == ["01.json", "02.json"]
    entries = [json.loads((slot_dir / n).read_text(encoding="utf-8")) for n in ("01.json", "02.json")]
    live_hashes = _hashes(archive / ARM / f"{CASE}-s{SEED}.jsonl")
    assert [e["request_hash"] for e in entries] == ["sha256:" + h for h in live_hashes]

    cfg = _config(tmp_path, monkeypatch, ART30_MODE="replay")
    assert (cfg.mode, cfg.record) == ("replay", False)
    before = (len(client.requests), client.constructions)
    result = _run(repo, cfg)

    assert result.stop_condition == "accepted", result.note
    assert (len(client.requests), client.constructions) == before, "replay reached the SDK"
    assert (result.steps, result.tool_calls_total, result.submits) == (2, 3, 1)
    assert _hashes(_trace_path(cfg)) == live_hashes
    assert _steps(_trace_path(cfg)) == _steps(archive / ARM / f"{CASE}-s{SEED}.jsonl")
    assert result.cost_usd == live.cost_usd > 0
    assert result.run_id == live.run_id

    replayed, original = _record_path(cfg), archive / "record.json"
    moving = ("started_at", "finished_at", "mode")
    assert _lines_minus(replayed, moving) == _lines_minus(original, moving)
    assert json.loads(replayed.read_text(encoding="utf-8"))["provenance"]["mode"] == "replay"
    assert json.loads(original.read_text(encoding="utf-8"))["provenance"]["mode"] == "live"


def test_one_changed_fixture_byte_misses_at_the_step_it_reaches(
    tmp_path: Path, repo: Path, client: FakeClient, monkeypatch: pytest.MonkeyPatch, recorded
) -> None:
    _, _, archive = recorded
    models = repo / "models.py"
    before = models.read_bytes()
    assert before.count(MUTATED_FROM) == 1
    models.write_bytes(before.replace(MUTATED_FROM, MUTATED_TO))
    assert len(models.read_bytes()) == len(before)

    cfg = _config(tmp_path, monkeypatch, ART30_MODE="replay")
    before = (len(client.requests), client.constructions)
    result = _run(repo, cfg)

    assert result.stop_condition == "replay_miss"
    assert (len(client.requests), client.constructions) == before, "a miss fell back to the network"
    # Step 1's request is the first user turn alone, so it still hits; the
    # mutated file reaches the request as a step-1 tool result, which makes
    # step 2 the first affected step.
    assert result.steps == 1
    assert _hashes(_trace_path(cfg)) == _hashes(archive / ARM / f"{CASE}-s{SEED}.jsonl")[:1]
    note = result.note or ""
    assert f"{CASE}/{ARM}/s{SEED}/02" in note
    assert "expected" in note and "computed" in note
    # A missed replay renders nothing: what stands in out/ is still the
    # recorded run's file, byte for byte.
    assert _record_path(cfg).read_bytes() == (archive / "record.json").read_bytes()
