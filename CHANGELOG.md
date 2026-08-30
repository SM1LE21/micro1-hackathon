# Changelog

## 2026-08-30 07:05 UTC — Three brains and one settings layer (ADR 0008)

- `--brain api|claude|codex`: local brains run the user's own logged-in CLI with the arms served as an MCP `submit_record` tool; isolation flags (no Bash, jailed reads, no user memory, our MCP only); traces converted line by line; cost as a labelled estimate reproducing Claude's own `total_cost_usd`
- Settings shared by CLI, harness and website: `art30 config`, `art30.toml`, key written to `.env` write-only; harness cells pin every request setting; `make eval-replay-local` re-verifies every recorded submission and re-scores every record
- Website: Settings view, brains panel with login detection, brain and model selectors, play back of saved runs, runs listed from disk
- Acceptance: real D02 runs on this machine's Claude and Codex logins; both brains read the D02 helper/call mismatch correctly, which is now fixed in the generator; 887 tests green

## 2026-08-30 00:22 UTC — Three surfaces: skill, CLI, local website

- ADR 0007: one core, three surfaces; the website drives the CLI as a subprocess (same seam as the harness), never a second loop
- `--approve file` gate mode; skill package generated from the prompt files with the verifier as a script and a Stop hook; CLI polish for arbitrary repositories; wheel ships both arms
- `art30 serve`: stdlib server, SSE trace stream, file gate relay, jailed source excerpts, results view; one inlined page, bundled OFL font, no external requests
- Advanced records now carry their verification history and rule-set sha (ADR 0006 addendum); 750 offline tests green; pixels unverified (no browser here)

## 2026-08-29 20:13 UTC — Phase 3 built and audited: v1 ready for review

- Evidence tooling (`verify-docs`, failure index, gate targets), spec-vs-code audit (`docs/spec/DEVIATIONS.md`, 21 rows, specs amended to the code), example record regenerated from the generated S10, hardening and record→replay tests; README and REPRODUCE materialised; build trajectory committed (main session, gzipped)
- Independent end-to-end audit: clean clone passes in ~10 s, no SDK mismatch, no false safe on four hand-run repos; five defects fixed before any recording (trace dir seam, sweep scoping, cost ceiling, report scope, D02 emitter)
- 656 offline tests green; live sweeps wait on the API key, the cost ceiling and the hand-labelled real-repo manifests

## 2026-08-29 15:34 UTC — Phase 2 built: the verifier and the advanced arm

- `art30/verify/` on stdlib ast: call graph, entry points, store detection, synthetic edges, reachability over (node, mode, passed) states, the 6.1 verdict table, claim checking with the contract's feedback object; `advanced/arm.py` and gate
- Acceptance: all twelve synthetic fixtures reproduce every manifest verdict; twelve adversarial false safes closed with regression tests; 590 offline tests green
- Harness refactored under the 300-line rule with byte-identical CLI help; two demo repos D01/D02 for hand testing; R01 PEP 758 syntax noted (upstream, not a vendoring artefact)
- Phase 2 restarted once after the machine slept mid-response; the build machine is held awake for the rest of the weekend

## 2026-08-29 01:02 UTC — Phase 1 built: fixtures, runtime, baseline arm, harness

- R01–R04 vendored at pinned SHAs (LICENSE kept, SOURCE.md each); fixture generator + ten generated repos and manifests, `make fixtures` clean; 90 tuples as the spec's table
- art30 runtime (config, trace, tools, llm, loop, cli, render, prompts, schema), baseline/arm.py, harness (score, trace_check, run, report); 221 offline tests, `make smoke` green; Makefile recipes real
- Four fixture specs amended before any run (CASES.md errata); ADR 0006 freezes the baseline and shared runtime at 7681cb6 so the verifier can be built before Sweep A while no API key is available
- Verified Opus subagents throughout: builder → adversarial verifier → fixer per module; the lead commits per file

## 2026-08-29 22:15 UTC — v1 accepted

- Author reviewed all 428 v1 decisions through the review ledger and accepted every one; Q2–Q5 closed with their defaults
- `.gitattributes` pins fixture bytes (plan item 0) before any fixture is generated
- Next: the build, in the order of docs/spec/08-plan.md §7

## 2026-08-28 21:09 UTC — v1 concept, research and spec

- Three verified agent workflows (42 Opus subagents): research with re-fetched sources (docs/research/), judge mapping (docs/judging/), specs 00–10 + fixture generator + example record (docs/spec/), ten fixture specs and the split (evals/fixtures/specs/, evals/split.yaml), build plan and narrative drafts
- ADR 0003 (runtime: Opus 5, no temperature/seed, identical prompt across arms), ADR 0004 (every contract change the spec pass asked for), ADR 0005 (kill switch 2 narrowed, freeze 19:30 UTC, one-window test sweep, $300 ceiling)
- Tooling: dependencies and art30 console script, Docker path with make and git, Makefile stubs for every contract target incl. gate checks; make smoke green
- Open for the author: Q2 video tooling, Q3 anecdote wording, Q4 licence, Q5 budget — defaults recorded

## 2026-08-28 16:02 UTC — Direction chosen: GDPR inventory + erasure check

- ADR 0002: codebase → Art. 30 technical inventory + erasure-path table, closed over an ast reachability verifier; baseline is the skill (same tools, open loop)
- AMBIGUITIES (15 rows) and NON-GOALS filled for the slice; AI Act rule set gated behind a locked GDPR test number
- evals/CASES.md: 14 cases (10 synthetic, 4 real at pinned SHAs) + 1 reserve; hard case S10 = soft delete whose purge job never reaches object storage
- docs/demo-script.md: 90-second execution segment

## 2026-08-28 15:20 UTC — Repo skeleton

- Problem statement saved to docs/problem/; read in full
- Conventions scaffold: CLAUDE.md pointer, AGENTS.md spec, .vault/ decision log with ADR 0001
- Deliverable stubs (README, REPRODUCE, CHANGELOG_EVAL, HOT_TAKE) and eval/trace directory structure
- Direction decision open as .vault/QUESTIONS.md Q1
