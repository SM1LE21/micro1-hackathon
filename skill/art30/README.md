# art30, packaged as a skill

`SKILL.md` is the instruction text that reads one Python repository and drafts the
technical half of a record of processing under Article 30(1) GDPR, with an erasure
verdict per store. Two scripts sit beside it: `scripts/verify.py` checks the drafted
record against the code, and `scripts/render.py` turns it into the Markdown and HTML
document a founder signs.

The instruction half of `SKILL.md` is generated from `art30/prompts/system.md` and
`taxonomy.md` by `make skill`, and `tests/test_skill.py` asserts it byte for byte
against what `art30/llm.py` sends as the system prompt.

## Install

1. Copy this directory where Claude Code looks for skills:

   ```bash
   cp -R skill/art30 ~/.claude/skills/art30      # every project
   cp -R skill/art30 .claude/skills/art30        # one project
   ```

2. Give the two scripts the `art30` package. From a checkout of this repository:

   ```bash
   uv run --project /path/to/art30 python ~/.claude/skills/art30/scripts/verify.py \
       --repo . --record ./art30-record.json
   ```

   Or install the package into the environment you run the scripts with:

   ```bash
   uv tool install /path/to/art30      # also puts the `art30` command on PATH
   uv pip install /path/to/art30       # into an environment you activate yourself
   ```

   One caveat about the installed route, today: `art30/verify/rules.py` loads the
   scorer's `norm()` from `evals/harness/score.py` so the metric and the verifier
   cannot drift, and the wheel does not carry that file. A wheel-installed `art30`
   therefore imports, and `art30.verify` does not. Both scripts print the missing
   path and the command that fixes it rather than a traceback. Until the package
   ships that function, run the scripts against a checkout with `uv run --project`.

Nothing here needs an API key, a network, or the repository under test to be
runnable: the verifier reads source with Python's `ast`, like the skill itself.

## The three commands

**Draft.** Ask Claude Code for an Article 30 record of the repository you are in.
The skill's own steps take it from there: it reads the code, writes the record to
`./art30-record.json` against `resources/record.schema.json`, and leaves the legal
cells null.

**Check.**

```bash
python scripts/verify.py --repo . --record ./art30-record.json [--json]
```

Schema and the ten handler invariants first, then the call-graph check: for each
store the record claims is erased, is there a path from an erasure entry point to a
deletion primitive for that store? Output is the block the `art30` CLI prints, minus
the attempt counters, which belong to a run with a submission budget:

```
[verify] skill · 1 rejected claims · 1 missing entry points
  REJECT   uploads · erasure.verdict=erased
           no path from entry point close_account (api/account.py:12) to any object-storage
           deletion primitive; cleanup_user_files (storage.py:29) is defined but has no callers
           expected: verdict not_erased, or cite the path
  ENTRY    purge_closed_accounts · task
           expected: declare purge_closed_accounts as an entry point, or say in its note why
           it is not one

Each item above is one edit. Make them, then run this command again.
```

That is the S10 fixture with one claim changed, the case `tests/test_skill.py` drives.
The two long lines are one line each on a terminal; only this page wraps them.

Exit 0 accepted, 1 rejected, 2 the script could not run (bad path, unreadable
record, `art30` not importable). `--json` prints the feedback object instead: the
`accepted` flag and the seven lists, sorted keys, for a wrapper to read.

`REJECT`, `MISSING` and `CITE` items block acceptance. `ENTRY`, `UNVERIFIED` and
`SAFER` items print on an accepted record too: an entry point the record walked
past, a claim the source could not settle, a verdict more conservative than the
evidence.

**Render.**

```bash
python scripts/render.py --repo . --record ./art30-record.json
```

Writes `art30-record.md` and `art30-record.html` beside the record, through the same
renderer the CLI calls. The record itself is not rewritten. The HTML is one file
with no script and no external stylesheet; every citation carries the source line it
points at, and it prints on A4.

A hand-drafted record carries no provenance, so the header table says what it does
not know rather than leaving the rows blank:

| Row | A skill run renders |
|---|---|
| Run | `skill run` |
| Case | `skill run (synthetic)` |
| Model, effort | `not recorded`, `n/a` |
| Cost | `USD n/a, no tool calls` |
| Trace | `none` |
| Verification | `no submissions, accepted on attempt n/a` |
| Code read | the repository path and a sha256 over its files, both real |
| Instructions | the first twelve hex of the sha256 of the instruction text, real |

The bracket on the Case row is the eval's own fixture label, which the renderer prints
for every record. It says nothing about your repository.

Section G of the rendered record reads "Verification: none. This record was accepted
on schema validity alone." The renderer is told nothing about whether you ran
`verify.py`; the CLI fills that section from its own loop, which is the difference
the eval measures. Where the record already carries a `provenance` block, one
written by `art30 scan`, that block is kept and nothing is invented over it.

## The hook

`hooks/settings.example.json` turns the advisory verifier into a gate on your own
session: a `Stop` hook that runs `verify.py` whenever `./art30-record.json` exists
and blocks the session from ending while the record is rejected, with the verifier's
own output as the reason.

Copy the `hooks` block into `.claude/settings.json` (one project),
`.claude/settings.local.json` (one project, not committed) or `~/.claude/settings.json`
(every project), and replace the two absolute paths with your art30 checkout and
this directory. Exit codes carry the decision: the hook exits 0 when the record is
accepted or absent, 2 when it is rejected, which is what blocks the stop and hands
the output back to Claude, and 1 on a usage error, which shows a notice and lets the
session end.

The hook blocks once per rejection and gives up after three, so a claim the verifier
cannot settle does not trap the session; remove the hook or press Esc to stop it
sooner. The count lives in `.art30-hook-attempts` beside the record, and the hook
deletes it the moment the record is accepted, gone, or has cost three blocks. Without
that bound a `Stop` hook that exits 2 runs again on the next attempt to stop, and two
ordinary situations never end: a record the verifier keeps rejecting, and a stale
`art30-record.json` left in a project, which would block every later session with an
art30 rejection as the reason. Add `.art30-hook-attempts` to `.gitignore`.

Shape and semantics from the Claude Code hooks documentation
(<https://code.claude.com/docs/en/hooks>, read 2026-08-30): the `hooks.Stop[].hooks[]`
array with `type: "command"`, `Stop` taking no matcher, `${CLAUDE_PROJECT_DIR}` as
the project root in the hook's environment, exit code 2 blocking the stop with the
message from stderr, any other non-zero code being a non-blocking error, and the
page's own warning that a `Stop` hook must not block unconditionally.

## What this is

The baseline arm of the eval, packaged. The eval's baseline is this instruction text
with basic file tools and no verifier in the loop; the advanced arm is the same text
with the verifier inside the submission handler and a human checkpoint before the
render. `SKILL.md` carries the baseline's instruction bytes, so the baseline row in
`results/metrics.json`, once `make eval-replay` has written it, is the closest
measurement this repository has of what this text does on its own: measured through
the CLI's four tools and its budgets, not in a Claude Code session. The gap from that
row to the advanced arm is what the closed loop is worth.

`verify.py` hands you the advanced arm's verifier as a command you run yourself.
Which leaves three things the CLI does that the skill does not:

- **The gate is advisory.** Nothing makes you run `verify.py`, and nothing stops a
  record it rejected from being rendered and signed. The `Stop` hook above is the
  only thing here that closes the loop, and it closes it in your session, not in the
  tool. In the CLI the verifier runs inside `submit_record`: the model cannot see an
  acceptance it did not earn, and a human approves the record before it renders.
- **No trace.** A CLI run writes a JSONL trace: one line per step with the model's
  reasoning summary, every tool call and result, tokens and cost per step, the
  checkpoint, the stop condition. A skill run leaves the record and whatever your
  session transcript happens to hold.
- **No replay.** `art30 scan --mode replay` reproduces a recorded run from the
  committed cache, byte for byte, with no API key. Nothing here can be replayed, and
  nothing here is measured: the skill sits outside the eval it comes from.

Budgets go with them. The CLI stops at 60 tool calls and five submission attempts
and reports which it hit; a session has neither.

## Codex

`AGENTS.md.include` is the same instruction text without the Claude Code
frontmatter. Its opening paragraph differs from `SKILL.md`'s in one way: appended to
your `AGENTS.md`, nothing is beside it, so the paragraph points `SKILL_DIR` and the
files it names at `skill/art30/` in your art30 checkout. Codex reads `AGENTS.md`, so
append the file to yours:

```bash
cat skill/art30/AGENTS.md.include >> AGENTS.md
```

The two scripts are plain Python and need no Claude Code. Whether Codex has a skill
mechanism of its own is not something this repository has checked, and the include is
what it ships until it does.
