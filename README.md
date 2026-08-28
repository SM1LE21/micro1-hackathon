# [Project name — TO FILL]

Built solo for the micro1 Agentic Workflows Hackathon, 2026-08-28 to 2026-08-31.
Everything in this repo was created during the competition window.

**If you have 5 minutes:** `make smoke && make eval-replay` — no API key needed.

## Who has this problem?

[TO FILL — the named user, one paragraph.]

## What bottleneck makes it worth solving?

[TO FILL — the bottleneck as it exists today, and why solving it matters in practice.]

## Does the agent solve it well?

[TO FILL — the design in three or four sentences: the agent loop, the deterministic verifier it closes over, the human checkpoint. Every design choice named here maps to a measured row in CHANGELOG_EVAL.md.]

## Can another person reproduce the result?

Yes — see [REPRODUCE.md](REPRODUCE.md). `make eval-replay` reproduces every number in `results/` from recorded responses with no API key. Live re-runs: `make eval`.

## Results

| Metric | Simple baseline | Agent solution | Change |
|---|---|---|---|
| [Primary outcome — TO FILL] | | | |
| Human time per task | | | |
| Cost per task | | | |

Full metrics (pass^3, regressions, robustness, turns, tool calls): `results/metrics.json`. Statistics method: paired per-task differences, exact McNemar; details in REPRODUCE.md.

## Improvement changelog

See [CHANGELOG_EVAL.md](CHANGELOG_EVAL.md) — every iteration with the evidence that drove the next decision, removed experiments included.

## Main failure mode and hot take

See [HOT_TAKE.md](HOT_TAKE.md).

## Agent trajectories

`traces/` holds runtime traces for both arms (failures included, one-line diagnosis each). The full coding-agent build trajectory renders via `make traces`. Tools used to build: Claude Code (sessions disclosed in the trajectory bundle).
