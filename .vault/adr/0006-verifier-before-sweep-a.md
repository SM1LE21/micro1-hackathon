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

Addendum 2026-08-29 (before any cache exists, so nothing is invalidated): two frozen files changed after the independent audit — `art30/config.py` now reads `ART30_TRACE_DIR` (the harness seam it was always meant to honour; without it `make gate-timing` overwrote committed traces), and `art30/loop.py` treats `stop_reason: model_context_window_exceeded` as an early stop. Neither changes a hashed byte of any request. The frozen-list check in this ADR now runs from the commit that lands this addendum.

Addendum 2026-08-29 (still before any cache exists): ADR 0007 adds `"file"` to the `approve` literal in `art30/config.py` and the matching CLI choice, for the website's gate. No request byte changes; the frozen-list check runs from the commit that lands it.

Addendum 2026-08-30 (still before any cache exists): `art30/loop.py` now records the full feedback of every rejected `submit_record` attempt and the accepted attempt's `unverified`/`conservative_divergences` lists, and takes `verification.rule_set_sha` from the arm (the advanced arm exposes a sha over its five rule files; the baseline has none). Before this, every advanced record rendered "Verification: none. This record was accepted on schema validity alone." — the signed document contradicting itself. `record.json` is an output; no request byte changes.

Addendum 2026-08-30 (ADR 0008; still before any recording): `art30/config.py` gains `brain`, `brain_model`, `max_turns` and reads through `art30/settings.py`. The API brain's hashed request bytes are unchanged; `tests/test_llm.py`'s step-1 hash constant is the check.
