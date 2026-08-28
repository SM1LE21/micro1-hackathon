# STATUS

status: active
last_updated: 2026-08-28 16:02 UTC

## Where we are

- Hour ~1 of 75 (kickoff 2026-08-28 15:00 UTC; deadline 2026-08-31 18:00 UTC; the earlier "67" was a miscount).
- Direction chosen and recorded: GDPR Art. 30 inventory + erasure-path check, closed over an `ast` reachability verifier (`adr/0002`). Baseline is the skill; advanced arm is the closed loop.
- AMBIGUITIES (15 rows), NON-GOALS (AI Act gated), `docs/demo-script.md` (90-second execution segment) and `evals/CASES.md` (14 cases + 1 reserve, hard case S10) written and committed.
- Five real repos verified for size and licence, SHAs pinned in CASES.md. Nothing vendored, nothing labelled.
- No solution code. No harness code. Eval harness and baseline come first.

## Next action (in order)

1. Synthetic fixture generator: one YAML spec per case → repo + manifest (`evals/fixtures/gen.py`). S01, S02 first so the verifier has something to pass on.
2. Vendor R01–R04 at pinned SHAs under `evals/fixtures/real/` with LICENSE; label under the CASES.md protocol, timer on. R05 only if runtime allows.
3. Scorer: manifest vs output JSON → P/R/F1, false safe, pass, pass^3, regressions.
4. Verifier (`advanced/verify.py`): name-based call graph, `path_exists`, rule sets as data. Passing on S01+S02 by Sat 12:00 UTC or kill switch 1 fires.
5. Baseline arm = the skill: list/read/grep, instruction text, open loop, 5-attempt retry ramp. Dev set, 3 seeds → first CHANGELOG_EVAL row. A number by Sat 18:00 UTC or kill switch 2 fires.
6. Only then the advanced loop.

Open for Tun: Q2 (video tooling), Q3 (how much of the lived bug story goes in the README).

## Plan checkpoints

| Checkpoint | Target (UTC) | State |
|---|---|---|
| Direction chosen, ADR written | Fri evening | done Fri 16:02 |
| Fixture generator + manifests S01–S10 | Fri night | |
| Real repos vendored + labelled | Sat morning | |
| Verifier passes S01+S02 (kill switch 1) | Sat 12:00 | |
| Baseline number on dev (kill switch 2) | Sat 18:00 | |
| GDPR test number locked (AI Act gate opens) | Sat ~22:00 | |
| Advanced iterations w/ live changelog | Sat–Sun | |
| Adversarial hardening | Sun afternoon | |
| CODE FREEZE | Sun ~21:00 | |
| Clean-env repro + traces rendered | Sun night | |
| README/REPRODUCE final, video | Mon morning | |
| SUBMIT | Mon by 17:30 | |
