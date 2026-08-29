# Traces

`traces/<arm>/<case>-s<seed>.jsonl` — one runtime trace per run, one JSON object per line.
`traces/failures/` — the same files for runs that failed, each with a `.diagnosis.txt` beside it.
`traces/build-trajectory.html` — the coding-agent sessions that built this repository, rendered
by `make traces` (author-only target; the HTML is committed so no judge needs to run it).

## Line types

| `type` | When | Fields that matter |
|---|---|---|
| `run_start` | once, first line | `run_id`, `arm`, `case`, `seed`, `model`, `effort`, `mode` |
| `step` | one per model turn | `step`, `phase`, `reasoning`, `text`, `tool_calls[]`, `tool_results[]`, `usage`, `cost_usd`, `cost_cum_usd` |
| `checkpoint` | at the human gate | `risk`, `summary`, `decision`, `by`, `wait_s` |
| `run_end` | once, last line | `stop_condition`, `steps`, `tool_calls_total`, `submits`, `verify_rounds`, `wall_s`, `cost_usd` |

`reasoning` is the model's summarised thinking, not raw chain of thought. Tool outputs are stored in full.

## Reading one by hand

Everything below is stdlib Python; no `jq`, no viewer.

## The build trajectory

`traces/build-trajectory.html.gz` is the Claude Code transcript of the session that built this project, rendered with `claude-code-log` 1.5.0 and gzipped (the uncompressed page is ~60 MB; `gunzip -k traces/build-trajectory.html.gz` and open it in a browser). It covers the main session; the ~120 subagent transcripts it spawned are not rendered, and `make traces` (author-only) regenerates it.
