# ADR 0005 — Plan amendments: kill switch 2, code freeze, one-window test sweep

status: accepted
date: 2026-08-28

## Decision

1. **Kill switch 2 (ADR 0002) is amended.** At Saturday 2026-08-29 18:30 UTC, if no baseline number exists on the dev set, the action is to narrow Sweep A to the seven synthetic dev cases (S01–S07) and continue, not to switch problem domain. The domain fallback is withdrawn: the research, specs and fixtures now carry more value than a restart could recover.
2. **Code freeze moves to Sunday 2026-08-30 19:30 UTC**, with 21:00 UTC as the backstop, so both reported sweeps run against frozen code and the seven-hex sha in every `run_id` resolves to the submitted tree.
3. **The test split is swept live once, both arms in one recording window** (Sweep C), and the second ledger slot is held for a re-record. `01-architecture.md` §4.2 refuses to report two arms recorded in non-overlapping windows, which makes a Saturday baseline-only test sweep unreportable. The baseline arm is frozen from Saturday 18:15 UTC and unchanged, so its test cases are uncontaminated by running later. `evals/CASES.md` carries a dated errata line.
4. **Live-API ceiling for the weekend: $300**, an assumption the author may change (QUESTIONS.md Q5). Hard stop before Sweeps B and C is $300 minus their measured cost, re-derived at the Saturday 15:15 UTC calibration.

## Context

`docs/spec/08-plan.md` §3, §4 and §Questions for the author. Each item was deferred to the author by the plan; the lead takes them so the build can start, and records them here so the author can revert any with one edit.

## Options considered

- Keep the domain switch as the Saturday fallback — a restart on Saturday evening cannot rebuild the eval, the research and the artefact target in the time left; narrowing keeps the measured comparison.
- Keep the 21:00 freeze — leaves no window for both sweeps against frozen code before Sunday night's evidence work.
- Two live test sweeps (baseline Saturday, final Sunday) — unreportable under the window rule; also spends the re-record slot.

## Consequences

- AGENTS.md's code-freeze line and `.vault/STATUS.md`'s checkpoint table follow this ADR.
- `results/test-runs.log` will show one `live` line for Sweep C and, if used, one re-record; a third needs an ADR.
- If the author sets a ceiling other than $300, `08-plan.md` §3's iteration count is re-derived from the Saturday calibration.
