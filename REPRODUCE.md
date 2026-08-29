# Reproduction guide

Written for a clean environment. No account with any provider is needed for the replay path.

## Setup

Requirements: git, and [uv](https://docs.astral.sh/uv/) (or Docker — see below). uv installs
Python 3.12 itself; nothing else is needed and no API key is needed for the path below.

```
git clone <repo-url>
cd <repo>
make setup     # uv sync --locked; fails loudly if the lockfile is stale
make smoke     # under 60 s: interpreter version, imports, trace validation over the committed traces
```

`make smoke` runs `evals/harness/trace_check.py` over `traces/`, so a broken trace fails the wiring
check rather than surfacing later as a missing deliverable.

## Reproduce the results (no API key)

```
make eval-replay
```

It replays every recorded API response from `evals/cache/`, re-scores all [identity_check.n] runs,
regenerates `results/metrics.json` and then runs `git diff --exit-code` against the committed file.
A cache miss fails loudly rather than falling back to a live call (ADR 0003 §6).

Expected runtime: [timing.replay.json — under a minute on the reference machine; state the machine].
Expected final lines, verbatim:

```
[identity_check.n] runs: [identity_check.success] success, [identity_check.failure] failure  (success + failure == n: ok)
dev   baseline F1 [arms.baseline.dev.f1_mean] ± [..f1_std_seeds] | advanced F1 [arms.advanced.dev.f1_mean] ± [..f1_std_seeds] | false safe [arms.baseline.dev.false_safe_total] → [arms.advanced.dev.false_safe_total]
test  baseline F1 [arms.baseline.test.f1_mean] ± [..f1_std_seeds] | advanced F1 [arms.advanced.test.f1_mean] ± [..f1_std_seeds] | false safe [arms.baseline.test.false_safe_total] → [arms.advanced.test.false_safe_total]
McNemar (pass, majority of 3): dev b=[comparison.dev.mcnemar.b] c=[comparison.dev.mcnemar.c] p=[comparison.dev.mcnemar.p_exact] | test b=[comparison.test.mcnemar.b] c=[comparison.test.mcnemar.c] p=[comparison.test.mcnemar.p_exact]
wrote results/metrics.json
metrics.json unchanged
```

The last two lines are the reproducibility claim. `metrics.json unchanged` means the replay produced
the committed numbers byte for byte.

## Live runs (API key required)

```
cp .env.example .env   # add ANTHROPIC_API_KEY
make baseline          # baseline arm over the dev split, 3 runs per case
make advanced          # advanced arm over the dev split, 3 runs per case
make eval              # the full sweep, both arms, dev + test
```

Model: `claude-opus-5`, adaptive thinking with summarised display, `output_config.effort: high`,
`max_tokens` 32000, streamed (ADR 0004 P-11, amending ADR 0003 §1). This model accepts no
`temperature`, `top_p` or `top_k` — the request is rejected with a 400 — and has no seed parameter
at all (ADR 0003 §2). "Seeds" `s1`–`s3` are harness
labels, and the three runs per case measure sampling variance, reported as mean ± std. A live sweep
therefore does not reproduce the committed numbers exactly; `make eval-replay` does, and that is the
path a judge should use.

Approximate live cost for one full sweep: [timing.json + metrics.json — the measured figure from the
recorded sweep; before it exists, docs/spec/01-architecture.md §10 estimates $80–$176]. Approximate
wall clock: [timing.json wall_s_mean summed; 01-architecture.md §10 estimates ≈107 min at
concurrency 4]. A single advanced run on a real repository is [per_case cost_usd].

## Docker path

For a machine without uv:

```
docker build -t art30 .
docker run --rm art30 make eval-replay
```

The image is `python:3.12-slim` with uv [pinned version/digest] copied in, `uv sync --locked` at
build time, and `make eval-replay` as the default command.

## Versions

Python 3.12 (`.python-version`, asserted by `make smoke`). Runtime dependencies and their resolved
versions are in `uv.lock`, which `make setup` installs with `--locked`: `anthropic`, `pyyaml`,
`jsonschema`; `pytest` in the dev group. The verifier uses stdlib `ast` and no parser dependency.
Model `claude-opus-5` as configured above.
