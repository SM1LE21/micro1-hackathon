# STATUS

status: active
last_updated: 2026-08-29 01:02 UTC

## Where we are

- Hour ~6 of 75 (kickoff 2026-08-28 15:00 UTC; deadline 2026-08-31 18:00 UTC; code freeze Sunday 19:30 UTC, ADR 0005).
- Direction chosen and recorded: GDPR Art. 30 inventory + erasure-path check, closed over an `ast` reachability verifier (ADR 0002). Runtime decisions in ADR 0003; contract amendments in ADR 0004; plan amendments in ADR 0005.
- **v1 concept, research and spec are complete, committed and accepted by the author in full (2026-08-29).** The design of record from here on. Entry point: `docs/spec/README.md`. Research with verified sources under `docs/research/`; judge-facing mapping under `docs/judging/`; ten fixture specs under `evals/fixtures/specs/`; the target artefact at `docs/spec/example-record-S10.md`; the build plan at `docs/spec/08-plan.md`; the narrative drafts at `docs/spec/09-narrative.md`.
- Produced by three verified agent workflows (research → verify → fix; spec → adversarial verify → fix → cross-doc reconcile; apply ADR 0004 → plan + narrative → verify → fix → completeness critic), 42 Opus subagents, plus the lead's own spot-reads. Every proposal the spec pass raised was decided (ADR 0004).
- Tooling: `pyproject.toml` carries the runtime dependencies and the `art30` console script; `make smoke` passes; Dockerfile has make and git; Makefile has every contract target as a stub.
- **Phase 1 built and committed (2026-08-29 ~01:30 UTC):** fixture generator + the ten generated repos and manifests (`make fixtures` → "fixtures clean"), `art30/` runtime (config, trace, tools, llm, loop, cli, render, prompts, schema), `baseline/arm.py`, harness (score, trace_check, run, report), 221 offline tests green (`make smoke`). R01–R04 vendored. **Baseline and shared runtime frozen at commit 7681cb6 (ADR 0006).**
- **Phase 2 in progress:** verifier (`art30/verify/`), its tests, `advanced/arm.py`; a refactor agent splits the oversize phase-1 files (run.py 644, report.py 576, loop.py 414, trace_check.py 384 lines) without behaviour change.
- Known drift to refresh from the first real run: `docs/spec/example-record-S10.md` line numbers vs the generated S10.
- **Blocker for live runs: no API credentials on this machine** (no `.env`, no `ant` profile, no `ANTHROPIC_API_KEY`). Everything up to the first calibration run builds and tests offline; the calibration run and Sweep A wait for a key in `.env`.
- AMBIGUITIES has 16 rows; NON-GOALS admits the HTML render; Q2–Q5 resolved with their defaults (QuickTime; anecdote as drafted; no LICENSE file; $300 ceiling). `.gitattributes` committed (plan item 0).

## Next action (in order; details in docs/spec/08-plan.md §7 "Saturday's first four hours")

1. **Author: put an API key in `.env`** (`ANTHROPIC_API_KEY=`); then calibration run on S01 baseline, then Sweep A (`make baseline`), then CHANGELOG_EVAL row 1.
2. Author blind-labels S03 and S05 (timed, before opening their manifests), then R03/R04, then R01/R02 under the CASES.md protocol → `evals/fixtures/manifests/R0x.yaml` + `.labelling.yaml` sidecars.
3. Phase 2 lands (verifier, advanced arm); no advanced run before Sweep A (ADR 0006).
4. Iterations on S02/S05/S07, Sweeps B and C after the freeze, evidence phase (08-plan.md §2).

## Plan checkpoints (from docs/spec/08-plan.md §9; UTC)

| Checkpoint | Target | Kill switch | State |
|---|---|---|---|
| Direction chosen, ADR written | Fri 16:02 | — | done |
| Specs 00–07, 10 written and reconciled; ADR 0004 | Fri 20:00 | — | done |
| Build plan committed | Fri 20:45 | — | done |
| ADR 0005; Q5 opened; CASES.md errata for the one-window test sweep | Fri 21:00 | — | done |
| Packaging, Makefile recipes, Docker path, `.gitattributes` | Fri 21:15 | — | done |
| Q2–Q5 resolved by the author | Sat 2026-08-29 | — | done (defaults accepted) |
| R01–R04 vendored with LICENSE and SOURCE.md | Fri 21:45 | — | done Fri 22:45 |
| `make fixtures` clean; ten repos and manifests committed | Sat 08:30 | 4 (Sat 11:00) | done Sat 01:20 |
| S03 and S05 blind-labelled, timed | Sat 09:15 | — | |
| Tools, schema, prompts, llm; golden tool test green | Sat 11:00 | — | done Sat 01:20 (loop, cli, render, baseline arm, harness too) |
| R03 and R04 labelled and committed; not reopened until Sweep C | Sat 11:15 | — | |
| R01 and R02 labelled | Sat 14:45 | — | |
| One live run end to end; cost and prefix size measured | Sat 15:15 | 5 (Sat 15:15) | |
| **SWEEP A** — baseline dev number | Sat 18:15 | 2 (Sat 18:30, narrow to synthetic dev; ADR 0005) | |
| CHANGELOG_EVAL row 1; Sweep A aggregate and traces copied aside | Sat 19:00 | — | |
| `tests/verify/` core green; callgraph, rules, reach | Sat 23:00 | 1 (Sat 23:00) | |
| `verify/check.py` and `advanced/arm.py`; first advanced run | Sun 10:30 | — | |
| Advanced probe on R01 and R02 recorded; unverified rate read | Sun 12:00 | 3 (Sun 12:00) | |
| Iteration rows complete (three to five) | Sun 16:30 | 6 (Sun 17:30) | |
| Qualification-gate targets; adversarial pass | Sun 18:30 | — | |
| Freeze rehearsal green | Sun 19:30 | 7 (Sun 19:30) | |
| **CODE FREEZE** | Sun 19:30 | — | |
| **SWEEP B** — dev, both arms, one window | Sun 21:00 | — | |
| **SWEEP C** — test, both arms, one ledger line, `ART30_RECORD=1` | Sun 22:00 | 8 (Sun 22:45) | |
| `make report`; S10 note written; results, traces, `evals/cache/` committed | Sun 22:45 | — | |
| Clean-clone replay rehearsal | Mon 06:45 | — | |
| Gate-timing pass; `results/gate-timing.yaml` | Mon 07:15 | — | |
| README, REPRODUCE, HOT_TAKE final | Mon 09:15 | — | |
| Build trajectory rendered; gitleaks clean | Mon 09:45 | — | |
| Video recorded and uploaded; `traces/` and `results/` restored | Mon 13:15 | 9 (Mon 09:45) | |
| Writing-rules and citation pass | Mon 14:30 | — | |
| Docker path rehearsed | Mon 15:00 | 10 (Mon 15:00) | |
| **SUBMIT** | Mon 17:30 | — | |
