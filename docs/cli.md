# The command line (`art30 scan`)

`art30 scan` is the only thing in this project that runs the agent loop, the verifier, the gate and the renderer. The eval harness starts it as a subprocess, the local website starts it as a subprocess, and a person points it at a repository. Whatever you read on the page or in `results/` came out of this command (ADR 0007).

`art30 serve` is the other subcommand; it has its own page, `docs/web.md`.

```
art30 scan <repo> --arm advanced|baseline [--case ID] [--seed N]
                  [--mode live|replay] [--approve ask|auto|file] [--out DIR]
```

## Install

Inside this repository, which is where the eval and the fixtures live:

```
uv sync --locked
uv run art30 scan <repo> --arm advanced
```

Anywhere else:

```
uv tool install .        # puts `art30` on the PATH
```

The wheel carries the data files the agent cannot work without: `art30/prompts/system.md` and `taxonomy.md` (the instruction text), `art30/schema/record.schema.json`, every rule set under `art30/verify/rules/`, and the website page. It also carries `baseline/` and `advanced/`, which are packages of their own next to `art30/` rather than modules inside it.

`tests/test_wheel.py` builds the wheel, opens it, and then runs a whole `art30 scan <repo> --arm baseline --mode replay` from an environment holding the wheel and nothing of this repository — a replay against an empty cache, so no key and no network, ending at exit 4. `--help` alone would only prove the parser builds; the scan proves the arms and the data files came along. Anything the package drops fails there and not on a stranger's first scan. If an arm is missing anyway, the run says so in one sentence and exits 2.

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `<repo>` | required | The repository to read. Read-only: nothing in it is imported or executed. |
| `--arm` | required | `advanced` runs the verifier inside `submit_record` and the human gate before render. `baseline` validates the schema and accepts. Same prompt, same tools, same model (ADR 0003). |
| `--case` | the fixture's case id, else a slug of the directory name | The id in the trace, the record's provenance and the results path. |
| `--seed` | `1` | A label. The model exposes no sampling controls, so the seed names a run, it does not steer one. |
| `--mode` | `live` | `replay` serves every request from `evals/cache/` and needs no API key. A miss is exit 4, never a silent live call. |
| `--approve` | `ask` | The gate, advanced arm only. `ask` prompts on the terminal, `auto` approves and records `by: "simulated"`, `file` waits for `<out>/gate/decision.json` (what the website uses). |
| `--out` | see below | Where `record.json`, `record.md` and `record.html` are written. |

The tool budget has no flag. It follows the repository (below) or `ART30_TOOL_BUDGET`.

## The case id

`--case` defaults to a slug of the repository directory name: letters and digits survive, every other run of characters becomes a single `_`, and leading and trailing `_` are dropped. `~/src/My Repo (copy)` scans as `My_Repo_copy`.

The slug keeps its letter case, which is why an evaluation id passes through it unchanged. `D02` is already a slug; lowering it would look for a cache slot at `evals/cache/d02/` and a `d02` line in `evals/split.yaml`, and find neither.

A path under `evals/fixtures/` is resolved to its case id before the slug is reached. The synthetic fixtures are named after their case, so nothing changes there. The five real ones are vendored under their upstream names, and those are mapped: `evals/fixtures/real/pinry` is `R03`, `microblog` is `R04`, and so on for `R01`, `R02` and `R05`. The test-split lock below reads that resolved id, so it holds on `R03` and `R04` — which is the whole point of vendoring them under names that carry no case id — and `--case` cannot talk it out of the lock.

## Where a run writes

An evaluation fixture keeps the layout the harness reports from:

```
results/runs/<arm>/<case>/s<seed>/{record.json,record.md,record.html}
traces/<arm>/<case>-s<seed>.jsonl
```

Any other repository gets a directory of its own and takes its trace with it, so scanning your own code writes nothing into the eval's trees:

```
art30-out/<slug>/<arm>/s<seed>/{record.json,record.md,record.html}
art30-out/<slug>/<arm>/s<seed>/<arm>/<case>-s<seed>.jsonl
```

`art30-out/` is git-ignored. `--out DIR` is used verbatim — DIR, not DIR plus three derived segments — and off the eval fixtures it moves the trace too; `ART30_TRACE_DIR` still overrides it, because that is the seam the harness hands each cell.

The directory is keyed on the slug, and the slug is lossy: `~/src/my-shop` and `~/src/my shop` are both `my_shop`, so the second scan overwrites the first, trace included, without saying so. Scanning two repositories whose names differ only in punctuation wants `--out`.

The last line of an accepted run names the record, the two rendered files and the trace, in that order. Every other run ends at the trace, because the three files do not exist.

## The budget of a repository nobody named

The contract sets 60 tool calls for a synthetic case and 120 for a real one. A case id listed in `evals/split.yaml` — `S01`–`S10`, `D01`, `D02`, `R01`–`R05` — keeps the kind its id carries. Anything else is sized: **more than 40 files and the scan runs at the real budget of 120 tool calls, 40 or fewer at 60.** The count excludes `.git`, `__pycache__`, `node_modules`, `static` and `media` *inside* the repository, and it is the number printed in the header line, so the budget you got is always visible next to the size it was chosen from. Where the checkout itself sits changes nothing: a repository under `~/media/` counts its own files and gets its own budget, which it has to, because the budget is named in the first user message and a request that moved with the parent directory could never be replayed.

Forty is not a measurement, it is a gap. The largest synthetic fixture holds 16 files; the smallest vendored real repository holds 73. Any threshold between them sorts the fixtures correctly, and 40 leaves room on both sides. A repository that needs more than 120 calls sets `ART30_TOOL_BUDGET`, which is recorded in the trace and in `provenance.config.overridden`.

## Environment

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | unset | Read by the SDK, never by this code. Live mode without it stops before the client is built (exit 2). `.env` is read first, so the key can live there. |
| `ART30_MAX_USD` | unset | A per-run ceiling on cumulative cost. Crossing it ends the run with `budget_exhausted` and its own printed line. |
| `ART30_MODEL` | `claude-opus-5` | Changes a hashed request byte, so it invalidates every recorded response. |
| `ART30_EFFORT` | `high` | Same. |
| `ART30_MAX_TOKENS` | `32000` | Same. |
| `ART30_TOOL_BUDGET` | by kind | Overrides the 60/120 above. Named in the first user message, so it changes the request hash. |
| `ART30_SUBMIT_BUDGET` | `5` | `submit_record` attempts. Also in the first user message. |
| `ART30_MODE` | `live` | What `--mode` sets; the flag wins. |
| `ART30_RECORD` | unset | `1` writes every live response into the cache at `<case>/<arm>/s<seed>/<NN>.json`. This is how a replay becomes possible. |
| `ART30_CACHE_DIR` | `evals/cache` | Where replay reads and `ART30_RECORD` writes. |
| `ART30_TRACE_DIR` | `traces` | The trace root. The harness sets it per cell; without it a sweep would overwrite the committed traces. |
| `ART30_UNLOCK_TEST` | unset | `1` allows a live run on a case in the `test` split. Record the sweep in `results/test-runs.log`. |
| `ART30_REPRODUCIBLE` | unset | `1` suppresses every file a replay must not rewrite (`results/timing.json`, `results/gate-timing.yaml`, the ledger). `make eval-replay` sets it. |
| `ART30_GATE_TIMEOUT` | `1800` | Seconds `--approve file` waits for a decision. A timeout is `gate_rejected` with a note, never an approval. |

The five variables that change a request — model, effort, max tokens, and the two budgets — are printed in the header line under `overridden:` and recorded in `provenance.config`, so a run at non-default settings cannot be mistaken for a reported one.

## Exit codes

| Code | When |
|---|---|
| 0 | `accepted`: the record passed, the gate approved it, three files were written |
| 1 | any other stop condition — `budget_exhausted`, `max_submits`, `no_submission`, `max_tokens`, `timeout`, `api_error`, `refusal`, `render_failed` |
| 2 | usage error: `argparse`, a missing directory, a test-split case without `ART30_UNLOCK_TEST`, live mode with no key, `--approve ask` with no terminal, an arm that cannot be imported |
| 3 | `gate_rejected`: the approver said no. `record.draft.json` is kept; nothing is rendered |
| 4 | `replay_miss`: the cache has no entry for a request, or the request changed since it was recorded |

A stale cache and a transport failure exit differently on purpose: they need different fixes, and folding them together would put every `make eval-replay` failure in the same bucket as a real API error.

`evals/harness/run.py` maps a child's 4 to its own 5 and turns every other non-zero child code into a recorded run failure inside a sweep that still exits 0.

## A worked example: D02

`D02` is one of the two demo fixtures — a SQLAlchemy shop where the cache is purged on account deletion and the support tickets and the search index survive it. It is never scored and never part of a sweep.

Replay, which is the path that needs no key and no network:

```
$ uv run art30 scan evals/fixtures/synthetic/D02 --arm advanced --mode replay --approve auto
art30 0.1.0 · case D02 · arm advanced · seed 1 · mode replay
model claude-opus-5 · effort high · max_tokens 32000
budget 60 tool calls · 5 submit attempts · repo evals/fixtures/synthetic/D02 (16 files)
```

The case id comes from the directory name, the budget from the id, and the run then reads its responses out of `evals/cache/D02/advanced/s1/`. With no recording there yet, this is what you get instead:

```
[agent] replay miss at step 0. The cache is stale or the fixture changed.
replay_miss · 0 steps · 0 tool calls · 0 submits · 0 verify rounds · no gate (advanced)
$0.00 · 0.0s · traces/advanced/D02-s1.jsonl
```

Exit 4, no network touched, nothing spent. `REPRODUCE.md` says which cases have recorded responses.

Live, with a key in `.env`:

```
$ uv run art30 scan evals/fixtures/synthetic/D02 --arm advanced --approve ask
```

The run prints one line per tool call with a running cost, the `[verify]` block when the record is submitted, and the gate before anything is rendered; `docs/spec/07-ui.md` §3 shows a full transcript of that shape. Add `ART30_RECORD=1` and the same run fills the cache, which is what makes the replay above work. Without the key:

```
$ uv run art30 scan evals/fixtures/synthetic/D02 --arm advanced --approve auto
no ANTHROPIC_API_KEY: put it in .env (see .env.example) or export it; --mode replay needs no key
```

Exit 2, printed before the SDK is imported.

Scanning something of your own is the same command with a path:

```
$ uv run art30 scan ~/src/my-shop --arm advanced --approve ask
```

Case `my_shop`, budget from the file count, and everything the run produces under `art30-out/my_shop/advanced/s1/`.
