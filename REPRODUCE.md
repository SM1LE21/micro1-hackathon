# Reproduction guide

Written for a clean environment. No account with any provider is needed for the replay path.

## Setup

Requirements: git, [uv](https://docs.astral.sh/uv/) (or Docker — see below). Python 3.12 is installed by uv automatically.

```
git clone <repo-url>
cd <repo>
make setup     # uv sync --locked; fails loudly if the lockfile is stale
make smoke     # <60s wiring check, no API key
```

## Reproduce the results (no API key)

```
make eval-replay
```

Replays recorded model responses and regenerates `results/metrics.json`. Expected runtime: [TO FILL]. Expected output: [TO FILL — the exact final lines].

## Live runs (API key required)

```
cp .env.example .env   # add your key
make baseline          # baseline arm, 3 seeded runs
make advanced          # advanced arm, 3 seeded runs
make eval              # full evaluation, both arms
```

Model: `claude-opus-5`, adaptive thinking, effort `high`, `max_tokens` 32000 (ADR 0003, ADR 0004). This model exposes no sampling parameters and no seed; the request rejects `temperature`. "Seeds" are harness labels (`s1`–`s3`) and the three runs per arm measure sampling variance, reported as mean ± std. Approximate live cost: [TO FILL from results/metrics.json]. Approximate runtime: [TO FILL from results/timing.json].

## Data

[TO FILL — which data, where it comes from, why it is public or synthetic.]

## Which numbers came from where

Every number in README and CHANGELOG_EVAL: [TO FILL — live run date/commit vs replay]. Raw traces for both arms: `traces/`.

## Docker path

```
docker build -t hackathon .
docker run --rm hackathon make eval-replay
```
