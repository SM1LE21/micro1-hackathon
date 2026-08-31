# Reproduction guide

Written for a clean environment. The reproduction path needs no account with any provider.

The scored sweep ran on the author's own logged-in Claude Code CLI, not against the API
(`--brain claude`, ADR 0008 item 1): `submit_record` is served to the CLI as an MCP stdio tool whose
handler *is* `baseline/arm.py` or `advanced/arm.py`, and the record is finalised, verified and scored
by the same code either way (`docs/brains.md`). No API key was used. The model that answered is
`claude-opus-5` (`results/metrics.json` `brain_model`, from each run's `provenance.brain_model`); cost
is an estimate at API list prices from the CLI's own token counts (`art30/brains/pricing.py`,
`cost_source: "cli_estimate"`).

## Setup

Requirements: git, make, and [uv](https://docs.astral.sh/uv/). uv installs Python 3.12 itself.

```
git clone <repo-url>
cd <repo>
make setup     # uv sync --locked; fails loudly if the lockfile is stale
make smoke
```

`make smoke` asserts the interpreter is 3.12, imports `anthropic`, `yaml` and `jsonschema`, checks
`.env.example` and the problem statement are present, runs `evals/harness/trace_check.py` over
`traces/`, then the pytest suite ([FILL: pytest summary line from `make smoke`]), and prints
`smoke OK` (`Makefile`, target `smoke`).

## Reproduce the results (no API key)

```
make eval-replay-local
```

Use this target, not `make eval-replay`. `eval-replay` replays recorded API responses out of
`evals/cache/`; that directory does not exist here, because a local-brain sweep records no responses
(the model output was produced inside the `claude` process). `eval-replay-local` re-runs the
deterministic half instead, in three steps (`Makefile`; `docs/runbook-sweeps.md` §7). First
`evals/harness/reverify.py` re-runs the arm's own submit handler over every recorded submission in
`results/runs/<arm>/<case>/s<seed>/brain/submissions.jsonl` — schema validation, plus
`art30.verify.check` against the fixture for the advanced arm — comparing its answer to the recorded
one key by key, then re-scores every delivered `record.json` through `score.score_run` and compares
f1, precision, recall, both safety counters, `pass` and the quality flags against the committed
per-run metrics; any difference names the run and exits 1.
Then `evals.harness.report` re-aggregates into `results/metrics.json`, with `ART30_REPRODUCIBLE=1`
suppressing the timing file and the ledger. Then `git diff --exit-code -- results/metrics.json`.
No brain can regenerate model outputs and this target does not pretend to; its claim is that on the
committed records and fixtures the verifier still says what it said, and every published number still
follows from the record beside it.

Expected final lines:

```
reverified [FILL: N] submissions and [FILL: M] records in [FILL: K] runs, 0 mismatches
[identity_check.n] runs: [identity_check.success] success, [identity_check.failure] failure  (success + failure == n: ok)
dev   baseline F1 [arms.baseline.dev.f1_mean] ± [..f1_std_seeds] | advanced F1 [arms.advanced.dev.f1_mean] ± [..f1_std_seeds] | false safe [arms.baseline.dev.false_safe_total] → [arms.advanced.dev.false_safe_total]
test  baseline F1 [arms.baseline.test.f1_mean] ± [..f1_std_seeds] | advanced F1 [arms.advanced.test.f1_mean] ± [..f1_std_seeds] | false safe [arms.baseline.test.false_safe_total] → [arms.advanced.test.false_safe_total]
McNemar (pass, majority of 3): dev b=[comparison.dev.mcnemar.b] c=[comparison.dev.mcnemar.c] p=[comparison.dev.mcnemar.p_exact] | test b=[comparison.test.mcnemar.b] c=[comparison.test.mcnemar.c] p=[comparison.test.mcnemar.p_exact]
wrote results/metrics.json
eval-replay-local reproduced results/metrics.json
```

`git diff --exit-code` prints nothing when it passes, so the last line is the reproducibility claim.
Scored set: dev S01–S07, test S08–S10, both arms, three runs per case, `--jobs 1`
(`evals/split.yaml`, `docs/runbook-sweeps.md` §6a).

## Live re-runs (a logged-in `claude` CLI)

These regenerate the results; they do not reproduce the committed ones. The model takes no
`temperature`, `top_p` or `top_k` and has no seed (ADR 0003 §2), so `s1`–`s3` are harness labels and
the three runs measure sampling variance, reported as mean ± std.

```
uv run python -m evals.harness.run --split dev --arms baseline,advanced --seeds 1,2,3 \
    --mode live --approve auto --jobs 1 --brain claude
uv run python -m evals.harness.report --runs results/runs --out results/metrics.json --markdown
```

The test split, same shape, plus the lock (`docs/runbook-sweeps.md` §6 and §6a):

```
uv run python -m evals.harness.run --split test --arms baseline,advanced --seeds 1,2,3 \
    --mode live --approve auto --jobs 1 --brain claude \
    --unlock-test --reason "final system, both arms, one window"
```

That spends one of the two live test sweeps `evals/split.yaml` allows
(`policy.live_test_sweeps_allowed: 2`) and appends a line to `results/test-runs.log` before the first
call. One repository, one arm, with the human gate:

```
uv run art30 scan <repo> --arm advanced --approve ask --brain claude
uv run art30 scan <repo> --arm baseline --approve ask --brain claude
```

The API is the alternative: `cp .env.example .env`, put `ANTHROPIC_API_KEY` and `ART30_MAX_USD` in
it, then run the same commands with `--brain api` into its own `--out` tree (`docs/cli.md`). One
results tree is one brain: `report` refuses a tree that mixes brains, mixes `brain_model`s, or holds
a scored run with no trace, and `art30/cli.py` refuses `--mode replay` on a local brain
(`docs/runbook-sweeps.md` §6a).

The brain does not move the arms. The harness pins model, effort, `max_tokens` and the budgets per
cell and drops your settings files (`ART30_IGNORE_SETTINGS_FILES=1`, `evals/harness/plan.py` `PINS`),
so no `art30.toml` of yours reaches a sweep; each run header records what ran —
`"effort":"high"`, `"max_tokens":32000`, `"tool_budget":60`, `"submit_budget":5`
(`traces/advanced/S01-s1.jsonl`).

## Runtime and cost

Per run on the claude brain, over the cells finished so far: 42.0–80.1 s wall and USD 0.26–0.41, read
off the `run_end` lines of `traces/baseline/S01-s1.jsonl` … `S03-s2.jsonl` and
`traces/advanced/S01-s1.jsonl` … `S03-s2.jsonl` (`wall_s`, `cost_usd`). Whole sweep:
[FILL from `results/timing.cases-*.json` and `results/metrics.json`]. A subscription run costs zero
marginal dollars; that dollar range is what the same tokens would have cost on the API, the only
number comparable across brains (ADR 0008 item 3). Replay costs nothing and needs no network.

## Data

Both kinds are in the repository and neither holds anyone's data.

**Synthetic cases S01–S10, the scored set.** Generated by `evals/fixtures/gen.py` from the YAML specs
in `evals/fixtures/specs/`, committed under `evals/fixtures/synthetic/`. One spec produces both the
repository and its manifest, so the answer key cannot drift from the fixture. `make fixtures`
regenerates and re-checks them, and must leave a clean `git diff`.

**Real cases R01–R04, vendored but not scored.** `fastapi/full-stack-fastapi-template` @ `486f054`
(MIT), `flaskbb/flaskbb` @ `fc64c74` (BSD-3), `pinry/pinry` @ `05476b1` (BSD-2) and
`miguelgrinberg/microblog` @ `a975ef6` (MIT), under `evals/fixtures/real/`, each with its upstream
LICENSE and a `SOURCE.md` giving url, commit, licence, vendoring date and what was stripped. Their
manifests were never hand-labelled, so they are out of the scored evaluation and stay as demo material
the CLI can scan (`evals/CASES.md` §Errata, 2026-08-31; commit 7521862). Evaluation touches no
network and calls no GitHub API.

## Which numbers came from where

| Number | Produced by | Committed at |
|---|---|---|
| Everything in `results/metrics.json` and `results/report.md` | `make report` over `results/runs/` after the live sweeps; re-derived by `make eval-replay-local` | [commit sha] |
| Wall clock per case and arm | the live sweep, into `results/timing.cases-<sha>.json`; `ART30_REPRODUCIBLE=1` suppresses it, so replay never regenerates it | [commit sha] |
| Which live test sweeps happened | `results/test-runs.log`, appended before the first call | at sweep time |
| Every number in README and CHANGELOG_EVAL | pasted from the files above, never typed | — |

That ledger is chained — each line carries the sha256 of the previous one and the runner verifies the
chain before appending, so deleting lines to reset the budget is detectable (`evals/split.yaml`,
`docs/spec/05-eval-harness.md` §5.4).

## Docker

`Dockerfile` builds `python:3.12-slim` with uv copied in, `uv sync --locked` at build time and
`make eval-replay-local` as `CMD`. It has never been run: the build machine has no container runtime
at all (`docs/evidence/docker-rehearsal.md` holds the attempt and a static review), and the uv layer
is pinned to the moving tag `0.12` rather than a digest. Treat it as unrehearsed and use the uv path
above.

## Versions

Python 3.12 (`.python-version`, asserted by `make smoke`); uv 0.11.26 (`uv --version` on the build
machine); `claude` CLI 2.1.251 (`claude --version`). `uv.lock` pins the rest and `make setup`
installs it with `--locked`: `anthropic` 1.2.0, `pyyaml`, `jsonschema`, plus `pytest` in the dev
group. The verifier uses stdlib `ast` and no parser dependency. Model `claude-opus-5`, the CLI's own
default: `ART30_CLAUDE_MODEL` is pinned to the empty string per cell so a shell export cannot move a
sweep, and the model that answered is recorded per run (`docs/runbook-sweeps.md` §6a).
