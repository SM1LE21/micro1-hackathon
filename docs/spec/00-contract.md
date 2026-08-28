# 00 — Interface contract

The shared vocabulary every spec document and every line of code must use. Written by the lead before the spec fan-out; amended by ADR 0004 after it; changed only through an ADR. Where a later spec document and this file disagree, this file wins until the ADR lands.

## Names

- Product, package and CLI: `art30`. The record it produces is "the record"; the erasure table is "the erasure table".
- Arms: `baseline` and `advanced`. Same prompt, same tools, same model (ADR 0003). The advanced arm adds the verifier inside `submit_record` and the human gate before render.
- Cases: `S01`–`S10` synthetic, `R01`–`R05` real (`evals/CASES.md`).

## Repository layout

```
art30/                    shared runtime (both arms)
  cli.py                  art30 scan ... (argparse)
  config.py               model, effort, budgets, env overrides
  llm.py                  Anthropic client wrapper: call, record/replay, usage → cost
  tools.py                list_tree, read_file, grep, submit_record dispatch
  loop.py                 single-threaded step loop; arm object decides submit handling + gate
  trace.py                JSONL trace writer
  prompts/system.md       the instruction text (the "skill"), byte-identical for both arms
  prompts/taxonomy.md     personal-data categories with examples (included by system.md)
  schema/record.schema.json
  verify/callgraph.py     ast → symbols, edges, entry points, decorators
  verify/rules.py         rule-set loading and matching (YAML under verify/rules/)
  verify/reach.py         path_exists(graph, entry, target, must_pass_through=None), verdicts
  verify/check.py         claim-by-claim check of a submitted record → feedback object
  verify/rules/*.yaml     data: store kinds, deletion primitives, recipients, entry-point patterns, soft-delete markers
  render/markdown.py      validated record → record.md
  render/html.py          record.json + repository path → record.html (single template, no JS)
baseline/arm.py           tool set + submit handler (schema only) + no gate
advanced/arm.py           tool set + submit handler (schema + verifier + completeness guard) + gate
evals/
  CASES.md
  fixtures/gen.py         YAML spec → synthetic repo + manifest (deterministic; outputs committed)
  fixtures/specs/S01.yaml … S10.yaml
  fixtures/synthetic/<case>/           generated repos (committed)
  fixtures/real/<name>/                vendored at pinned SHA, LICENSE kept, SOURCE.md (url, sha, licence, date, what was stripped)
  fixtures/manifests/<case>.yaml       ground truth; header carries labelling_minutes for real repos
  fixtures/manifests/<case>.labelling.yaml   blind-labelling sidecar for S03, S05 (author's minutes; never generated)
  fixtures/synthetic/.gen-index.json   generator index: spec sha → output sha per case (clean-diff check)
  harness/run.py          cases × arms × seeds → results/runs/…, traces/…; launches art30 scan as a subprocess per cell; writes results/timing.json after a live sweep
  harness/score.py        manifest vs record → per-case metrics
  harness/report.py       results/runs → results/metrics.json + Markdown tables
  harness/trace_check.py  trace validator (run by make smoke and after every run)
  cache/                  recorded API responses for replay (committed; path-addressed, hash-verified)
tests/
  verify/test_*.py        unit tests over hand-written repos (fixtures inline)
  verify/conftest.py      mkrepo() and the shared fixtures
  test_schema.py          record.schema.json + handler invariants; asserts the shipped schema and the spec copy hash equal
  test_score.py           normalisation, tuple extraction, the scoring rows
  test_tools.py           golden tool output, the jail, the step-1 request hash constant
results/                  metrics.json, timing.json, gate-timing.yaml, test-runs.log (chained ledger),
                          runs/<arm>/<case>/s<seed>/{record.json,record.md,record.html,metrics.json,record.draft.json (gate-rejected runs only)}
traces/{baseline,advanced}/<case>-s<seed>.jsonl ; traces/failures/<arm>/<case>-s<seed>.jsonl + .diagnosis.txt
```

`docs/spec/record.schema.json` is a byte-identical spec copy of `art30/schema/record.schema.json`; `tests/test_schema.py` asserts it.

Files stay under ~300 lines; one responsibility each.

## Run phases

One run = one case, one arm, one seed.

1. `agent` — the model calls `list_tree`, `read_file`, `grep` freely and ends by calling `submit_record`. The prompt recommends scan → classify → draft as a method; the harness does not enforce stages.
2. `verify` (advanced only, inside the `submit_record` handler) — schema validation, then `verify/check.py`. Failure returns a feedback object as the tool result and the loop continues. Baseline: schema validation only; valid → accepted.
3. `gate` (advanced only) — harness-driven human checkpoint after acceptance. Never model-initiated. Recorded as a tool call in the trace with `caller: "harness"`, a risk rating and the decision. `--approve ask` prompts on the terminal; `--approve auto` records `by: "simulated"` (eval mode).
4. `render` — validated record → `record.json`, `record.md`, `record.html`.

## Budgets (both arms)

- Tool calls per run: 60 synthetic, 120 real. Exceeded → `stop_condition: budget_exhausted`, run counted as failure.
- `submit_record` attempts per run: 5. Exceeded → `max_submits`, failure.
- Both budgets are overridable per run by `ART30_TOOL_BUDGET` and `ART30_SUBMIT_BUDGET`. Both are named in the first user message, so both change the request hash. The harness sets the tool budget from the case kind.
- `ART30_MAX_USD` (optional, unset by default) ends a run with `budget_exhausted` when `cost_cum_usd` crosses it.
- `ART30_UNLOCK_TEST=1` lets `art30 scan` run on a repository that resolves to a test case (the harness has `--unlock-test`); `ART30_REPRODUCIBLE=1` is set by `make eval-replay` and suppresses every file a replay must not rewrite (`results/timing.json`, `results/gate-timing.yaml`, the ledger).
- `read_file` returns at most 400 lines per call; `grep` at most 100 matches; `list_tree` excludes `.git`, `__pycache__`, `node_modules`, `static`, `media`.

## Tools (model-facing; identical in both arms)

| Tool | Input | Output |
|---|---|---|
| `list_tree` | `path` (default "."), `max_depth` (default 4) | indented tree with byte sizes |
| `read_file` | `path`, `start_line` (1-based, default 1), `end_line` (optional) | `n: line` numbered text |
| `grep` | `pattern` (regex), `path` (default "."), `glob` (default "*.py"), `max_results` (default 100) | `file:line: text` lines |
| `submit_record` | `record` (object matching `record.schema.json`) | `{accepted: true}` or a feedback object |

Tool schemas use `strict: true` (`additionalProperties: false`, all `required` listed). Tool results are deterministic functions of the fixture, which is what makes replay exact.

## Feedback object (advanced `submit_record`)

```json
{
  "accepted": false,
  "attempt": 2,
  "attempts_left": 3,
  "schema_errors": [],
  "rejected_claims": [
    {"store": "uploads", "field": null, "claim": "erasure.verdict=erased",
     "reason": "no path from entry point close_account (api/account.py:12) to any object-storage deletion primitive; cleanup_user_files (storage.py:41) is defined but has no callers",
     "path": [],
     "expected": "verdict not_erased, or cite the path"}
  ],
  "missing_stores": [{"store": "sessions", "kind": "cache", "evidence": "app/cache.py:18 writes user email under key session:<id>", "expected": "add the store with its fields and an erasure verdict"}],
  "missing_entry_points": [{"name": "delete_user", "file": "cli.py", "line": 40, "kind": "cli", "expected": "declare it, or say why it is not an erasure entry point"}],
  "bad_citations": [{"file": "models.py", "line": 14, "symbol": "email", "problem": "line 14 does not contain 'email'", "expected": "cite the line that carries the symbol"}],
  "unverified": [{"store": "stripe", "claim": "erasure.verdict=external_manual", "reason": "call resolved through getattr; treated as unverified", "expected": "keep the verdict, or cite a resolvable call"}],
  "conservative_divergences": [{"store": "orders", "claim": "erasure.verdict=not_erased", "verifier": "erased via on_delete=CASCADE models.py:40", "note": "accepted; the record is more conservative than the evidence"}]
}
```

Every item on `rejected_claims`, `missing_stores`, `missing_entry_points`, `bad_citations` and `unverified` carries `expected`; `conservative_divergences` items carry `note` instead. `path` on a rejected claim is the structured call path the verifier found (empty when none). `conservative_divergences` are accepted, never rejected: the model may be safer than the evidence, never safer than the code. Baseline feedback contains only `schema_errors`.

## Record vocabulary (details in 04-output-schema.md)

- Store kinds: `relational | object_storage | cache | search_index | queue | third_party | log | backup`. Recipients are stores of kind `third_party`; there is no separate recipients list.
- Field categories: `identifier | contact | financial | behavioural | free_text_may_contain | technical`.
- Erasure verdicts: `erased | erased_after_timer | anonymised | pseudonymised | not_erased | external_manual | no_entry_point | governed_by_retention | no_schedule_evidenced | unverified`. `reaches_erasure` (scoring) is true for `erased`, `erased_after_timer`, `anonymised` only. `pseudonymised` (hash, token, UUID, mask, or a surviving key to the subject) is the false side and a false safe when claimed as reaching. `governed_by_retention` / `no_schedule_evidenced` are the only verdicts rendered for stores of kind `backup` (research: gdpr-sources.md §3.1).
- Erasure is recorded per store; a field whose fate differs from its store (email anonymised, invoice reference kept ten years) carries its own `erasure` block that overrides the store's for that field. The scorer reads the field-level block when present.
- Retention items are per `(store, category)` where the code distinguishes them, per store otherwise; a `criteria` string is allowed where no number exists (Art. 30(1)(f) "where possible"; CNIL "or the criteria"). The tool never invents a number; absence renders `no_timer_evidenced`.
- Stores of kind `third_party` carry `recipient_kind: unknown | internal | processor | external_controller`, default `unknown`, set by the human at the gate. The agent may never set it.
- The record has an `activities` layer (Art. 30's unit is a processing activity) that the agent leaves empty; the render shows the empty layer with "requires human completion" rather than hiding it.
- Hint fields the agent may fill, each rendered under a heading that says it is not a finding: `observed_module_names` (not purposes), `observed_region_hints` (region strings and API hosts with `file:line`; not a transfer finding), `security_evidence` (Art. 32(1)(a) technical measures only: hashing, TLS, encryption at rest, each `file:line`).
- Entry-point kinds: `route | view | cli | admin | task | signal | unknown`.
- Every field, entry point and erasure evidence item carries `file` and `line` (1-based, relative to the repo root). The cited line is the logical line: a statement spanning several physical lines is cited by its first.
- Every store carries `subject_link {file, line}` (nullable): the citation that ties the store to a data subject, kept even when subject foreign keys are not listed as fields.
- Human-only cells (never filled by the agent): controller identity and contact, DPO, purposes, legal basis, data-subject category confirmation, transfer existence and safeguards, recipient kind, activity grouping, retention justification.
- Name normalisation (used by scorer and verifier alike): lowercase; non-alphanumerics → `_`; collapse repeats; strip a leading app prefix when the remainder matches a known model name; compare plural and singular as equal.

## Verifier contract

- Input: the submitted record + the repo path + rule sets. Output: the feedback object. No access to manifests, ever.
- `path_exists(graph, entry, target, must_pass_through=None)` as specified in `03-verifier.md` §5.1, over a name-based intra-repo call graph; the delete mode is carried in the search state, not the signature. Django `on_delete=CASCADE` edges and SQLAlchemy relationship cascades are synthetic edges added by rules. Unresolvable calls (dynamic dispatch, `getattr`, string imports) yield `unverified`, never a guess.
- Completeness guard: any store the verifier's own scan finds with a personal-data-looking field (rule-set patterns) that is absent from the record → `missing_stores`.
- Citation check: for each cited `file:line`, the logical line must contain the cited symbol (after normalisation).
- Store identity: a store is named after the identifier the code carries (table name or model name, bucket or prefix constant, SDK name, job module for backups); the same rule binds the manifests and the instruction text.

## API configuration (ADR 0003)

`model=claude-opus-5`, `thinking={"type":"adaptive","display":"summarized"}`, `output_config={"effort":"high"}`, `max_tokens=32000` with the request streamed (`messages.stream(...).get_final_message()`), no sampling parameters, no fallbacks. The replay hash covers model, system, tools, messages, output_config, thinking and `max_tokens` (ADR 0004 P-11). System prompt and tools carry `cache_control` so the repeated prefix is cached across steps. Thinking blocks are echoed back unchanged on the next turn. `stop_reason == "refusal"` → run failure.

Cost per step from `usage`: input $5/MTok, output $25/MTok, cache write ×1.25, cache read ×0.1.

## Trace contract

`traces/<arm>/<case>-s<seed>.jsonl`, one JSON object per line:

- `{"type":"run_start", "run_id", "arm", "case", "seed", "model", "effort", "mode": "live|replay", "prompt_sha", "config":{"max_tokens","tool_budget","submit_budget","overridden":[...]}, "ts"}`
- `{"type":"step", "step", "phase":"agent|verify", "ts", "request_id", "request_hash", "stop_reason", "reasoning", "text", "tool_calls":[{"id","name","input"}], "tool_results":[{"call_id","output","is_error","bytes"}], "usage":{"input","cache_read","cache_write","output"}, "cost_usd", "cost_cum_usd"}`
- `{"type":"checkpoint", "tool":"request_approval", "caller":"harness", "risk":"low|medium|high", "summary", "decision":"approved|rejected", "by":"human|simulated", "wait_s", "human_completions":{...}|null, "ts"}`
- `{"type":"run_end", "stop_condition":"accepted|gate_rejected|budget_exhausted|max_submits|max_tokens|no_submission|timeout|crashed|replay_miss|render_failed|api_error|refusal", "steps", "tool_calls_total", "submits", "verify_rounds", "wall_s", "cost_usd", "record_path", "note":string|null}`

`run_id` is `<adv|base>-<case>-s<seed>-<sha7>` (seven-hex short sha of the working tree). `submits` counts `submit_record` calls; `verify_rounds` counts the ones that returned `accepted: false`. `prompt_sha` is the SHA-256 of the spliced instruction text; `make report` fails when the two arms' values differ. `reasoning` is the summarised thinking text (may be empty). Tool outputs are stored in full. `wait_s` is 0.0 when `by` is `simulated`.

Risk rating for the checkpoint: `high` if any store is `not_erased`, `pseudonymised`, `external_manual`, `no_entry_point`, `no_schedule_evidenced` or `unverified` with an `identifier` or `contact` field; `medium` if every store reaches erasure but at least one only after a timer; `low` otherwise. The gate fires at every rating.

## Scoring contract

As in `evals/CASES.md`: tuple `(store, field, reaches_erasure)`; per-case precision, recall, F1; false-safe count; pass; pass^3; regressions; unverified count; cost, turns, tool calls from traces; human minutes from manifests. `success + failure == n` per arm.

## CLI contract

```
art30 scan <repo> --arm advanced|baseline [--case ID] [--seed N] [--mode live|replay] [--approve ask|auto] [--out DIR]
```
Makefile targets: `setup`, `smoke` (runs `trace_check.py` over committed traces), `fixtures` (must leave a clean `git diff`), `run CASE=`, `baseline`, `advanced`, `eval`, `eval-replay` (ends with `git diff --exit-code -- results/metrics.json`), `report`, `traces` (author-only, pinned `claude-code-log`), `gate-timing`, `check-secrets` (gitleaks over full history, author-only), `check-traces`, `verify-docs`, `check-clean` (qualification-gate checks).

## Writing contract for the rendered record

`docs/writing-rules.md` applies. No emoji. Verdicts render as words in capitals (`NOT ERASED`). Every cell that came from code carries `file:line`. Human-only cells render as "requires human completion". The record never contains the words "compliant", "compliance", or a legal basis.
