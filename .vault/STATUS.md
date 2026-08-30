# STATUS

status: active
last_updated: 2026-08-30 00:22 UTC

## Where we are

- Hour ~6 of 75 (kickoff 2026-08-28 15:00 UTC; deadline 2026-08-31 18:00 UTC; code freeze Sunday 19:30 UTC, ADR 0005).
- Direction chosen and recorded: GDPR Art. 30 inventory + erasure-path check, closed over an `ast` reachability verifier (ADR 0002). Runtime decisions in ADR 0003; contract amendments in ADR 0004; plan amendments in ADR 0005.
- **v1 concept, research and spec are complete, committed and accepted by the author in full (2026-08-29).** The design of record from here on. Entry point: `docs/spec/README.md`. Research with verified sources under `docs/research/`; judge-facing mapping under `docs/judging/`; ten fixture specs under `evals/fixtures/specs/`; the target artefact at `docs/spec/example-record-S10.md`; the build plan at `docs/spec/08-plan.md`; the narrative drafts at `docs/spec/09-narrative.md`.
- Produced by three verified agent workflows (research → verify → fix; spec → adversarial verify → fix → cross-doc reconcile; apply ADR 0004 → plan + narrative → verify → fix → completeness critic), 42 Opus subagents, plus the lead's own spot-reads. Every proposal the spec pass raised was decided (ADR 0004).
- Tooling: `pyproject.toml` carries the runtime dependencies and the `art30` console script; `make smoke` passes; Dockerfile has make and git; Makefile has every contract target as a stub.
- **Phase 1 built and committed (2026-08-29 ~01:30 UTC):** fixture generator + the ten generated repos and manifests (`make fixtures` → "fixtures clean"), `art30/` runtime (config, trace, tools, llm, loop, cli, render, prompts, schema), `baseline/arm.py`, harness (score, trace_check, run, report), 221 offline tests green (`make smoke`). R01–R04 vendored. **Baseline and shared runtime frozen at commit 7681cb6 (ADR 0006).**
- **Phase 2 built and committed (2026-08-29 ~14:00 UTC):** the verifier (`art30/verify/`, ~30 modules on stdlib `ast`), the advanced arm and gate, 590 offline tests green. Acceptance: all twelve synthetic fixtures (S01–S10, D01, D02) reproduce every manifest verdict; twelve adversarially constructed false safes closed with regression tests; two documented xfails (no-sender receivers, graph-layer gap). Harness split under the 300-line rule with byte-identical `--help`. `art30/loop.py` (414) and `evals/harness/score.py` (315) stay over the limit: loop.py is frozen (ADR 0006), score.py has a live importer.
- **Phase 3 built and committed (2026-08-29 ~22:00 UTC):** `verify-docs` and the failure index wired into the Makefile; `docs/spec/DEVIATIONS.md` (21 rows; every spec amended to the code, one debt paid, two safe-side xfails owed); example record regenerated from the generated S10 (70 citations resolve); hardening tests and a record→replay round-trip through the real cache; README/REPRODUCE materialised from the accepted drafts; build trajectory rendered (main session, gzipped). 655 offline tests green. Docker: no runtime on this machine — rehearsal is a checklist (`docs/evidence/docker-rehearsal.md`); Dockerfile fixed to install the dev group.
- **Independent audit done (2026-08-29 ~23:30 UTC):** clean clone → `make setup && make smoke` in ~10 s; `make fixtures` clean; no SDK mismatch (anthropic 1.2.0 introspected: stream/get_final_message, usage fields, strict tools, adaptive thinking, cache_control); verifier hand-run on D01, D02, S10, R04 — every verdict matches the manifest or a human reading, no false safe; the guard rejects a planted false claim. Five defects found and fixed before any recording: `ART30_TRACE_DIR` ignored (would have overwritten committed traces during gate timing), `make baseline` aborting on the unlabelled R01, unscoped `report` booking unrun cells as crashed, no cost ceiling enforced, D02's route calling an undefined name. ADR 0006 addendum covers the two frozen-file edits.
- **Three surfaces built (ADR 0007, 2026-08-30 ~03:30 UTC):** skill package (`skill/art30/`, generated from the prompt files, `make skill` clean; verify/render scripts hand-tested from outside the repo — the dead-helper claim is rejected with the CLI's exact reason); CLI polish (arbitrary repos, no-key message, wheel ships both arms and `norm` moved into the package); local website (`art30 serve`: stdlib server that spawns `art30 scan`, SSE trace tail, file gate, jailed source excerpts, host/origin checks; one inlined page with a bundled OFL font; adversarial design review: "a considered product, not an AI template"; no browser on this machine, so the pixels are unverified). Also fixed: every advanced record used to render "Verification: none" — record.json now carries the rejected claims, what replaced them, and the rule-set sha. 750 tests green.
- **v1 CLI is built for review.** Everything runs offline; the live path (calibration, Sweep A, iterations, Sweeps B/C) waits on `ANTHROPIC_API_KEY` and `ART30_MAX_USD` in `.env` and on the hand-labelled R01–R04 manifests (`docs/runbook-sweeps.md`).
- Two demo repos for hand testing outside the scored set: `evals/fixtures/synthetic/D01` (Django membership site; avatar file survives deletion) and `D02` (SQLAlchemy shop; cache purged, tickets and search index survive). `evals/split.yaml` lists them under `demo:`; the harness never selects them. Remote `origin` = github.com/SM1LE21/micro1-hackathon, pushed after each phase.
- Known drift to refresh from the first real run: `docs/spec/example-record-S10.md` line numbers vs the generated S10.
- **Blocker for live runs: no API credentials on this machine** (no `.env`, no `ant` profile, no `ANTHROPIC_API_KEY`). Everything up to the first calibration run builds and tests offline; the calibration run and Sweep A wait for a key in `.env`.
- AMBIGUITIES has 16 rows; NON-GOALS admits the HTML render; Q2–Q5 resolved with their defaults (QuickTime; anecdote as drafted; no LICENSE file; $300 ceiling). `.gitattributes` committed (plan item 0).

## Next action (in order; details in docs/spec/08-plan.md §7 "Saturday's first four hours")

1. **Author: `.env` with `ANTHROPIC_API_KEY=` and `ART30_MAX_USD=6`**; then calibration (`docs/runbook-sweeps.md` §1), `ART30_RECORD=1 make baseline` (seven synthetic dev cases until R01/R02 are labelled), CHANGELOG_EVAL row 1.
2. Author blind-labels S03 and S05 (timed, before opening their manifests), then R03/R04, then R01/R02 under the CASES.md protocol → `evals/fixtures/manifests/R0x.yaml` + `.labelling.yaml` sidecars.
3. Phase 3 lands; then, with the key: calibration → Sweep A → CHANGELOG_EVAL row 1 → first advanced run (`docs/runbook-sweeps.md`).
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
| `tests/verify/` core green; callgraph, rules, reach | Sat 23:00 | 1 (Sat 23:00) | done Sat 14:00 (ahead; ADR 0006) |
| `verify/check.py` and `advanced/arm.py`; first advanced run | Sun 10:30 | — | code done Sat 14:00; first run waits for the key |
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
