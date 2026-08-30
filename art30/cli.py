"""`art30 scan ...`: parse, resolve the case, run the loop, print the tail.

No run logic lives here. The header and the last three lines are this module's
whole output contract (07-ui.md sections 2 and 6); everything between them is
printed by the loop as it happens.
"""

from __future__ import annotations

import argparse

from art30.config_cli import config_command, config_parser
import os
import re
import sys
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import yaml

from art30 import __version__, config, settings, tools
from art30.loop import CaseRef, RunResult, out_dir, run

REPO_ROOT = Path(__file__).resolve().parent.parent
SPLIT = REPO_ROOT / "evals" / "split.yaml"
FIXTURES = REPO_ROOT / "evals" / "fixtures"
AD_HOC_OUT = Path("art30-out")   # a repository of the user's own, not an evaluation case
REAL_REPO_FILES = 40             # above this an off-eval repository gets the real budget
# The real fixtures keep their upstream directory names, so the path does not carry the
# case id the way evals/fixtures/synthetic/S10 does. Duplicated from
# evals/harness/plan.py REAL_DIRS, inverted: art30/ never imports the harness.
REAL_DIRS = {
    "full-stack-fastapi-template": "R01", "flaskbb": "R02", "pinry": "R03",
    "microblog": "R04", "Django-Styleguide-Example": "R05",
}
NO_ARM = (
    "no {arm} arm: {arm}/arm.py could not be imported. Inside this repository run"
    " `uv run art30 scan ...`; an installed copy needs a wheel that packages"
    " baseline/ and advanced/ alongside art30/."
)
NO_KEY = (
    "no ANTHROPIC_API_KEY: put it in .env (see .env.example) or export it;"
    " --mode replay needs no key"
)
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
    scan.add_argument("--approve", default=None, choices=("ask", "auto", "file"))
    scan.add_argument("--out", default=None, help="where record.json, record.md and record.html go")
    scan.add_argument("--brain", default=None, choices=settings.BRAINS,
                      help="what runs the loop: the API, or your own logged-in claude/codex CLI")
    scan.add_argument("--model", default=None, help="the model for the brain that was selected")
    config_parser(subs)
    return parser


def load_arm(name: str):
    """Both arms live outside the `art30` package, so a wheel that ships only that
    package has neither. An import failure comes back as None and is printed as a
    sentence by `main`; it used to be a traceback out of an installed console script."""
    try:
        if name == "baseline":
            from baseline.arm import BaselineArm

            return BaselineArm()
        from advanced.arm import AdvancedArm
    except ImportError:
        return None
    return AdvancedArm()


@lru_cache(maxsize=1)
def _split() -> dict:
    return (yaml.safe_load(SPLIT.read_text(encoding="utf-8")) or {}) if SPLIT.is_file() else {}


def test_cases() -> set[str]:
    return {str(case) for case in _split().get("test") or []}


def eval_cases() -> set[str]:
    """Every case id evals/split.yaml names, on whichever of its lists."""
    data = _split()
    return {str(c) for key in ("dev", "test", "demo", "reserve") for c in data.get(key) or []}


def slug(name: str) -> str:
    """A directory name as one path segment. Case is kept: `D02` is already a slug,
    and lowering it would miss both its cache slot and its line in split.yaml."""
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "repo"


def case_kind(case_id: str, files: int | None = None) -> str:
    """An evaluation id keeps its kind; any other repository is sized by file count,
    because the budget is what the kind buys and a big repository needs the big one."""
    if files is None or case_id in eval_cases():
        return "real" if case_id.upper().startswith("R") else "synthetic"
    return "real" if files > REAL_REPO_FILES else "synthetic"


def fixture_case(root: Path) -> str | None:
    """The case id an evaluation fixture path carries, or None off the fixture tree.
    A synthetic fixture is named after its case; a real one keeps its upstream name,
    which is what `REAL_DIRS` translates. The test-split lock reads this, so pointing
    the CLI at evals/fixtures/real/pinry is R03 whatever `--case` says."""
    if not root.is_relative_to(FIXTURES):
        return None
    return REAL_DIRS.get(root.name, slug(root.name))


def _files(root: Path) -> int:
    """Files under `root`, minus the directories the tools never walk. The parts are
    taken relative to the repository — the same idiom as art30/tools.py — so a
    checkout under a directory called `media` still counts its own files."""
    return sum(
        1
        for path in root.rglob("*")
        if path.is_file()
        and not any(part in tools.EXCLUDED_DIRS for part in path.relative_to(root).parts)
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "config":
        return config_command(args)
    if args.command == "serve":
        from art30.web.server import serve as _serve   # lazy: the website is optional
        return _serve(args.host, args.port, args.open)
    repo = Path(args.repo)
    if not repo.is_dir():
        print(f"not a directory: {args.repo}", file=sys.stderr)
        return USAGE_EXIT
    root = repo.resolve()
    files = _files(root)
    fixture = fixture_case(root)
    case_id = args.case or fixture or slug(root.name)
    overrides: dict[str, object] = {}
    if args.mode:
        overrides["mode"] = args.mode
    if args.approve:
        overrides["approve"] = args.approve
    if args.brain:
        overrides["brain"] = args.brain
    kind = case_kind(case_id, files)
    # `--model` is routed by the brain the loader resolved, never by the flag: a brain
    # that came from art30.toml would otherwise move the API model and leave the CLI
    # that runs with nothing (ADR 0008 item 1).
    cfg = config.load(overrides).for_case_kind(kind)
    if args.model:
        cfg = replace(cfg, **({"model": args.model} if cfg.brain == "api"
                              else {"brain_model": args.model}))
    if cfg.brain != "api":
        # The two local brains land with art30/brains/; until then the flag parses,
        # says so and spends nothing (ADR 0008 item 1).
        print(f"brain {cfg.brain} is not built yet", file=sys.stderr)
        raise SystemExit(USAGE_EXIT)
    if cfg.model != config.DEFAULT_MODEL and "ART30_MODEL" not in cfg.overridden:
        # A run at a model nobody configured is a run at non-default settings, and the
        # header and provenance.config are where that has to show (07-ui.md section 1).
        cfg = replace(cfg, overridden=tuple(sorted((*cfg.overridden, "ART30_MODEL"))))

    # The path decides as well as `--case`: a fixture that resolves to a test case is
    # locked even when `--case` names something else (evals/split.yaml, comment 4).
    locked = {case_id, fixture} & test_cases()
    if locked and cfg.mode != "replay" and not cfg.unlock_test:
        print(
            f"{', '.join(sorted(locked))} is in the test split (evals/split.yaml)."
            " Set ART30_UNLOCK_TEST=1 to run it, and record the sweep in"
            " results/test-runs.log.",
            file=sys.stderr,
        )
        return USAGE_EXIT
    # `config.load` has read `.env` by now, so this is the last word on the key
    # and it is spoken before `llm` imports the SDK or builds a client.
    if cfg.mode == "live" and not os.environ.get("ANTHROPIC_API_KEY"):
        print(NO_KEY, file=sys.stderr)
        return USAGE_EXIT
    arm = load_arm(args.arm)
    if arm is None:
        print(NO_ARM.format(arm=args.arm), file=sys.stderr)
        return USAGE_EXIT
    if args.arm == "advanced" and cfg.approve == "ask" and not sys.stdout.isatty():
        print("--approve ask needs a terminal; use --approve auto", file=sys.stderr)
        return USAGE_EXIT

    case = CaseRef(id=case_id, name=root.name, root=root, kind=kind)
    cfg = replace(cfg, **_paths(cfg, args, arm, case, root))
    _header(cfg, args, case, files)
    result = run(case, arm, args.seed, cfg, report)
    _tail(cfg, args, result)
    return EXIT.get(result.stop_condition, 1)


def _paths(cfg: config.Config, args: argparse.Namespace, arm, case: CaseRef, root: Path) -> dict:
    """Where this run writes. The loop uses `cfg.out_dir` verbatim, so the default
    layout is expanded here, once (07-ui.md section 1). A repository that is not an
    evaluation fixture keeps its record and its trace together under one directory
    of its own, instead of writing into the eval's results/ and traces/ trees."""
    own = not root.is_relative_to(FIXTURES)
    if args.out:
        target = Path(args.out)
    elif own:
        target = AD_HOC_OUT / slug(root.name) / arm.name / f"s{args.seed}"
    else:
        target = out_dir(cfg, arm, case, args.seed)
    if own and not os.environ.get("ART30_TRACE_DIR"):   # the harness seam still wins
        return {"out_dir": target, "trace_dir": target}
    return {"out_dir": target}


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


def _header(cfg: config.Config, args: argparse.Namespace, case: CaseRef, files: int) -> None:
    print(
        f"art30 {__version__} · case {case.id} · arm {args.arm} · seed {args.seed}"
        f" · mode {cfg.mode}"
    )
    print(f"model {cfg.model} · effort {cfg.effort} · max_tokens {cfg.max_tokens}")
    ceiling = f" · ceiling ${cfg.max_usd}" if cfg.max_usd else ""
    print(
        f"budget {cfg.tool_budget} tool calls · {cfg.max_submits} submit attempts"
        f" · repo {args.repo} ({files} files){ceiling}"
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
    case_id = args.case or slug(Path(args.repo).resolve().name)
    trace = Path(cfg.trace_dir) / args.arm / f"{case_id}-s{args.seed}.jsonl"
    written = ""
    if result.stop_condition == "accepted":
        written = f"{Path(cfg.out_dir) / 'record.json'} · record.md · record.html · "
    print(f"${result.cost_usd:.2f} · {result.wall_s}s · {written}{trace}")


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
