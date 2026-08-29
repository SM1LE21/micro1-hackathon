"""Request hashing, the price table, the replay cache and the prompt splice.

Nothing here calls the API. The one test that would is skipped with its reason,
never faked: a green test that did not run is worse than a red one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from art30.config import Config, ConfigError, load, read_dotenv
from art30.llm import (
    Cache,
    ReplayMiss,
    Slot,
    build_request,
    call,
    canonical,
    cost_of,
    prices,
    prompt_sha,
    request_hash,
    system_blocks,
    system_prompt,
)
from art30.tools import SPEC

# The spliced instruction text, frozen: an accidental edit to either prompt
# file invalidates every cache entry, and this is where it fails fast.
PROMPT_SHA = "43c86cec9e8caa6d78e5457d4fa4b7ae1bb9dc288f302642e423b05beb8cd1c6"

FIRST_TURN = (
    "Scan target: S10\n\n"
    "Budget for this run: {tool_budget} tool calls and {submit_budget} "
    "submit_record attempts. Exceeding either ends the run with no record."
)


def _messages(tool_budget: int = 60, submit_budget: int = 5) -> list[dict]:
    text = FIRST_TURN.format(tool_budget=tool_budget, submit_budget=submit_budget)
    return [{"role": "user", "content": [{"type": "text", "text": text}]}]


def _request(cfg: Config | None = None, **budgets: int) -> dict:
    return build_request(cfg or Config(), system_blocks(), SPEC, _messages(**budgets))


def test_request_hash_is_stable_across_two_builds() -> None:
    assert request_hash(_request()) == request_hash(_request())


def test_request_hash_moves_with_max_tokens() -> None:
    assert request_hash(_request()) != request_hash(_request(Config(max_tokens=16_000)))


def test_request_hash_moves_with_either_budget() -> None:
    base = request_hash(_request())
    assert base != request_hash(_request(tool_budget=120))
    assert base != request_hash(_request(submit_budget=3))


def test_request_hash_moves_with_model_and_effort() -> None:
    base = request_hash(_request())
    assert base != request_hash(_request(Config(model="claude-sonnet-5")))
    assert base != request_hash(_request(Config(effort="medium")))


def test_request_carries_the_pinned_api_configuration() -> None:
    request = _request()
    assert request["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert request["output_config"] == {"effort": "high"}
    assert request["max_tokens"] == 32_000
    assert request["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert [tool["name"] for tool in request["tools"]] == [tool["name"] for tool in SPEC]
    assert "temperature" not in request and "tool_choice" not in request


def test_build_request_does_not_mutate_the_system_blocks() -> None:
    blocks = system_blocks()
    build_request(Config(), blocks, SPEC, _messages())
    assert "cache_control" not in blocks[0]


def test_build_request_refuses_a_float() -> None:
    messages = [{"role": "user", "content": [{"type": "text", "text": "x", "weight": 0.5}]}]
    with pytest.raises(ConfigError):
        build_request(Config(), system_blocks(), SPEC, messages)


def test_canonical_is_sorted_and_compact() -> None:
    assert canonical({"b": 1, "a": {"d": 2, "c": 3}}) == '{"a":{"c":3,"d":2},"b":1}'


def test_prices_are_keyed_by_model_and_never_default() -> None:
    assert prices("claude-opus-5") == {
        "input": 5.0,
        "cache_write": 6.25,
        "cache_read": 0.5,
        "output": 25.0,
    }
    with pytest.raises(ConfigError):
        prices("claude-opus-4-1")


def test_cost_of_at_opus_5_prices() -> None:
    usage = {"input": 1_000_000, "cache_write": 1_000_000, "cache_read": 1_000_000, "output": 1_000_000}
    assert cost_of(usage, "claude-opus-5") == pytest.approx(5.0 + 6.25 + 0.5 + 25.0)
    step = {"input": 2314, "cache_read": 0, "cache_write": 4180, "output": 188}
    expected = (2314 * 5.0 + 4180 * 6.25 + 188 * 25.0) / 1_000_000
    assert cost_of(step, "claude-opus-5") == pytest.approx(expected)


def _store(cache: Cache, slot: Slot, request: dict, content: list[dict]) -> None:
    cache.write(
        slot,
        request_hash(request),
        model="claude-opus-5",
        effort="high",
        request_id="req_test",
        message={"content": content, "stop_reason": "tool_use", "stop_details": None},
        usage={"input": 10, "cache_read": 20, "cache_write": 30, "output": 40},
    )


def test_cache_round_trip_in_replay_mode(tmp_path: Path) -> None:
    cfg = Config(mode="replay", cache_dir=tmp_path / "cache")
    slot = Slot(case="S10", arm="advanced", seed=1, step=1)
    request = _request(cfg)
    content = [{"type": "text", "text": "reading the models"}]
    _store(Cache(cfg.cache_dir), slot, request, content)

    response = call(request, cfg=cfg, slot=slot)
    assert response.content == content
    assert response.stop_reason == "tool_use"
    assert response.request_id == "req_test"
    assert response.usage == {"input": 10, "cache_read": 20, "cache_write": 30, "output": 40}
    assert cost_of(response.usage, cfg.model) > 0


def test_cache_layout_is_case_arm_seed_step(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    path = cache.path(Slot(case="S10", arm="baseline", seed=3, step=7))
    assert path.relative_to(tmp_path / "cache").as_posix() == "S10/baseline/s3/07.json"


def test_replay_miss_names_the_slot_and_both_hashes(tmp_path: Path) -> None:
    cfg = Config(mode="replay", cache_dir=tmp_path / "cache")
    slot = Slot(case="S10", arm="advanced", seed=2, step=4)
    request = _request(cfg)
    _store(Cache(cfg.cache_dir), slot, request, [])

    with pytest.raises(ReplayMiss) as miss:
        call(_request(Config(mode="replay", cache_dir=cfg.cache_dir, max_tokens=16_000)), cfg=cfg, slot=slot)
    message = str(miss.value)
    assert "S10/advanced/s2/04" in message
    assert request_hash(request) in message
    # 01-architecture.md section 4.5 wants the four request-shaping values by
    # value, not two bare hashes.
    assert "model=claude-opus-5 effort=high tool_budget=60 submit_budget=5" in message


def test_replay_miss_names_the_recorded_model_and_effort(tmp_path: Path) -> None:
    cfg = Config(mode="replay", cache_dir=tmp_path / "cache", model="claude-sonnet-5")
    slot = Slot(case="S10", arm="advanced", seed=2, step=4)
    _store(Cache(cfg.cache_dir), slot, _request(), [])  # recorded at opus 5, effort high

    with pytest.raises(ReplayMiss) as miss:
        call(_request(cfg), cfg=cfg, slot=slot)
    assert "recorded with model=claude-opus-5" in str(miss.value)


def test_replay_of_a_missing_entry_is_a_miss_not_a_crash(tmp_path: Path) -> None:
    cfg = Config(mode="replay", cache_dir=tmp_path / "cache")
    with pytest.raises(ReplayMiss):
        call(_request(cfg), cfg=cfg, slot=Slot(case="S01", arm="baseline", seed=1, step=1))


def test_replay_constructs_no_client(tmp_path: Path) -> None:
    from art30 import llm

    llm._client.cache_clear()
    cfg = Config(mode="replay", cache_dir=tmp_path / "cache")
    slot = Slot(case="S10", arm="advanced", seed=1, step=1)
    request = _request(cfg)
    _store(Cache(cfg.cache_dir), slot, request, [])
    call(request, cfg=cfg, slot=slot)
    assert llm._client.cache_info().currsize == 0


def test_recording_clears_the_slot_before_the_first_write(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    slot = Slot(case="S10", arm="advanced", seed=1, step=1)
    stale = cache.slot_dir(slot) / "09.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}", encoding="utf-8")

    _store(cache, slot, _request(), [])
    assert not stale.exists()
    assert cache.path(slot).is_file()

    # The clear happens once per run, not once per step.
    _store(cache, Slot(case="S10", arm="advanced", seed=1, step=2), _request(), [])
    assert cache.path(slot).is_file()


def test_cache_entry_carries_the_documented_keys(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    slot = Slot(case="S10", arm="advanced", seed=1, step=1)
    _store(cache, slot, _request(), [])
    entry = json.loads(cache.path(slot).read_text(encoding="utf-8"))
    assert set(entry) == {
        "request_hash",
        "model",
        "effort",
        "recorded_at",
        "request_id",
        "usage",
        "response",
    }
    assert entry["request_hash"].startswith("sha256:")


def test_prompt_splice_and_sha() -> None:
    text = system_prompt()
    assert "<!-- include: taxonomy.md -->" not in text
    assert "# Personal-data taxonomy" in text
    assert text.index("# Stores") > text.index("# Personal-data taxonomy")
    assert prompt_sha() == PROMPT_SHA
    assert len(text.encode("utf-8")) == 16_341


def test_config_env_overrides_and_trace_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ART30_TOOL_BUDGET", "120")
    monkeypatch.setenv("ART30_MODE", "replay")
    cfg = load()
    assert cfg.tool_budget == 120 and cfg.mode == "replay"
    assert cfg.trace_config() == {
        "max_tokens": 32_000,
        "tool_budget": 120,
        "submit_budget": 5,
        "overridden": ["ART30_TOOL_BUDGET"],
    }
    # An explicit override wins over the case kind.
    assert cfg.for_case_kind("synthetic").tool_budget == 120
    assert Config().for_case_kind("real").tool_budget == 120


def test_dotenv_never_overrides_a_set_variable(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nART30_EFFORT=low\nEMPTY\n", encoding="utf-8")
    assert read_dotenv(env_file) == {"ART30_EFFORT": "low"}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ART30_EFFORT", "high")
    assert load().effort == "high"


def test_live_call_belongs_to_the_calibration_run() -> None:
    # Unconditional: a `skipif` on the key turns green into red the moment the
    # author puts ANTHROPIC_API_KEY in .env for the first recording, which is
    # the machine REPRODUCE.md asks for. The offline property this file cares
    # about is proved by test_replay_constructs_no_client above.
    pytest.skip("live calls belong to the calibration run, not to the unit suite")
