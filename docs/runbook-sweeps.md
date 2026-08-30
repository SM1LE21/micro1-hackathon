# Runbook — the live sweeps

The exact commands, in order, from the first live call to the final report. Every number the README quotes comes from an artefact one of these commands writes. Times are `docs/spec/08-plan.md` §2's; the arithmetic is `01-architecture.md` §10's.

## 0. Before the first live call

- `.env` holds `ANTHROPIC_API_KEY=` and `ART30_MAX_USD=` (a per-run ceiling; 6 on synthetic cases, 9 on real — `08-plan.md` §3; the sweep targets refuse to start without it). The file is git-ignored; `.env.example` carries names only.
- `make smoke` green; `make fixtures` prints `fixtures clean`.
- The frozen files (ADR 0006) are unchanged since `7681cb6`: `git log --oneline 7681cb6.. -- baseline/arm.py art30/prompts art30/schema art30/tools.py art30/loop.py art30/llm.py art30/config.py` is empty.

## 1. Calibration — one live S01 baseline run (~4 min, $0.5–1.3)

```
ART30_RECORD=1 uv run art30 scan evals/fixtures/synthetic/S01 --arm baseline --case S01 --seed 1 --mode live --approve auto --out results/.calibration
```

Read off the trace: `usage` per step, `cost_usd` on `run_end`, and the step-1 `cache_creation_input_tokens` (the static prefix). Pin the prefix size and the per-run cost into `docs/spec/01-architecture.md` §10 and `08-plan.md` §3; decide three or five iterations (§3: ≤ $0.90 per synthetic baseline run → five).

## 2. Sweep A — baseline, dev, three seeds (27 runs, ~35 min, $22–49)

```
ART30_RECORD=1 make baseline
```

`make baseline` runs the seven synthetic dev cases until `evals/fixtures/manifests/R01.yaml` exists, then the whole dev split; it ends with `report` scoped to the same cases and arm (an unscoped `report` books every unrun cell as `crashed`). Sweep A over synthetic only is ADR 0005's kill-switch-2 narrowing applied up front; R01/R02 join Sweep B once labelled.

Then `CHANGELOG_EVAL.md` row 1 (Baseline) from `results/metrics.json`; copy `results/metrics.json` → `results/metrics.sweepA.json` and `traces/baseline/` → `traces/baseline.sweepA/` (08-plan Decision 3). Commit `results/`, `traces/`, `evals/cache/`. Kill switch 2 (ADR 0005): no number by Sat 18:30 UTC → narrow to S01–S07.

## 3. First advanced run, then iterations on the dev subset

```
ART30_RECORD=1 uv run art30 scan evals/fixtures/synthetic/S02 --arm advanced --case S02 --seed 1 --mode live --approve auto --out results/.probe
ART30_RECORD=1 uv run python -m evals.harness.run --cases S02,S05,S07 --arms advanced --seeds 1,2,3 --mode live --approve auto --jobs 4
uv run python -m evals.harness.report --runs results/runs --out results/metrics.json --markdown
uv run python -m evals.harness.report --diff results/metrics.prev.json results/metrics.json --stage "Iteration N"
```

One variable per iteration; replay first (`--mode replay`), pay live only for the cases that miss. The real-repo probe (R01, R02, advanced, one seed) is kill switch 3's signal.

## 4. Code freeze — Sunday 19:30 UTC

Rehearsal: `make fixtures && make smoke && make check-clean && ART30_REPRODUCIBLE=1 uv run python -m evals.harness.run --split dev --arms baseline,advanced --seeds 1,2,3 --mode replay --approve auto --jobs 1`.

## 5. Sweep B — dev, both arms, one window (54 runs, ~70 min, $47–104)

```
ART30_RECORD=1 uv run python -m evals.harness.run --split dev --arms baseline,advanced --seeds 1,2,3 --mode live --approve auto --jobs 4
```

## 6. Sweep C — test, both arms, one ledger line (30 runs, ~45 min, $34–72)

```
ART30_RECORD=1 uv run python -m evals.harness.run --split test --arms baseline,advanced --seeds 1,2,3 --mode live --approve auto --jobs 4 --unlock-test --reason "final system, both arms, one window (ADR 0005)"
uv run python -m evals.harness.report --runs results/runs --out results/metrics.json --markdown
```

Commit `results/`, `traces/`, `evals/cache/`, `results/test-runs.log`. Write the S10 note (what the hard case revealed) into `evals/CASES.md` §Errata and `CHANGELOG_EVAL.md`.

## 6a. Running the sweeps on your Claude login (ADR 0008)

The scored sweeps may run on the `claude` CLI already installed and logged in on this machine instead of on the API. Nothing about the arms, the prompts, the tools or the gate changes: `submit_record` is served to the CLI as an MCP stdio tool whose handler *is* `baseline/arm.py` or `advanced/arm.py`, and the record is finalised and rendered by the same code (`docs/brains.md`). What changes is who assembles the request, and therefore what the cost column can honestly say.

```
uv run python -m evals.harness.run --split dev --arms baseline,advanced --seeds 1,2,3 \
    --mode live --approve auto --jobs 1 --brain claude
uv run python -m evals.harness.report --runs results/runs --out results/metrics.json --markdown
```

`--brain claude` reaches every cell as `art30 scan --brain claude`. Two flags are deliberate:

- **`--jobs 1`.** Four `claude` processes against one subscription is the fastest way to meet a usage window, and a sweep that stalls halfway leaves half a comparison. A dev sweep of 54 runs at roughly two minutes a run is about two hours single-threaded; plan the window before starting, not after.
- **`--mode live`.** A local brain records no response, so `--mode replay` is refused by `art30/cli.py` with the reason. The replay of a local-brain sweep is §7's `eval-replay-local`, below.

Each cell is pinned by the harness, not by your settings: `ART30_IGNORE_SETTINGS_FILES=1` drops `~/.config/art30/config.toml` and `art30.toml`, and `ART30_MODEL`, `ART30_EFFORT`, `ART30_MAX_TOKENS`, `ART30_TOOL_BUDGET`, `ART30_SUBMIT_BUDGET` and `ART30_MAX_TURNS` are written back from the harness's own constants (`evals/harness/plan.py` `PINS`). `ART30_MAX_USD` is removed from a local-brain cell — no dollar ceiling exists on a subscription run and the child must not print one — and `ART30_RECORD` does nothing there, because there is no API response to record.

`ART30_CLAUDE_MODEL`, `ART30_CODEX_MODEL` and `ART30_CODEX_PRICES` are pinned too, to the empty string, which the settings loader reads as no value: an exported `ART30_CLAUDE_MODEL` would otherwise move every cell of a sweep, an exported `ART30_CODEX_PRICES` would move every dollar in the cost column, and neither appears in `provenance.config.overridden`, which is computed from the five request variables `art30/config.py` names. So a cell runs at the CLI's own default whatever your shell exports. Which model that turned out to be is an observation, not a pin: `run_start.config.brain_model` is the configured value (null when the CLI chose) and `record.json`'s `provenance.brain_model` is the model that actually answered. The report reads the second, publishes it as `brain_model`, and refuses a tree whose runs do not share one.

**What the numbers mean.**

- `results/metrics.json` carries `"brain"`, `"brain_model"` and `"cost_source"` at the top and in every arm block, and `"model"` is the model that answered rather than the API brain's pin. The report refuses to write a file that mixes brains, one that mixes `brain_model`s, or one in which a scored run has no trace: measured dollars and a list-price estimate are not one column, two CLI defaults are not one comparison, and a run whose trace cannot be found would otherwise be read as an API run and folded into a column of billed dollars.
- **The traces root follows `--runs`.** `traces/` holds the scored tree's traces; a sweep at any other `--out` took its traces with it to `<out>/traces`, and `report --runs <that tree>` looks there for them. `--traces <dir>` overrides it for a tree whose traces were moved after the fact.
- The cost row is labelled **"Cost per task (estimate at list prices)"**. The `claude` CLI reports its own token counts; `art30/brains/pricing.py` prices them at API list prices. It is not what the run cost you — a subscription run costs no marginal dollars — it is what the same tokens would have cost on the API, which is the only number comparable with the baseline's.
- A **tokens row** sits beside it: input · output · cache read · cache write, per run. Read the two cache columns as the input: the CLI puts almost the whole prompt through the cache, so a real run shows a two-digit `input` and six-digit cache numbers (the D02 acceptance run: 14 · 9,435 · 114,399 · 29,249). Reads and writes are separate columns because they price an order of magnitude apart — a cache read is 0.1x input and Claude Code's one-hour cache write is 2x it — and folded into one number the row could not be multiplied back against the price table. A model with no price entry reports the tokens and `n/a`, never `$0.00`.
- **Arm equality** is checked on `prompt_sha` rather than on the step-1 request hash: art30 never sees the bytes the CLI sends, so the hash is null on every step (`06-traces.md` check 12 allows null only when `run_start.config.brain` is not `api`). The instruction text is still compared across the arms; the CLI's own wrapper around it is not, and cannot be.
- **The recording window** is `run_start.ts` per arm, not `recorded_at` on a cache entry, because a local-brain sweep writes no cache. The refusal is the same one: two arms swept in windows that do not overlap carry any drift on one arm alone (`01-architecture.md` §4.2). Run both arms in one sitting.
- The ledger line for a locked sweep records the brain in its reason field (`brain claude; <your reason>`).

**Subscription windows.** Claude plans have rolling usage windows. A sweep that runs into one stalls or fails mid-way; the runs that completed are still scored and the failures ship in `traces/failures/`, so the honest report of a stalled sweep is `success + failure = n` with the failures visible, never a rerun of the missing cells into the same `metrics.json`. If a window is hit, note it in `CHANGELOG_EVAL.md` and re-run the whole sweep in a fresh window.

**The optional API check.** With a key in `.env`, one or two cases on `--brain api` are worth running beside the local sweep, into a separate results tree, to show the two engines agree on the same fixtures:

```
uv run python -m evals.harness.run --cases S01,S02 --arms advanced --seeds 1 \
    --mode live --approve auto --brain api --out results/.api-check
uv run python -m evals.harness.report --runs results/.api-check --cases S01,S02 \
    --arms advanced --seeds 1 --out results/.api-check/metrics.json
```

A separate `--out` is required, not tidiness: one results tree is one brain. The api-check sweep's traces go to `results/.api-check/traces` and `report --runs results/.api-check` reads them there, so the two trees never borrow each other's traces.

## 7. Evidence

```
make eval-replay          # must end in "eval-replay reproduced results/metrics.json"
make gate-timing          # then hand-write results/gate-timing.yaml
make check-traces && make check-clean && make check-secrets
make traces               # author-only; commits traces/build-trajectory.html
```

Then README, REPRODUCE, HOT_TAKE from `results/metrics.json` and the traces; video; Docker rehearsal (`docker build -t hackathon . && docker run --rm hackathon make eval-replay`).

### `eval-replay` for a sweep run on a local brain

`make eval-replay` replays recorded API responses through the loop and is unchanged for `--brain api`. A local-brain sweep has no recorded responses to replay — the model output was produced inside the `claude` process — so its replay re-runs the deterministic half over what the sweep committed: every submitted record and the verifier's full answer to each (`results/runs/<arm>/<case>/s<seed>/brain/submissions.jsonl`), and then every delivered `record.json` through the scorer again. The recipe, for the Makefile:

```make
eval-replay-local:
	uv run python -m evals.harness.reverify --runs results/runs
	ART30_REPRODUCIBLE=1 uv run python -m evals.harness.report \
	    --runs results/runs --out results/metrics.json --markdown
	git diff --exit-code -- results/metrics.json
	@echo "eval-replay-local reproduced results/metrics.json"
```

Three steps, and what each one proves:

1. `reverify` does both halves. It re-runs `advanced/arm.py`'s handler (schema validation, then `art30.verify.check` over the case's fixture) or `baseline/arm.py`'s (schema validation) over every recorded submission and compares its answer to the recorded one key by key; then it re-scores every run, calling `score.score_run` over the delivered `record.json`, the case manifest and the run's own trace — the same call the sweep made — and compares f1, precision, recall, both safety counters, `pass`, `unverified`, `invalid_verdict_for_kind` and `citation_check` against the committed `metrics.json`. It prints `reverified N submissions and M records in K runs, 0 mismatches` and exits 1 on any difference, naming the run and, for a submission, the attempt. This is the claim: on the committed records and the committed fixtures, the verifier still says what it said, and every number in the per-run metrics still follows from the record beside it. `--traces` overrides where it looks for the traces, the same way `report`'s flag does.
2. `report` re-aggregates: it rebuilds `results/metrics.json` from the per-run `metrics.json` files and the traces, with `ART30_REPRODUCIBLE=1` suppressing the timing file and the ledger exactly as the API path does. It recomputes nothing from a record — step 1 is what checks the per-run files it reads — and it refuses if any scored run has no trace.
3. `git diff --exit-code` is the reproducibility claim in one line, unchanged.

For a judge to run this, the sweep's own output has to be in the repository: commit `results/runs/` with each run's `metrics.json`, `record.json` and `brain/submissions.jsonl`, alongside `traces/` and `results/metrics.json`. `submissions.jsonl` is the file the first half reads and `record.json` the second; without the spool the target reports `reverified 0 submissions` and proves only the re-score.

What no brain can do is regenerate model outputs, and the target does not pretend to: it is why the website calls a saved local-brain run "play back" and not "replay" (ADR 0008 item 4). Run `reverify` on an `api` results tree too — it finds no `submissions.jsonl`, prints `reverified 0 submissions and 0 records in 0 runs`, and exits 0.
