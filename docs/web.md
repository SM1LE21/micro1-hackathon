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
| `GET /api/settings` | `{keys, brains, files, note}` — every setting with the layer it came from, what the two local CLIs report, the three file paths, and the note below. `?refresh=1` re-runs the detection |
| `POST /api/settings` | `{key, value, scope?}` → `{key, written_to, present}`. `scope` is `project` (default) or `user`. A value outside a key's list is a 400 carrying the loader's own sentence |
| `DELETE /api/settings/<key>?scope=` | drops the line from that file; `present` says whether a layer below still sets the key |
| `POST /api/runs` | `{repo, arm, mode, seed?, case?, brain?, model?}` → `{run_id, status, brain}`. `repo` is a case id, or a directory inside the project that exists. A directory that is one of the evaluation's fixtures runs under that fixture's own case id, whatever `case` says, so the test-split lock cannot be relabelled away |
| `GET /api/runs` | every run this server started **and every run directory it finds under `results/web/`**, with `status`: `running`, `gate_waiting`, `accepted`, or `failed:<stop_condition>`, plus `brain` and `cost_source` |
| `GET /api/runs/<id>` | the same row for one run |
| `GET /api/runs/<id>/events` | the event stream (below) |
| `POST /api/runs/<id>/gate` | `{approved, edits}` → writes `decision.json`. 409 before the request exists, 410 once a decision does |
| `POST /api/runs/<id>/cancel` | SIGTERM, then SIGKILL five seconds later |
| `GET /api/runs/<id>/record` | `record.json`, 404 until the renderer has written it. Also `/record.md` and `/record.html` |
| `GET /api/runs/<id>/source?path=&line=&context=` | `{path, line, start, lines: [[n, text], ...]}` for a citation |
| `GET /api/results` | `results/metrics.json` and `results/report.md`, or the hint |

Errors are `{"error": "..."}` with the status that fits. A traceback goes to the server's terminal, never to the client.

Every `source` read goes through `art30.tools.resolve` against the repository root recorded in `run.json` at spawn time — the same jail the model's own `read_file` uses. An absolute path, a `..` that leaves the root, a symlink pointing out of it or a path carrying a NUL byte is 403; a missing file is 404. The root itself is confined: `repo` must name a case or a directory **inside** this project — the project root itself is refused — so the website cannot be talked into making an arbitrary directory on the machine readable through `source`, and the checkout's own `.env` never falls inside a jail. A request for `.env` under any root is 403 as well: the API key goes into that file through `POST /api/settings` and is never read back, and this endpoint is not the way out (`tests/test_web_server.py::test_the_secrets_file_is_not_readable_as_source`).

## The event stream

`GET /api/runs/<id>/events` is `text/event-stream`. It replays both files from their first byte, then tails them, and a reconnect starts over: there is no `Last-Event-ID` to carry.

- `trace` — one raw JSONL line, unchanged. The page parses the same bytes a judge reads in `traces/`.
- `stdout` — one line the CLI printed, in order, so a client can show the terminal's own output. This page does not: the stage reads the same facts back from the trace, and only the tail of a crashed child is printed (`onDone`).
- `gate` — the contents of `gate/request.json`, sent when it appears and no decision exists.
- `done` — `{exit_code, stop_condition, status}` once the child has exited, with a `note` from the tail of `stdout.log` when nothing wrote a `run_end`.

A comment line keeps the connection alive every 5 seconds. That write is also how a stream whose page has gone finds out: the poll ends, the two file handles close, and the handler thread returns.

## What a run leaves on disk

`results/web/<run_id>/`, where `run_id` is `<arm>-<case>-s<seed>-<six hex>`. The directory is git-ignored and nothing the website does touches `results/runs/`, `traces/` or `evals/cache/`.

```
results/web/advanced-D01-s1-4d2a91/
  run.json        the case, the arm, the mode, the brain, the repository root, the argv
  stdout.log      the child's stdout and stderr, in order
  traces/advanced/D01-s1.jsonl    written by the child, ART30_TRACE_DIR points here
  gate/request.json               written by the gate; the run blocks on it
  gate/decision.json              written by this server when a person answers
  record.json, record.md, record.html
```

The child is spawned as an argv list — never a shell string — with the same seam `evals/harness/cells.py` uses: `ART30_TRACE_DIR` per run, and `ART30_UNLOCK_TEST=1` for a replay so a recorded test case can be watched without touching the live sweep budget. Two more variables are set rather than inherited: `ART30_RECORD=0`, because a recording run clears the cache slot it writes and would overwrite the corpus the offline demo replays from, and `ART30_CACHE_DIR`, so the child reads the cache the catalogue read when it marked a case replayable.

The registry is read back off those directories on every `GET /api/runs`, not held in memory alone, so restarting the server keeps the history: a directory with a `run.json` and a trace that ends in `run_end` is listed with the status that line carries, one without a `run_end` is listed `failed:crashed`, and opening either streams its saved trace out of the directory. `art30/web/runs.py::adopt` is what wraps such a directory as a run; a `run_id` that is not a plain directory name reaches nothing.

Runs land in `results/web/` inside a checkout. Installed as a wheel there is no checkout: set `ART30_WEB_DIR` to say where runs go, and without it they go to `art30-out/web/` beside you. `GET /api/cases` from outside a checkout answers an empty list and a `hint` saying so, rather than an empty table.

## Settings, and the three brains

`art30 scan --brain api|claude|codex` (ADR 0008). The Run strip offers two of the three: **api** is the Anthropic API and the loop as built, **Claude (your login)** runs the `claude` CLI already installed and logged in on the machine. Codex is not offered on the page for now (2026-08-31, the author's call for the demo); the CLI and the harness keep `--brain codex`. A brain that is not installed or not logged in is a disabled toggle with the reason under the strip — the same sentence `POST /api/runs` would have refused with. The API brain needs a key or a recording, as before; when it has neither and Claude is logged in, a callout says so and points at that brain. Dismiss hides the callout for this page load; a reload asks again.

A model can be typed beside the brain; empty means the brain's own default, and the placeholder names it: the `model` setting for `api`, `claude_model` or `codex_model` for the two CLIs. Both travel to the child as `--brain` and `--model`, which the CLI routes by the brain it resolved, so a `brain` in `art30.toml` cannot leave the flag pointing at the wrong engine.

**Play back, not replay.** A local brain's run went through somebody's own CLI and no response was recorded, so it cannot be re-run from a cache. What the page offers instead is the trace that run already wrote: pick the brain, switch the mode to `play back`, press Start, and the newest finished run of that brain streams out of its directory through the same event stream a live run uses, with the same pacing controls. The mode is disabled until such a run exists.

**Cost.** A local brain bills no dollars, so no ceiling stops it and the page names none; the turn budget does, and the meter shows `turns n/max_turns` whenever the trace's `run_start` carries one. The cost figure on a local run is labelled *estimated* and is priced at API list prices from the tokens the CLI reported. The Runs view carries both facts per row: the brain, and `measured` or `cli estimate`.

The Settings view has two cards. **Brains** reports, per CLI, whether it is installed, the version string it printed, and whether it says it is logged in, with a Refresh; the detection shells out to four commands, so its answer is held for thirty seconds and Refresh is what asks again. Nothing of the account survives that detection — no email, no organisation, no token (`tests/test_brains_detect.py`).

**Keys** is one row per setting in the order `art30/settings.py` declares them: the control follows the type (a select where the key has a list, a number where it takes one, text otherwise), a chip names the layer the value came from — `default`, `user`, `project`, `.env`, `env` — and Save writes one line into one file. The file is chosen once, at the top of the card: this project's `art30.toml` or this machine's `~/.config/art30/config.toml`. Emptying a field and saving removes the line, and the layer below it takes over. A value a key does not accept comes back as the loader's own sentence, under the row.

The API key is the exception, and the rule it follows is the one `docs/settings.md` states: it is written to `.env` at mode `0600` and never read back. Its row shows `present` or `absent` and a Replace; the answer to the write names the file and not the value; and `tests/test_web_settings.py::test_the_key_is_written_to_dotenv_and_never_read_back` scans the whole settings document for the characters that were sent.

Wherever a local brain is selected, the page prints the note ADR 0008 item 6 wrote, verbatim:

> Local brains run the `claude` / `codex` command already installed and logged in on this machine. art30 never stores or asks for those credentials; if the CLI is not logged in, the run fails with the CLI's own login error. Anthropic does not allow third parties to offer claude.ai login or rate limits inside their products; this tool does not — it runs your own CLI on your own machine.

The string lives in `art30/web/settings_api.py` and reaches the page through `GET /api/settings`. There is no second copy on the page, and a test asserts there is not. The brand is "Claude (your login)"; the page does not contain the words "Claude Code", and `tests/test_web_page.py` greps for both. The rule also holds for what the page draws rather than what it ships: `claude --version` prints `2.1.251 (Claude Code)`, so the version chip renders the number without the CLI's own trailing parenthetical (`versionText`, driven by `tests/test_web_page.py::test_the_version_chip_drops_the_clis_own_parenthetical`).

## The stage

A run takes the view. The strip and the introduction hide, and the stage is what is left: one line, large and centred, saying what the child is doing now — the agent's tool calls read back as sentences (*Reading `members/models.py`*; a step that read four files shows each in turn), then *Handing the record to the verifier*, then what the verifier said — with the step count and the files read so far under it, and the budgets at the side: tool calls, submit attempts, turns where the trace carries a turn budget, and the cost, labelled *estimated* on a local brain. Nothing else is drawn while it runs.

When the verifier accepts a submission and the checkpoint opens, the line says so and a card states the finding: how many stores are not proven erased, each with its kind, its verdict, where it is declared and the reason, every citation opening the source drawer; then the entry points the check ran against, the stores that do reach erasure, whether a retention timer was found, and the cells the code cannot answer. The gate card under it keeps its risk band and its two buttons; the CLI's own checkpoint text is folded behind a disclosure, since the card above says the same thing in rows. Once the record is rendered the card is drawn again from `record.json`, and two buttons appear under it: **Open the full report** (`record.html`) and `record.md`. A finish card carries the totals — steps, tool calls, submits, verify rounds, seconds, cost — and **New scan** returns to the strip; the run stays in the Runs view, which plays it back through the same stage.

The status chip says `scanning`, `waiting for your approval` and `finished` where the server says `running`, `gate_waiting` and `accepted`; the stop condition itself is on the finish card and in `run.json`.

Nothing stops early. The checkpoint opens once, after the whole repository has been read and the record has passed the verifier: it is an approval before rendering, not an interruption on the first finding.

## The record

The page does not draw `record.json`; it links the two files the child wrote. `Open the full report` and `record.md` point at `/api/runs/<id>/record.html` and `/api/runs/<id>/record.md` on this same loopback server; `tests/test_web_e2e.py` reads those two hrefs out of `recordLinks` in the page and requests them, so a renamed route breaks the test rather than the demo.

`record.html` is a finished document and not a fragment: serif type, its own `<style>` and its own `<body>`, built to open from a USB stick and print on A4, with each citation a `<code class="cite">` that carries the source line as a tooltip. The renderer is the only renderer: `GET /api/runs/<id>/record.html` hands back the child's own file byte for byte, which `tests/test_web_e2e.py` asserts against the bytes on disk, and nothing on the server or the page re-renders anything. What the page adds is the findings card — the erasure verdicts with their citations as buttons, because a citation that opens the source drawer through `GET /api/runs/<id>/source` is most of what this page is for — drawn from the same `record.json`, with `requires human completion` in the words the renderer uses (`tests/test_web_page.py`).

## Screenshots

There are none. The machine this was built on has no browser that can be driven — no Chrome, no Chromium, no Playwright, no driver of any kind — and a screenshot is either taken off the running page or it is a drawing.

The page was run instead. `node` is on PATH, the page's script is ES5 against a small DOM, so a scratch harness built that DOM out of `index.html`, fed it the bytes of real traces, called the page's own functions, and dumped what each view then held. The frames below are that output, described. Nothing in them was composed by hand.

| Frame | What it shows |
|---|---|
| Run, scanning | The stage, the strip gone: `scanning` in the header, *Reading `members/models.py`* centred and large, `Step 2 · 5 tool calls · 4 files read` under it, the four paths in small type; at the side, tool calls 5/60, submit attempts 0/5, cost $0.19 *estimated*. From the D01 trace a real Claude-login run wrote on 2026-08-31 (`tests/test_web_simple_view.py` holds the harness; the trace is under `results/web/`, git-ignored). |
| Run, at the checkpoint | The line reads *Scan complete. The verifier accepted the record; approve below to write it.*; the findings card: **2 of 4 stores are not proven erased.**, checked against `delete_account (members/views.py:9)` and `register (members/admin.py:7, admin only)`; `member.avatar · object storage · NOT ERASED · members/models.py:14` with its reason and three evidence buttons; `members_order · relational · UNVERIFIED · members/models.py:38`; *Reaching erasure: members_member, members_note.*; then the gate card — RISK HIGH and its reason, the CLI's text folded, what Approve writes and what Reject ends, Approve and write the record, Reject. |
| Run, finished | `finished` in the header; *Finished. The record is written.*; the findings card again, from `record.json`; **Open the full report** and `record.md`; the finish card: `record written`, 7 steps, 13 tool calls, 1 submit, 0 verify rounds, 111.4 s, $0.4718; New scan. |
| Source drawer | `storage.py` lines 25 to 33 with line 29 highlighted — `def cleanup_user_files(user_id):` — opened by clicking the citation in the findings card, and read through the same jail the model's `read_file` uses. |
| Runs | One row: `advanced-S10-s1-<hex>`, `accepted`, `S10 · advanced · replay · seed 1 · <started at>`. |
| Results, empty | What `GET /api/results` answers before any sweep, with `make eval` and `make eval-replay` set as code inside the sentence. |
| About | The four questions, answered, and the boundary the tool refuses to cross. |

The Settings view and the brain picker landed after those frames and have none of their own. They were driven the same way instead: the page's script, a stubbed DOM, and canned `/api/cases`, `/api/settings` and `/api/runs` answers. With `claude` logged in, the brain toggle offers api and Claude; selecting Claude renames the mode to `play back`, shows the note, and puts the CLI's own default in the model placeholder; Start then opens the finished Claude run and labels its cost *estimated*. With no key, no recording and Claude logged in, the callout stops saying nothing can run and says live runs are available on that brain (`tests/test_web_simple_view.py`).

On a machine with Chrome, the two static views photograph themselves:

```
uv run art30 serve
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
  --window-size=1440,900 --virtual-time-budget=4000 \
  --screenshot=about.png "http://127.0.0.1:8734/#/about"
```

The Run view is not one of them. It needs a replay in flight and a person at the gate, so it is a window capture during a demo, which is also the only honest way to show a checkpoint waiting on somebody.
