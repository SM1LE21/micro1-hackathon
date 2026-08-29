# ADR 0006 — Verifier code before Sweep A, with the baseline frozen

status: accepted
date: 2026-08-29

## Decision

The verifier (`art30/verify/`), its tests and `advanced/arm.py` are written before Sweep A has run, because no API credential exists on the build machine at 2026-08-29 01:00 UTC and Sweep A cannot start until one does. To keep the measurement rule that AGENTS.md and `08-plan.md` §1.2 protect ("harness and baseline before the advanced system"):

1. The baseline arm and every byte the two arms share are **frozen at the commit that lands this ADR**: `baseline/arm.py`, `art30/prompts/*`, `art30/schema/record.schema.json`, `art30/tools.py` (the tool schemas), `art30/loop.py`, `art30/llm.py`, `art30/config.py`. A later change to any of them is a new `CHANGELOG_EVAL.md` row and re-records every sweep it precedes (`08-plan.md` §3).
2. `git log` keeps the build order: every harness and baseline commit precedes the first commit under `art30/verify/` and `advanced/`.
3. No advanced-arm run is made against any evaluation case, live or replay, before Sweep A is recorded. Offline tests with a scripted model on fixture copies are allowed; they produce no results and no traces under `results/` or `traces/`.
4. Sweep A runs the moment a key is available, before any advanced sweep, and its changelog row is written before the first advanced number.

## Context

`08-plan.md` §1 schedules `tests/verify/**` after Sweep A and its changelog row. The purpose of that ordering is that the advanced system is not tuned against a baseline that does not yet exist and that the baseline is not adjusted after the advanced arm is seen. Both purposes are served by freezing the shared bytes and the baseline arm now; the code order in git is unchanged. Waiting for the key would idle the build for the hours the schedule has no slack for (`08-plan.md` §Open risks 1).

## Options considered

- Wait for the key — loses the night; Saturday is already over-subscribed.
- Write only `tests/verify/**` and stop — the tests are most of the verifier's design work; stopping there buys little.

## Consequences

- The frozen-file list is checked before Sweep A: `git log --oneline <this commit>.. -- baseline/arm.py art30/prompts art30/schema art30/tools.py art30/loop.py art30/llm.py art30/config.py` must be empty, or the change is a changelog row.
- The plan's kill switch 1 (verifier not passing its rule tests) moves earlier and loses none of its meaning.
