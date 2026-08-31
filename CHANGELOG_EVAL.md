# Improvement changelog

The story of how the solution evolved, in the official format. One entry per meaningful experiment, measured with the same evaluation wherever possible. Removed experiments stay in — they taught us something.

| Stage | What you tried and why | Evidence | Decision / learning |
|---|---|---|---|
| Baseline | [TO FILL — the basic approach] | [baseline result + trace ID] | Established the starting point |
| Incident 2026-08-31 | First dev+test sweeps on the claude brain: all 60 cells died in 0.2 s | `traces` of the failed sweep cleared; ledger line 1 in `results/test-runs.log` records the spent slot | The driver handed the CLI a relative `mcp.json` path that the child resolved against the scanned repository. Fixed (`art30/brains/driver.py` resolves every child-facing path), regression-tested, sweeps re-run. A harness defect, not a model result; kept here so the ledger's first line has its explanation |

<!-- Row discipline (AGENTS.md): one change per row · dev-set numbers with paired SE ·
     cost delta · regressions (report even at zero) · one trace ID actually read ·
     one sentence on what the transcript showed. Commit each row as docs(changelog). -->
