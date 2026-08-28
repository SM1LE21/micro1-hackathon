# Changelog

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
