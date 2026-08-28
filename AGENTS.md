# micro1 Agentic Workflows Hackathon — agent guide

Canonical instructions for all agents working in this repo. `CLAUDE.md` is a pointer only.
The official problem statement lives at `docs/problem/problem-statement.pdf` (text extract alongside it). It wins over anything written here.

## Competition facts

- Event: micro1 Agentic Workflows Hackathon (HackerEarth), solo, started 2026-08-28 15:00 UTC.
- Deadline: **2026-08-31 18:00 UTC** (20:00 CEST). Submit 30+ minutes early.
- This repo was created after kickoff. Everything in it was built during the competition unless a file says otherwise.
- Rubric /100: Agent Solution & Engineering 30 · End-to-End Quality 20 · Problem & User Value 15 · Measured Improvement 15 · Reproducibility 15 · Hot Take 5.
- Qualification gate before scoring: the project must run and verify from a clean environment, with intact agent traces. Unreproducible scores zero.
- micro1 owns the submission and may train on it. Nothing proprietary (TK MEDIA, Founta, client data) enters this repo. Public or synthetic data only.

## Working Principles

- **Think Before Coding** — map every piece of work to a rubric line before starting it; work that maps to nothing is cut.
- **Simplicity First** — single-threaded agent loop, bounded steps, deterministic checks. No orchestrator fan-out, no framework unless it removes more code than it adds. Purposeful choices matter more than the number of components (the PDF says this verbatim).
- **Surgical Changes** — one variable per iteration. Never bundle a fix with a refactor.
- **Goal-Driven Execution** — the goal is a scored submission, not a product. Code freeze Sunday ~21:00 UTC (hour 30); after that only evidence work: repro, traces, writeup, video.

## The four questions (from the PDF — they structure the README and the video)

1. Who has this problem?
2. What bottleneck makes it worth solving?
3. Does the agent solve it well?
4. Can another person reproduce the result?

## Evidence discipline (non-negotiable)

- Every claim in `README.md` / `REPRODUCE.md` cites a file path, test name, or trace ID.
- `CHANGELOG_EVAL.md` uses the official four columns: Stage · What you tried and why · Evidence · Decision / learning. One entry per meaningful experiment, removed experiments included, each tied to the evidence that drove the next decision.
- Keep entries where a change made things worse. Never edit history to look monotonic.
- Failures are shipped, not hidden: `traces/failures/` with a one-line diagnosis each.
- Report `success + failure == n` explicitly. Errors are never folded into accuracy.

## Eval rules

- Eval harness and baseline are built BEFORE the advanced system.
- **One primary metric** that reflects what success means to the user, defined before running anything. Secondary rows: human time per task, cost per task (the PDF's own table), plus pass^3 and regressions.
- **10+ eval cases** minimum, one deliberately challenging case with a written note on what it revealed. Same cases for both arms; any resource difference between arms explained.
- Baseline options per the PDF: one direct prompt · one general-purpose agent with basic tools · a simple script · the manual process. Ours adds a 5-attempt retry with temperature ramp 0 → 0.3 → 0.5 so nobody can say we measured retries.
- Advanced loop closes over a **deterministic verifier** (tests, schema checks, fetch-and-confirm, rule engine). LLM-as-judge only for free text, with tolerance bands, order-swapped, "Unknown" allowed.
- Dev/test split. Iterate on dev only; test is touched twice (baseline once, final once).
- 3 runs per arm, seeds fixed, mean ± std. Temperature 0 is not determinism; say so in REPRODUCE.md.
- Output quality bar (worth 20 points): the final artifact must have "the finish of something a person would sign their name to rather than an obvious AI generated draft." `docs/writing-rules.md` applies to the product's user-facing output.

## Trace rules

- Every Claude Code work session runs in THIS directory, named (`claude -n "<day>-<focus>"`), reattached with `--continue`. The transcript is a deliverable — treat it as an always-on camera.
- Runtime agent traces (the product's own loop): JSONL, one step per line with reasoning, tool calls, tool responses linked back to their call id, per-step token and cost counts, run-level stop condition and tool-call count. Both arms traced, failures included.
- Human checkpoints appear IN the trace as tool calls, annotated with the risk rating that triggered them.
- Short disciplined runs beat long ones. Turns and tool calls are reported metrics, not hidden costs.

## Code rules

- Python 3.12, uv with committed lockfile. Max ~300 lines/file, one responsibility per file, no dead code, lean over clever.
- Consequential actions run sandboxed or simulated; human approval before anything irreversible (PDF ground rule 04). A qualified human reviewer is part of any flow that could significantly affect someone (rule 05).
- No secrets anywhere: `.env.example` carries names only; run gitleaks over full history before final push.

## Decision logging

- Architecture decisions → `.vault/adr/NNNN-title.md` (one per decision, template in the folder).
- Problem-statement ambiguities → `.vault/AMBIGUITIES.md` (both readings, chosen one, why).
- Deliberate exclusions → `.vault/NON-GOALS.md`.
- Open questions for Tun → `.vault/QUESTIONS.md`.
- Session state → `.vault/STATUS.md` (update at end of every work block).
- Project history → `CHANGELOG.md` (`## YYYY-MM-DD HH:MM — Title` + up to 4 bullets).

## Commits

- `<type>(<scope>): <lowercase summary, no trailing period>` — feat|fix|refactor|chore|docs|test.
- Micro-commit every file change. No batching. Under-committing is treated as a defect.
- `docs(changelog)` for CHANGELOG_EVAL.md rows; `docs(vault)` for `.vault/` updates.
- Keep the Claude co-author trailer on agent commits — it doubles as the required coding-agent disclosure.

## Deliverables checklist (all four required)

1. Complete solution code + improvement changelog (README opens with the four questions; closes with main failure mode + hot take).
2. Reproduction guide (`REPRODUCE.md`): clean-environment setup, exact commands for solution, baseline and evaluation, data needed, expected output, versions, approximate runtime and cost.
3. Solution video ≤5 min (target 3:00–3:30): problem + baseline first, one realistic execution start to finish, final comparison table on screen, changelog highlights, the change that contributed most, one removed experiment.
4. Agent trajectories: representative, easy to follow from instructions to final result, tool responses included, retries and human checkpoints visible. Rendered build trajectory via `make traces`.
