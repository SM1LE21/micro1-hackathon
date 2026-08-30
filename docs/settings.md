# Settings (`art30 config`)

One loader, `art30/settings.py`, answers the CLI, the eval harness and the website, so the model a scan uses on the page is the model a scan uses on the terminal. `art30 config list` prints every key with the layer its value came from (ADR 0008 item 5).

## Precedence

Lowest first. Each layer wins over the one above it.

1. The defaults in `art30/settings.py` (`KEYS`), which are the numbers in the table below.
2. `~/.config/art30/config.toml` — you, on this machine, across every checkout.
3. `<project>/art30.toml` — this repository. `<project>` is the directory holding `pyproject.toml`, found by walking up from the working directory; with no `pyproject.toml` above you, it is the working directory itself.
4. `<project>/.env` — the API key belongs here. `ART30_*` lines are read here too, because a `.env` is what people reach for.
5. The process environment.
6. A CLI flag on `art30 scan`, which the command applies after the loader has run.

`art30 config list` names the layer per key: `default`, `user`, `project`, `.env`, `env`. An eval cell drops layers 2 and 3 entirely; "What a sweep pins" below says how.

## The keys

| Key | Environment | Default | Values |
|---|---|---|---|
| `brain` | `ART30_BRAIN` | `api` | `api`, `claude`, `codex` |
| `model` | `ART30_MODEL` | `claude-opus-5` | any model id |
| `claude_model` | `ART30_CLAUDE_MODEL` | unset | what `claude --model` accepts |
| `codex_model` | `ART30_CODEX_MODEL` | unset | what `codex exec -m` accepts |
| `effort` | `ART30_EFFORT` | `high` | `low`, `medium`, `high`, `xhigh`, `max` |
| `max_tokens` | `ART30_MAX_TOKENS` | `32000` | a whole number |
| `max_turns` | `ART30_MAX_TURNS` | `60` | a whole number |
| `tool_budget` | `ART30_TOOL_BUDGET` | by case kind: 60 synthetic, 120 real | a whole number |
| `submit_budget` | `ART30_SUBMIT_BUDGET` | `5` | a whole number |
| `max_usd` | `ART30_MAX_USD` | unset | a number of dollars |
| `gate_timeout` | `ART30_GATE_TIMEOUT` | `1800` | seconds |
| `approve` | `ART30_APPROVE` | `ask` | `ask`, `auto`, `file` |
| `concurrency` | `ART30_CONCURRENCY` | `4` | a whole number |
| `codex_prices` | `ART30_CODEX_PRICES` | `{}` | JSON: `{"<model>": [input, cached_input, output]}`, dollars per million tokens |
| `anthropic_api_key` | `ANTHROPIC_API_KEY` | absent | `.env` only, see below |

`model`, `effort`, `max_tokens`, `tool_budget` and `submit_budget` are hashed into the request or named in the first user message. Moving any of them invalidates the recorded responses in `evals/cache/`, and the run says so: whichever layer moved one off its default value, its `ART30_*` name appears under `overridden:` in the header line, in `run_start.config.overridden` and in `provenance.config` (`docs/spec/07-ui.md` §1). A layer that spells out the default value changes nothing and declares nothing.

An empty value is not a value, in a file as well as in a variable. `ART30_MAX_USD=` in a `.env` leaves the key unset, which is what `.env.example` ships; `model = ""` in an `art30.toml` leaves `model` at the layer below it rather than putting `null` in a request nothing can answer.

## The two files

Both are flat: one `key = value` per line, no tables, no sections. `art30 config set` rewrites the one line it owns and leaves your comments and your other keys where they are. An unknown key in either file is an error naming the file, not a line that quietly does nothing.

```
$ art30 config path
user      /Users/you/.config/art30/config.toml   (not there yet)
project   /Users/you/src/art30/art30.toml
.env      /Users/you/src/art30/.env
```

`art30.toml.example` is a copy of the defaults with a comment on each key. `art30.toml` and `.env` are both git-ignored.

## The secret

`ANTHROPIC_API_KEY` lives in `.env` and nowhere else. Neither settings file may hold it: a key named `anthropic_api_key` in a `.toml` is refused with a message saying where it belongs.

```
$ art30 config set ANTHROPIC_API_KEY sk-ant-...
written to .env (not echoed)
```

The file is created at mode `0600` before any content reaches it, and the line is replaced if one is there. `art30 config unset ANTHROPIC_API_KEY` rewrites the same `.env`, because that is the only file the key is ever in. A settings file it was never in must not report the key removed. Nothing reads the value back. `art30 config list` and the website's settings view print `present` or `absent`, the loader keeps a boolean, and `tests/test_settings.py::test_the_key_is_a_presence_and_never_a_value` is what holds that: the key's own characters must not appear in what `describe()` returns. The SDK reads the environment for itself, which is why `config.load()` pushes `.env` into `os.environ` with `setdefault` without ever looking at that entry.

## The commands

```
art30 config list                    every key, its value, the layer it came from
art30 config get KEY                 one value, for a script
art30 config set KEY VALUE [--user]  writes ./art30.toml, or ~/.config/art30/config.toml
art30 config unset KEY [--user]      drops the line; the layer below it takes over
art30 config path                    the three files, in precedence order
```

`KEY` is accepted in any spelling a person uses: `model`, `MODEL`, `ART30_MODEL`. A value outside a key's list is a usage error (exit 2) naming the key and what it accepts:

```
$ art30 config set effort enormous
effort must be one of low, medium, high, xhigh, max, got 'enormous'
```

## What a sweep pins, and what it does not

The harness runs one `art30 scan` child per cell (`evals/harness/cells.py`, `launch`). It pins, per cell:

- as flags, which beat every layer: `--arm`, `--case`, `--seed`, `--mode`, `--approve`, `--out`, from the `Cell` that `evals/harness/plan.py` built;
- as environment variables, which beat both files: `ART30_TRACE_DIR` (the trace root for this sweep, so a scratch sweep cannot overwrite a committed trace), `ART30_UNLOCK_TEST=1` on a test-split cell, and `ART30_IGNORE_SETTINGS_FILES=1`.

That last one is the pin ADR 0008 item 5 asks for, and it covers every key at once rather than the five request variables: a cell reads no `~/.config/art30/config.toml` and no `<project>/art30.toml`, so a sweep runs at art30's own defaults plus what the sweep itself set. One switch rather than five pinned values, because a user file that set `brain` or `max_usd` would break a sweep as surely as one that set `model`, and because a pinned value at the default would have to be declared as an override it is not. `tests/test_run.py::test_no_settings_file_of_the_users_reaches_a_cell` holds it. A clean checkout was never enough on its own: `~/.config/art30/config.toml` is not a checkout artefact.

`.env` and the process environment are **not** dropped — they are how a sweep is deliberately configured, and the parent's environment is what the child inherits. And the declaration stays: any of the five request variables whose value is not the default is named in `overridden`, in the trace and in `provenance.config`, so a sweep at settings nobody reported cannot pass for a reported one. The comparison is on the value, so copying `art30.toml.example` verbatim declares nothing: every line in it is already the default.

The website pins the same switch where it means the same thing. A replay child (`art30/web/runs.py`, `environment`) is spawned with `ART30_IGNORE_SETTINGS_FILES=1`, so it replays at the recorded settings and no user file reaches it. A live run started from the page does read the two files, which is what the Settings view is for: it is the surface where a person sets them.

## What is not a setting

The run switches stay environment-only, and no settings file reaches them. They are the seams the harness and the website pin per child, and a file that could move them would move a sweep: `ART30_MODE`, `ART30_RECORD`, `ART30_CACHE_DIR`, `ART30_TRACE_DIR`, `ART30_UNLOCK_TEST`, `ART30_REPRODUCIBLE`, `ART30_WEB_DIR`, `ART30_IGNORE_SETTINGS_FILES`. `docs/cli.md` is their table. The last one drops the two settings files for one process; it is read from the environment only, so no settings file can switch off the reading of settings files.

One key straddles the line. `gate_timeout` is a setting the CLI and the website can show, but the code that waits at the gate (`advanced/gate.py`) reads `ART30_GATE_TIMEOUT` from the environment itself, and it is frozen until the core freeze lifts (ADR 0006, ADR 0008). Setting `gate_timeout` in `art30.toml` therefore shows up in `art30 config list` and not at the gate. Put it in `.env` or export it, which does reach the gate, until `advanced/gate.py` reads the loader.

## Local brains

`brain = "claude"` and `brain = "codex"` select a CLI on your machine instead of the API. `art30 scan --brain claude` parses today and stops with `brain claude is not built yet`; `art30/brains/` is where they land. `art30.brains.detect()` already reports what is installed: the binary's path, its `--version` line, and whether the CLI says it is logged in. Nothing else from those answers is kept. `claude auth status` returns an email, an organisation and a plan, and `tests/test_brains_detect.py::test_nothing_of_the_account_survives_the_detection` is the check that none of it reaches a page, a trace or a log line.

The note that belongs wherever a local brain is selected, verbatim from ADR 0008 item 6:

> Local brains run the `claude` / `codex` command already installed and logged in on this machine. art30 never stores or asks for those credentials; if the CLI is not logged in, the run fails with the CLI's own login error. Anthropic does not allow third parties to offer claude.ai login or rate limits inside their products; this tool does not — it runs your own CLI on your own machine.

The brand is "Claude (your login)", never "Claude Code".
