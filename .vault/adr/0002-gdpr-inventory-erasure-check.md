# ADR 0002 — GDPR Art. 30 inventory and erasure-path check, closed over a reachability verifier

status: accepted
date: 2026-08-28

## Decision

The project is an agent that reads a Python codebase and produces the technical half of a GDPR Art. 30 record of processing (personal-data fields per store, third-party recipients, retention timers) together with an erasure-path table: for every store holding personal data, whether account deletion actually reaches it, with `file:line` evidence. Every claim is re-verified by deterministic code the model cannot bypass. An erasure claim needs a static call path from the erasure entry point to a deletion primitive for that store, or it is rendered "not erased" or "unverified". Legal cells (purpose, legal basis, risk class) are never filled by the agent. A human approval gate precedes the final render.

The baseline is the same model with the same read-only tools and the same instruction text, open loop — what a SKILL.md gets you in Claude Code or Codex. The advanced arm adds the verifier, the output schema, the completeness guard and the gate. The difference under test is enforcement, not intelligence.

Evaluation: 12–14 repositories as cases — a spec-generated synthetic set with planted traps plus real open-source repos vendored at pinned SHAs. Primary metric: F1 over `(store, field, erasure verdict)` tuples against a manifest the verifier never sees. "False safe" claims (agent says erased, code says no) are a must-be-zero secondary. Case list: `evals/CASES.md`.

## Context

Who has the problem: a technical founder of a small EU SaaS who has to hand a record of processing and a deletion guarantee to a co-founder, a lawyer or a data-protection authority. The document is written by hand and drifts from the code. The author has lived this in a product he runs: a hand-written report with two statements reversed, and a soft-delete that never reached object storage, undetected for a month. No detail of that product enters this repo.

Why an agent and not a script: deciding what is personal data is semantic (`notes`, `metadata` JSON, an IP in a log line, a comment saying "contains phone numbers"), and drafting the record is judgment.

Why a closed loop and not a skill: a skill is instructions the model may follow. It cannot reject the claim "user data is deleted in `delete_user()`" after the model saw `deleted_at = now()`. The verifier can, regardless of what the model wrote. That is why the baseline is deliberately the skill: the changelog then answers "what does the loop add over a good SKILL.md" with numbers.

Rubric fit: the verifier is structural (reachability), so "which design choice helped" has a crisp answer (Agent Solution, 30). The artifact is a document a founder signs and hands to a lawyer (End-to-End Quality, 20). The bottleneck is concrete and lived (Problem, 15). Static reads only, no repo execution, pinned SHAs, replay without a key (Reproducibility, 15). The hard case is a bug class present in real frameworks: Django does not delete `FileField` uploads on cascade (Hot Take, 5).

Constraints from AGENTS.md that shaped it: eval and baseline before the advanced system; one primary metric; deterministic verifier; synthetic or public data; code freeze Sunday ~21:00 UTC.

## Options considered

- Verified B2B prospect researcher on a synthetic web corpus — lower build risk, but the verifier is string presence over pages and the loop it closes over risks reading as "retry until grep passes"; "AI SDR" is also one of the most common agent demos. Kept as the fallback below.
- Receipt/invoice extraction with audit gate — safest eval, but a single structured-output call already sits near the ceiling on clean synthetic receipts, so no design choice would measurably help.
- Repo due-diligence (the PDF's own appendix example) — one-rater ranking as ground truth, must build and test real repos in a clean environment, and "you wrapped Claude Code" is a plausible judge reaction.
- Annotation-quality reviewer — the helpful design choices are statistical, not agentic; too close to the author's own QC IP.
- AI Act rule set in the core from day one — doubles fixtures and ontology before a number exists. Gated instead; see NON-GOALS.
- Migration safety reviewer — cleanest ground-rule-04 story, but narrow and served by existing linters. Reserve.

## Consequences

Commits us to:

- Python-only fixtures; Django and SQLAlchemy/SQLModel idioms only. Anything else is reported "unscanned", never guessed.
- A verifier of roughly 150–200 lines on stdlib `ast`: name-based intra-repo call graph, `path_exists(entry, primitive, must_pass_through=None)`, rule sets as data (store kinds, deletion primitives, recipient SDKs). Django `on_delete=CASCADE` counts as a path for relational rows; file and object stores need an explicit storage delete on the path.
- Hand-labelled ground truth for real repos under a written protocol, committed with the SHA before the agent reads them. Labelling time is the "human time per task" row.
- Dev/test split by repository, real repos concentrated in test. The test number will be lower than dev and the README says so before a judge notices.
- Single-threaded loop with phases (scan → classify → draft → verify → gate). Not separate agents.

Costs: fixture generator, manifests and verifier all precede the first agent line — Friday night plus Saturday morning. Real repos add tokens and variance per run.

Kill switches, in order:

1. Saturday 2026-08-29 12:00 UTC — reachability not passing on the first two synthetic repos: narrow the verifier to "deletion primitive for the store is reachable within the erasure module", log the narrowing in AMBIGUITIES, continue.
2. Saturday 2026-08-29 18:00 UTC — no baseline number on the dev set: switch to the prospect-researcher fallback on a synthetic corpus, in a new ADR superseding this one.

What would reopen this decision: an "unverified" rate on real repos so high that the advanced arm cannot separate from the baseline, or a real-repo set that cannot be labelled inside the cap (2 h each, max 5 repos).
