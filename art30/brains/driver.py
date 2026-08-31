"""`run_brain`: spawn a local CLI, convert its stream into the trace, finish the run.

Brain-agnostic. The module it is handed (`art30/brains/claude.py` or `codex.py`)
builds the command line and the environment and names the reader for its own event
stream; everything here is the part that must be the same for every brain, because
it is the part the measurement rests on: the trace contract, the two budgets, the
human gate, `loop._finalise` and the renderer, all of them the same code the API
brain runs (ADR 0008 item 1).

A brain module is read through five optional names, so adding one costs nothing
here: `STEPPER` (its stream reader, default `convert.Stepper`), `LABEL`,
`USAGE_NOTE`, `priced` and `run_note`.

What the CLI cannot be trusted with is enforced from outside it. Tool calls and
turns are counted off the event stream by the brain's stepper and the run is
stopped when either budget runs out -- neither `claude --help` on 2.1.251 nor
`codex exec --help` on 0.148.0 has a `--max-turns`, and the first ignores an
unknown flag rather than refusing it, so a ceiling passed on the command line
would be a ceiling nobody applied.

The wall-clock ceiling is `ART30_BRAIN_TIMEOUT` seconds, 30 minutes by default: a
run switch like the others `art30/config.py` documents, not a setting, because it
bounds the subprocess rather than the request.

Two more things are checked rather than assumed. The CLI's own `init` line has to
report that it loaded no memory, or the run stops before it is scored (ADR 0008
item 2, and `convert.Stepper`). And a model with no entry in the price table
leaves `cost_source: "unpriced"` on the result and in `provenance` instead of a
dollar figure that would read as free (ADR 0008 item 3).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from art30 import llm, loop as loop_mod
from art30.arm import Arm, Feedback, RunCtx
from art30.brains import claude as claude_brain
from art30.brains import codex as codex_brain
from art30.brains import convert, pricing
from art30.brains.spool import Spool
from art30.config import Config
from art30.loop import CaseRef, RunResult
from art30.render import RenderError, apply_edits, render_all, stamp, write_draft
from art30.tools import ToolCtx
from art30.trace import Trace

BRAINS = {"claude": claude_brain, "codex": codex_brain}
COST_SOURCE = "cli_estimate"
UNPRICED = "unpriced"
# The two places a local-brain step figure is not reproducible from the contract's
# own arithmetic. Said in the trace rather than only in this file, because a reader
# with the trace and the contract would otherwise find a discrepancy and no reason.
USAGE_NOTE = (
    "per-step output tokens are the CLI's placeholders; the run's remainder is"
    " settled on the last step; one-hour cache writes price at 2x input, not the"
    " contract's 1.25x"
)
TIMEOUT_VAR = "ART30_BRAIN_TIMEOUT"
DEFAULT_TIMEOUT_S = 1800.0
GRACE_S = 5.0
STDERR_TAIL = 40
MCP_NAME = "mcp.json"
PROMPT_NAME = "system-prompt.md"
STDOUT_NAME = "cli-stdout.jsonl"
STDERR_NAME = "cli-stderr.log"
SPOOL_NAME = "brain"
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class LocalRunResult(RunResult):
    """`RunResult` plus the two things only a local brain has to say about money.

    `cost_source` is `"unpriced"` when no price exists for the model that answered,
    and `art30/cli.py` prints `n/a` rather than `$0.00` for it: ADR 0008 item 3 says
    an unpriced run reports tokens and "n/a", never a dollar figure that reads as
    free. Every other field is the one `loop.run` returns, so the CLI, the harness
    and the website consume both brains' results the same way.
    """

    cost_source: str = COST_SOURCE
    tokens: int = 0


def run_brain(cfg: Config, case: CaseRef, arm: Arm, seed: int,
              report: Callable[[str, dict], None] | None = None) -> RunResult:
    """One case, one arm, one seed, on a local CLI. Same `RunResult` as `loop.run`."""
    brain = BRAINS.get(cfg.brain)
    if brain is None:   # pragma: no cover - the CLI offers the same names this dict has
        raise ValueError(f"no brain module for {cfg.brain!r}")
    return Driver(cfg, case, arm, seed, brain, report).run()


class Driver:
    def __init__(self, cfg: Config, case: CaseRef, arm: Arm, seed: int, brain,
                 report: Callable[[str, dict], None] | None) -> None:
        self.cfg, self.case, self.arm, self.seed, self.brain = cfg, case, arm, seed, brain
        self.report = report
        # Resolved, not as given: every path that reaches the CLI child or the MCP
        # server (mcp.json's own path, the spool inside it) is interpreted against
        # THEIR cwd - the scanned repository - not ours. A relative --out from the
        # harness sent claude looking for mcp.json inside the fixture (2026-08-31).
        self.out = Path(cfg.out_dir).resolve()
        self.spool = Spool(self.out / SPOOL_NAME).reset()
        self.trace = Trace(loop_mod.trace_path(cfg, arm, case, seed))
        self.ctx = RunCtx(case=case.id, arm=arm.name, seed=seed, root=case.root,
                          tools=ToolCtx(root=case.root), trace=self.trace, cfg=cfg)
        # Each brain reads its own stream; `STEPPER` is how a brain module says so.
        # The model is seeded from the configuration because one CLI names the model
        # on its init line and the other never names it at all -- a stream that does
        # report one overwrites this on the first event that carries it.
        self.stepper = getattr(brain, "STEPPER", convert.Stepper)(
            cfg.tool_budget, cfg.max_submits, cfg.max_turns)
        self.stepper.model = self.stepper.model or cfg.brain_model
        self.written = 0        # step lines on disk
        self.said = 0           # submissions already printed
        self.cost_cum = 0.0
        self.spent = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
        self.spent_1h = 0
        self.tail: list[str] = []
        self.unpriced = False   # set by `_write` the first time a step has no price
        self.ended = False      # `run_end` is written once, whoever raised
        self.started, self.clock = stamp(), time.monotonic()

    # --- the run --------------------------------------------------------------
    def run(self) -> RunResult:
        system = llm.system_prompt()
        first = self.brain.first_message(loop_mod.FIRST_TURN.format(
            repo_name=self.case.name, tool_call_budget=self.cfg.tool_budget,
            submit_budget=self.cfg.max_submits))
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / PROMPT_NAME).write_text(system + "\n\n---\n\n" + first + "\n", encoding="utf-8")
        mcp = self._write_mcp_config()
        self.trace.run_start(
            run_id=loop_mod.run_id(self.arm.name, self.case.id, self.seed), arm=self.arm.name,
            case=self.case.id, seed=self.seed, model=self.cfg.model, effort=self.cfg.effort,
            mode=self.cfg.mode, prompt_sha=llm.prompt_sha(), config=self._trace_config(),
        )
        self._say("phase", {"name": "agent"})
        try:
            code = self._spawn(
                self.brain.argv(system, first, mcp, self.cfg.brain_model, self.cfg.effort),
                self.brain.env())
            # The gate, `_finalise` and the renderer run in `_outcome`, and any of the
            # three can raise. `loop.run` guards the same span for the same reason: a
            # trace with no `run_end` is a check 2 violation and an undiagnosable row.
            return self._outcome(code)
        except OSError as exc:
            return self._end("api_error", note=f"{self.brain.BINARY} did not start: {exc}")
        except Exception as exc:   # nothing leaves this function without a run_end line
            return self._end("api_error", note=f"{type(exc).__name__}: {exc}")

    def _write_mcp_config(self) -> Path:
        path = self.out / MCP_NAME
        payload = {"mcpServers": {"art30": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "art30.brains.mcp_server", "--arm", self.arm.name,
                     "--repo", str(self.case.root), "--spool", str(self.spool.root),
                     "--tool-budget", str(self.cfg.tool_budget),
                     "--submit-budget", str(self.cfg.max_submits),
                     "--case", self.case.id, "--seed", str(self.seed)],
            # The CLI starts the server from the repository under scan, which is not
            # this checkout: the interpreter finds `art30` by path, not by cwd.
            "env": {"PYTHONPATH": str(REPO_ROOT)},
        }}}
        path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        return path

    def _trace_config(self) -> dict:
        """`run_start.config`: the contract's four keys plus what a local brain adds.

        `brain`, `brain_model` and `cost_source` belong on `run_start` (ADR 0008 item 1)
        and `art30/trace.py` takes no argument they could be their own field of, so they
        ride in the object that line already carries. `model` stays the configured one,
        which is what check 13 reads; `brain_model` is what actually answered.
        """
        # `cost_source` is the best answer available before the CLI names its model:
        # a configured model with no price is unpriced from the first line. A model
        # the CLI chose can only be judged once it has answered, and `provenance`
        # carries the verdict there.
        priced = getattr(self.brain, "priced", pricing.priced)(self.cfg.brain_model)
        return {**self.cfg.trace_config(), "brain": self.cfg.brain,
                "brain_model": self.cfg.brain_model,
                "cost_source": COST_SOURCE if priced else UNPRICED,
                "max_turns": self.cfg.max_turns,
                "usage_note": getattr(self.brain, "USAGE_NOTE", USAGE_NOTE)}

    # --- the subprocess -------------------------------------------------------
    def _spawn(self, argv: list[str], env: dict[str, str]) -> int:
        errors: deque[str] = deque(maxlen=STDERR_TAIL)
        raw = (self.out / STDOUT_NAME).open("w", encoding="utf-8", newline="\n")
        proc = subprocess.Popen(
            argv, cwd=str(self.case.root), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        drain = threading.Thread(target=self._drain, args=(proc, errors), daemon=True)
        drain.start()
        alarm = threading.Timer(_timeout(), self._timed_out, args=(proc,))
        alarm.start()
        try:
            for line in proc.stdout:   # type: ignore[union-attr]
                raw.write(line if line.endswith("\n") else line + "\n")
                self._event(convert.parse(line))
                if self.stepper.stop is not None:
                    break
        finally:
            alarm.cancel()
            self._terminate(proc)
            raw.close()
            drain.join(timeout=GRACE_S)
        for step in self.stepper.close():
            self._write(step, final=True)
        (self.out / STDERR_NAME).write_text("".join(errors), encoding="utf-8")
        self.tail = [line.strip() for line in "".join(errors).strip().splitlines()[-3:]]
        return int(proc.returncode or 0)

    def _timed_out(self, proc: subprocess.Popen) -> None:
        self.stepper.stop = ("timeout", f"no result within {_timeout():g} s")
        self._terminate(proc)

    def _drain(self, proc: subprocess.Popen, errors: deque) -> None:
        for line in proc.stderr:   # type: ignore[union-attr]
            errors.append(line)

    def _terminate(self, proc: subprocess.Popen) -> None:
        """SIGINT first: the CLI writes its `result` line on an interrupt, not on a kill."""
        if proc.poll() is not None:
            return
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                proc.send_signal(sig)
                proc.wait(timeout=GRACE_S)
                return
            except subprocess.TimeoutExpired:
                continue
            except OSError:
                return
        proc.kill()
        proc.wait(timeout=GRACE_S)

    # --- the stream -----------------------------------------------------------
    def _event(self, event: dict | None) -> None:
        for step in self.stepper.feed(event):
            self._write(step)
        if convert.is_tool_result(event):
            self._after_submit()

    def _after_submit(self) -> None:
        """What the spool says now: an acceptance ends the run, and so does a used-up budget."""
        entries = self.spool.entries()
        for entry in entries[self.said:]:
            self._say_verify(entry)
        self.said = len(entries)
        if self.spool.accepted_record() is not None:
            # Not a stop: the CLI is left to finish its own turn, which is the only
            # way the `result` line -- and with it `cli_total_cost_usd` -- ever arrives.
            # The two budgets still bound whatever it does next.
            return
        if self.spool.is_exhausted() and self.stepper.stop is None:
            self.stepper.stop = ("max_submits", _submits_note(self.spool, self.cfg.max_submits))

    def _write(self, step: dict, final: bool = False) -> None:
        self.written += 1
        usage, cache_1h = self._usage(step, final)
        cost = pricing.estimate(usage, self.stepper.model, cache_1h)
        if cost is None:
            # No price for this model. The trace still needs a number in `cost_usd`,
            # so it is zero -- and `cost_source` says the zero means "unknown", which
            # is the difference ADR 0008 item 3 asks for.
            self.unpriced, cost = True, 0.0
        self.cost_cum = round(self.cost_cum + cost, 6)
        submitted = any(c["name"] == convert.SUBMIT for c in step["tool_calls"])
        self.trace.step(
            step=self.written, phase="verify" if submitted else "agent", request_id=None,
            request_hash=None, stop_reason=step["stop_reason"], reasoning=step["reasoning"],
            text=step["text"], tool_calls=step["tool_calls"], tool_results=step["tool_results"],
            usage=usage, cost_usd=round(cost, 6), cost_cum_usd=self.cost_cum,
        )
        self._progress(step, cost)

    def _usage(self, step: dict, final: bool) -> tuple[dict[str, int], int]:
        """The step's token counts, with the run's totals settled on the last one.

        The CLI reports every input and cache count per message and its output count
        only for the run as a whole: the per-message `output_tokens` is a placeholder
        (1, 3, 17 on the D02 run, against 9,553 for the run). Rather than leave the
        trace understating the run by half, the last step carries whatever the final
        `result` line says was spent and no earlier step declared. Every number in the
        trace is then a count the CLI reported, and they sum to its own totals.
        """
        usage = dict(step["usage"])
        cache_1h = int(step.get("cache_1h") or 0)
        totals = self.stepper.totals if final else {}
        if totals:
            for key, spent in self.spent.items():
                short = int((totals.get("usage") or {}).get(key, 0)) - spent - usage.get(key, 0)
                usage[key] = usage.get(key, 0) + max(0, short)
            cache_1h += max(0, int(totals.get("cache_1h") or 0) - self.spent_1h - cache_1h)
        for key in self.spent:
            self.spent[key] += usage.get(key, 0)
        self.spent_1h += cache_1h
        return usage, cache_1h

    # --- the end --------------------------------------------------------------
    def _outcome(self, code: int) -> RunResult:
        self.ctx.tool_calls = self.stepper.tool_calls
        # The attempts the arm answered, which is what `verification` counts. The
        # trace's `submits` counts `submit_record` calls, and a call made after the
        # record was accepted is one of those without being an attempt.
        self.ctx.submits = len(self.spool.entries()) or self.stepper.submits
        self.ctx.verify_rounds = len(self.spool.rejections())
        self.ctx.cost_cum_usd = self.cost_cum
        self.ctx.accepted = self.spool.accepted_record()
        stop = self.stepper.stop
        if self.ctx.accepted is not None:
            return self._finish()
        if stop is not None and stop[0] != "accepted":
            return self._end(stop[0], note=stop[1])
        if code != 0:
            tail = " / ".join(line for line in self.tail if line)
            return self._end("api_error", note=f"{self.brain.BINARY} exited {code}: {tail}"[:400])
        if self.ctx.submits >= self.cfg.max_submits:
            return self._end("max_submits", note=_submits_note(self.spool, self.cfg.max_submits))
        note = (f"{self.ctx.submits} submits rejected; the CLI ended its turn"
                if self.ctx.submits else "the CLI ended its turn with no submit_record call")
        return self._end("no_submission", note=note)

    def _finish(self) -> RunResult:
        record = self.ctx.accepted or {}
        self.ctx.final_feedback = self.spool.final_feedback()
        self.ctx.rejections = self.spool.rejections()
        decision = self.arm.gate(record, self.ctx)
        gate = None
        if decision is not None:
            verdict = "approved" if decision.approved else "rejected"
            self.trace.checkpoint(risk=decision.risk, summary=decision.summary, decision=verdict,
                                  by=decision.by, wait_s=decision.wait_s,
                                  human_completions=decision.human_completions())
            gate = {"risk": decision.risk, "decision": verdict, "by": decision.by,
                    "wait_s": round(decision.wait_s, 3), "at": stamp()}
            if not decision.approved:
                write_draft(record, self.out)
                reason = (decision.summary.splitlines() or [""])[0]
                return self._end("gate_rejected", gate=gate,
                                 note=f"gate rejected at risk={decision.risk}: {reason}")
            record = apply_edits(record, decision.edits)
        record = loop_mod._finalise(record, self.ctx, self.case, self.cfg, self.arm,
                                    {"started": self.started}, gate)
        record["provenance"].update({
            "brain": self.cfg.brain, "brain_model": self.stepper.model,
            "brain_label": getattr(self.brain, "LABEL", self.cfg.brain),
            "cost_source": self._cost_source(),
            "cli_total_cost_usd": self.stepper.totals.get("total_cost_usd"),
        })
        try:
            paths = render_all(record, self.out, self.case.root)
        except RenderError as exc:
            return self._end("render_failed", gate=gate, record_path=exc.record_path, note=str(exc))
        self._say("render", {"paths": paths})
        return self._end("accepted", gate=gate, record_path=paths.json)

    def _cost_source(self) -> str:
        """`unpriced` unless a step was actually priced, and unless `run_start` already
        said otherwise. `self.unpriced` is only set by `_write`, so a run that ends
        before any step line -- a CLI that was not logged in, a turn that failed at the
        first event -- would otherwise call itself `cli_estimate` and print `$0.00 est`
        while its own `run_start.config.cost_source` said `unpriced`. The two halves of
        one run must agree, so the end asks the same hook the start asked."""
        priced = getattr(self.brain, "priced", pricing.priced)(self.stepper.model)
        return UNPRICED if self.unpriced or not priced else COST_SOURCE

    def _end(self, condition: str, *, record_path: str | None = None, note: str | None = None,
             gate: dict | None = None) -> RunResult:
        counters = dict(
            stop_condition=condition, steps=self.written,
            tool_calls_total=self.stepper.tool_calls, submits=self.stepper.submits,
            verify_rounds=len(self.spool.rejections()),
            wall_s=round(time.monotonic() - self.clock, 1), cost_usd=self.cost_cum,
            record_path=record_path, note=self._note(note),
        )
        if not self.ended:   # a raise out of `_outcome` must not write a second one
            self.ended = True
            self.trace.run_end(**counters)
            self.trace.close()
        # `spent` only counts tokens that reached a step line. A run that ended before
        # any step was written still has the CLI's own totals, and `run_end.note` is
        # already printing them: the terminal must not say `tokens 0` beside a note
        # that says 45,000.
        spent = sum(self.spent.values())
        totals = sum((self.stepper.totals.get("usage") or {}).values()) if (
            self.stepper.totals) else 0
        return LocalRunResult(run_id=loop_mod.run_id(self.arm.name, self.case.id, self.seed),
                              gate=gate, cost_source=self._cost_source(),
                              tokens=spent or totals, **counters)

    def _note(self, note: str | None) -> str | None:
        """`run_end.note`, plus whatever the brain has to add to every run of its own.

        The codex stream reports a reasoning-token count that the contract's four
        usage keys have no home for, and a codex run is usually unpriced, so its
        totals are said here in words. A brain with nothing to add contributes
        nothing and the note is the one the stop condition wrote.
        """
        extra = getattr(self.brain, "run_note", None)
        tail = extra(self.stepper, note) if callable(extra) else None
        return " · ".join(part for part in (note, tail) if part) or None

    # --- the terminal ---------------------------------------------------------
    def _say(self, kind: str, data: dict) -> None:
        if self.report is not None:
            self.report(kind, data)

    def _say_verify(self, entry: dict) -> None:
        """The `[verify]` block of 07-ui.md section 5, rebuilt from the spooled feedback."""
        payload = dict(entry.get("feedback") or {})
        accepted = bool(payload.pop("accepted", False))
        attempt = int(entry.get("attempt") or 0)
        feedback = Feedback(accepted=accepted, attempt=attempt,
                            attempts_left=max(0, self.cfg.max_submits - attempt), **payload)
        self._say("phase", {"name": "verify"})
        self._say("verify", {"arm": self.arm, "feedback": feedback})

    def _progress(self, step: dict, cost: float) -> None:
        if self.report is None:
            return
        names = ", ".join(c["name"] for c in step["tool_calls"]) or "no tool call"
        print(f"{self.stepper.tool_calls:>4}/{self.cfg.tool_budget}  step {self.written:<4}"
              f"{names[:44]:<46}${cost:.3f}  Σ${self.cost_cum:.3f}", flush=True)


def _timeout() -> float:
    raw = os.environ.get(TIMEOUT_VAR)
    try:
        seconds = float(raw) if raw else DEFAULT_TIMEOUT_S
    except ValueError:
        seconds = DEFAULT_TIMEOUT_S
    return seconds if seconds > 0 else DEFAULT_TIMEOUT_S


def _submits_note(spool: Spool, budget: int) -> str:
    rejections = spool.rejections()
    last = rejections[-1] if rejections else {}
    claims = last.get("rejected_claims") or []
    reason = (claims[0].get("reason") if claims else None) or (
        (last.get("schema_errors") or ["no reason recorded"])[0])
    return f"{budget} submits rejected; last rejection: {reason}"
