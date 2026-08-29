"""`art30 scan ...`: parse, resolve the case, run the loop, print the tail.

No run logic lives here. The header and the last three lines are this module's
whole output contract (07-ui.md sections 2 and 6); everything between them is
printed by the loop as it happens.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import yaml

from art30 import __version__, config, tools
from art30.loop import CaseRef, RunResult, out_dir, run

REPO_ROOT = Path(__file__).resolve().parent.parent
SPLIT = REPO_ROOT / "evals" / "split.yaml"
EXIT = {"accepted": 0, "gate_rejected": 3, "replay_miss": 4}
USAGE_EXIT = 2

STOP_LINES = {
    "budget_exhausted": "[agent] tool-call budget exhausted at {calls}/{budget} without submit_record.",
    "no_submission": "[agent] turn ended with no tool call, three times. No record was submitted.",
    "max_tokens": "[agent] output truncated at max_tokens={max_tokens} on step {steps}.",
    "max_submits": "[verify] attempt {submits} · rejected · no attempts left.",
    "api_error": "[agent] API error: {note}",
    "refusal": "[agent] stop_reason refusal at step {steps}. Counted as a failure, not re-prompted.",
    "timeout": "[agent] wall-clock timeout at {wall}s.",
    "replay_miss": "[agent] replay miss at step {steps}. The cache is stale or the fixture changed.",
    "render_failed": "[render] {note} Nothing written. The record is kept at {record_path}.",
    "gate_rejected": "[gate] rejected by the approver. Nothing rendered.",
}
# One printed line type per key of the feedback object (07-ui.md section 2 rule 3).
FEEDBACK_LINES = (
    ("rejected_claims", "REJECT", ("store", "claim")),
    ("missing_stores", "MISSING", ("store", "kind")),
    ("missing_entry_points", "ENTRY", ("name", "kind")),
    ("bad_citations", "CITE", ("file", "symbol")),
    ("unverified", "UNVERIFIED", ("store", "claim")),
    ("conservative_divergences", "SAFER", ("store", "claim")),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="art30", description="Read an Art. 30 record out of a repository.")
    subs = parser.add_subparsers(dest="command", required=True)
    serve = subs.add_parser("serve", help="local website: drive scans and watch them (ADR 0007)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8734)
    serve.add_argument("--open", action="store_true", help="open the page in a browser")
    scan = subs.add_parser("scan", help="scan one repository with one arm")
    scan.add_argument("repo", help="path to the repository to read; nothing in it is executed")
    scan.add_argument("--arm", required=True, choices=("advanced", "baseline"))
    scan.add_argument("--case", default=None, help="case id for the trace and the results path")
    scan.add_argument("--seed", type=int, default=1, help="harness label; the model takes no seed")
    scan.add_argument("--mode", default=None, choices=("live", "replay"))
    scan.add_argument("--approve", default=None, choices=("ask", "auto"))
    scan.add_argument("--out", default=None, help="where record.json, record.md and record.html go")
    return parser


def load_arm(name: str):
    """The advanced arm is imported lazily: it does not exist yet."""
    if name == "baseline":
        from baseline.arm import BaselineArm

        return BaselineArm()
    try:
        from advanced.arm import AdvancedArm
    except ImportError:
        return None
    return AdvancedArm()


def test_cases() -> set[str]:
    if not SPLIT.is_file():
        return set()
    data = yaml.safe_load(SPLIT.read_text(encoding="utf-8")) or {}
    return {str(case) for case in data.get("test") or []}


def case_kind(case_id: str) -> str:
    return "real" if case_id.upper().startswith("R") else "synthetic"


def _files(root: Path) -> int:
    return sum(
        1
        for path in root.rglob("*")
        if path.is_file() and not any(part in tools.EXCLUDED_DIRS for part in path.parts)
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        from art30.web.server import serve as _serve   # lazy: the website is optional
        return _serve(args.host, args.port, args.open)
    repo = Path(args.repo)
    if not repo.is_dir():
        print(f"not a directory: {args.repo}", file=sys.stderr)
        return USAGE_EXIT
    case_id = args.case or repo.resolve().name
    overrides: dict[str, object] = {}
    if args.mode:
        overrides["mode"] = args.mode
    if args.approve:
        overrides["approve"] = args.approve
    cfg = config.load(overrides).for_case_kind(case_kind(case_id))

    if case_id in test_cases() and cfg.mode != "replay" and not cfg.unlock_test:
        print(
            f"{case_id} is in the test split (evals/split.yaml). Set ART30_UNLOCK_TEST=1 to run it,"
            " and record the sweep in results/test-runs.log.",
            file=sys.stderr,
        )
        return USAGE_EXIT
    arm = load_arm(args.arm)
    if arm is None:
        print(
            "the advanced arm is not built yet (advanced/arm.py); run --arm baseline",
            file=sys.stderr,
        )
        return USAGE_EXIT
    if args.arm == "advanced" and cfg.approve == "ask" and not sys.stdout.isatty():
        print("--approve ask needs a terminal; use --approve auto", file=sys.stderr)
        return USAGE_EXIT

    case = CaseRef(id=case_id, name=repo.resolve().name, root=repo.resolve(), kind=case_kind(case_id))
    # The loop writes to cfg.out_dir verbatim, so the expansion happens here,
    # once, and only where the default layout is wanted (07-ui.md section 1).
    cfg = replace(cfg, out_dir=Path(args.out) if args.out else out_dir(cfg, arm, case, args.seed))
    _header(cfg, args, case, repo)
    result = run(case, arm, args.seed, cfg, report)
    _tail(cfg, args, result)
    return EXIT.get(result.stop_condition, 1)


def report(kind: str, data: dict) -> None:
    """The run as it happens: banners, one line per tool call, the verify block."""
    if kind == "phase":
        print(f"\n[{data['name']}]", flush=True)
    elif kind == "call":
        _call_line(data["ctx"], data["call"], data["output"], data["is_error"], data["cost"])
    elif kind == "verify":
        _verify_block(data["arm"], data["feedback"])
    elif kind == "render":
        paths = data["paths"]
        print("\n[render]")
        for path in (paths.json, paths.md, paths.html):
            print(f"  {path}")


def _call_line(ctx, call: dict, output: str, is_error: bool, cost: float | None) -> None:
    args, summary = _summarise(call, output, is_error, ctx)
    money = f"${cost:.3f}  \u03a3${ctx.cost_cum_usd:.3f}" if cost is not None else ""
    line = (
        f"{ctx.tool_calls:>4}/{ctx.cfg.tool_budget}  {call['name']:<15}{args:<40}"
        f"{summary:>11}   {money}"
    )
    print(line.rstrip(), flush=True)


def _summarise(call: dict, output: str, is_error: bool, ctx) -> tuple[str, str]:
    payload = call.get("input") or {}
    name = call["name"]
    if is_error:
        return str(payload)[:38], "error"
    if name == "list_tree":
        where = f"{payload.get('path', '.')} depth={payload.get('max_depth', 4)}"
        return where, f"{len(output.splitlines())} paths"
    if name == "read_file":
        end = payload.get("end_line")
        return (
            f"{payload.get('path')}:{payload.get('start_line', 1)}-{end if end else 'end'}",
            f"{len(output.splitlines())} lines",
        )
    if name == "grep":
        found = 0 if output.startswith("no matches") else len(output.splitlines())
        return (
            f"{payload.get('pattern')}  {payload.get('glob', '*.py')}",
            f"{found} match" if found == 1 else f"{found} matches",
        )
    stores = (payload.get("record") or {}).get("stores") or []
    fields = sum(len(s.get("fields") or []) for s in stores)
    return f"{len(stores)} stores \u00b7 {fields} fields", f"attempt {ctx.submits}"


def _verify_block(arm, feedback) -> None:
    """UNVERIFIED, ENTRY and SAFER print on an accepted record too (07 section 2 rule 3)."""
    label = getattr(arm, "verify_label", "")
    head = "\n[verify] " + (f"{label} \u00b7 " if label else "")
    attempt = f"attempt {feedback.attempt} \u00b7 " if feedback.attempt else ""
    if feedback.accepted:
        print(head + attempt + "accepted", flush=True)
    else:
        print(head + attempt + _reject_summary(feedback))
        for error in feedback.schema_errors:
            print(f"  SCHEMA   {error}")
    for key, tag, names in FEEDBACK_LINES:
        for item in getattr(feedback, key):
            print(f"  {tag:<8} " + " \u00b7 ".join(str(item[n]) for n in names if item.get(n)))
            for detail in ("reason", "problem", "evidence", "note"):
                if item.get(detail):
                    print(f"           {item[detail]}")
            if item.get("expected"):
                print(f"           expected: {item['expected']}")
    if not feedback.accepted:
        print(f"  attempts left: {feedback.attempts_left}", flush=True)


def _reject_summary(feedback) -> str:
    counts = []
    if feedback.schema_errors:
        counts.append(f"{len(feedback.schema_errors)} schema errors")
    counts += [
        f"{len(getattr(feedback, key))} {key.replace('_', ' ')}"
        for key, _, _ in FEEDBACK_LINES
        if getattr(feedback, key)
    ]
    return " \u00b7 ".join(counts) or "rejected"


def _header(cfg: config.Config, args: argparse.Namespace, case: CaseRef, repo: Path) -> None:
    print(
        f"art30 {__version__} · case {case.id} · arm {args.arm} · seed {args.seed}"
        f" · mode {cfg.mode}"
    )
    print(f"model {cfg.model} · effort {cfg.effort} · max_tokens {cfg.max_tokens}")
    ceiling = f" · ceiling ${cfg.max_usd}" if cfg.max_usd else ""
    print(
        f"budget {cfg.tool_budget} tool calls · {cfg.max_submits} submit attempts"
        f" · repo {args.repo} ({_files(repo)} files){ceiling}"
    )
    if cfg.overridden:
        print("overridden: " + ", ".join(cfg.overridden))


def _tail(cfg: config.Config, args: argparse.Namespace, result: RunResult) -> None:
    if _cost_ceiling(result):
        print(f"\n[agent] cost ceiling ${cfg.max_usd} crossed at step {result.steps}.")
    elif result.stop_condition in STOP_LINES:
        print(
            "\n"
            + STOP_LINES[result.stop_condition].format(
                calls=result.tool_calls_total, budget=cfg.tool_budget, max_tokens=cfg.max_tokens,
                steps=result.steps, submits=result.submits, wall=result.wall_s,
                note=result.note or "", record_path=result.record_path or "",
            )
        )
    if result.stop_condition == "gate_rejected":
        print(f"  record kept at {Path(cfg.out_dir) / 'record.draft.json'}")
    rounds = "round" if result.verify_rounds == 1 else "rounds"
    submits = "submit" if result.submits == 1 else "submits"
    print(
        f"{result.stop_condition} · {result.steps} steps · {result.tool_calls_total} tool calls"
        f" · {result.submits} {submits} · {result.verify_rounds} verify {rounds}"
        f" · {_gate_words(args, result)}"
    )
    trace = Path(cfg.trace_dir) / args.arm / f"{args.case or Path(args.repo).resolve().name}-s{args.seed}.jsonl"
    print(f"${result.cost_usd:.2f} · {result.wall_s}s · {trace}")


def _cost_ceiling(result: RunResult) -> bool:
    """The cost half of `budget_exhausted` prints its own line (07 section 6)."""
    return result.stop_condition == "budget_exhausted" and (result.note or "").startswith(
        "cost ceiling"
    )


def _gate_words(args: argparse.Namespace, result: RunResult) -> str:
    """The gate the run reported, never one re-derived from the arm it ran."""
    if result.gate is None:
        return f"no gate ({args.arm})"
    if result.gate["decision"] == "rejected":
        return "gate rejected"
    return f"gate approved ({result.gate['by']})"


if __name__ == "__main__":  # pragma: no cover - the console script calls main()
    sys.exit(main())
