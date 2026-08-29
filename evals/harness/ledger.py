"""The test-split ledger and its chain (docs/spec/05-eval-harness.md section 5.4).

Split out of `run.py`, which keeps the lock's decision (which cases are locked, and whether this
sweep may proceed) and passes the ledger's path in, so a sweep pointed at a sandbox writes there.
Every refusal here is an `Abort` carrying section 5.5's exit code, and no function writes anything
except `append`, which is called once per locked sweep before the first model call.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from evals.harness.plan import REPO_ROOT, Abort

ZERO_SHA = "0" * 64


def git_sha7() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError):
        return "0000000"
    return out.stdout.strip() or "0000000"


def read_lines(path: Path) -> list[str]:
    return [l for l in path.read_text(encoding="utf-8").split("\n") if l.strip()] if path.is_file() else []


def committed_lines(path: Path, repo_root: Path) -> list[str]:
    """The committed copy of the ledger, which the chain alone cannot stand in for (section 5.4).

    A forward chain proves each remaining line follows its predecessor, so an edit or a deletion in
    the middle is caught and a deletion at the end is not: drop the last two lines and every
    survivor still verifies. `results/test-runs.log` is committed precisely so there is a witness;
    this reads it. A ledger outside the working tree (a test sandbox) has none, and is skipped.
    """
    try:
        relative = path.resolve().relative_to(repo_root)
    except ValueError:
        return []
    try:
        out = subprocess.run(["git", "show", f"HEAD:{relative.as_posix()}"], cwd=repo_root,
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    return [l for l in out.stdout.split("\n") if l.strip()] if out.returncode == 0 else []


def check_chain(lines: list[str], committed: list[str]) -> None:
    """Step 2: append-only against the witness, then the forward chain over what is on disk."""
    if lines[:len(committed)] != committed:  # append-only against the witness, not only forward
        raise Abort(1, f"results/test-runs.log does not begin with its committed copy: "
                       f"{len(committed)} committed lines, {len(lines)} on disk; lines were "
                       "removed or edited")
    for index, line in enumerate(lines):  # the chain, or an edit in the middle resets the budget
        want = ZERO_SHA if index == 0 else hashlib.sha256(lines[index - 1].encode("utf-8")).hexdigest()
        if line.rsplit("|", 1)[-1].strip() != want:
            raise Abort(1, f"results/test-runs.log:{index + 1}: chain broken; expected {want}")


def check_live_budget(lines: list[str], mode: str, adr: str | None, adr_dir: Path) -> None:
    """Steps 3 and 4: two live test sweeps are the ceiling; a third needs an ADR that names one."""
    live = [l for l in lines if len(l.split("|")) > 5 and l.split("|")[5].strip() == "live"]
    if mode == "live" and len(live) >= 2:
        print("\n".join(live))
        if not adr:
            raise Abort(3, "two live test sweeps are on the record; a third needs --adr NNNN naming an ADR")
        found = sorted(adr_dir.glob(f"{adr}-*.md"))
        if not found:
            raise Abort(3, f"no ADR at {adr_dir}/{adr}-*.md")
        if "test sweep" not in found[0].read_text(encoding="utf-8"):
            raise Abort(3, f"{found[0]} does not contain the string 'test sweep'")


def append(path: Path, args: argparse.Namespace, cases: list[str], lines: list[str]) -> None:
    """One line per sweep, written before the first model call; the caller owns the replay clause."""
    reason = f"ADR {args.adr}: {args.reason}" if args.adr else str(args.reason)
    previous = hashlib.sha256(lines[-1].encode("utf-8")).hexdigest() if lines else ZERO_SHA
    fields = [datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), git_sha7(), args.arms,
              ",".join(cases), args.seeds, args.mode, reason.replace("|", "/"), previous]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(" | ".join(fields) + "\n")
