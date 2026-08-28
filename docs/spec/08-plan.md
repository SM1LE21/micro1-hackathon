# 08 — Build plan to code freeze and submission

Written 2026-08-28 at 20:17 UTC (`date -u`), hour 5.3 of 75. Deadline 2026-08-31 18:00 UTC; submission target 17:30 (AGENTS.md §Competition facts). Code freeze Sunday, moved to 19:30 UTC for the reason in §1.

At the moment of writing the repository holds decisions, specs, research, ten fixture specs and a Makefile of stubs. It holds no fixture, no harness, no arm and no verifier. Everything below is written against that starting point rather than against the one `.vault/STATUS.md` describes, which was last updated at 16:02 and predates the spec pass.

**Reads with** `AGENTS.md` (build order, deliverables, trace rules), `.vault/adr/0002-gdpr-inventory-erasure-check.md` (kill switches), `docs/spec/00-contract.md` (amended by ADR 0004; it wins), `docs/spec/01-architecture.md` §8 and §10 (concurrency, the cost arithmetic every number here rests on), `docs/spec/03-verifier.md` §10 and §11, `docs/spec/05-eval-harness.md` §5.4, §9, §10 and §11, `docs/spec/fixture-generator.md` §8, `docs/spec/06-traces.md` §6, `evals/CASES.md`, `docs/judging/requirements-matrix.md` (the rubric IDs every row cites).

---

## 1. Build order

### 1.1 The graph

```
  problem statement · ADRs 0001-0004 · specs 00-07, 10 · research · 10 fixture specs
        │  [complete]
        │
        ├── .gitattributes  (evals/fixtures/** -text -diff)  ─────────────┐
        ├── pyproject packaging (art30, evals importable)                 │  all of these
        ├── art30/schema/record.schema.json + spec copy                   │  precede the
        ├── art30/prompts/{system,taxonomy}.md                            │  FIRST cache
        │                                                                 │  write.
        ├── vendor R01–R04 at pinned SHAs ──► hand labels: R03, R04 ──┐   │  01 §Open
        │                                     then R01, R02           │   │  risks 8–9
        │                                                             │   │
        └── evals/fixtures/gen.py ──► synthetic/** + manifests/** ────┤   │
                     │                     │                          │   │
                     │                     └──► blind labels S03, S05 │   │
                     │                                                │   │
                     ▼                                                │   │
                art30/tools.py ──► golden tool test on a reverse-      │   │
                     │             alphabetical fixture ──────────────────┘
                     ▼                                                │
        art30/config.py · trace.py · llm.py ──► count_tokens + S01     │
                     │                          cost calibration       │
                     ▼                                                 │
        art30/loop.py · cli.py · render/markdown.py                    │
                     │                                                 │
         ┌───────────┴───────────┐                                     │
         ▼                       ▼                                     │
   baseline/arm.py     evals/harness/{run,score,report,trace_check}.py │
         └───────────┬───────────┘                                     │
                     ▼                                                 │
              SWEEP A — baseline, dev, 3 seeds, live+record ───────────┘
                     │        (kill switch 2 discharges here)
                     ▼
              CHANGELOG_EVAL row 1
                     │
                     ▼
              tests/verify/**   ← nothing advanced runs before this (matrix G-05)
                     │
                     ▼
   art30/verify/{callgraph,rules,reach,check}.py ──► advanced/arm.py
                     │
                     ▼
      iteration sweeps on the dev subset S02, S05, S07  (05 §11)
                     │      + one advanced probe on R01, R02 (kill switch 3's signal)
                     │
                     ▼
   hardening: check-traces · verify-docs · check-clean · failure index
                     │
                     ▼
              freeze rehearsal (fixtures · smoke · replay of what is recorded)
                     │
                     ▼
              CODE FREEZE — Sunday 19:30 UTC
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
   SWEEP B — dev, both arms   SWEEP C — test, both arms, --unlock-test
         └───────────┬───────────┘
                     ▼
   make report ──► README · REPRODUCE · HOT_TAKE · gate timing · video · traces
```

### 1.2 The constraints the graph encodes

**Eval harness and baseline before the advanced system** (AGENTS.md §Eval rules, matrix X06). `git log` has to show harness and baseline commits before the first commit under `advanced/`. The graph puts Sweep A and its changelog row between the baseline and the first line of `verify/`.

**Fixtures and manifests before any run.** `evals/harness/run.py` refuses a case whose manifest `spec_sha256` differs from the spec on disk, exit 4 (`05-eval-harness.md` §5.1). A spec freezes the moment a run exists for its case (`fixture-generator.md` §8), so every spec edit belongs before Sweep A or it costs an errata line and the deletion of that case's rows.

**Verifier tests before the first advanced run.** The verifier is the load-bearing claim (ADR 0002), and a verifier bug that fabricates a path is a false safe the eval cannot tell apart from a model error (matrix G-05). The core of `03-verifier.md` §10's sixty-five tests ships in the same block as the modules.

**Three things and three amendments before the first recording.** `01-architecture.md` §Open risks 8 and 9 name them: the committed `.gitattributes`, the golden tool-output test on a reverse-alphabetically created fixture, the `count_tokens` measurement of the static prefix; and in code, `max_tokens` 32000 with streaming (ADR 0004 P-11), `request_hash` and `stop_reason` on every step line (P-12), `note` on `run_end` (P-13). A cache recorded before them is a cache to be thrown away, at $80–$176 a sweep.

**Two live test sweeps, and the plan spends one.** §3 explains why.

**Code freeze at Sunday 19:30 UTC**, ninety minutes earlier than AGENTS.md's "~21:00". The reason is mechanical: `run_id` carries the seven-hex sha of the working tree (`00-contract.md` §Trace contract), so a sweep made from uncommitted edits produces run ids that do not resolve. The two reported sweeps have to run against frozen code, and they take about two and a half hours together (§3). Freezing at 19:30 puts both of them inside Sunday evening and leaves 21:00 as the backstop for a fix a sweep forces.

**Evidence phase after.** Nothing under `art30/`, `baseline/`, `advanced/` or `evals/harness/` is touched after the freeze (matrix X29). Report, README, REPRODUCE, HOT_TAKE, gate timing, trajectories, video and the clean-environment rehearsal are all after it.

---

## 2. Schedule

Two workers. The **author** does what only a person can do: blind and hand labelling under the `evals/CASES.md` protocol, the decisions, the gate-timing pass, the trace reads that AGENTS.md's changelog row discipline requires, the video, the final read-through. The **coding agent** does everything else. They overlap by construction: the author starts an agent task, works by hand while it runs, and reviews the commits at the end of the window. Rows that share a window are parallel on purpose.

Sleep is in the table. A solo entrant who plans forty waking hours over three days is planning the Monday morning when the video does not get recorded.

### Friday 2026-08-28

| UTC | What | Who | Done when | Rubric |
|---|---|---|---|---|
| 20:15–20:45 | Answer Q2 (video tooling), Q3 (how much of the lived story), Q4 (repository licence); add the live-API ceiling as Q5 (§Questions for the author 4); write `.vault/adr/0005-plan-amendments.md` (kill switch 2's action, the code-freeze hour) and the dated `evals/CASES.md` §Errata line for the one-window test sweep; paste §9's checkpoints into `.vault/STATUS.md` | author | `.vault/QUESTIONS.md` carries three `[RESOLVED 2026-08-28]` lines and a Q5; `.vault/adr/0005-*.md` exists; `evals/CASES.md` §Errata carries a 2026-08-28 line naming Sweep C | D3g, J1, G02 |
| 20:30–21:15 | `.gitattributes`; `pyproject.toml` packaging; real `fixtures` and `run` recipes in the Makefile. The committed Makefile carries `CASE ?= S10` and no `MODE`: change it to `CASE ?= S05`, add `MODE ?= live` and `OUT ?= results/runs`, and thread `--mode $(MODE) --out $(OUT)` into the `run` recipe | agent | `make run` prints an `art30 scan … S05 --mode live` command line; `make run CASE=S10 MODE=replay OUT=results/.demo` prints the replay form | 01 §4.5, D2b |
| 21:15–21:45 | Vendor R01–R04 at the CASES.md SHAs; strip `.git`, tests, docs; keep LICENSE; write `SOURCE.md` per tree | agent | `ls evals/fixtures/real/*/SOURCE.md` lists four | G02, G03, E5 |
| 21:45–00:15 | `evals/fixtures/gen.py`: spec loader, anchor resolution, the two templates, manifest derivation, the nine assertions of `fixture-generator.md` §8; regenerate all ten cases | agent | `make fixtures` prints `fixtures clean` and exits 0 | D2h, E5 |
| 00:15–07:00 | Sleep | author | — | — |

### Saturday 2026-08-29

| UTC | What | Who | Done when | Rubric |
|---|---|---|---|---|
| 07:00–07:30 | Review the overnight commits; `make fixtures`; read nothing under `evals/fixtures/manifests/` | author | clean `git diff` | D2h |
| 07:30–08:30 | Contingency, taken only if Friday night did not land it: finish `evals/fixtures/gen.py` (`--case`, `--all`, `--check`) and regenerate the ten cases. When it is taken, `art30/llm.py` and the two prompt files move into the 11:00–13:00 block | agent | `make fixtures` prints `fixtures clean` | D2h, E5 |
| 07:30–11:00 | `art30/schema/record.schema.json` + the byte-identical spec copy; `art30/tools.py`; `tests/test_tools.py` (golden output on a reverse-alphabetically created fixture, the jail, the step-1 hash constant); `art30/prompts/{system,taxonomy}.md` from `10-instructions.md`; `art30/config.py`; `art30/trace.py`; `art30/llm.py` | agent | `uv run pytest tests/test_tools.py tests/test_schema.py` green | 01 §4.5, D1b, X17 |
| 07:30–08:15 | Blind-label S03 under the CASES.md protocol, timer running, manifest unopened | author | `evals/fixtures/manifests/S03.labelling.yaml` committed | G-01, E7, X07 |
| 08:15–09:15 | Blind-label S05, same protocol | author | `S05.labelling.yaml` committed | G-01 |
| 09:15–10:00 | Hand-label R04 (microblog, 24 files) | author | manifest with `labelling_minutes` in the header | E5, X08 |
| 10:00–11:15 | Hand-label R03 (pinry, 75 files) | author | manifest committed; R03 and R04 not opened again until Sweep C | X08, Q19 |
| 11:00–13:00 | `art30/loop.py`, `art30/cli.py`, `baseline/arm.py`, `art30/render/markdown.py`; plus `art30/llm.py` and the two prompt files if the 07:30–08:30 contingency row was taken | agent | `art30 scan evals/fixtures/synthetic/S01 --arm baseline --mode live` writes `record.json` and `record.md` (one live run, priced in §3's smoke line) | B1, J3 |
| 11:15–12:15 | Hand-label R01 (full-stack-fastapi-template, 43 files) | author | manifest committed | E5 |
| 12:15–12:45 | Eat. Away from the machine | author | — | — |
| 12:45–14:45 | Hand-label R02 (flaskbb, 110 files). Two-hour cap; a repo that hits it is dropped, not half-labelled | author | manifest, or a dated line in CASES.md §Errata dropping R02 | E5, Q20 |
| 13:00–14:45 | `evals/harness/run.py`, `score.py`, `report.py`, `trace_check.py`; the test-split lock and the chained ledger | agent | `uv run python -m evals.harness.run --cases S01 --arms baseline --seeds 1 --mode live` completes and scores (one live run, priced in §3's smoke line) | E9, X05, X08 |
| 14:45 | **Manifest drop decision.** If any real manifest is incomplete, drop in the order R02, then R01, each with a dated `evals/CASES.md` §Errata line. R03 and R04 are never dropped: they are test and must be committed before Sweep C | author | every remaining real manifest committed, or an errata line naming the dropped repo | E5, X08 |
| 14:45–15:15 | Calibration: one live S01 baseline run. Pin `usage.output_tokens` per step and `count_tokens` on the assembled static prefix back into `01-architecture.md` §10 and into a test constant | agent | §10's $80–$176 range collapses to a number; the prefix-size test passes | 01 §Open risks 1–2, D2g |
| 15:15 | **Checkpoint: one live run end to end.** Trace validates, record renders, cost is a measured number | author | `uv run python -m evals.harness.trace_check traces/` green | X14 |
| 15:15–17:30 | Failure capture and diagnosis generation; `traces/failures/` wiring; `make baseline`, `make eval`, `make report` recipes; `make smoke` runs `trace_check.py` for real | agent | `make smoke` green on a committed trace | X04, D2b |
| 17:30–18:15 | **SWEEP A** — baseline arm, dev split, seeds 1–3, live with `ART30_RECORD=1`. 27 runs | agent | `results/metrics.json` carries a baseline dev F1 and `identity_check.ok` | C1, B5, E4 |
| 18:15–19:00 | `CHANGELOG_EVAL.md` row 1 (Baseline), written from the sweep; read one baseline trace end to end and write the sentence about what it showed; `cp results/metrics.json results/metrics.sweepA.json` and `cp -r traces/baseline traces/baseline.sweepA`, both committed, because Sweep B overwrites the originals (01 §4.2) | author | one row in the four official columns, one trace ID; `results/metrics.sweepA.json` committed | C1, C2, X02 |
| 18:30 | **Kill switch 2** (ADR 0002, amended in §4; ADR 0005 carries the amendment) | author | — | — |
| 19:00–19:30 | Eat | author | — | — |
| 19:30–23:00 | `tests/verify/conftest.py` and the core of `03-verifier.md` §10 (tests 1–20, 25, 26, 36, 37, 37a, plus 38, 41, 42, 44, 46, 49, 51 — every rule §5's cut list calls core has a test before the Sunday advanced runs); then `verify/callgraph.py`, `verify/rules.py`, `verify/rules/*.yaml`, `verify/reach.py` | agent | `uv run pytest tests/verify -q` green on the written subset | G-05, J2 |
| 23:00 | **Kill switch 1** (ADR 0002, restated in §4), read against this block's own done-when | author | — | — |
| 23:00–06:30 | Sleep | author | — | — |

The four labelling windows are targets, not the protocol's cap. `evals/CASES.md` §Labelling protocol allows two hours per repo and gives no estimate below it, so 45, 75 and 60 minutes are what the author aims at and 120 is what he is allowed. What slips when they are missed, in order: the 12:15–12:45 meal, then the author's review of the 13:00–14:45 agent block, then R02 itself under the 14:45 drop decision. R01 and R02 manifests are committed before Sweep A opens at 17:30 or their cases are not in it (`evals/CASES.md` §Rules: every manifest is committed before the first agent run on that repository).

### Sunday 2026-08-30

| UTC | What | Who | Done when | Rubric |
|---|---|---|---|---|
| 06:30–07:00 | Review the overnight commits; `pytest tests/verify` | author | green | G-05 |
| 07:00–10:00 | `verify/check.py`, `advanced/arm.py` (risk rating, gate, `record.draft.json` on a rejected gate), remaining verifier tests | agent | `pytest tests/verify` green; `art30 scan … --arm advanced` completes on S02 | J2, X15 |
| 10:00–10:30 | First advanced live run, S02, one seed | agent | the trace shows a rejected submit followed by a revision; if the arm accepts on its first submit, D4d falls to the 16:30–17:30 adversarial pass, whose malformed-record case rejects a submit by construction | D4d, Q12 |
| 10:30–12:00 | Iteration 1 on the dev subset (S02, S05, S07), advanced arm, 3 seeds, `ART30_RECORD=1`. One changelog row. Archive the traces the row cites: `cp traces/advanced/{S02,S05,S07}-s*.jsonl traces/iterations/row1/` | agent + author | row with dev delta, cost delta, regressions, one trace ID resolving under `traces/iterations/row1/` | C3, C4, X28 |
| 11:00–11:30 | Advanced arm, live, R01 + R02, seed 1 only, `ART30_RECORD=1`. The only real-repo advanced run before the freeze, and kill switch 3's only signal | agent | two records written; the `unverified` tuple count per repo printed | ADR 0002 §Consequences, X28 |
| 12:00 | **Kill switch 3: unverified rate on R01 and R02.** See §4 | author | — | — |
| 12:00–12:30 | Eat | author | — | — |
| 12:30–16:30 | Iterations 2 to N (§3 fixes N). One variable per row, replay first and live only where replay misses, `ART30_RECORD=1` on every live re-run. Archive each row's traces to `traces/iterations/row<N>/` before the next row starts | agent + author | one `docs(changelog)` commit per row, interleaved with the code commit it measures; each row's trace ID resolves under `traces/iterations/row<N>/` | C3, C5, X28 |
| 16:30–17:30 | Adversarial pass: prompt-injection string in a fixture read path, a malformed record at `submit_record`, a citation the renderer cannot resolve, a forced timeout | agent | each lands on its own `stop_condition` with a diagnosis file | 01 §9, X04 |
| 17:30–18:30 | Qualification-gate targets: `check-traces`, `verify-docs`, `check-clean`; `traces/failures/README.md` index; `render/html.py` if the hour is there | agent | the three targets exit 0 | matrix §Qualification-gate risks |
| 18:30–19:30 | Freeze rehearsal: `make fixtures`, `make smoke`, `git status` clean, `wc -l` over the solution tree against the 300-line rule, and the replay of what is actually recorded — `--split dev --arms baseline --seeds 1,2,3 --mode replay`, then `--cases S02,S05,S07 --arms advanced --seeds 1,2,3 --mode replay`, then `--cases R01,R02 --arms advanced --seeds 1 --mode replay` | agent + author | all three replay selections exit 0; no file over ~300 lines | J5, X17 |
| 19:30 | **CODE FREEZE.** Last commit touching `art30/`, `baseline/`, `advanced/`, `evals/harness/` | author | `git log -1 --format=%H -- art30 baseline advanced evals/harness` predates every later commit | X29 |
| 19:30–21:00 | **SWEEP B** — both arms, dev split, seeds 1–3, live with `ART30_RECORD=1`. 54 runs, both arms in one recording window | agent | `report.py` writes `metrics.json` without tripping the window or `prompt_sha` refusals | B5, E3, 01 §4.2 |
| 21:00–22:00 | **SWEEP C** — both arms, test split, seeds 1–3, live with `ART30_RECORD=1`, `--unlock-test --reason "final system, frozen at <sha7>"`. 30 runs. This is the only live run of the test split in the plan, so it is the only thing that can write the test half of the replay cache | agent | one new chained line in `results/test-runs.log` | X08, E3 |
| 22:00–22:45 | `make report`; final `CHANGELOG_EVAL.md` row; the S10 note in `evals/CASES.md` §Errata and as a `CHANGELOG_EVAL.md` line, with the Sweep C trace ids for both arms; commit `results/`, `traces/`, `evals/cache/` | agent + author | `identity_check.ok == true`; `success + failure == n` printed; `test -d evals/cache/S08 && test -d evals/cache/R03` before `evals/cache/` is committed; the S10 note names one baseline trace id and one advanced trace id | X05, E4, E6 |
| 22:45–06:00 | Sleep | author | — | — |

A full `make eval-replay` is not possible before Sweep C. The target is `--split all … --mode replay` over 84 runs (`05-eval-harness.md` §10), and the test half of the cache does not exist until Sweep C records it, so 30 of those runs would raise `ReplayMiss` and the runner would exit 5 (§5.5). The freeze rehearsal therefore replays the selections that are recorded, and the whole-corpus replay is the Monday 06:00 clean-clone rehearsal's job, which is where §6 Deliverable 02 already puts it.

### Monday 2026-08-31

| UTC | What | Who | Done when | Rubric |
|---|---|---|---|---|
| 06:00–06:45 | Clean-clone rehearsal in a scratch directory: `git clone`, `make setup`, `make smoke`, `make eval-replay` | author | `metrics.json unchanged`, exit 0 | J5, D2a, X23 |
| 06:45–07:15 | `make gate-timing` (replay, `--approve ask`, six cases); hand-write `results/gate-timing.yaml` | author | six entries with `wait_s` | 05 §9, G-01 |
| 07:15–09:15 | README: the four questions in PDF order, the results table pasted from `make report`, the sentence saying the gate approved by construction in every scored run. REPRODUCE: measured runtime and cost, the two-sweep rule, `ART30_UNLOCK_TEST`. HOT_TAKE from a real failure trace | agent + author | every number in both files resolves to a committed artefact | D1c, D2d–g, D1f, J6 |
| 09:15–09:45 | `make traces` → `traces/build-trajectory.html`; `make check-secrets` | author | HTML committed and newer than the last code commit; gitleaks clean | D4a, X20, X26 |
| 09:45–11:45 | Record the video: problem and baseline (0:00–1:00), the S10 execution from `docs/demo-script.md` (1:00–2:30), comparison table, changelog highlights, the change that contributed most, one removed row (2:30–3:30). Before the take, `cp traces/advanced/S10-s1.jsonl /tmp/S10-s1.sweepC.jsonl`; the shot is `ART30_UNLOCK_TEST=1 make run CASE=S10 MODE=replay OUT=results/.demo`, which is a replay of the Sweep C run | author | file ≤ 5:00, target 3:00–3:30; `/tmp/S10-s1.sweepC.jsonl` exists before the first take | D3a–f |
| 11:45–12:15 | Eat | author | — | — |
| 12:15–13:15 | Edit and upload; link in README; restore the Sweep C evidence the demo take touched: `git checkout -- traces/ results/` | author | link resolves; `git status` clean under `traces/` and `results/` | D3a |
| 13:15–14:30 | Final read of README, REPRODUCE, HOT_TAKE and one rendered `record.md` against `docs/writing-rules.md`; X01 citation pass, line by line | author | no number without a citation; no banned word | X01, X12, J3 |
| 14:30–15:00 | Docker path: `docker build -t hackathon .`, `docker run --rm hackathon make eval-replay` | author | exit 0 | J5, G10 |
| 15:00–16:15 | Buffer. This is the hour that absorbs whatever went wrong | author | — | — |
| 16:15–17:00 | Submission checklist (`docs/submission-checklist.md`); final commit; push | author | `git status` clean; `git log -1` pushed to the remote; the checklist lists a gitleaks line, an X24 forbidden-name grep line, and the four committed `results/` paths | X30, X20, X24 |
| 17:00–17:30 | **SUBMIT** | author | timestamp at or before 17:30 | X30 |

Sleep totals 6.75 h Friday, 7.5 h Saturday, 7.25 h Sunday. Meals are in the table on Saturday and Sunday because those are the days they get skipped.

---

## 3. Live-sweep budget

Every per-run figure is `01-architecture.md` §10's, which `05-eval-harness.md` §11 defers to. Synthetic run $0.53–$1.28, real run $1.85–$3.73, an advanced verify round $0.15–$0.30 synthetic and $0.35–$0.70 real. The spread rests on one unmeasured quantity, thinking billed as output at effort `high`, and the 15:15 Saturday calibration collapses it.

| Sweep | Shape | Runs | Cost | Wall clock at `--jobs 4` |
|---|---|---:|---:|---:|
| Calibration | S01, baseline, 1 seed, live | 1 | $0.53–$1.28 | 4 min |
| Smoke and adversarial | S01 baseline ×2 (the two done-whens on Sat 11:00–13:00 and 13:00–14:45), S02 advanced ×1 (Sun 10:00), the adversarial pass's forced timeout, malformed record and unresolvable citation ×3 | 6 | $4–$9 | — |
| Real-repo probe | R01 + R02, advanced, 1 seed, one verify round each | 2 | $4–$9 | 10 min |
| Iteration | S02 · S05 · S07, advanced, 3 seeds | 9 | $6–$14 | 10 min |
| Sweep A | dev, baseline only, 3 seeds | 27 | $22–$49 | 35 min |
| Sweep B | dev, both arms, 3 seeds | 54 | $47–$104 | 70 min |
| Sweep C | test, both arms, 3 seeds | 30 | $34–$72 | 45 min |

The task's framing of an iteration sweep as 9 cases × 2 arms × 3 runs is Sweep B's shape, and Sweep B is an anchor, not an iteration. Iterating on it costs $47 a time at the floor and takes over an hour, so `05-eval-harness.md` §11 puts iterations on the three dev cases with the most non-reaching tuples, advanced arm only. Sweep B runs twice at most across the weekend, and this plan runs it once.

**Total ceiling $300**, an author-owned number the plan assumes and cannot cite; §Questions for the author 4 carries it. **Planned spend $142–$286:** at the floor, $111.53 for everything but the iterations plus five at $6; at the ceiling, $244.28 plus three at $14. Sweeps B and C are reserved off the top ($81–$176), which leaves $124 at the ceiling for everything before them.

**Number of changelog iterations the budget allows: five at the floor, three at the ceiling.** The Saturday 15:15 calibration decides which, inside the first hour of live running. If the measured cost of a synthetic baseline run is at or under $0.90, five iteration sweeps fit; above it, three. Three is what the ceiling arithmetic supports: $1.28 calibration + $9 smoke and adversarial + $9 real-repo probe + $49 Sweep A + 3 × $14 = $110.28 against $124. A sixth comes out of contingency and only once Sweeps B and C are banked, which is Sunday night, which is too late for a sixth. Rows measured by unit test rather than by sweep are free and are not counted here; `03-verifier.md` §10's fixtures are where a rule whose failure shape lives only on a test case gets developed (`05-eval-harness.md` Decision 14).

**Hard stop = $300 minus the measured cost of Sweeps B and C, re-derived at the Saturday 15:15 calibration. $124 until it is measured.** Beyond it the remaining budget belongs to Sweeps B and C and nothing else. The earlier fixed $220 was $300 minus the floor reservation, which funds the two reported sweeps only if they come in at their floor: at their ceiling, $220 spent first plus $176 is $396. Cost is read from `results/metrics.json`'s `cost_usd_total` per arm, summed across sweeps.

`ART30_MAX_USD` is the per-run guard so one runaway run cannot eat an iteration (`00-contract.md` §Budgets), and it is deliberately set to trip rather than to overspend: crossing it does not skip a run, it ends it with `stop_condition: budget_exhausted`, and a failed run scores `f1 = 0.0` and stays in the denominator (`05-eval-harness.md` §4.4, Decision 1). At `01-architecture.md` §10's ceiling an advanced real-repo run with two verify rounds is $3.73 + 2 × $0.70 = $5.13, close enough to $6 that the guard could convert a cost overrun into a scored failure on R01–R04 inside Sweeps B and C, where nothing can be fixed. So: **6 on synthetic cases, 9 on real ones.**

### When a sweep is skipped in favour of replay

Replay first, always. It costs nothing and it is exact (`01-architecture.md` §4.4). What the change touches decides what comes back.

| Change | What happens on replay | Action |
|---|---|---|
| `score.py`, `report.py`, a manifest, a renderer | No request byte moves; no miss. `metrics.json` changes | Replay plus `make report`. Never a sweep. This is exactly the class §4.4 says hashes cannot see, and the `git diff` is the check |
| A verifier rule that only makes the verifier **stricter** on a run it already rejected | The rejection text changes, so the next request changes | Replay misses on those cases only. Live re-run of the missing cases, not the sweep |
| A verifier rule that makes the verifier **accept** where it rejected | The loop stops earlier; every request it makes is in the cache | Replay completes. The number is free and valid |
| `prompts/system.md`, `prompts/taxonomy.md`, a tool schema, `record.schema.json`, `ART30_MODEL`, `ART30_EFFORT`, `ART30_MAX_TOKENS`, either budget | Step 1's hash moves in every run | Full re-record. At most **two** of these across the weekend, and each one costs a whole sweep |

So the working rule for an iteration: run replay, read the miss list, and pay live only for the cases that missed. A rule change that is purely a tightening on two dev cases costs two runs, not nine.

### The two live test sweeps, and why this plan spends one

`evals/CASES.md` §Rules says the test set is touched twice, once for the baseline and once for the final, and `05-eval-harness.md` §5.4 enforces a ceiling of two live sweeps through a hash-chained ledger. Spending one on a baseline-only test sweep on Saturday collides with `01-architecture.md` §4.2: `report.py` refuses to write `results/metrics.json` when the two arms' `recorded_at` spans do not overlap, and a Saturday baseline against a Sunday advanced arm is precisely the drift that refusal exists to catch.

Decision: **Sweep C runs both arms in one window, and the second ledger slot is held for a re-record.** The reported test comparison then comes from one window with both arms in it. The baseline arm's code is frozen from Saturday 18:15 and unchanged, so nothing about it is contaminated by running its test cases later. `evals/CASES.md` owes an errata line saying so, dated and naming Sweep C; the author writes it in the Friday 20:15–20:45 row, before any run exists (§Questions for the author 2).

Sweep A's baseline dev cache is superseded by Sweep B's, and superseded means deleted: recording a run clears its slot directory first (`01-architecture.md` §4.2), and `results/runs/baseline/<case>/s<seed>/` and `traces/baseline/<case>-s<seed>.jsonl` are overwritten at the same paths. The two recordings of the same frozen baseline arm, ten hours apart, are a free measurement of the model's own sampling drift and belong in REPRODUCE.md next to the sentence about there being no seed (ADR 0003 item 2), so the Saturday 18:15–19:00 row copies Sweep A's aggregate and traces aside — `results/metrics.sweepA.json` and `traces/baseline.sweepA/` — and commits them. Without that copy the drift claim has no artefact and comes out of §3 and §Decisions 3 instead.

---

## 4. Kill switches

Each one names a time, a signal and an action. Passing the time with the signal absent is the switch closing, and it is recorded in `.vault/STATUS.md`.

| # | Time (UTC) | Signal | Action | Source |
|---|---|---|---|---|
| 1 | Sat 23:00, the 19:30–23:00 block's own done-when; Sun 06:30 if the block overruns | `path_exists` does not pass `tests/verify/` tests 1, 7, 15, 18, 36, 37 and 38 — the S01, S02, S03, S09 and S10 shapes | Narrow the verifier to "a deletion primitive for the store is reachable within the erasure module", log the narrowing in `.vault/AMBIGUITIES.md`, continue. Costs recall on R02 and R03, not correctness | ADR 0002, restated: see below |
| 2 | Sat 18:30 | No baseline F1 on the dev set | Drop R01 and R02 from Sweep A and run it on the seven synthetic dev cases. A number by 20:00 or the fallback in ADR 0002 opens | ADR 0002, amended: see below; ADR 0005 |
| 3 | Sun 12:00 | The advanced arm renders more than half the tuples of R01 and R02 `unverified` | Cut the real repos from the iteration loop and report them as a separate table with the unverified count beside it. Do **not** cut them from Sweep C: the test split is where the honest number lives | ADR 0002 §Consequences ("what would reopen this decision"); `03-verifier.md` §Open risks 2 |
| 4 | Sat 11:00 | `make fixtures` does not produce a clean `git diff`, or the nine assertions of `fixture-generator.md` §8 cannot all pass | Hand-write S01, S02 and S10 as literal repositories with hand-written manifests, drop the other seven, take the errata line. `fixture-generator.md` §Open risks calls this trade worse than it looks; it is still better than no fixtures | `fixture-generator.md` §8, §Open risks |
| 5 | Sat 15:15, re-read at Sun 11:30 | Measured `usage.output_tokens` per step implies, through `01-architecture.md` §10's arithmetic, an advanced real-repo run above $4.40. The Sunday 11:00–11:30 probe reads the same threshold from two measured real runs instead of an implication | Drop R02 from the dev iteration set, hold `ART30_MAX_USD` at 6 synthetic and 9 real, and re-derive §3's iteration count from the measured figure | `01-architecture.md` §10, §Open risks 1 |
| 6 | Sun 17:30 | Cumulative live spend above the derived hard stop: $300 minus the measured cost of Sweeps B and C, $124 until the Saturday calibration measures it | Stop iterating. The rest of the budget belongs to Sweeps B and C | §3 |
| 7 | Sun 19:30 | Freeze rehearsal red: `make fixtures` dirty, `make smoke` failing, or either replay selection missing | Freeze anyway at 21:00 with the failing target named in REPRODUCE.md, and re-time the night: Sweep B 21:00–22:30, Sweep C 22:30–23:30, `make report` and the commit window 23:30–00:15, sleep 00:15–06:30, switch 8 read at 23:30. An unreproducible submission scores zero (AGENTS.md §Competition facts); a submission with one honestly documented red target does not | matrix §Qualification-gate risks |
| 8 | Sun 22:45 | Sweep C did not complete, or its failure rate is above 20% | Spend the second ledger slot Monday 06:00, before the video, and cut the Docker rehearsal and the HTML render to pay for the hours | `05-eval-harness.md` §5.4 |
| 9 | Mon 09:45 | Video not started | Record one 3-minute take with no editing, straight from `docs/demo-script.md`, and cut the comparison-table segment to a still | D3a |
| 10 | Mon 15:00 | Anything outstanding | Take §5's item 4, the Docker rehearsal: at 15:00 it is the only cut whose last hour has not passed, and that is worth reading as the warning it is. Everything else the switch could have spent was spent on Sunday, and the answer at 15:00 is the 15:00–16:15 buffer and then submitting what exists | X30 |

**Switch 1 is restated, not moved.** ADR 0002 sets it at Saturday 12:00 on the signal "reachability not passing on the first two synthetic repos". Under the build order AGENTS.md requires — harness and baseline before the advanced system (X06) — no verifier line exists at 12:00 on Saturday, so the switch as written can only ever fire. Its underlying question was answered on Friday by the feasibility spike in `03-verifier.md` §11: 149 lines of stdlib `ast` produced the right verdict on both hard shapes, the S09 wrong-sender decoy and the S10 dead helper. The restatement keeps the same fallback and moves the signal to the unit tests that pin those shapes, at the hour the modules actually exist, which is 23:00 and not 20:00. `verify/reach.py` is written last in the 19:30–23:00 block, so `path_exists` does not exist at 20:00 and a switch read then fires by construction, the same defect it was restated to remove. The signal set names tests 36 and 37 rather than the S02 shape it used to claim: soft delete is `test_r25_is_active_false` and `test_r25_soft_delete_plus_purge` (`03-verifier.md` §10), while test 7 is R5 delete-orphan and test 15 is R8 `FileField`.

**Switch 2 is amended.** ADR 0002's action is "switch to the prospect-researcher fallback on a synthetic corpus, in a new ADR". At hour 27 of 75, with the specs, the fixtures and the labelled manifests already built against Art. 30, that action throws away more than it saves, and it does not address the failure it responds to. The realistic failure at Saturday 18:00 is that the runtime is not finished, and switching problem domain does not finish a runtime. The amended action narrows the sweep instead. This amends an accepted ADR, so it belongs in ADR 0005, which the author writes in the Friday 20:15–20:45 row: without that file the switch's action at Saturday 18:30 is still ADR 0002's "switch to the prospect-researcher fallback". The read moves from 18:00 to 18:30 for a duller reason — Sweep A's own done-when is 18:15, and a switch read fifteen minutes before its signal exists narrows a sweep that is still running.

---

## 5. Cut order

### Already decided, not cuts

Neither of these returns an hour or a dollar on Monday, and both used to head this list.

- **R05.** Already reserve (`evals/split.yaml`), and nothing in this plan runs it (§Open risks 5). Cutting it on Monday frees nothing.
- **The AI Act extension.** Cut outright in §Decisions 10 before the weekend starts: NON-GOALS gates it behind a locked GDPR test number by Saturday ~22:00 UTC and this schedule puts that number on Sunday night, so the gate does not open. It goes in `CHANGELOG_EVAL.md` as a scope row with the date, the gate condition and the reason it stayed shut.

### The cut list

First to go at the top. Each line names what it costs, what it returns, and the last hour at which taking it still returns that. **Items 1 to 5 the agent or the author may take alone. Items 6 to 10 need the author,** because each one costs a claim in the README.

| # | Cut | Returns | Last hour it still returns it | Costs |
|---|---|---|---|---|
| 1 | **`art30/render/html.py`** | 1 h | Sun 18:30 (it is conditional work in the 17:30–18:30 row) | The citation tooltips in the video's 1:15–1:30 beat, which becomes a scroll through `record.md`. Markdown is canonical (ADR 0003 item 8) |
| 2 | **The gate-timing pass** | 30 min | Mon 06:45 | The "0.7 minutes of a person approving" half of the README's comparison. `report.py` prints `n/a (no gate-timing pass recorded)` rather than a zero that reads like a measurement (`05-eval-harness.md` §9) |
| 3 | **Iteration sweeps beyond the third** | 1.5 h and $14–$42 | Sun 16:30 | The changelog gets three measured rows instead of five |
| 4 | **The Docker rehearsal** | 30 min | Mon 15:00 | The Dockerfile stays; REPRODUCE.md says the path is unrehearsed rather than implying it was tried |
| 5 | **Verifier tests 51–65** | 1 h | Sun 07:00 | They pin rules no fixture exercises |
| 6 | **pass^3 on the real repos** | $20–$45 | Sun 19:30 (before Sweep B) | Drop seeds 2 and 3 on R01–R04. Breaks "3 runs per arm" (X09) for four cases, so it needs an errata line and a sentence in the README, and it goes only if the alternative is not finishing |
| 7 | **R02 from the dev split** | 2 h of labelling and $8–$16 | Sat 14:45 (the drop decision) | The harder half of the real-repo dev signal. FlaskBB is 110 files and the most expensive case in the set |
| 8 | **`--approve ask` terminal polish** | 45 min | Sun 19:30 | The formatted prompt of `10-instructions.md` §5 becomes a bare y/n. The gate, the checkpoint line and the risk rating stay |
| 9 | **Verifier rules beyond the core** | 2 h | Sun 19:30 | R1, R5, R8, R9, R13, R25, R26 and the `path_exists` core carry S01–S10 (`03-verifier.md` §Open risks 1). Everything else degrades to `unverified`, the safe direction and a reported row |
| 10 | **The blind labelling of S05** | 1 h | Sat 08:15 — spent by 09:15 Saturday and unrecoverable after it | Keep S03. Halves the synthetic half of the human-time denominator; the row survives with n=5 and says so |

### What may never be cut

- **The baseline arm and its measured number.** It is the comparison (PDF p.2, B1). Without it there is no changelog and no measured improvement.
- **The replay path.** `make eval-replay` regenerating `results/metrics.json` with no API key and ending in `git diff --exit-code`. This is the qualification gate (AGENTS.md §Competition facts, J5).
- **Traces for both arms, failures included, with a one-line diagnosis each**, plus `traces/build-trajectory.html`. Deliverable 04. An empty `traces/failures/` is a claim that nothing failed.
- **The README's four questions, in the PDF's order.** D1c.
- **The false-safe row**, reported for both arms whatever it says. It is the error that gets a founder fined (`evals/CASES.md` §Primary metric) and the reason the project exists.
- **`success + failure == n`,** printed and asserted (X05).
- **The human gate and the empty legal cells.** Ground rules 04 and 05 are not optimisations.
- **`make fixtures` leaving a clean diff** (ADR 0003 item 9).
- **gitleaks over full history before the final push** (X20).

---

## 6. Definition of done

### Deliverable 01 — solution code and improvement changelog

- [ ] `make setup && make smoke` green on a clean clone
- [ ] `wc -l` over `art30/`, `baseline/`, `advanced/`, `evals/harness/` shows no file over ~300 lines (X17)
- [ ] `uv run pytest` green, `tests/verify/` included
- [ ] `git log --format=%cI -- baseline evals/harness | head -1` (newest baseline or harness commit) is earlier than `git log --format=%cI --reverse -- advanced | head -1` (first `advanced/` commit). The matrix's X06 proof is "harness and baseline commits preceding the first `advanced/` commit", which wants the newest one; `tail -1` would assert only that baseline work started first
- [ ] `art30/prompts/system.md` and `taxonomy.md` committed, loaded by both arms, `prompt_sha` equal across arms in every trace (P-14)
- [ ] `grep -c 'arm.name' art30/loop.py` shows no branch (01 Decision 1)
- [ ] `CHANGELOG_EVAL.md` has a Baseline first row and a Final last row, every row in the four official columns, at least one row with a negative delta kept, at least one row marked removed, one trace ID per row (C1–C6, X02, X03)
- [ ] `git log --oneline -- CHANGELOG_EVAL.md` shows one `docs(changelog)` commit per row (C3)
- [ ] README opens with the four questions and closes with the failure mode and hot take (D1c, D1f)
- [ ] The S10 note — what the challenging case revealed — in `evals/CASES.md` §Errata and as a `CHANGELOG_EVAL.md` line, naming one baseline and one advanced Sweep C trace id (E6)

### Deliverable 02 — reproduction guide

- [ ] `git clone` into a scratch directory, then `make setup && make smoke && make eval-replay`, exit 0, from a shell with no `ANTHROPIC_API_KEY`
- [ ] `make eval-replay`'s final lines pasted verbatim into REPRODUCE.md §Reproduce (D2d)
- [ ] Runtime measured with `time`, machine stated (D2f)
- [ ] Cost taken from `results/metrics.json` per arm, with the sentence that the baseline's retry attempts are billed in (D2g)
- [ ] Model, effort, `max_tokens`, the no-temperature-no-seed paragraph, and what the three seeds do and do not control (D2e, X09, X10)
- [ ] `ART30_UNLOCK_TEST` and the two-sweep rule documented in the same paragraph (`05-eval-harness.md` §5.4)
- [ ] `docker build && docker run --rm hackathon make eval-replay` exit 0, or the file says the path is unrehearsed
- [ ] All fifteen Makefile targets copy-pasteable with no hidden flags (D2b)

### Deliverable 03 — video

- [ ] Duration ≤ 5:00, target 3:00–3:30 (D3a)
- [ ] Opens on the problem and the baseline's wrong answer on the hard case, from a committed trace (D3b)
- [ ] One realistic execution start to finish, following `docs/demo-script.md` (D3c)
- [ ] The comparison table on screen matches `results/metrics.json` digit for digit (D3d)
- [ ] Two or three changelog rows named aloud with their numbers (D3e)
- [ ] The largest single delta and one removed row both named (D3f)
- [ ] The take is a replay of the Sweep C S10 run, and that run's id — the one in the README results table — is what the segment shows. `traces/advanced/S10-s1.jsonl` and `results/runs/advanced/S10/s1/` are the committed Sweep C files, unchanged by the take (demo-script checklist)
- [ ] The word "compliant" is not spoken

### Deliverable 04 — agent trajectories

- [ ] `traces/baseline/` and `traces/advanced/` non-empty, one file per completed run
- [ ] `traces/failures/<arm>/` non-empty, every `.jsonl` with a `.diagnosis.txt` beside it (X04)
- [ ] `uv run python -m evals.harness.trace_check traces/` green, all sixteen checks (`06-traces.md` §3)
- [ ] Every `tool_calls[].id` has a matching `tool_results[].call_id` (D4c)
- [ ] At least one advanced trace shows a rejected `submit_record` followed by a revision (D4d)
- [ ] Every advanced trace carries a `checkpoint` line with `caller: "harness"` and its risk rating (X15)
- [ ] No baseline tool result anywhere contains `rejected_claims`, `missing_stores`, `missing_entry_points`, `bad_citations`, `unverified` or `conservative_divergences` (01 Decision 21)
- [ ] `traces/build-trajectory.html` committed and newer than the last code commit (X26, G-02)

### Cross-cutting

- [ ] `gitleaks detect --source . --log-opts="--all"` clean, output pasted into the submission checklist (X20)
- [ ] `grep -ri` over the tree and history for the forbidden name list returns nothing (X24)
- [ ] Every number in README, REPRODUCE and CHANGELOG_EVAL resolves to a committed file path, test name or trace ID (X01, G09)
- [ ] `results/metrics.json`, `results/timing.json`, `results/gate-timing.yaml`, `results/test-runs.log` committed
- [ ] One rendered `record.md` read end to end against `docs/writing-rules.md`; no banned word, no legal cell filled, no "compliant" (X12, G05)
- [ ] `docs/submission-checklist.md` exists and carries the gitleaks output, the X24 forbidden-name grep line and the four committed `results/` paths (X20, X24, X30). Assumption: the checklist is a file at that path; the matrix names it ("output pasted into the submission checklist") without fixing one

---

## 7. Saturday's first four hours

07:30–11:00 UTC, in write order, so the coding session starts without re-reading the specs. Every item names the spec section that fixes it. (07:00–07:30 is the author's review row in §2, not an agent block.)

1. **`evals/fixtures/gen.py`** — the 07:30–08:30 contingency row in §2, taken only if Friday night did not land it. `--case`, `--all`, `--check`. Spec: `fixture-generator.md` §2 (spec format), §3 (the two templates), §4 (anchors), §5 (what each knob emits), §6 (manifest derivation and the implication check), §8 (the nine assertions). When it is taken, items 9 and 10 move into the 11:00–13:00 block.
2. **`evals/fixtures/synthetic/**`, `evals/fixtures/manifests/*.yaml`, `evals/fixtures/synthetic/.gen-index.json`** — generated and committed. `make fixtures` must print `fixtures clean`.
3. **`art30/schema/record.schema.json`** and the byte-identical copy at **`docs/spec/record.schema.json`**. Spec: `04-output-schema.md`, `00-contract.md` §Record vocabulary. The copy already exists; the shipped one is written from it and the hash equality is asserted in step 8.
4. **`art30/config.py`** — `Config` dataclass, `load()`, `read_dotenv()`, `trace_config()`, budget selection by case kind. Spec: `01-architecture.md` §1.3 and §6. The two budget variables are `ART30_TOOL_BUDGET` and `ART30_SUBMIT_BUDGET`; the older names in an early draft would have run every real-repo case at the synthetic 60-call budget with nothing erroring (`01-architecture.md` §6).
5. **`art30/trace.py`** — the four line writers, one JSON object per line, flushed per line, fields in contract order including `request_hash`, `stop_reason`, `note`, `config`, `prompt_sha`, `wait_s`, `human_completions`. Spec: `00-contract.md` §Trace contract, ADR 0004 P-10 to P-14.
6. **`art30/tools.py`** — `SPEC` as a literal tuple in the order `list_tree`, `read_file`, `grep`, `submit_record`; `resolve()` jail with symlinks resolved before the containment check; every traversal sorted before it is emitted; `grep` sorted before the `max_results` cut; `read_file` splitting on `\n` and stripping a trailing `\r`; `end_line` as `anyOf` integer-or-null, in `required`, clamped. Spec: `01-architecture.md` §1.3, §7, Decisions 12, 14, 15, 23.
7. **`tests/conftest.py`** and **`tests/test_tools.py`** — golden output for `list_tree` and `grep` against a committed string, on a fixture whose files are created in reverse-alphabetical order; jail escape cases; the recursive `rglob` case. Spec: `01-architecture.md` §4.5, Decisions 14 and 15.
8. **`tests/test_schema.py`** — the shipped schema and the spec copy hash equal; the handler invariants. Spec: `00-contract.md` §Repository layout, P-07.
9. **`art30/prompts/system.md`** and **`art30/prompts/taxonomy.md`** — spliced from `10-instructions.md` §1–§5, byte-identical for both arms. Includes the store-identity convention (ADR 0004) and the tool budget named in the first user message (`10-instructions.md` §3), which is why both budgets are inside the request hash.
10. **`art30/llm.py`** — `build_request`, `canonical`, `request_hash`, `prices(model)` keyed by model id, `cost_of`, cache read and write under `evals/cache/<case>/<arm>/s<seed>/<NN>.json` with the slot directory cleared before the first write, `client.messages.stream(...).get_final_message()` unconditionally, `stop_reason` checked before `content` is read. Spec: `01-architecture.md` §1.3, §4.1, §4.2, §5, Decisions 3, 4, 17, 25; ADR 0004 P-11.
11. **Scratch: `count_tokens` on the assembled static prefix.** Under the session scratchpad, not the repository. Pin the measured number into `01-architecture.md` §10 and into a test constant. Spec: `01-architecture.md` §Open risks 2.

The `.gitattributes` line `evals/fixtures/** -text -diff` has to be committed before item 2, or a judge's checkout can convert the fixture bytes and miss every replay (`01-architecture.md` §4.5, Decision 16). If Friday night did not land it, it is item 0.

The author's parallel four hours are in §2: blind-label S03 from 07:30, blind-label S05 from 08:15, hand-label R04 from 09:15, hand-label R03 from 10:00. Nothing in `evals/fixtures/manifests/` gets opened before the timer stops on the case it belongs to.

---

## 8. Risk register

| Risk | Early signal | Mitigation | Owner |
|---|---|---|---|
| The runtime is not finished by Saturday evening and there is no baseline number | The 15:15 checkpoint (one live run end to end) slips past 16:00 | Kill switch 2 as amended: Sweep A on the seven synthetic dev cases, R01 and R02 folded into Sweep B. Cut the HTML render and the adversarial pass to buy hours | agent |
| The verifier's rule surface does not fit the time. Twenty-eight rules, twelve synthetic edge types and six delete modes is a lot for one Saturday night | `pytest tests/verify` still red on tests 1–20 at Saturday 22:00 | `03-verifier.md` §Open risks 1: R1, R5, R8, R9, R13, R25, R26 and the `path_exists` core carry S01–S10; everything else degrades to `unverified`, which is the safe direction. Kill switch 1 narrows further | agent |
| Unverified inflation on the real repos, so the advanced arm cannot separate from the baseline | More than half the tuples of R01 and R02 read `unverified` on the Sunday 11:00–11:30 probe, the one scheduled advanced real-repo run before the freeze | Kill switch 3. Real repos leave the iteration loop and get their own table with the unverified count beside the F1, which is the honest reading either way | author |
| A cache recorded before the pre-recording amendments has to be thrown away, at a sweep's cost | Any live run before `max_tokens` is 32000, `request_hash` is on the step line, `.gitattributes` is committed and the golden tool test is green | The §1.2 ordering, and a smoke assertion that fails a live run when the step line lacks `request_hash`. `01-architecture.md` §Open risks 8 and 9 are the source | agent |
| Replay misses on a judge's machine while passing on the author's. Filesystem order, absolute paths, line endings: all three are invisible where the cache was recorded and fatal everywhere else | The golden tool test on a reverse-alphabetically created fixture goes red, or the committed step-1 hash constant for S01 moves | `.gitattributes`, sorted traversals before emission, `grep` sorted before truncation, repo-relative paths only, the S01 step-1 hash as a committed constant. `01-architecture.md` §4.5 lists the whole class | agent |
| Cost overruns. §3's spread is four times its own floor and rests on one unmeasured quantity | The Saturday 15:15 calibration lands above $0.90 per synthetic run | Iteration count drops from five to three, `ART30_MAX_USD` 6 synthetic and 9 real, hard stop at $300 minus the measured cost of Sweeps B and C with the remainder reserved for them | author |
| Sweeps B and C both run after the freeze, so nothing they reveal can be fixed | The freeze rehearsal at 18:30 Sunday finds anything red | Full dev replay plus `make fixtures` plus `make smoke` before the freeze; kill switch 7 freezes anyway with the failure named; kill switch 8 holds the second ledger slot for a Monday morning re-run | author |
| `report.py` refuses to write `metrics.json` because the two arms' recording windows do not overlap, or their `prompt_sha` differ | The refusal, which is loud and names the offending slots | Sweeps B and C each run both arms in one window (§3), and the run plan is ordered `case → seed → arm` so drift is shared (`01-architecture.md` §8). A prompt edit after Sweep B forces a re-record of both arms, which is why §3 caps prompt edits at two | agent |
| Hand labelling overruns Saturday and the manifests are not committed before the runs that use them | R02 passes 90 minutes without a complete store list | The CASES.md two-hour cap: a repo that hits it is dropped with a dated errata line, not half-labelled. Labelling order puts R03 and R04 first because they are test and must be committed before Sweep C | author |
| The blind labelling of S03 and S05 is not blind enough. The author read the specs during the spec pass, and a spec names the planted trap | Nothing signals this at the time, which is the problem | The sidecar records `blind: true` meaning the manifest was not read before the timer stopped, and that is exactly what it claims. REPRODUCE.md states the limitation: the synthetic manual number is an upper bound on the author's speed and a lower bound on a stranger's. The real repos carry the number that is not compromised | author |
| No genuine removed experiment. C6 requires one and a scope decision is not one | Sunday 16:30 with every iteration row positive | Keep every row, including the ones that made things worse (AGENTS.md §Evidence discipline). The AI Act gate goes in as a scope row, separately labelled, and is not counted as the removed experiment. If no iteration regressed by Sunday afternoon, the honest row is the one that says the change made no measurable difference and was kept or reverted on cost | author |
| `make run CASE=S10` is the video's opening shot and the CLI refuses it. `07-ui.md` §1 and `docs/demo-script.md` build the segment on a test case; `05-eval-harness.md` §5.4 has `art30/cli.py` refuse a direct scan of a test fixture without `ART30_UNLOCK_TEST=1` | The first time the target is run | Decision: `make run` defaults to `CASE=S05`, a dev case, and the Friday 20:30–21:15 row adds the `MODE` and `OUT` variables the shot needs. The video shot runs `ART30_UNLOCK_TEST=1 make run CASE=S10 MODE=replay OUT=results/.demo` after Sweep C, from the committed cache. Replay is exempt from the lock and consumes no sweep budget. `--out` keeps the take out of `results/runs/`; the trace path is fixed by the contract and cannot be redirected, so the take is bracketed by a copy of `traces/advanced/S10-s1.jsonl` and a `git checkout -- traces/ results/` afterwards | agent |
| The build trajectory is missing or stale. It lives in `~/.claude/projects/`, outside the repository | `traces/build-trajectory.html` older than the last code commit at the Monday 09:15 check | `make traces` at every session boundary and last after the freeze; the rendered HTML is the deliverable and the target is documented as author-only with `claude-code-log` pinned at 1.5.0 (`06-traces.md` §6) | author |
| Secrets in history, discovered at hour 70 | Nothing, until gitleaks runs | `.env` gitignored from commit one, `.env.example` names only, `make check-secrets` on the Monday 09:15 line rather than as a thing to remember | author |
| Monday compresses. Video, final docs, Docker and the citation pass all land on one morning | The 06:00 clean-clone rehearsal slips past 07:00 | Kill switch 9 and 10. The 15:00–16:15 buffer exists to be spent; §5 is worked in order, and by Monday afternoon only the Docker rehearsal is still cuttable | author |

---

## 9. Checkpoint table for `.vault/STATUS.md`

The lead replaces the existing §Plan checkpoints table with this one. Times are UTC.

| Checkpoint | Target | Kill switch | State |
|---|---|---|---|
| Direction chosen, ADR written | Fri 16:02 | — | done |
| Specs 00–07, 10 written and reconciled; ADR 0004 | Fri 20:00 | — | done |
| Build plan committed | Fri 20:45 | — | |
| Q2, Q3, Q4 resolved; Q5 (the live-API ceiling) opened | Fri 21:00 | — | |
| ADR 0005 written; `evals/CASES.md` §Errata line for the one-window test sweep | Fri 21:00 | — | |
| `.gitattributes`, packaging, Makefile recipes | Fri 21:15 | — | |
| R01–R04 vendored with LICENSE and SOURCE.md | Fri 21:45 | — | |
| `make fixtures` clean; ten repos and manifests committed | Sat 08:30 | 4 (Sat 11:00) | |
| S03 and S05 blind-labelled, timed | Sat 09:15 | — | |
| Tools, schema, prompts, llm; golden tool test green | Sat 11:00 | — | |
| R03 and R04 labelled and committed; not reopened until Sweep C | Sat 11:15 | — | |
| R01 and R02 labelled | Sat 14:45 | — | |
| One live run end to end; cost and prefix size measured | Sat 15:15 | 5 (Sat 15:15) | |
| **SWEEP A** — baseline dev number | Sat 18:15 | 2 (Sat 18:30) | |
| CHANGELOG_EVAL row 1; Sweep A aggregate and traces copied aside | Sat 19:00 | — | |
| `tests/verify/` core green; callgraph, rules, reach | Sat 23:00 | 1 (Sat 23:00) | |
| `verify/check.py` and `advanced/arm.py`; first advanced run | Sun 10:30 | — | |
| Advanced probe on R01 and R02 recorded; unverified rate read | Sun 12:00 | 3 (Sun 12:00) | |
| Iteration rows complete (three to five) | Sun 16:30 | 6 (Sun 17:30) | |
| Qualification-gate targets; adversarial pass | Sun 18:30 | — | |
| Freeze rehearsal green | Sun 19:30 | 7 (Sun 19:30) | |
| **CODE FREEZE** | Sun 19:30 | — | |
| **SWEEP B** — dev, both arms, one window | Sun 21:00 | — | |
| **SWEEP C** — test, both arms, one ledger line, `ART30_RECORD=1` | Sun 22:00 | 8 (Sun 22:45) | |
| `make report`; S10 note written; results, traces and `evals/cache/` committed | Sun 22:45 | — | |
| Clean-clone replay rehearsal | Mon 06:45 | — | |
| Gate-timing pass; `results/gate-timing.yaml` | Mon 07:15 | — | |
| README, REPRODUCE, HOT_TAKE final | Mon 09:15 | — | |
| Build trajectory rendered; gitleaks clean | Mon 09:45 | — | |
| Video recorded and uploaded; `traces/` and `results/` restored | Mon 13:15 | 9 (Mon 09:45) | |
| Writing-rules and citation pass | Mon 14:30 | — | |
| Docker path rehearsed | Mon 15:00 | 10 (Mon 15:00) | |
| **SUBMIT** | Mon 17:30 | — | |

---

## Decisions taken here

1. Code freeze moves to Sunday 19:30 UTC so both reported sweeps run against frozen code and the seven-hex sha in every `run_id` resolves. 21:00 is the backstop.
2. Sweep C runs both arms on the test split in one recording window, and the second ledger slot is held for a re-record. `01-architecture.md` §4.2's window refusal makes a Saturday baseline-only test sweep unreportable.
3. Sweep A's baseline dev cache is superseded by Sweep B's, which under `01-architecture.md` §4.2 means deleted. The Saturday 18:15–19:00 row copies the aggregate and the traces aside as `results/metrics.sweepA.json` and `traces/baseline.sweepA/`, and the difference between the two recordings of the same frozen arm is reported as a measurement of sampling drift rather than discarded.
4. Iterations run on the three-case dev subset (S02, S05, S07) at $6–$14 a time, never on the 54-run dev sweep. Five iterations at the measured floor, three at the ceiling, decided by the Saturday 15:15 calibration.
5. Replay runs before every live re-run. A change that cannot move a request byte, and a verifier change that only makes the verifier more permissive, are both measured for free; a tightening is paid for one case at a time from the miss list.
6. Prompt, tool-schema, schema and model changes are capped at two across the weekend, because each one re-records every sweep it precedes.
7. ADR 0002's kill switch 1 is restated onto the unit tests that pin the S01, S02, S03, S09 and S10 shapes at Saturday 23:00, the hour `verify/reach.py` exists, keeping the same fallback. The spike in `03-verifier.md` §11 already answered its underlying question.
8. ADR 0002's kill switch 2 is amended: the action at Saturday 18:30 is to narrow Sweep A to the seven synthetic dev cases, not to change problem domain. It needs ADR 0005, written in the Friday 20:15–20:45 row; see §Questions for the author.
9. `make run` defaults to `CASE=S05` and gains `MODE` and `OUT`. The video's S10 shot runs in replay with `ART30_UNLOCK_TEST=1` after Sweep C, writing to `results/.demo`, with the Sweep C trace copied aside and restored around the take.
10. The AI Act extension is cut and recorded as a scope row in `CHANGELOG_EVAL.md`, not as the removed experiment C6 asks for. The removed experiment has to be earned by an iteration.
11. Matrix gap G-03 is closed and needs no work: `evals/CASES.md` §"Definition of a good result" states the dev and test targets, the false-safe zero and the unsignable conditions, and it was committed 2026-08-28, before any run exists.

## Open risks

1. **Saturday is the whole project.** Fixtures, tools, llm, loop, both harness halves, the baseline arm and a live sweep, with the author hand-labelling four real repositories in parallel. Every kill switch before Sunday exists because this day is over-subscribed, and the honest reading of §2 is that Saturday has about two hours of slack in fourteen.
2. **The Saturday agent blocks assume about 2,100 lines of specified code in seven hours, not the thousand an earlier draft claimed.** Against the specs' own budgets: 07:30–11:00 is `tools.py` 220 + `config.py` 90 + `trace.py` 80 + `llm.py` 180 plus the schema, two prompt files spliced from a 604-line source and three test modules; 11:00–13:00 is `loop.py` 190 + `cli.py` 110 + `baseline/arm.py` 45 + `render/markdown.py` 200; 13:00–14:45 is `run.py` 180 + `score.py` 200 + `report.py` 160 + `trace_check.py`. That is roughly 1,800 lines of runtime and eval code plus 300 to 400 of tests. The specs are unusually complete, which is what makes it plausible at all, and nothing in this plan has a fallback for it being wrong beyond kill switch 2's narrowing and the 07:30–08:30 contingency row.
3. **Sweep B and Sweep C both run after the freeze.** A bug either of them reveals cannot be fixed without breaking the freeze, and the only recourse is the second ledger slot and an honest note.
4. **The blind labelling is not blind to the specs.** The author participated in the spec pass that wrote S03 and S05. The sidecar's claim is narrow and accurate; the README has to carry the limitation rather than let the number read as a stranger's.
5. **`--include-reserve` and R05 are in the split file and named in §5 as already decided.** Nothing in this plan runs them, and `identity_check.n` is 84 throughout. A sweep that silently picked up R05 would report 90 against a README that says 84 (`05-eval-harness.md` §5).
6. **Three of `03-verifier.md`'s rules are first met on the test split.** `no_entry_point`, `no_schedule_evidenced` and the admin-only entry point have unit tests and no dev rehearsal (`fixture-generator.md` §9). A bug in any of them is discovered by Sweep C, which is the sweep there is no time to repeat.

## Questions for the author

Four, and none of them blocks a line of code. Each is a decision only the author can make; the plan runs on the stated assumption until it is answered. The Friday 20:15–20:45 row is where the first three become artefacts.

1. **Kill switch 2's action.** ADR 0002 says switch problem domain at Saturday 18:00. §4 amends it to narrowing Sweep A to the seven synthetic dev cases, read at 18:30. Amending an accepted ADR is the author's call, and it needs ADR 0005, which the Friday 20:15–20:45 row writes. Applied 2026-08-28: ADR 0005 item 1.
2. **One live test sweep instead of two.** `evals/CASES.md` §Rules says the test set is touched twice, once for the baseline and once for the final. §3 spends one sweep with both arms in it and holds the second slot for a re-record, because `01-architecture.md` §4.2 refuses to report two arms recorded in windows that do not overlap. This needs a dated errata line in `evals/CASES.md`, which no spec document may edit. Applied 2026-08-28: ADR 0005 and the CASES.md errata line exist.
3. **The code-freeze hour.** AGENTS.md says Sunday ~21:00 UTC; §1 moves it to 19:30 so both reported sweeps run against frozen code. Applied 2026-08-28: ADR 0005 item 2; AGENTS.md updated.
4. **The live-API ceiling for the weekend.** §3 spends against $300, and $300 appears nowhere else in the repository: `00-contract.md` §Budgets carries only `ART30_MAX_USD`, unset by default, and neither `AGENTS.md`, `evals/CASES.md` nor `docs/judging/` names a figure. Every dollar decision here — the reservation, the derived hard stop, the iteration count, kill switch 6 — hangs off it. Recorded 2026-08-28 as ADR 0005 item 4 and `.vault/QUESTIONS.md` Q5; the author may change it.
