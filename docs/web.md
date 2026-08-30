# The local website (`art30 serve`)

The website does not run the agent. It starts `art30 scan` as a child process, tails the trace that child writes, relays what the child prints, and answers the human gate through two files. Everything a judge sees on the page came out of the CLI (ADR 0007).

```
uv run art30 serve            # http://127.0.0.1:8734
uv run art30 serve --open     # the same, with the browser opened for you
make serve                    # the same as --open
```

`--host` accepts a loopback address only — `127.0.0.1`, `localhost`, `::1` — and anything else is refused before the socket opens. `--port 0` picks a free port and the printed URL names it. A request whose `Host` header is not that address, or whose `Origin` is a different site, is answered 403 and never routed: a name someone else controls can be pointed at 127.0.0.1, and a page on it would otherwise read and start runs as though it were the page this server sent.

## Without an API key

Replay is the whole demo path. A case is replayable when `evals/cache/<case>/<arm>/s1` is on disk: the page marks it, `POST /api/runs` refuses `mode: replay` for anything else, and the run costs nothing and reaches no network. `mode: live` needs `ANTHROPIC_API_KEY` in the environment or in `.env` — the server checks that the name is set and never reads or returns the value. A case in the `test` split is refused in live mode with the split named; replay of the same case is allowed, because re-serving recorded responses reveals nothing the recorded sweep did not (`evals/split.yaml`, `policy.replay_counts_against_budget`).

`GET /api/results` reads `results/metrics.json`; before any sweep it answers `{"available": false, "hint": ...}` and the hint names `make eval` and `make eval-replay` (`docs/runbook-sweeps.md`).

## The endpoints

| Route | What it does |
|---|---|
| `GET /` | the page, one file, no CDN and no external request |
| `GET /api/cases` | `{cases: [...], live_enabled: bool}` from `evals/split.yaml` and the two fixture roots. Each case carries `id`, `kind` (`synthetic`, `demo`, `real`), `split`, `path`, `present`, `replayable`, `replay_arms`, `name` |
| `POST /api/runs` | `{repo, arm, mode, seed?, case?}` → `{run_id, status}`. `repo` is a case id, or a directory inside the project that exists. A directory that is one of the evaluation's fixtures runs under that fixture's own case id, whatever `case` says, so the test-split lock cannot be relabelled away |
| `GET /api/runs` | every run this server started, with `status`: `running`, `gate_waiting`, `accepted`, or `failed:<stop_condition>` |
| `GET /api/runs/<id>` | the same row for one run |
| `GET /api/runs/<id>/events` | the event stream (below) |
| `POST /api/runs/<id>/gate` | `{approved, edits}` → writes `decision.json`. 409 before the request exists, 410 once a decision does |
| `POST /api/runs/<id>/cancel` | SIGTERM, then SIGKILL five seconds later |
| `GET /api/runs/<id>/record` | `record.json`, 404 until the renderer has written it. Also `/record.md` and `/record.html` |
| `GET /api/runs/<id>/source?path=&line=&context=` | `{path, line, start, lines: [[n, text], ...]}` for a citation |
| `GET /api/results` | `results/metrics.json` and `results/report.md`, or the hint |

Errors are `{"error": "..."}` with the status that fits. A traceback goes to the server's terminal, never to the client.

Every `source` read goes through `art30.tools.resolve` against the repository root recorded in `run.json` at spawn time — the same jail the model's own `read_file` uses. An absolute path, a `..` that leaves the root, a symlink pointing out of it or a path carrying a NUL byte is 403; a missing file is 404. The root itself is confined: `repo` must name a case or a directory inside this project, so the website cannot be talked into making an arbitrary directory on the machine readable through `source`.

## The event stream

`GET /api/runs/<id>/events` is `text/event-stream`. It replays both files from their first byte, then tails them, and a reconnect starts over: there is no `Last-Event-ID` to carry.

- `trace` — one raw JSONL line, unchanged. The page parses the same bytes a judge reads in `traces/`.
- `stdout` — one line the CLI printed, in order, so a client can show the terminal's own output. This page does not: the step cards carry the same facts in a form a reader can open, and only the tail of a crashed child is printed (`onDone`).
- `gate` — the contents of `gate/request.json`, sent when it appears and no decision exists.
- `done` — `{exit_code, stop_condition, status}` once the child has exited, with a `note` from the tail of `stdout.log` when nothing wrote a `run_end`.

A comment line keeps the connection alive every 5 seconds. That write is also how a stream whose page has gone finds out: the poll ends, the two file handles close, and the handler thread returns.

## What a run leaves on disk

`results/web/<run_id>/`, where `run_id` is `<arm>-<case>-s<seed>-<six hex>`. The directory is git-ignored and nothing the website does touches `results/runs/`, `traces/` or `evals/cache/`.

```
results/web/advanced-D01-s1-4d2a91/
  run.json        the case, the arm, the mode, the repository root, the argv
  stdout.log      the child's stdout and stderr, in order
  traces/advanced/D01-s1.jsonl    written by the child, ART30_TRACE_DIR points here
  gate/request.json               written by the gate; the run blocks on it
  gate/decision.json              written by this server when a person answers
  record.json, record.md, record.html
```

The child is spawned as an argv list — never a shell string — with the same seam `evals/harness/cells.py` uses: `ART30_TRACE_DIR` per run, and `ART30_UNLOCK_TEST=1` for a replay so a recorded test case can be watched without touching the live sweep budget. Two more variables are set rather than inherited: `ART30_RECORD=0`, because a recording run clears the cache slot it writes and would overwrite the corpus the offline demo replays from, and `ART30_CACHE_DIR`, so the child reads the cache the catalogue read when it marked a case replayable.

Runs land in `results/web/` inside a checkout. Installed as a wheel there is no checkout: set `ART30_WEB_DIR` to say where runs go, and without it they go to `art30-out/web/` beside you. `GET /api/cases` from outside a checkout answers an empty list and a `hint` saying so, rather than an empty table.

## The record view

The page draws `record.json` itself, in the section order and the wording of `art30/render/markdown.py`. It does not embed `record.html` — it links it. Two buttons sit beside the store count on the record card, `Open the rendered record` and `record.md`, pointing at `/api/runs/<id>/record.html` and `/api/runs/<id>/record.md` on this same loopback server. `tests/test_web_e2e.py` reads those two hrefs out of `recordLinks` in the page and requests them, so a renamed route breaks the test rather than the demo.

`record.html` is a finished document and not a fragment: serif type, its own `<style>` and its own `<body>`, built to open from a USB stick and print on A4, with each citation a `<code class="cite">` that carries the source line as a tooltip. Putting it inside this page means an iframe with a second stylesheet in it, and the citations stop being buttons — and a citation that opens the source drawer through `GET /api/runs/<id>/source` is most of what this page is for. The renderer is still the only renderer: `GET /api/runs/<id>/record.html` hands back the child's own file byte for byte, which `tests/test_web_e2e.py` asserts against the bytes on disk, and nothing on the server or the page re-renders anything.

The drift that a second implementation risks is answered by a test rather than by a promise. `tests/test_web_page.py` reads the eight `## A.` to `## H.` headings out of `art30/render/markdown.py` and requires the page's `SECTIONS` array to be that list, verbatim and in order; the record's other fixed wording — the boundary paragraph, `requires human completion` — is asserted on the page beside it. The Markdown renderer is frozen and the page is not, so the page is compared to the renderer and never to a copy of it.

One row departs on purpose. `markdown.py` writes `Approved: <time> at the terminal`; a run started from this page answers the gate through `--approve file` and no terminal is involved, so the page prints the time, the wait, the risk and `recorded by: <provenance.gate.by>` instead of a place the decision did not come from.

Section G departs for a different reason: the record it is given is wrong. `art30/loop.py` writes `"rule_set_sha": None` for both arms, and `docs/spec/04-output-schema.md` §5 makes that null mean *no verifier ran*. On the advanced arm the same document then carries both `Verification: 2 submissions, accepted on attempt 2` in the provenance table and `Verification: none. This record was accepted on schema validity alone.` in section G, after a judge has watched the verifier strike a claim and approved it at the gate. Until `loop.py` sets the digest, the page prints that sentence only where it is true. The discriminator is not the arm: `loop.py` appends one `rejected_history` entry per refused submit, and a schema refusal carries the errors that caused it while the verifier's carries an empty list, because what it struck was a claim and not a shape. An entry with no schema error is a refusal the verifier made, and the appendix then says so and points at the trace instead. A baseline record, whose refusals always carry schema errors, still renders `markdown.py`'s line word for word.

## Screenshots

There are none. The machine this was built on has no browser that can be driven — no Chrome, no Chromium, no Playwright, no driver of any kind — and a screenshot is either taken off the running page or it is a drawing.

The page was run instead. `node` is on PATH, the page's script is ES5 against a small DOM, so a scratch harness built that DOM out of `index.html`, fed it the bytes of a real S10 replay — the run `tests/test_web_e2e.py` drives — called the page's own renderers, and dumped what each view then held. The six frames below are that output, described. Nothing in them was composed by hand.

| Frame | What it shows |
|---|---|
| Run, stopped at the checkpoint | The start strip, opened on S10 because that is the first case with a recording on the selected arm, its intent sentence under the strip; the run header reading `gate_waiting`, 2/60 tool calls, 2/5 submit attempts, $0.0848; step 1, whose `submit_record · 4 stores, 11 fields` came back `refused`; the rejection card under it, quoting the verifier: *no path from entry point close_account (api/account.py:12) to any object-storage deletion primitive; cleanup_user_files (storage.py:29) is defined but has no callers*; step 2; and the gate card — RISK HIGH and its reason first, then the record being approved and the block behind it, then the recipient kind for `stripe`, then Approve and render. The run column holds the whole page while the gate waits (`.columns.gate-open`): the right column can only be a placeholder until a decision exists, and the gate block is fixed columns that must not wrap. |
| Record, after approval | The provenance table, the boundary paragraph, sections A to H, in two thirds of the page (`.columns.has-record`), with `Open the rendered record` and `record.md` beside the store count. `stripe` carries `PROCESSOR`, which is the kind the person set at the gate and not something the model claimed. `uploads` carries `NOT ERASED` with the dead helper as its note. Section G names no rule set and says which submission the verifier refused. |
| Source drawer | `storage.py` lines 25 to 33 with line 29 highlighted — `def cleanup_user_files(user_id):` — opened by clicking the citation in the record, and read through the same jail the model's `read_file` uses. |
| Runs | One row: `advanced-S10-s1-<hex>`, `accepted`, `S10 · advanced · replay · seed 1 · <started at>`. |
| Results, empty | What `GET /api/results` answers before any sweep, with `make eval` and `make eval-replay` set as code inside the sentence. |
| About | The four questions, answered, and the boundary the tool refuses to cross. |

On a machine with Chrome, the two static views photograph themselves:

```
uv run art30 serve
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
  --window-size=1440,900 --virtual-time-budget=4000 \
  --screenshot=about.png "http://127.0.0.1:8734/#/about"
```

The Run view is not one of them. It needs a replay in flight and a person at the gate, so it is a window capture during a demo, which is also the only honest way to show a checkpoint waiting on somebody.
