"""Render a drafted record as the document its reader signs.

    python render.py --repo <path> --record art30-record.json

Writes `<record>.md` and `<record>.html` beside the record, through the same
renderer the `art30` CLI calls, so the skill's output and the CLI's are the same
document. The record itself is not rewritten.

A record drafted by hand carries no provenance: no run id, no cost, no trace, no
model. Those rows render as `skill run` and `n/a` rather than as blanks, so the
reader can see what the document does and does not know about its own making.
Where the record already carries a `provenance` block (one written by `art30
scan`), that block is kept and nothing is invented over it.

Exit 0 written, 1 the record does not render, 2 the script could not run at all.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

USAGE_EXIT = 2
INSTALL = """This script reads the `art30` package; {reason}.

Run it against an art30 checkout:

  uv run --project /path/to/art30 python {script} --repo . --record ./art30-record.json

or install the package into the environment you run it with:

  uv tool install /path/to/art30      (also gives you the `art30` command)
  uv pip install /path/to/art30

README.md beside this script carries both routes."""
PACKAGING = (
    "it imported, but {path} is not there, so the verifier cannot load the one"
    " implementation of norm() it shares with the scorer"
)
# What a run records and a hand-drafted record cannot. `render/markdown.py` prints
# each of these verbatim, so the words below are the words on the page.
VERIFICATION = {
    "submits": "no",
    "accepted_on_attempt": "n/a",
    "rejected_history": [],
    "missing_stores_resolved": [],
    "bad_citations_resolved": [],
    "unverified": [],
    "rule_set_sha": None,
}


def die(message: str) -> int:
    print(message, file=sys.stderr)
    return USAGE_EXIT


def load():
    try:
        from art30 import llm
        from art30.arm import validate
        from art30.render import RenderError, relative, stamp, tree_sha
        from art30.render.html import render_html
        from art30.render.markdown import render_markdown
    except ModuleNotFoundError as exc:
        raise SystemExit(
            die(INSTALL.format(reason=f"{exc.name} is not importable", script=__file__))
        ) from None
    except FileNotFoundError as exc:
        raise SystemExit(
            die(INSTALL.format(reason=PACKAGING.format(path=exc.filename), script=__file__))
        ) from None
    return {
        "llm": llm, "validate": validate, "RenderError": RenderError, "relative": relative,
        "stamp": stamp, "tree_sha": tree_sha, "html": render_html, "markdown": render_markdown,
    }


def provenance(api: dict, repo: Path) -> dict:
    """The provenance a skill run can evidence: the code read and the instructions."""
    return {
        "arm": "skill",
        "model": "not recorded",
        "effort": "n/a",
        "run_id": "skill run",
        "case": "skill run",
        "seed": None,
        "mode": "skill",
        "instruction_sha256": api["llm"].prompt_sha()[:12],
        "fixture": {"id": repo.name, "path": api["relative"](repo), "sha256": api["tree_sha"](repo)},
        "started_at": None,
        "finished_at": api["stamp"](),
        "trace": "none",
        "cost_usd": "n/a",
        "tool_calls": "no",
        "gate": None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="render.py", description="Render an art30 record as Markdown and HTML."
    )
    parser.add_argument("--repo", required=True, help="the repository the record describes")
    parser.add_argument("--record", required=True, help="path to the record JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    api = load()
    repo = Path(args.repo)
    record_path = Path(args.record)
    if not repo.is_dir():
        return die(f"not a directory: {args.repo}")
    if not record_path.is_file():
        return die(f"no record at {args.record}")
    try:
        raw = json.loads(record_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return die(f"{args.record} is not a readable record: {exc}")

    record = {k: v for k, v in raw.items() if k not in ("provenance", "verification")}
    errors = api["validate"](record)
    if errors:
        print("this record does not validate, so it is not rendered:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    record["provenance"] = raw.get("provenance") or provenance(api, repo)
    record["verification"] = raw.get("verification") or dict(VERIFICATION)
    try:  # both documents are built before either is written, as `render_all` does
        text = api["markdown"](record)
        page = api["html"](record, repo.resolve())
    except api["RenderError"] as exc:
        print(f"{exc} Nothing written.", file=sys.stderr)
        return 1
    markdown_path = record_path.with_suffix(".md")
    html_path = record_path.with_suffix(".html")
    markdown_path.write_text(text, encoding="utf-8")
    html_path.write_text(page, encoding="utf-8")
    print(f"  {markdown_path}\n  {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
