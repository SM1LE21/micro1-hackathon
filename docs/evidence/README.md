# docs/evidence/

Working notes for the qualification gate: the checks that have to pass before submission, what each
one proves, and the observed output of the last time it ran. Judge-facing claims live in `README.md`
and `REPRODUCE.md`; this directory is where the proof behind them is parked while the work is still
in progress, so that nothing in those two files is written from memory.

House rule for every page here: a check is "done" only with its command and its real output pasted
in, dated. An expectation is written as an expectation and marked as one. Pasted lines are not
rewrapped and not retyped, even where they overflow the 100-column margin; the single permitted edit
is replacing a scratch or temp directory path with `<scratch>`, marked where it happens.

## Files

| File | What it holds |
|---|---|
| `readme-markers.md` | The markers `make verify-docs` expects in README.md, the block it diffs, and the exact edit the lead makes after the sweep |
| `docker-rehearsal.md` | The Docker path: attempted 2026-08-29, no runtime on this machine; one blocker found by static review, plus the checklist the real rehearsal must satisfy |

## The evidence targets, and how each is proven

Six Makefile targets carry the gate (`docs/judging/requirements-matrix.md`:181-195, the five
qualification-gate risks; `08-plan.md`:154 and 168). Four of them must exit 0 before the freeze
rehearsal; two are author-only. `make check-secrets` runs once, before the final push; `make traces`
runs at every session boundary and last of all (`08-plan.md`:171 is its checkpoint, not its only
run).

### `make setup && make smoke` — the clean environment

The check behind the gate's largest risk: "Judge clones, runs `make setup`, and something resolves
differently" (`requirements-matrix.md`:187). `make setup` is `uv sync --locked`, which errors rather
than silently relocking; `make smoke` then asserts Python 3.12, imports the three runtime
dependencies, checks `.env.example` and the problem statement are present, validates every committed
trace, and runs the suite.

State today: passes on the host. Re-run 2026-08-29, 3.0 s wall:

```
$ make smoke
uv run python -c "import sys; assert sys.version_info[:2] == (3, 12), sys.version"
uv run python -c "import anthropic, yaml, jsonschema"
uv run python -m evals.harness.trace_check traces/
uv run pytest tests -q
652 passed, 2 skipped, 2 xfailed in 2.53s
smoke OK
```

Proven when: the same two commands exit 0 from a fresh clone in a scratch directory
(`08-plan.md`:168, Mon 06:00-06:45) **and** inside the container (`08-plan.md`:176,
Mon 14:30-15:00). Passing on the author's machine proves nothing about either; the host run above is
the baseline the two rehearsals have to match. The Docker half, including a blocker that stops
`make smoke` in the image today, is `docker-rehearsal.md`.

### `make check-traces` — the trajectories are there and the failures are indexed

Rebuilds `traces/failures/INDEX.md` from the `.diagnosis.txt` files, then asserts a non-empty
`traces/baseline/`, a non-empty `traces/advanced/`, and a committed `traces/build-trajectory.html`.

State today: it cannot pass. No sweep has run, so both trace directories hold only `.gitkeep`, and
the trajectory HTML has not been rendered. The read-only half of the first line reports the same
thing without writing:

```
$ uv run python -m evals.harness.failure_index --check
/Users/tun/Documents/micro1-hackathon/traces/failures/INDEX.md is stale (absent); run `uv run python -m evals.harness.failure_index`
(exit 1)
```

Proven when: after Sweep C, `make check-traces` prints `check-traces OK` and the regenerated
`INDEX.md` is committed with the traces it describes. Its row count is a second opinion on
`cells.failure_index`, which writes `traces/failures/README.md` from the traces themselves; the two
counts disagreeing means a diagnosis without a trace or a trace without a diagnosis.

### `make verify-docs` — the README's numbers are the harness's numbers

Regenerates the test-split tables from `results/metrics.json` and diffs them against the block
between the markers in README.md.

State today: exit 2, `no results/metrics.json`, which is the documented state before the first
sweep. The markers are already in README.md (lines 85 and 91) around a placeholder table.

Proven when: `verify-docs OK: README.md matches the test tables in metrics.json`, in the same commit
as the metrics file. The edit that gets it there, and the three prose fixes it forces, are in
`readme-markers.md`.

### `make check-clean` — nothing proprietary in the tree or the history

Greps the working tree and the full history for the forbidden name list (AGENTS.md §Competition
facts, ADR 0002).

State today: passes.

```
$ make check-clean
check-clean OK
```

Proven when: re-run at the freeze and again after the last commit before submission, since it reads
history and history keeps growing. It is cheap; run it after every rebase or squash.

### `make check-secrets` — no key ever entered the history

`gitleaks detect --source . --log-opts="--all" --redact` over every ref. Author-only: the target
refuses with an install line rather than pretending to pass.

State today: gitleaks is not installed on this machine, so the target refuses as designed.

Proven when: the author installs gitleaks (`brew install gitleaks`), runs the target before the
final push, and pastes the clean report here with its date. `.env` has been gitignored since the
first commit and `.env.example` carries names only, so a finding would be a surprise; the point is
the receipt, not the expectation.

### `make traces` — the build trajectory the judges read

Renders every Claude Code session in this directory to `traces/build-trajectory.html` with
`uvx claude-code-log@1.5.0`. Author-only. The HTML is committed, which is what makes it a
deliverable rather than a command.

**Blocker, found 2026-08-29: the guard does not guard.** `Makefile`:61-67 means to skip the render
when the transcripts are absent, but its `exit 0` ends only the first recipe line; make starts the
next line in a fresh shell and runs `uvx` anyway. On a judge's machine that reaches the network and
either errors or overwrites the committed deliverable. Two reproductions:

```
$ make -n traces CLAUDE_PROJECT_DIR=/nonexistent-dir
test -d "/nonexistent-dir" || { \
	  echo "author-only target; transcripts not present."; \
	  echo "the rendered trajectory is committed at traces/build-trajectory.html"; \
	  exit 0; }
uvx claude-code-log@1.5.0 "/nonexistent-dir" -o traces/build-trajectory.html
echo "rendered traces/build-trajectory.html"
```

`make -n` only expands, so the second proof is a replica Makefile with the same recipe shape (GNU
Make 3.81, the version on this machine), the `uvx` line replaced by an echo so nothing renders:

```
$ make traces
author-only target; transcripts not present.
the rendered trajectory is committed at traces/build-trajectory.html
SECOND RECIPE LINE RAN (stands in for uvx)
rendered traces/build-trajectory.html
$ echo $?
0
```

Recommended fix, for the lead to make (this page edits no file): collapse `Makefile`:62-66 into one
recipe line, so the guard and the render share a shell.

```make
	@if [ -d "$(CLAUDE_PROJECT_DIR)" ]; then \
	  uvx claude-code-log@1.5.0 "$(CLAUDE_PROJECT_DIR)" -o traces/build-trajectory.html \
	    && echo "rendered traces/build-trajectory.html"; \
	else \
	  echo "author-only target; transcripts not present."; \
	  echo "the rendered trajectory is committed at traces/build-trajectory.html"; \
	fi
```

That replacement was rehearsed in the same replica: with the directory absent it prints the two
guard lines and stops, with the directory present it reaches the render, and both exit 0.

After that fix the target is safe to describe as: without the transcripts the guard prints two lines
and skips the render, so it never fails or overwrites the committed HTML on a judge's machine. Until
the fix lands, that description is an expectation and not a fact, and `make traces` is not safe to
run anywhere but the author's machine.

State today: the transcript directory exists
(`~/.claude/projects/-Users-tun-Documents-micro1-hackathon/`) and the HTML has not been rendered.
`uvx` fetches the tool, so the render needs a network the first time.

Proven when: the committed HTML is newer than the last code commit (the freshness check on the
Monday 09:15 line of `08-plan.md`), and `make check-traces` finds it. Render at every session
boundary and last after the freeze, or the trajectory silently ends before the final work.

## Order before submission

1. Sweep C, `make report`, commit `results/metrics.json`.
2. Clean-clone rehearsal in a scratch directory: `git clone`, `make setup`, `make smoke`,
   `make eval-replay` (`08-plan.md`:168).
3. `make verify-docs` after the README paste.
4. `make check-traces` after the failure diagnoses and the trajectory render.
5. `make traces` last, so the trajectory covers the evidence phase itself.
6. `make check-clean` and `make check-secrets` on the final commit, both pasted here.
7. Docker rehearsal on a machine that has Docker, output pasted into `docker-rehearsal.md`.
