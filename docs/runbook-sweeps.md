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

## 7. Evidence

```
make eval-replay          # must end in "eval-replay reproduced results/metrics.json"
make gate-timing          # then hand-write results/gate-timing.yaml
make check-traces && make check-clean && make check-secrets
make traces               # author-only; commits traces/build-trajectory.html
```

Then README, REPRODUCE, HOT_TAKE from `results/metrics.json` and the traces; video; Docker rehearsal (`docker build -t hackathon . && docker run --rm hackathon make eval-replay`).
