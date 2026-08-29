# Spec versus code — the reconciliation

Written 2026-08-29, after Phase 1 and Phase 2 landed (`.vault/STATUS.md`). One row per place the built code and the spec that describes it disagree. The spec was written before any solution code existed; some of it was wrong, some of it was right and the code drifted, and the only way to tell the two apart in an hour is to list them.

Two decisions are available per row:

- **code wins (spec amended)** — the code is right and the spec document now carries an `Amended 2026-08-29:` line at the section named in the first column. History is appended to, never rewritten.
- **spec wins (code owed)** — the code is wrong and the fix is owed before freeze. Nothing on this list is silently dropped.

`00-contract.md` is not editable here: it changes only through an ADR (its own opening line). Rows that need a contract edit carry the proposed wording in §3 below and stay open until an ADR lands.

**Reads with** `.vault/adr/0006-verifier-before-sweep-a.md` (what is frozen and why), `.vault/adr/0004-contract-amendments-after-spec-pass.md`, `AGENTS.md` §Code rules.

---

## 1. Runtime: `art30/llm.py`, `art30/config.py`, `art30/tools.py`, `art30/loop.py`

| # | Spec section | What the spec says | What the code does | Why | Decision |
|---|---|---|---|---|---|
| D-01 | `01-architecture.md` §9, failure-taxonomy table | The `max_tokens` and `pause_turn` rows both name `llm.call, surfaced in loop.run` as the place the condition is raised | `llm.call` raises `LlmError` for SDK transport failures only. The three `stop_reason` exits are read in `loop._run` (`art30/loop.py:178`) and turned into a stop condition by `_early_stop` (`art30/loop.py:301`) | `art30/llm.py`, `_response`: "The three stop_reason exits (refusal, max_tokens, pause_turn) belong to the loop, which traces the step and its usage before it stops (02-agent-loop.md section 1); raising here would lose both." The two spec documents already disagreed — `02` §1 puts all three in the loop — and the loop is where the step line and its usage get written | code wins (spec amended) |
| D-02 | `02-agent-loop.md` §1 line 45; `01-architecture.md` §9 note column | `note="output truncated at max_tokens={cfg.max_tokens}"` (02) / `output truncated at max_tokens=<n> on step <k>` (01) | `output cut off at max_tokens=32000 on step 7` — the step number is carried, the word "truncated" is not | `art30/loop.py:306`: "\"truncated\" is reserved for the harness's own partial-line repair (06-traces.md check 16), so the note says the same thing in other words." Check 16 greps `run_end.note` for a byte count | code wins (spec amended) |
| D-03 | `02-agent-loop.md` §2, "System" | "`config.py` asserts the **spliced** string's sha256 against `PROMPT_SHA`, a constant committed with the prompt" | `art30/config.py` holds no such constant and performs no such assertion. `llm.prompt_sha()` computes the value on demand; the frozen constant lives at `tests/test_llm.py:33` and is asserted by `test_prompt_splice_and_sha`, together with the spliced byte length (16,341) | `tests/test_llm.py:31`: "The spliced instruction text, frozen: an accidental edit to either prompt file invalidates every cache entry, and this is where it fails fast." A constant in `config.py` would also have to be edited every time the prompt is, and `config.py` is frozen by ADR 0006 | code wins (spec amended) |
| D-04 | `02-agent-loop.md` §2, "First user turn" | "`config.py` asserts that the rendered string contains no `os.sep`-prefixed token, so an absolute path cannot arrive through a future template edit" | No such assertion exists in `art30/config.py`, `art30/loop.py` or any test. `FIRST_TURN` is rendered from `case.name`, `cfg.tool_budget` and `cfg.max_submits` only, which is the property the assertion was meant to protect | Nothing in the code claims otherwise; the guard was specified and never written | **spec wins (code owed)** — one assertion in `tests/test_loop.py`, not in `config.py` (frozen, ADR 0006). Cheap; do it before freeze |
| D-05 | `04-output-schema.md` §4 and Decision 4; `02-agent-loop.md` §3 request shape | The record schema "can be sent verbatim as the tool's `input_schema`"; the step-1 request shows `{"record": {/* record.schema.json, inlined */}}` | `art30/tools.py::_submit_input_schema` pops `$schema` and `$id`, lifts `$defs` out of the record schema and re-attaches it at the **tool** `input_schema` root, beside `properties.record` | `art30/tools.py:60`: "`$ref` targets resolve against the document root, and a tool's document root is its `input_schema`: nested `$defs` would leave every ref dangling." Sent verbatim, every `$ref` in the schema would have resolved against nothing | code wins (spec amended) |
| D-06 | `00-contract.md` §Budgets; `01-architecture.md` §7 "Limits as guards"; `10-instructions.md` §1b `grep` description | The five-directory exclusion list (`.git`, `__pycache__`, `node_modules`, `static`, `media`) is stated for `list_tree` only | `EXCLUDED_DIRS` is module-level in `art30/tools.py` and `_greppable` applies it to every `grep` candidate as well | Consistency: a `grep` that returns hits inside `__pycache__` spends the model's 60-call budget on compiled copies of files `list_tree` said were not there. The tool description does not say so, which is the half that is wrong | code wins (spec amended); the description is frozen bytes (ADR 0006) and cannot be corrected before Sweep A without re-recording, so `01` §7 carries the sentence instead; contract wording proposed in §3 |
| D-07 | `00-contract.md` §Tools, output column | Three output shapes: an indented tree, `n: line` numbered text, `file:line: text` lines. No empty case | `list_tree` returns `(empty)`, `read_file` returns `(empty file)\n`, `grep` returns `no matches\n` | `art30/tools.py:196`: "An empty `__init__.py` is a normal answer, not a tool failure; and a tool_result block rejects an empty string, as in grep and list_tree." An empty `content` on a `tool_result` block is a 400 | code wins (spec amended); contract wording proposed in §3 |
| D-08 | `01-architecture.md` §1.1 and §1.2, `Lines` column | `loop.py` 190, `tools.py` 220, `llm.py` 180, `render/markdown.py` 200, `score.py` 200, `gen.py` 200 | 414, 306, 311, 340, 315, and `gen.py` split across twelve modules. `art30/loop.py` and `evals/harness/score.py` are the two that stay over the ~300-line rule: `loop.py` is frozen at 414 by ADR 0006, and `score.py` is imported at run time by `art30/verify/rules.py` so splitting it moves a path the verifier resolves | `art30/verify/rules.py::_load_norm`: "`norm` has one implementation (05-eval-harness.md Decision 5): the scorer's. Imported as a module where the repository is on the path, loaded from the file beside `art30/` where it is not, so the metric and the tool can never drift" | code wins for the estimates (spec amended); **the two over-limit files are a standing AGENTS.md exception**, recorded here rather than hidden |

---

## 2. Verifier: `art30/verify/`

| # | Spec section | What the spec says | What the code does | Why | Decision |
|---|---|---|---|---|---|
| D-09 | `03-verifier.md` §0 "Shape of the thing"; `00-contract.md` §Repository layout | "Four modules, one responsibility each, all under the 300-line rule": `callgraph.py`, `rules.py`, `reach.py`, `check.py` | Thirty-three modules, 6,583 lines: `__init__ anon astdata binding callgraph caps check citations completeness context declared discovery downgrades engines entities entrypoints facts feedback findings imports keyed primitives reach recipients registration rules services stores subjects symbols synthetic timers verdicts` — plus five YAML rule files. `art30/verify/__init__.py` carries the module map | The four responsibilities are unchanged and the data still flows one way; each of the four grew past 300 lines and split under AGENTS.md §Code rules. `verdicts.py`: "reach.py owns the walk and hands this module a context with the paths already found; this module owns which row fires and why" | code wins (spec amended); contract layout edit proposed in §3 |
| D-10 | `03-verifier.md` §2.2, `route` rows | A `route` entry point is detected from a DELETE-carrying route decorator (Flask, FastAPI, DRF) plus the subject qualification | Every fixture route in `S01`–`S10` is an **undecorated module-level function** (`api/account.py::close_account`), so no route row fires and `_unclaimed` records it as kind `unknown`. The manifests call the same function kind `route` | `art30/verify/entrypoints.py:300`: "2.2 last row: a module-level function nothing else claimed, kind `unknown`." The kind is not scored — the tuple is `(store, field, reaches_erasure)` — and `unknown` is "still a valid start node" in the spec's own table, so the walk is unaffected | code wins (spec amended); the manifests keep `route`, and `03` §2.2 now says the two need not agree |
| D-11 | `03-verifier.md` §2.2 `admin` row; §4.3 R16 | "two entry points: `admin_delete_model` … and `admin_delete_selected`" per admin registration | `registration.admin_entry_points` returns exactly two entry points **for the whole repository**, whatever the number of registered models: both cite the first qualifying registration line, both carry `models=[every qualifying model]`, both are `admin_only` | `tests/verify/test_entrypoints.py::test_admin_gives_exactly_two_entry_points` pins the pair, the shared citation and the two `sets_mode` values. Two per model would multiply start nodes that all set the same two modes and reach the same stores | code wins (spec amended) |
| D-12 | `03-verifier.md` §4.2, synthetic-edge table | The table runs SE1–SE12. Entry points are start nodes; nothing gives them an out-edge except SE10 (admin) | A thirteenth edge, **SE0**, from `entry:<name>` to the symbol the entry point names, admissible in every mode, setting none | `art30/verify/synthetic.py:178`: "Only the two admin entry points had an out-edge (SE10), so a walk from `entry:close_account` left the start node with nowhere to go: `path_exists` returned None for every store in every non-admin repository, and S01, S04 and S06 all read `not_erased` however plainly the body deletes." | code wins (spec amended) |
| D-13 | `03-verifier.md` §3.2, "Bucket-or-prefix is the store identity where a bucket name is visible; otherwise the field … names it" | A Django `FileField` store is named after the field | `stores._file_store` names it `<normalised model>.<field>` — `avatar.image`, the id every verdict key and every test uses — and keeps the parent relational store `avatar` beside it | `art30/verify/stores.py:275`: "R8 [S1] [S2]: the row and the bytes have different fates, so two stores." `tests/verify/test_fixtures_reproduce.py::_key`: "`avatar.image` and `uploads` never normalise equal, so a record — and a manifest written in the record's vocabulary — reconciles a Django file store by the `FileField` declaration it cites" | code wins (spec amended); the scorer reconciles by declaration line, not by name |
| D-14 | `03-verifier.md` §4.5, R6 | SQLite enforcement may be evidenced by "`PRAGMA foreign_keys` in a migration or startup module that names it" | `engines.pragma_listener` accepts the evidence only when the listener symbol's module is inside the **engine's own import closure** (`_engine_modules`: the module that builds the engine plus everything it transitively imports), when the listener is registered on `Engine` or on that engine's own variable, and when the PRAGMA literal appears at a call site rather than anywhere in the source span | `art30/verify/engines.py:45`: "A `PRAGMA` in a module nobody loads is a string in a file, and SQLite's foreign keys stay inert." And `_emits`: "Read off the call sites and never off the raw source span. A text scan accepted `# TODO: emit PRAGMA foreign_keys=ON here one day` over a body of `pass`" | code wins (spec amended) |
| D-15 | `03-verifier.md` §3, "A store is `{id, kind, name, …}`"; §3.10 | The graph is keyed `store:<id>`; §3.10 forbids attributing a deletion to a shared client handle | `context.Ctx.add` keys its own table on `(kind, id)`. A second store arriving with a kind already taken by that id keeps its own entry under `<id>#<kind>`, both stores are flagged `store_id_conflict`, and neither is merged | `art30/verify/context.py:147`: "Keyed on the id alone, a `sessions` table and a `session`-prefixed cache namespace became one store, so the relational SE12 edge marked the cache erased and the emails in it survived — a false safe of exactly the shape 3.10 forbids for a client handle." | code wins (spec amended) |
| D-16 | `03-verifier.md` §10, test plan | Sixty-five named tests, every one expected to pass | 339 tests under `tests/verify/`, of which **two are `xfail(strict=True)`**: `test_r09_receiver_without_sender` (spec test 19) and `test_r09_no_sender_receiver_with_guard` (spec test 62). Both are R9 no-sender receivers | `tests/verify/test_verdicts.py:377`: "`instance` is left unbound by `synthetic.add_edges` when the decorator carries no `sender=`, so the body's `instance.image.delete()` is attributed to no store and no SE12 edge exists. The verdict falls to `not_erased`, which is the conservative side of R9 but not what section 10 test 19 asks for." Test 62 fails the same way toward `not_erased` where `unverified` was asked for | **spec wins (code owed)**, and the debt is on the safe side: both failures land conservative. Shipped as strict xfails so the day the graph layer learns to bind `instance` the tests turn red for the right reason |

---

## 3. The edits `00-contract.md` needs

These belong in `00-contract.md` — §Repository layout, §Budgets, §Tools and the Makefile list — and only an ADR may put them there. The proposed wording, for whoever writes it:

**Replace** the four `verify/*.py` lines with:

```
  verify/                 ~30 modules, one responsibility each; art30/verify/__init__.py
                          carries the module map. Entry points: build_graph(root),
                          reach.verdicts(graph), check.check(record, root, rules)
  verify/rules/*.yaml     data: store kinds, deletion primitives, recipients,
                          entry-point patterns, soft-delete markers
```

**Replace** the four `evals/harness/*.py` lines with:

```
  harness/run.py          the sweep: pre-flight gates, lock, launch, timing
    plan.py               case selection and the cell plan
    ledger.py             the test-split ledger and its hash chain
    cells.py              one cell: the child process, its trace, its scoring
  harness/score.py        manifest vs record → per-case metrics (owns norm())
  harness/report.py       results/runs → results/metrics.json + Markdown tables
    stats.py              aggregates, McNemar, the paired bootstrap, human time
    tables.py             the Markdown tables and the changelog row
  harness/trace_check.py  trace validator, checks 1-2 and the CLI
    trace_checks.py       checks 3-18
  harness/verify_docs.py  make verify-docs: README/REPRODUCE numbers vs metrics.json
  harness/failure_index.py  traces/failures/README.md, one diagnosis line per failure
```

**Add** four entries the layout never named and the code needs:

```
art30/arm.py              the Arm protocol, Feedback, RunCtx and the shared
                          schema-invariant handler both arms call
advanced/gate.py          the human checkpoint: risk rating, prompt, edits
evals/split.yaml          dev / test / demo case lists, read by the harness
evals/fixtures/*.py       gen.py plus twelve sibling modules (anchors, checks, emit,
                          manifest, naming, render_*, spec_model)
```

**Replace** the `list_tree` clause of §Budgets' last line (contract line 78) with:

```
`list_tree` and `grep` both exclude `.git`, `__pycache__`, `node_modules`, `static`, `media`.
```

That is the D-06 edit. The `grep` tool description the model reads stays as it is: it is frozen bytes (ADR 0006) and tells the model less than the tool does, which is the safe direction.

**Add** to §Tools, under the output column:

```
An empty result is a placeholder, never an empty string: `list_tree` returns `(empty)`,
`read_file` returns `(empty file)`, `grep` returns `no matches`. None of the three is an
`is_error` result.
```

That is the D-07 edit.

**Add** `test` to the Makefile target list: a sixteenth target, `test`, runs `uv run pytest tests -q`; `make smoke` runs the same command inline rather than calling the target, so an edit to `test` does not reach `smoke`.

Until that ADR lands, the contract's four-module layout, its `list_tree`-only exclusion and its three output shapes are what a reader meets first, and this file is the correction.

---

## 4. Numbers that are still estimates

| # | Spec section | Status |
|---|---|---|
| D-17 | `01-architecture.md` §10, every cost and wall-clock figure | **Unmeasured.** No live run has been made — there is no API credential on the build machine (`.vault/STATUS.md`, Blocker). The section's own instruction stands: "The fix is a measurement, not a better guess: one live S01 run at effort `high` before the batch, with `usage.output_tokens` per step pinned back into this section as a measured number." The 4,000-token static-prefix assumption is likewise unpinned: `client.messages.count_tokens` needs a key, so the only pinned figure is the spliced prompt's **byte** length, 16,341, in `tests/test_llm.py` |
| D-18 | `example-record-S10.md`, provenance block | Run id `adv-S10-s1-9f3ac1e`, the sha values, the timestamps, the 34-second gate wait, the $0.41 and the 21 tool calls are invented and stay invented until the first real S10 run. Every `file:line` in that document has been regenerated from the committed fixture (2026-08-29); the provenance rows have not, because there is nothing yet to regenerate them from. The same invented line `storage.py:41` was corrected to the fixture's `storage.py:29` in `fixture-generator.md` §2, `03-verifier.md` §10 test 53, `04-output-schema.md` §6 and §7, and `anticipated-questions.md` #12. Four documents keep the wrong number on purpose, because they quote `00-contract.md:101`'s feedback example verbatim and the contract changes only by ADR: `03-verifier.md` §7.3, `10-instructions.md` §4, `04-output-schema.md` §5 and `07-ui.md` §3 (and §6, where the same line is the `render_failed` example). They move with the contract line, under the same ADR, together with `09-narrative.md`, `docs/demo-script.md`, `evals/CASES.md` and the worked trace in `06-traces.md` §2 / `02-agent-loop.md` §9 |

---

## 5. What this list is not

It is not a defect list. Fourteen of the eighteen rows are the code being right and the spec being early. The two owed rows (D-04, D-16) are named with their fix, and the two remaining items (D-17, D-18) are measurements waiting on a key, not decisions waiting on anyone.

The rule for the rest of the build: a spec document and the code may not disagree silently. A disagreement is either an `Amended 2026-08-29:` line in the spec or a row here saying the code is wrong.
