"""`make verify-docs`: the README's results block against the tables `make report` generates.

The README quotes numbers a reader cannot recompute by eye. This module re-runs `report.py`'s own
table generation over `results/metrics.json` — the same `tables.markdown` the report writes, so a
change to a row's format string changes both sides at once — and diffs the two tables it produces
for one split against the block the README carries between its markers.

    uv run python -m evals.harness.verify_docs

Exit codes (05-eval-harness.md section 5.5's shape: a refusal is a code, never a traceback):

    0  the README block equals the generated block
    1  they differ; a unified diff is printed
    2  the comparison could not be made: no `results/metrics.json` (the state today, before the
       first sweep), no README, no markers in it, or a metrics file that is not a report

The markers. README.md carries none at the time of writing, so this module defines them:

    <!-- metrics:begin -->
    ... the three-row table, a blank line, the secondary table ...
    <!-- metrics:end -->

The block between them is exactly the two generated tables and nothing else — prose about them
belongs outside the markers, or every sentence an author adds reads as a diff. Trailing whitespace
and blank lines at the two ends are ignored; everything else must match byte for byte.

This module never writes README.md. `--emit` prints the block for the author to paste.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

from evals.harness.plan import REPO_ROOT
from evals.harness.tables import markdown

BEGIN = "<!-- metrics:begin -->"
END = "<!-- metrics:end -->"
DEFAULT_METRICS = "results/metrics.json"
DEFAULT_README = "README.md"
SPLITS = ("dev", "test")

MARKER_HELP = (
    f"README.md carries no {BEGIN} / {END} pair. Add one around the results tables:\n"
    f"    {BEGIN}\n"
    "    | Metric | Simple baseline | Agent solution | Change |\n"
    "    ... the three-row table, a blank line, then the secondary table ...\n"
    f"    {END}\n"
    "and keep the surrounding prose outside the markers."
)


class Blocked(Exception):
    """The comparison cannot be made; exit 2, with the reason on stderr."""


def normalise(text: str) -> str:
    """Trailing whitespace per line and blank lines at the two ends carry no information."""
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip("\n")


def read_metrics(path: Path) -> dict:
    if not path.is_file():
        raise Blocked(
            f"no {path}: nothing to verify the README against yet. Run `make eval-replay` (or "
            "`make report`) first; before the first sweep this is the expected state.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Blocked(f"cannot read {path}: {exc}") from None
    if not isinstance(value, dict):
        raise Blocked(f"{path} is not a metrics object")
    return value


def tables_for(text: str, split: str) -> list[str]:
    """The Markdown table blocks under `## <split>` in a generated report, in order."""
    lines = text.split("\n")
    try:
        start = lines.index(f"## {split}")
    except ValueError:
        raise Blocked(f"the generated report carries no '## {split}' section") from None
    blocks: list[str] = []
    current: list[str] = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if line.startswith("|"):
            current.append(line.rstrip())
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def generate(metrics: dict, split: str) -> str:
    """The two tables section 7.1 and section 7.2 define, blank line between, for one split."""
    if split not in SPLITS:
        raise Blocked(f"unknown split {split!r}; expected one of {', '.join(SPLITS)}")
    try:
        report = markdown(metrics)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise Blocked(f"metrics file is not a report ({type(exc).__name__}: {exc})") from None
    blocks = tables_for(report, split)
    if len(blocks) < 2:
        raise Blocked(
            f"the generated '## {split}' section holds {len(blocks)} table(s), not the three-row "
            "table and the secondary table; report.py and this checker have drifted apart")
    return normalise(blocks[0] + "\n\n" + blocks[1])


def extract(readme: Path) -> str:
    """The block between the markers. A README without them is exit 2, never a silent pass."""
    if not readme.is_file():
        raise Blocked(f"no {readme}")
    text = readme.read_text(encoding="utf-8").replace("\r\n", "\n")
    if BEGIN not in text or END not in text:
        raise Blocked(f"{readme}: {MARKER_HELP}")
    head, _, rest = text.partition(BEGIN)
    body, _, _ = rest.partition(END)
    if BEGIN in body or END in head:
        raise Blocked(f"{readme}: the markers are out of order or nested")
    return normalise(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evals.harness.verify_docs",
        description="diff the README results block against the tables make report generates")
    parser.add_argument("--metrics", default=DEFAULT_METRICS)
    parser.add_argument("--readme", default=DEFAULT_README)
    parser.add_argument("--split", default="test", choices=SPLITS)
    parser.add_argument("--emit", action="store_true",
                        help="print the block the README must carry and stop; writes nothing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    metrics_path = Path(args.metrics)
    readme_path = Path(args.readme)
    if not metrics_path.is_absolute():
        metrics_path = REPO_ROOT / metrics_path
    if not readme_path.is_absolute():
        readme_path = REPO_ROOT / readme_path
    try:
        expected = generate(read_metrics(metrics_path), args.split)
        if args.emit:
            print(f"{BEGIN}\n{expected}\n{END}")
            return 0
        found = extract(readme_path)
    except Blocked as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if expected == found:
        print(f"verify-docs OK: {readme_path.name} matches the {args.split} tables in "
              f"{metrics_path.name}")
        return 0
    lines = difflib.unified_diff(
        expected.split("\n"), found.split("\n"),
        fromfile=f"generated from {args.metrics} ({args.split})",
        tofile=f"{args.readme} between {BEGIN} and {END}", lineterm="")
    print("\n".join(lines))
    print(f"\nthe {args.split} tables in {args.metrics} and the block in {args.readme} differ; "
          "regenerate with `--emit` and paste the block between the markers", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover - module entry point
    sys.exit(main())
