"""`make eval-replay` for a local brain: the verifier, re-run over every recorded submission.

    uv run python -m evals.harness.reverify [--runs results/runs]

ADR 0008 item 4. The `api` brain replays: every request was hashed and its response
committed, so the loop can be run again and must produce the same record. A local brain
records no response — the model output was produced inside the `claude` or `codex` process
and no brain can regenerate it. What a local-brain run does commit is its trace, every
record it submitted and the verifier's full answer to each (`<run>/brain/submissions.jsonl`,
written by `art30/brains/spool.py`), and that is enough to re-run the deterministic half.

This module reads each of those submissions back, runs the same arm handler the MCP server
ran — `advanced/arm.py`, which is schema validation and then `art30.verify.check` over the
fixture; `baseline/arm.py`, which is schema validation alone — and compares its answer to
the recorded one key by key. A difference is a failure naming the run and the attempt: it
means the verifier's verdict on a committed record has changed, which is the one thing a
replay of a local-brain sweep can still prove and the one thing that would invalidate the
scored comparison.

It then re-scores, which is the other half ADR 0008 item 4 promises. Verifying the
submissions alone left the two artefacts the reported table is actually built from — each
run's `metrics.json` and the `record.json` it was scored from — checked by nothing: an
edited `metrics.json` (f1 0.87 to 1.00, pass false to true) and a `record.json` with four
of its seven stores deleted both passed this target clean. So every run is scored again
here, by the same `score.score_run` call `cells.finish_cell` makes, from the delivered
record, the case manifest and the run's own trace, and every differing metric is a
mismatch naming the key, the committed value and the recomputed one.

What it does not prove is that the model would say the same thing again. Nothing can, and
`docs/runbook-sweeps.md` says so beside the command rather than letting the word "replay"
carry a claim it cannot support.

Exit codes follow 05-eval-harness.md section 5.5's shape: 0 clean, 1 a mismatch or a run
this module could not check.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from art30.arm import RunCtx
from art30.config import Config
from art30.loop import _feedback_dict
from art30.tools import ToolCtx
from evals.harness import score as scoring
from evals.harness.cells import read_json
from evals.harness.plan import ARMS, REPO_ROOT, Abort, fixture, manifest
from evals.harness.run import trace_root

MANIFESTS = REPO_ROOT / "evals" / "fixtures" / "manifests"
SYNTHETIC = REPO_ROOT / "evals" / "fixtures" / "synthetic"
REAL = REPO_ROOT / "evals" / "fixtures" / "real"
SUBMISSIONS = "submissions.jsonl"
SPOOL_DIR = "brain"          # `art30/brains/driver.py` writes the spool beside the record
# The scored fields of a per-run `metrics.json`: the primary metric and its two halves, both
# safety counters, the binary pass, and the three quality rows section 7.2 prints. Everything
# else in that file is either provenance (`case`, `mode`, `manifest_sha256`) or a detail list
# whose count is already here, so a difference in one of these is a difference in the table.
SCORED_KEYS = ("f1", "precision", "recall", "false_safe", "unmatched_reaching_claims", "pass",
               "unverified", "invalid_verdict_for_kind", "citation_check")


class _NullTrace:
    """`RunCtx` carries a trace and no arm writes to it; this process owns none."""

    def __getattr__(self, name: str):   # pragma: no cover - never called by an arm
        return lambda *args, **kwargs: None


def load_arm(name: str):
    """The arms live outside the `art30` package, exactly as `art30/cli.py` finds them."""
    if name == "baseline":
        from baseline.arm import BaselineArm

        return BaselineArm()
    from advanced.arm import AdvancedArm

    return AdvancedArm()


def canonical(feedback: dict) -> str:
    """One spelling of one answer: key order is not a difference, content is."""
    return json.dumps(feedback, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def run_dirs(runs: Path) -> list[tuple[Path, Path]]:
    """(run directory, submissions file) for every run that recorded any submission."""
    found = []
    for path in sorted(Path(runs).rglob(SUBMISSIONS)):
        parent = path.parent
        found.append((parent.parent if parent.name == SPOOL_DIR else parent, path))
    return found


def identify(run_dir: Path, runs: Path) -> tuple[str, str, int]:
    """`<runs>/<arm>/<case>/s<seed>`, which is the layout section 6 fixes."""
    try:
        parts = run_dir.resolve().relative_to(Path(runs).resolve()).parts
    except ValueError:
        raise Abort(1, f"{run_dir} is not under {runs}") from None
    if len(parts) < 3 or parts[-3] not in ARMS:
        raise Abort(1, f"cannot read arm/case/seed from {run_dir}: expected <arm>/<case>/s<seed>")
    arm, case, seed = parts[-3], parts[-2], parts[-1]
    return arm, case, int(seed.lstrip("s") or 0)


def entries(path: Path) -> list[dict]:
    """Every recorded submission. A half-written last line is a failure, not an exception."""
    out = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            raise Abort(1, f"{path}:{lineno}: submission line does not parse as JSON") from None
        if not isinstance(item, dict):
            raise Abort(1, f"{path}:{lineno}: submission line is not an object")
        out.append(item)
    return out


def recheck(arm, record: dict, root: Path, case: str, arm_name: str, seed: int,
            attempt: int) -> dict:
    """The arm's own handler, called as `art30/brains/mcp_server.py` calls it."""
    cfg = Config(approve="auto")
    ctx = RunCtx(case=case, arm=arm_name, seed=seed, root=root, tools=ToolCtx(root=root),
                 trace=_NullTrace(), cfg=cfg)   # type: ignore[arg-type]
    ctx.submits = attempt
    feedback = arm.handle_submit(record, ctx)
    return {"accepted": bool(feedback.accepted), **_feedback_dict(feedback)}


def trace_end(path: Path) -> tuple[dict, dict | None]:
    """The last `run_end` and the last `checkpoint` of a run's trace, which is what
    `cells.finish_cell` scored from. A trace that is missing or unparseable scores the
    run as `crashed`, exactly as the sweep would have."""
    end: dict = {"stop_condition": "crashed"}
    point: dict | None = None
    if not path.is_file():
        return end, point
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line) if line.strip() else None
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") == "run_end":
            end = obj
        elif obj.get("type") == "checkpoint":
            point = obj
    return end, point


def rescore(run_dir: Path, traces: Path, arm_name: str, case: str, seed: int, data: dict,
            sha: str, root: Path) -> tuple[int, list[str]]:
    """The run scored again from what it delivered: (records checked, one line per difference).

    The same call `cells.finish_cell` makes, over the same inputs: the delivered
    `record.json`, the gate-rejected draft beside it, the case manifest, and the run's own
    trace for the stop condition and the checkpoint. `mode` comes off the committed file
    because it is provenance the sweep recorded and not something a record can carry.
    """
    committed = read_json(run_dir / "metrics.json")
    where = f"{arm_name}/{case}-s{seed}"
    if committed is None:
        return 0, [f"{where}: recorded submissions but no metrics.json to re-score against"]
    end, point = trace_end(traces / arm_name / f"{case}-s{seed}.jsonl")
    again = scoring.score_run(
        read_json(run_dir / "record.json"), data, end,
        draft=read_json(run_dir / "record.draft.json"), repo_root=root, checkpoint=point,
        arm=arm_name, seed=seed, mode=committed.get("mode"), manifest_sha256=sha)
    return 1, [f"{where}: {key} was {committed.get(key)!r}, re-scores {again.get(key)!r}"
               for key in SCORED_KEYS if committed.get(key) != again.get(key)]


def check_run(run_dir: Path, submissions: Path, runs: Path, arms: dict,
              traces: Path) -> tuple[int, int, list[str]]:
    """One run: (submissions checked, records re-scored, one line per difference)."""
    arm_name, case, seed = identify(run_dir, runs)
    data, sha = manifest(case, MANIFESTS)
    root = fixture(case, data, SYNTHETIC, REAL)
    if arm_name not in arms:
        arms[arm_name] = load_arm(arm_name)
    bad: list[str] = []
    checked = 0
    for entry in entries(submissions):
        attempt = int(entry.get("attempt") or 0)
        record = entry.get("record")
        where = f"{arm_name}/{case}-s{seed} attempt {attempt}"
        if not isinstance(record, dict):
            bad.append(f"{where}: the recorded submission carries no record object")
            continue
        checked += 1
        recorded = entry.get("feedback")
        recorded = recorded if isinstance(recorded, dict) else {}
        again = recheck(arms[arm_name], record, root, case, arm_name, seed, attempt)
        if canonical(again) != canonical(recorded):
            bad.append(f"{where}: the verifier no longer answers what was recorded\n"
                       f"  recorded: {canonical(recorded)[:300]}\n"
                       f"  now:      {canonical(again)[:300]}")
    scored, problems = rescore(run_dir, traces, arm_name, case, seed, data, sha, root)
    return checked, scored, bad + problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evals.harness.reverify",
        description="Re-run the verifier over every recorded submission of a local-brain sweep"
                    " and re-score every record it delivered.")
    parser.add_argument("--runs", default="results/runs")
    parser.add_argument("--traces", default=None,
                        help="trace root; default `traces/` for the scored tree and"
                             " <runs>/traces for any other, mirroring `run.trace_root`")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runs = Path(args.runs)
    traces = Path(args.traces) if args.traces else trace_root(args.runs)
    found = run_dirs(runs)
    arms: dict = {}
    checked = scored = 0
    bad: list[str] = []
    try:
        for run_dir, submissions in found:
            count, records, problems = check_run(run_dir, submissions, runs, arms, traces)
            checked += count
            scored += records
            bad += problems
    except Abort as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    for line in bad:
        print(line)
    print(f"reverified {checked} submissions and {scored} records in {len(found)} runs,"
          f" {len(bad)} mismatches")
    return 1 if bad else 0


if __name__ == "__main__":   # pragma: no cover - module entry point
    sys.exit(main())
