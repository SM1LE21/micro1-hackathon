"""Generate the skill package from the prompt files (ADR 0007 item 1).

`SKILL.md` is not written by hand: its instruction half is `art30/prompts/system.md`
with `taxonomy.md` spliced in, the same bytes `art30/llm.py` sends as the system
prompt, so the skill a user installs is the baseline arm the eval measures.
`AGENTS.md.include` carries the same instruction text without the Claude Code
frontmatter, and with the paragraph that locates `SKILL_DIR` rewritten for a file that
has been appended to someone's `AGENTS.md`. `resources/record.schema.json` is a byte
copy of the schema both arms validate against.

    uv run python skill/build.py            write the three generated files
    uv run python skill/build.py --check    exit 1 when the committed files differ

Two runs produce the same bytes: nothing here reads a clock, a path outside the
repository, or an environment variable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # `uv run python skill/build.py` puts skill/ on the path
    sys.path.insert(0, str(ROOT))

from art30.llm import system_prompt  # noqa: E402  (after the path is set)
from art30.tools import SCHEMA_PATH  # noqa: E402

OUT = ROOT / "skill" / "art30"
MARKER = "<!-- art30 instruction text, generated from art30/prompts — do not edit here -->"

FRONTMATTER = """---
name: art30
description: Draft the technical half of a GDPR Article 30(1) record of processing for a Python repository, with an erasure verdict per store, then check every claim against the code with a static verifier that reads the call graph. Use when someone asks what personal data a repository holds, where it goes, or whether closing an account actually deletes it.
---

"""

CODEX = "<!-- Codex reads AGENTS.md; append this file to yours. -->\n\n"

INTRO = """# art30

One Python repository in, two things out: the technical half of a record of
processing under Article 30(1) GDPR, and an erasure table that says, store by
store, whether closing an account reaches the data.

## How this skill works

"""

# Where the files this text names actually are, once each surface has installed it.
CLAUDE_WHERE = """`SKILL_DIR` below is the directory this file sits in.
`resources/record.schema.json`, `scripts/verify.py`, `scripts/render.py`,
`hooks/settings.example.json` and `README.md` are all beside this file.

"""

CODEX_WHERE = """`SKILL_DIR` below is `skill/art30/` in an art30 checkout. The files named here
(`resources/record.schema.json`, `scripts/verify.py`, `scripts/render.py`,
`hooks/settings.example.json`, `README.md`) live there and not beside this text,
which was appended to your `AGENTS.md`.

"""

BODY = """Read the repository. Do not run it, do not install it, do not import it: every
claim in the record comes from source you read, so Read, Grep and Glob are the
only tools that touch the repository. Bash runs the two scripts in steps 3 and 5,
and nothing else.

1. Follow the instruction text at the end of this file. It carries the method:
   what counts as personal data, what a store is, how each erasure verdict is
   decided, and which cells you never fill.
2. Write the record as JSON to `./art30-record.json`, matching
   `SKILL_DIR/resources/record.schema.json`.
3. Check the claims against the code:

   ```bash
   python SKILL_DIR/scripts/verify.py --repo . --record ./art30-record.json
   ```

   The script needs the `art30` package; where it cannot import it, it prints the
   command that installs it, and `SKILL_DIR/README.md` carries both install routes.

4. Every item the verifier prints is one edit: change what it names, or make the
   single read that settles it, and leave alone the parts it said nothing about.
   Run the command again. Repeat until it prints `accepted`.
5. Render the record for the person who signs it:

   ```bash
   python SKILL_DIR/scripts/render.py --repo . --record ./art30-record.json
   ```

   That writes `art30-record.md` and `art30-record.html` beside the record.
6. The legal cells stay empty. Controller identity and contact, the DPO,
   purposes, legal basis, recipient kind, transfers and their safeguards, the
   justification for a retention period, the grouping of stores into activities:
   the schema types every one of them null, and the render prints "requires
   human completion" in each. A purpose inferred from a module name is the most
   harmful sentence this document could carry.

The verifier reads the repository the same way you did, with Python's `ast`. It
is advisory here: nothing stops you submitting a record it rejects, which is why
step 4 is yours to run. `SKILL_DIR/hooks/settings.example.json` turns it into a
gate.

The instruction text below is the eval's, byte for byte, and it was written for
the `art30` CLI. Read it with three substitutions. Where it says `submit_record`,
this surface means steps 2 and 3: write the file, then run `verify.py`. Where it
says `read_file` and `grep`, use Read and Grep. There is no first message carrying
a budget and no count of attempts left, so read "the number of attempts left" as
"run the command again".

"""


def skill_md() -> str:
    return FRONTMATTER + INTRO + CLAUDE_WHERE + BODY + MARKER + "\n\n" + system_prompt()


def agents_include() -> str:
    return CODEX + INTRO + CODEX_WHERE + BODY + MARKER + "\n\n" + system_prompt()


def generated() -> dict[str, str]:
    """Every file this script owns, relative to `skill/art30/`."""
    return {
        "SKILL.md": skill_md(),
        "AGENTS.md.include": agents_include(),
        "resources/record.schema.json": SCHEMA_PATH.read_text(encoding="utf-8"),
    }


def write(out: Path) -> list[str]:
    written: list[str] = []
    for name, text in generated().items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        written.append(name)
    return written


def stale(out: Path) -> list[str]:
    """The generated files whose committed bytes are not what this run produces."""
    differs: list[str] = []
    for name, text in generated().items():
        target = out / name
        if not target.is_file() or target.read_bytes() != text.encode("utf-8"):
            differs.append(name)
    return differs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill/build.py", description="Generate skill/art30 from art30/prompts."
    )
    parser.add_argument("--check", action="store_true", help="report drift, write nothing")
    parser.add_argument("--out", default=None, help="target directory (default skill/art30)")
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else OUT
    if args.check:
        differs = stale(out)
        if differs:
            print(
                "the committed skill package is out of date: "
                + ", ".join(differs)
                + "\nrun: uv run python skill/build.py",
                file=sys.stderr,
            )
            return 1
        print(f"skill package up to date ({out})")
        return 0
    for name in write(out):
        print(f"  {out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
