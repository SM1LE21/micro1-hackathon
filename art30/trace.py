"""JSONL trace writer: one JSON object per line, in contract field order.

Every line is flushed as it is written. A run that dies mid-flight still leaves
a readable trace up to its last completed step, which is what the failure
diagnosis reads.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

_DUMP = {"ensure_ascii": False, "separators": (",", ":")}


def now_ts() -> str:
    """UTC, milliseconds, `Z` suffix - the contract's `ts` field."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Trace:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8", newline="\n")

    def _write(self, line: dict[str, Any]) -> None:
        self._fh.write(json.dumps(line, **_DUMP) + "\n")  # type: ignore[arg-type]
        self._fh.flush()

    def run_start(
        self,
        *,
        run_id: str,
        arm: str,
        case: str,
        seed: int,
        model: str,
        effort: str,
        mode: str,
        prompt_sha: str,
        config: dict,
    ) -> None:
        self._write(
            {
                "type": "run_start",
                "run_id": run_id,
                "arm": arm,
                "case": case,
                "seed": seed,
                "model": model,
                "effort": effort,
                "mode": mode,
                "prompt_sha": prompt_sha,
                "config": config,
                "ts": now_ts(),
            }
        )

    def step(
        self,
        *,
        step: int,
        phase: Literal["agent", "verify"],
        request_id: str | None,
        request_hash: str,
        stop_reason: str | None,
        reasoning: str,
        text: str,
        tool_calls: list[dict],
        tool_results: list[dict],
        usage: dict[str, int],
        cost_usd: float,
        cost_cum_usd: float,
    ) -> None:
        self._write(
            {
                "type": "step",
                "step": step,
                "phase": phase,
                "ts": now_ts(),
                "request_id": request_id,
                "request_hash": request_hash,
                "stop_reason": stop_reason,
                "reasoning": reasoning,
                "text": text,
                "tool_calls": tool_calls,
                "tool_results": tool_results,
                "usage": usage,
                "cost_usd": cost_usd,
                "cost_cum_usd": cost_cum_usd,
            }
        )

    def checkpoint(
        self,
        *,
        risk: str,
        summary: str,
        decision: str,
        by: str,
        wait_s: float,
        human_completions: dict | None,
    ) -> None:
        self._write(
            {
                "type": "checkpoint",
                "tool": "request_approval",
                "caller": "harness",
                "risk": risk,
                "summary": summary,
                "decision": decision,
                "by": by,
                "wait_s": wait_s,
                "human_completions": human_completions,
                "ts": now_ts(),
            }
        )

    def run_end(
        self,
        *,
        stop_condition: str,
        steps: int,
        tool_calls_total: int,
        submits: int,
        verify_rounds: int,
        wall_s: float,
        cost_usd: float,
        record_path: str | None,
        note: str | None,
    ) -> None:
        self._write(
            {
                "type": "run_end",
                "stop_condition": stop_condition,
                "steps": steps,
                "tool_calls_total": tool_calls_total,
                "submits": submits,
                "verify_rounds": verify_rounds,
                "wall_s": wall_s,
                "cost_usd": cost_usd,
                "record_path": record_path,
                "note": note,
            }
        )

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()
