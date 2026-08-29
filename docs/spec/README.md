# Spec — v1

The system as designed before any solution code. Written 2026-08-28 by the lead agent and five spec agents against the interface contract, each document adversarially verified by an independent agent and reconciled in a cross-document pass. Read in this order.

| # | File | What it fixes |
|---|---|---|
| 0 | `00-contract.md` | Vocabulary, layout, tools, feedback object, trace format, CLI. Wins over every other spec doc until an ADR changes it. |
| 1 | `01-architecture.md` | Modules, data flow, arms, record/replay, cost accounting, safety, failure taxonomy, estimates |
| 2 | `02-agent-loop.md` | The step loop as pseudocode, request shapes, caching breakpoints, invariants |
| 3 | `03-verifier.md` + `verifier-rules-draft.yaml` | Call graph, entry points, store detection, rules R1–R28 operationalised, `path_exists`, verdict table, claim checking, test plan, feasibility spike |
| 4 | `04-output-schema.md` + `record.schema.json` | Every field, who fills it, the Art. 30(1) item it serves, the render layout |
| 5 | `05-eval-harness.md` | Scorer, runner, test-split lock, results layout, report, statistics, replay path |
| 6 | `06-traces.md` | JSONL trace contract with a worked run, validator, failures, build trajectory |
| 7 | `07-ui.md` | CLI flags and a full terminal mock, gate prompt, HTML render, how the video maps onto it |
| 8 | `08-plan.md` | Hour-by-hour plan to code freeze and submission, kill switches, what gets cut first |
| 9 | `09-narrative.md` | Draft answers to the four questions, hot-take candidates, video outline |
| 10 | `10-instructions.md` | The instruction text both arms share, the taxonomy, feedback and gate templates |
| — | `fixture-generator.md` | How `evals/fixtures/gen.py` turns a spec into a repo and its manifest |
| — | `example-record-S10.md` | The target artefact: the rendered record for the hard case, written by hand |
| — | `PROPOSED-CONTRACT-CHANGES.md` | Resolved pointer: every proposal from the spec pass was accepted by ADR 0004 |
| — | `DEVIATIONS.md` | Spec versus code: one row per disagreement, the decision, and the contract edits an ADR still owes |

Decision records live in `.vault/adr/`. Research the specs cite lives in `docs/research/`. Judge-facing requirement mapping and anticipated questions live in `docs/judging/`.
