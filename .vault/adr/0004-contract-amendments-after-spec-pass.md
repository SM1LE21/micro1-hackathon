# ADR 0004 — Contract amendments after the spec pass

status: accepted
date: 2026-08-28

## Decision

Every change the five spec documents asked of `docs/spec/00-contract.md` during the 2026-08-28 spec fan-out is accepted and applied, using the wording consolidated in the reconciliation pass (`docs/spec/PROPOSED-CONTRACT-CHANGES.md`, now reduced to a pointer). Numbered as there:

- **P-01** `submits` = number of `submit_record` calls; `verify_rounds` = number that returned `accepted: false`.
- **P-02** `run_id` = `<adv|base>-<case>-s<seed>-<sha7>`; the same string is `provenance.run_id`, the `results/test-runs.log` column and `metrics.json.git_sha`'s companion.
- **P-03** Budgets are overridable per run by `ART30_TOOL_BUDGET` and `ART30_SUBMIT_BUDGET`; both appear in the first user message and so in the request hash.
- **P-07** `tests/` enters the layout (`verify/`, `test_schema.py`, `test_score.py`, `test_tools.py`); `evals/harness/trace_check.py` enters it; `results/test-runs.log`, `results/timing.json`, `results/gate-timing.yaml` enter it.
- **P-08** `stop_condition` enum: `accepted | gate_rejected | budget_exhausted | max_submits | max_tokens | no_submission | timeout | crashed | replay_miss | render_failed | api_error | refusal`.
- **P-09** `no_entry_point` joins the `high` list of the checkpoint risk rating.
- **P-10** `checkpoint` gains `wait_s` (0.0 when simulated) and optional `human_completions`.
- **P-11** `max_tokens` 32000, requests streamed; `max_tokens` is inside the request hash (amends ADR 0003 items 1 and 6).
- **P-12** `step` lines gain `request_hash` and `stop_reason`.
- **P-13** `run_end` gains `note: string|null`.
- **P-14** `run_start` gains `config` (`max_tokens`, both budgets, `overridden`) and `prompt_sha`; `make report` fails when the two arms' `prompt_sha` differ.
- **P-15** `path_exists(entry, target, must_pass_through=None, mode=...)` as specified in `03-verifier.md` §5.1.
- **P-16** `render/html.py` reads `record.json` and the repository path.
- Feedback object: `expected` on all four lists; `conservative_divergences` and `missing_entry_points` added; rejected claims carry a structured `path` array.
- Citation rule relaxed from the physical line to the logical line (a multi-line call cites its first line).
- Per-store `subject_link {file, line}` cell, nullable.
- `ART30_MAX_USD`, optional, ends a run with `budget_exhausted` when the cumulative cost crosses it.
- Failure traces live at `traces/failures/<arm>/<case>-s<seed>.jsonl` (directory form; the filename-prefix form is struck).
- The store-identity convention enters the shared instruction text: a store is named after the identifier the code carries (table name, bucket or prefix constant, SDK name, job module for backups).

Owed edits outside `docs/spec/` are applied in the same pass: `pyproject.toml` dependencies, `README.md` statistics sentence, `REPRODUCE.md` model paragraph, `evals/CASES.md` errata (cost, temperature, pass definition, tuple counts, S08/R04 verdict columns, retention row, S05 mail as a store), `docs/demo-script.md` narration, `Makefile` targets.

## Context

The contract was written before the specs existed, on purpose: a shared vocabulary first, detail second. The spec agents found seven places where the contract named a thing without defining it and nine where a specified code path contradicted it. None of the requests weakens a safety rule; several strengthen the arm-equality claim (`prompt_sha`, `request_hash`) that the whole comparison rests on. Two are on the critical path before the first recording because they change hashed bytes (`max_tokens`, `request_hash`).

## Options considered

- Decline the enum and trace-line additions to keep the contract short — each declined item forces an interim reading that misreports a failure class in the README's failure table.
- Keep `max_tokens` at 16000 without streaming — a truncated record on a real repository would report as an infrastructure error.
- Apply only the critical-path items now and the rest later — the reconciler's warning stands: interim readings that are never replaced become the design.

## Consequences

- `docs/spec/00-contract.md` is amended in place; the spec documents' "interim" readings are replaced with the binding ones in the next agent pass, and any leftover `P-0x`/"interim" marker is a defect.
- ADR 0003 items 1 and 6 are amended by P-11 (streaming, `max_tokens` hashed).
- The first live recording must not start before P-11 and P-12 are implemented.
