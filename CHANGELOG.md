# Changelog

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
