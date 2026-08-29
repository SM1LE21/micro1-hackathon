"""Check a drafted record against the repository it claims to describe.

    python verify.py --repo <path> --record art30-record.json [--json]

Schema and the ten handler invariants first, then `art30.verify.check`, which walks
the call graph and answers one question per claim: starting at an erasure entry
point, does anything actually reach this store? The printed block is the one the
`art30` CLI prints inside its own loop, minus the attempt counters, which belong to
a run with a submission budget and not to a person editing a file.

Exit 0 accepted, 1 rejected, 2 the script could not run at all.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

USAGE_EXIT = 2
KEYS = (
    "schema_errors",
    "rejected_claims",
    "missing_stores",
    "missing_entry_points",
    "bad_citations",
    "unverified",
    "conservative_divergences",
)
INSTALL = """This script reads the `art30` package; {reason}.

Run it against an art30 checkout:

  uv run --project /path/to/art30 python {script} --repo . --record ./art30-record.json

or install the package into the environment you run it with:

  uv tool install /path/to/art30      (also gives you the `art30` command)
  uv pip install /path/to/art30

README.md beside this script carries both routes."""
# `art30.verify.rules` loads the scorer's norm() from `evals/harness/score.py`, which
# a wheel does not carry. Naming the file is the difference between "reinstall" and
# an hour spent guessing (reported to the lead; the fix is in the package, not here).
PACKAGING = (
    "it imported, but {path} is not there, so the verifier cannot load the one"
    " implementation of norm() it shares with the scorer"
)


def die(message: str) -> int:
    print(message, file=sys.stderr)
    return USAGE_EXIT


def load():
    """The three entry points this script needs, or a message that names the fix."""
    try:
        from art30 import cli
        from art30.arm import Feedback, validate
        from art30.verify.check import check
    except ModuleNotFoundError as exc:
        raise SystemExit(
            die(INSTALL.format(reason=f"{exc.name} is not importable", script=__file__))
        ) from None
    except FileNotFoundError as exc:
        raise SystemExit(
            die(INSTALL.format(reason=PACKAGING.format(path=exc.filename), script=__file__))
        ) from None
    return cli, Feedback, validate, check


def read_record(path: Path) -> dict:
    """The submitted record. A rendered one carries two extra keys; they are dropped."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("the record is not a JSON object")
    return {key: value for key, value in data.items() if key not in ("provenance", "verification")}


def block(cli, feedback) -> str:
    """The CLI's own verify block. One line is dropped: a skill run has no attempts."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli._verify_block(_Surface(), feedback)
    kept = [
        line for line in buffer.getvalue().splitlines() if not line.startswith("  attempts left:")
    ]
    if not feedback.accepted:
        kept += ["", "Each item above is one edit. Make them, then run this command again."]
    return "\n".join(kept).strip("\n")


class _Surface:
    """What `_verify_block` reads off the arm: the label in front of the summary."""

    verify_label = "skill"


def payload(feedback) -> dict:
    return {"accepted": feedback.accepted} | {key: getattr(feedback, key) for key in KEYS}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify.py", description="Check a drafted art30 record against the code."
    )
    parser.add_argument("--repo", required=True, help="the repository the record describes")
    parser.add_argument("--record", required=True, help="path to the drafted record JSON")
    parser.add_argument("--json", action="store_true", help="print the feedback object instead")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cli, Feedback, validate, check = load()
    repo = Path(args.repo)
    record_path = Path(args.record)
    if not repo.is_dir():
        return die(f"not a directory: {args.repo}")
    if not record_path.is_file():
        return die(f"no record at {args.record}")
    try:
        record = read_record(record_path)
    except (ValueError, UnicodeDecodeError) as exc:
        return die(f"{args.record} is not a readable record: {exc}")

    errors = validate(record)
    feedback = (
        Feedback(accepted=False, schema_errors=errors)
        if errors
        else check(record, repo.resolve())
    )
    if args.json:
        print(json.dumps(payload(feedback), indent=1, sort_keys=True, ensure_ascii=False))
    else:
        print(block(cli, feedback))
    return 0 if feedback.accepted else 1


if __name__ == "__main__":
    sys.exit(main())
