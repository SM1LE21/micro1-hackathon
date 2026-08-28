# ADR 0001 — Build the skeleton before choosing the project direction

status: accepted
date: 2026-08-28

## Decision

Scaffold the full repo (conventions, eval structure, evidence files, tooling) before deciding what the project actually is. The skeleton is problem-agnostic by design.

## Context

The rubric pays 30/100 for evidence (measured improvement + reproducibility) and gates scoring on a clean-environment run. Every hour of scaffolding after the direction is chosen competes with build time; none of the scaffold depends on the direction. Kickoff research also showed the winning build order is eval-first, which requires the harness structure to exist.

## Options considered

- Decide direction first, scaffold after — loses the only hours where scaffolding is free.
- Skip the .vault/ layer for a 3-day sprint — the changelog and ambiguity log are judged deliverables here, not overhead.

## Consequences

Direction choice (ADR 0002) must slot into this structure: `baseline/` and `advanced/` share an interface, evals live as task files under `evals/tasks/`, all decisions get logged in `.vault/`.
