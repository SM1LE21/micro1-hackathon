"""The step loop: message construction, the two budget invariants, the stop
conditions, the gate call and the render call.

No arm-specific code and no branch on `arm.name`: the two arms are two
implementations of `art30.arm.Arm`, and every exit from `run` writes a
`run_end` line, including an unhandled exception anywhere below it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Literal

from art30 import llm, tools
from art30.arm import Arm, Feedback, RunCtx
from art30.config import Config
from art30.llm import LlmError, ReplayMiss, Slot
from art30.render import (
    RenderError, apply_edits, relative, render_all, stamp, tree_sha, write_draft,
)
from art30.tools import ToolCtx
from art30.trace import Trace

FIRST_TURN = """Scan target: {repo_name}

Every path you cite is relative to the repository root, and every line number is 1-based. `repository` in the record is the name the code gives itself, not this label.

Draft the Art. 30 record and the erasure table for this repository, then submit it with submit_record.

Budget for this run: {tool_call_budget} tool calls and {submit_budget} submit_record attempts. Exceeding either ends the run with no record.

Nobody is watching this run and no one can answer a question before it ends. Before you end a turn, read your last paragraph: if it is a plan, a question or a promise about work you have not done, do that work now with a tool call instead."""

NUDGE = (
    "You ended your turn without calling a tool. If your last message was a plan, carry it out"
    " now; if the record is ready, call submit_record."
)
SECOND_SUBMIT = '{"accepted": false, "reason": "one submit_record per turn"}'
ARM_PREFIX = {"advanced": "adv", "baseline": "base"}
REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class CaseRef:
    """The seam between the harness, the CLI and the loop.

    Only `name` may be formatted into the first user message; `root` reaches
    the tools through `ToolCtx` and nothing else.
    """

    id: str
    name: str
    root: Path
    kind: Literal["synthetic", "real"] = "synthetic"
    split: Literal["dev", "test"] = "dev"


@dataclass(frozen=True)
class RunResult:
    run_id: str
    stop_condition: str
    steps: int
    tool_calls_total: int
    submits: int
    verify_rounds: int
    wall_s: float
    cost_usd: float
    record_path: str | None
    note: str | None = None
    # The gate as it happened, or None where no gate ran: the tail line reads it
    # rather than re-deriving one from the arm name (07-ui.md section 2 rule 4).
    gate: dict | None = None


@lru_cache(maxsize=1)
def git_sha7() -> str:
    """Seven hex of the working tree, contract, Trace contract.

    Read from this repository rather than the process's cwd: `art30 scan` run
    from another directory would otherwise stamp that directory's sha. A dirty
    tree takes a sha of its own, because 01-architecture.md section 2 requires a
    run made from uncommitted edits to carry a different run id from the commit
    it sits on, and the contract's grammar has room for seven hex and nothing else.
    """
    head = _git("rev-parse", "--short=7", "HEAD")
    if not head:
        return "0000000"
    dirty = _git("status", "--porcelain")
    if not dirty:
        return head
    return hashlib.sha256(f"{head}\n{dirty}".encode("utf-8")).hexdigest()[:7]


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=5, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def run_id(arm: str, case: str, seed: int) -> str:
    return f"{ARM_PREFIX.get(arm, arm)}-{case}-s{seed}-{git_sha7()}"


def trace_path(cfg: Config, arm: Arm, case: CaseRef, seed: int) -> Path:
    return Path(cfg.trace_dir) / arm.name / f"{case.id}-s{seed}.jsonl"


def out_dir(cfg: Config, arm: Arm, case: CaseRef, seed: int) -> Path:
    """The default layout, expanded once by the caller.

    The loop writes to `cfg.out_dir` verbatim, so `--out DIR` means DIR and not
    DIR plus three derived segments (07-ui.md section 1).
    """
    return Path(cfg.out_dir) / arm.name / case.id / f"s{seed}"


def run(
    case: CaseRef, arm: Arm, seed: int, cfg: Config,
    report: Callable[[str, dict], None] | None = None,
) -> RunResult:
    """One case, one arm, one seed. `report` is the terminal view; the CLI owns it."""
    ctx = RunCtx(
        case=case.id, arm=arm.name, seed=seed, root=case.root,
        tools=ToolCtx(root=case.root), trace=Trace(trace_path(cfg, arm, case, seed)), cfg=cfg,
    )
    started = stamp()
    clock = time.monotonic()
    ctx.trace.run_start(
        run_id=run_id(arm.name, case.id, seed), arm=arm.name, case=case.id, seed=seed,
        model=cfg.model, effort=cfg.effort, mode=cfg.mode, prompt_sha=llm.prompt_sha(),
        config=cfg.trace_config(),
    )
    state = {
        "steps": 0, "started": started, "clock": clock, "say": report or _quiet, "pending": None,
    }
    try:
        return _run(ctx, case, arm, cfg, state)
    except Exception as exc:  # nothing leaves this function without a run_end line
        _flush(ctx, state)
        return _stop(ctx, state, "api_error", note=f"{type(exc).__name__}: {exc}")


def _run(ctx: RunCtx, case: CaseRef, arm: Arm, cfg: Config, state: dict) -> RunResult:
    say = state["say"]
    system = llm.system_blocks()
    messages = [
        _user_text(
            FIRST_TURN.format(
                repo_name=case.name,
                tool_call_budget=cfg.tool_budget,
                submit_budget=cfg.max_submits,
            )
        )
    ]
    step, nudges = 0, 0
    say("phase", {"name": "agent"})
    while True:
        step += 1
        request = llm.build_request(cfg, system, arm.tools(), _mark(messages))
        req_hash = llm.request_hash(request)
        try:
            resp = llm.call(request, cfg=cfg, slot=Slot(ctx.case, ctx.arm, ctx.seed, step))
        except (LlmError, ReplayMiss) as exc:
            kind = "replay_miss" if isinstance(exc, ReplayMiss) else "api_error"
            return _stop(ctx, state, kind, note=str(exc))
        cost = round(llm.cost_of(resp.usage, cfg.model), 6)
        ctx.cost_cum_usd = round(ctx.cost_cum_usd + cost, 6)
        if resp.stop_reason in ("refusal", "max_tokens", "pause_turn", "model_context_window_exceeded"):
            _trace_step(ctx, state, step, resp, req_hash, cost, [], [])
            condition, note = _early_stop(resp, cfg, step)
            return _stop(ctx, state, condition, note=note)
        messages.append({"role": "assistant", "content": resp.content})  # thinking blocks verbatim
        calls = [b for b in resp.content if b.get("type") == "tool_use"]
        if not calls:
            _trace_step(ctx, state, step, resp, req_hash, cost, [], [])
            nudges += 1
            if nudges > 2:
                # The diagnosis quotes the last text from the step line; the note
                # stays free of model prose, which check 16 reads for byte counts.
                return _stop(ctx, state, "no_submission", note="ended turn without submitting, 2 nudges")
            messages.append(_user_text(NUDGE))
            continue
        nudges = 0  # three quiet turns in a row, not three in the run (01 section 9)
        results: list[dict] = []
        phase: Literal["agent", "verify"] = "agent"
        submitted = False
        # The batch as it stands: `taken` is what the tool-call counter has
        # already bought, `results` is mutated in place. A raise below therefore
        # still writes a step line that run_end's counters reconcile with.
        pending = {
            "step": step, "resp": resp, "hash": req_hash, "cost": cost,
            "calls": calls, "results": results, "phase": phase, "taken": 0,
        }
        state["pending"] = pending
        for call in calls:
            if ctx.tool_calls >= cfg.tool_budget:  # invariant B, checked before each dispatch
                _flush(ctx, state)
                return _stop(ctx, state, "budget_exhausted", note=_budget_note(ctx, step, calls))
            if cfg.max_usd and ctx.cost_cum_usd >= cfg.max_usd:
                _flush(ctx, state)
                return _stop(
                    ctx, state, "budget_exhausted",
                    note=f"cost ceiling ${cfg.max_usd} crossed at step {step}",
                )
            ctx.tool_calls += 1
            pending["taken"] += 1
            if call["name"] != "submit_record":
                output, is_error = tools.dispatch(call["name"], call["input"], ctx.tools)
                results.append(_tool_result(call["id"], output, is_error))
                say("call", {"ctx": ctx, "call": call, "output": output,
                             "is_error": is_error, "cost": cost if len(results) == 1 else None})
                continue
            phase = pending["phase"] = "verify"
            if submitted:  # invariant A: one submit_record per turn is handled
                results.append(_tool_result(call["id"], SECOND_SUBMIT, True))
                continue
            submitted = True
            ctx.submits += 1  # before the handler: a raise cannot buy an attempt
            record = call["input"]["record"]
            say("call", {"ctx": ctx, "call": call, "output": "", "is_error": False,
                         "cost": None if results else cost})
            feedback = arm.handle_submit(record, ctx)
            if not feedback.accepted:
                ctx.verify_rounds += 1
                ctx.rejections.append({"attempt": ctx.submits, "schema_errors": feedback.schema_errors})
            results.append(_tool_result(call["id"], feedback.to_tool_result(), not feedback.accepted))
            say("verify", {"arm": arm, "feedback": feedback})
            if feedback.accepted:
                ctx.accepted = record
            elif ctx.submits >= cfg.max_submits:
                _flush(ctx, state)
                return _stop(ctx, state, "max_submits", note=_submits_note(ctx, feedback))
        _flush(ctx, state)
        messages.append({"role": "user", "content": results})  # all results, one message
        if ctx.accepted:
            break
        if phase == "verify":
            say("phase", {"name": "agent"})
    return _finish(ctx, case, arm, cfg, state)


def _finish(ctx: RunCtx, case: CaseRef, arm: Arm, cfg: Config, state: dict) -> RunResult:
    record = ctx.accepted or {}
    target = Path(cfg.out_dir)
    decision = arm.gate(record, ctx)
    gate = None
    if decision is not None:
        verdict = "approved" if decision.approved else "rejected"
        ctx.trace.checkpoint(
            risk=decision.risk, summary=decision.summary, decision=verdict, by=decision.by,
            wait_s=decision.wait_s, human_completions=decision.human_completions(),
        )
        gate = {
            "risk": decision.risk, "decision": verdict, "by": decision.by,
            "wait_s": round(decision.wait_s, 3), "at": stamp(),
        }
        if not decision.approved:
            write_draft(record, target)
            reason = (decision.summary.splitlines() or [""])[0]
            return _stop(
                ctx, state, "gate_rejected", gate=gate,
                note=f"gate rejected at risk={decision.risk}: {reason}",
            )
        record = apply_edits(record, decision.edits)
    record = _finalise(record, ctx, case, cfg, arm, state, gate)
    try:
        paths = render_all(record, target, case.root)
    except RenderError as exc:
        return _stop(
            ctx, state, "render_failed", gate=gate, record_path=exc.record_path, note=str(exc)
        )
    state["say"]("render", {"paths": paths})
    return _stop(ctx, state, "accepted", gate=gate, record_path=paths.json)


def _stop(
    ctx: RunCtx, state: dict, condition: str, *, record_path: str | None = None,
    note: str | None = None, gate: dict | None = None,
) -> RunResult:
    wall = round(time.monotonic() - state["clock"], 1)
    counters = dict(
        stop_condition=condition, steps=state["steps"], tool_calls_total=ctx.tool_calls,
        submits=ctx.submits, verify_rounds=ctx.verify_rounds, wall_s=wall,
        cost_usd=ctx.cost_cum_usd, record_path=record_path, note=note,
    )
    ctx.trace.run_end(**counters)
    ctx.trace.close()
    return RunResult(run_id=run_id(ctx.arm, ctx.case, ctx.seed), gate=gate, **counters)


def _early_stop(resp: llm.Response, cfg: Config, step: int) -> tuple[str, str]:
    if resp.stop_reason == "refusal":
        details = resp.stop_details or {}
        return "refusal", f"refusal category={details.get('category')}: {details.get('explanation')}"
    if resp.stop_reason == "model_context_window_exceeded":
        return "max_tokens", f"context window exceeded on step {step}"
    if resp.stop_reason == "max_tokens":
        # "truncated" is reserved for the harness's own partial-line repair
        # (06-traces.md check 16), so the note says the same thing in other words.
        return "max_tokens", f"output cut off at max_tokens={cfg.max_tokens} on step {step}"
    return "api_error", "pause_turn on a request with no server tools"


def _budget_note(ctx: RunCtx, step: int, calls: list[dict]) -> str:
    names = ", ".join(c["name"] for c in calls[-3:])
    return f"budget {ctx.cfg.tool_budget} exhausted at step {step}; last 3 calls: {names}; submits={ctx.submits}"


def _submits_note(ctx: RunCtx, feedback: Feedback) -> str:
    first = (feedback.rejected_claims or [{}])[0].get("reason") or (
        feedback.schema_errors[0] if feedback.schema_errors else "no reason recorded"
    )
    return f"{ctx.cfg.max_submits} submits rejected; last rejection: {first}"


def _mark(messages: list[dict]) -> list[dict]:
    """Breakpoints B and C: the newest user turn and the one before it."""
    copied = [dict(message) for message in messages]
    users = [i for i, message in enumerate(copied) if message["role"] == "user"]
    for index in users[-2:]:
        content = [dict(block) for block in copied[index]["content"]]
        content[-1]["cache_control"] = dict(llm.CACHE_CONTROL)
        copied[index]["content"] = content
    return copied


def _user_text(text: str) -> dict:
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def _tool_result(call_id: str, output: str, is_error: bool) -> dict:
    block = {"type": "tool_result", "tool_use_id": call_id, "content": output}
    if is_error:
        block["is_error"] = True
    return block


def _flush(ctx: RunCtx, state: dict) -> None:
    """Write the in-flight batch's step line, if one is still pending."""
    at = state["pending"]
    if not at:
        return
    try:
        _trace_step(
            ctx, state, at["step"], at["resp"], at["hash"], at["cost"],
            at["calls"][: at["taken"]], at["results"], at["phase"],
        )
    except Exception:  # a dead trace writer must not also cost the run_end line
        state["pending"] = None


def _trace_step(
    ctx: RunCtx, state: dict, step: int, resp: llm.Response, req_hash: str, cost: float,
    calls: list[dict], results: list[dict], phase: Literal["agent", "verify"] = "agent",
) -> None:
    ctx.trace.step(
        step=step, phase=phase, request_id=resp.request_id, request_hash=req_hash,
        stop_reason=resp.stop_reason, reasoning=_blocks(resp, "thinking"), text=_blocks(resp, "text"),
        tool_calls=[{"id": c["id"], "name": c["name"], "input": c["input"]} for c in calls],
        tool_results=[
            {"call_id": r["tool_use_id"], "output": r["content"],
             "is_error": bool(r.get("is_error")), "bytes": len(r["content"].encode("utf-8"))}
            for r in results
        ],
        usage=resp.usage, cost_usd=cost, cost_cum_usd=ctx.cost_cum_usd,
    )
    # After the line exists, never before: `run_end.steps` is the number of step
    # lines in the file, and every exit above writes one (06-traces.md check 7).
    state["pending"] = None
    state["steps"] = step


def _blocks(resp: llm.Response, kind: str) -> str:
    """The summarised thinking, or the text: both are one field named for their block."""
    return "\n".join(str(b.get(kind, "")) for b in resp.content if b.get("type") == kind).strip()


def _finalise(
    record: dict, ctx: RunCtx, case: CaseRef, cfg: Config, arm: Arm, state: dict, gate: dict | None
) -> dict:
    """The submitted record plus `verification` and `provenance` (04 section 5)."""
    out = json.loads(json.dumps(record))
    for store in out.get("stores") or []:
        if store.get("kind") == "third_party" and not store.get("recipient_kind"):
            store["recipient_kind"] = "unknown"
    # The baseline writes the same keys with its own counters: no reader of
    # record.json branches on the arm (04 section 5, decision 8).
    out["verification"] = {
        "submits": ctx.submits, "accepted_on_attempt": ctx.submits,
        "rejected_history": ctx.rejections, "missing_stores_resolved": [],
        "bad_citations_resolved": [], "unverified": [], "rule_set_sha": None,
    }
    out["provenance"] = {
        "arm": arm.name, "model": cfg.model, "effort": cfg.effort, "config": cfg.trace_config(),
        "run_id": run_id(arm.name, case.id, ctx.seed), "case": case.id, "seed": ctx.seed,
        "mode": cfg.mode, "instruction_sha256": llm.prompt_sha()[:12],
        "fixture": {"id": case.id, "path": relative(case.root), "sha256": tree_sha(case.root)},
        "started_at": state["started"], "finished_at": stamp(),
        "trace": str(trace_path(cfg, arm, case, ctx.seed)),
        "cost_usd": ctx.cost_cum_usd, "tool_calls": ctx.tool_calls, "gate": gate,
    }
    return out


def _quiet(kind: str, data: dict) -> None:
    """The default report: a run nobody is watching prints nothing."""
