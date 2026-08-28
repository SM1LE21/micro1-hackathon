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

Model: [TO FILL — exact model ID], temperature and seeds pinned in [TO FILL]. Temperature 0 does not guarantee bit-identical outputs; we run 3 trials per arm and report mean ± std. Approximate live cost: [TO FILL]. Approximate runtime: [TO FILL].

## Data

[TO FILL — which data, where it comes from, why it is public or synthetic.]

## Which numbers came from where

Every number in README and CHANGELOG_EVAL: [TO FILL — live run date/commit vs replay]. Raw traces for both arms: `traces/`.

## Docker path

```
docker build -t hackathon .
docker run --rm hackathon make eval-replay
```
