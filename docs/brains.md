# Brains (`art30 scan --brain api|claude|codex`)

A brain is what runs the agent loop. The rest of the system does not change with it: the same instruction text, the same `submit_record` schema, the same verifier inside the submit handler, the same human gate, the same `record.json` and the same trace contract (ADR 0008 item 1).

```
uv run art30 scan <repo> --arm advanced                      # the API, the default
uv run art30 scan <repo> --arm advanced --brain claude       # your own claude CLI
uv run art30 scan <repo> --arm advanced --brain claude --model opus
```

`--brain` can also live in `art30.toml` or `ART30_BRAIN` (`docs/settings.md`). `--model` follows the brain the loader resolved: on `api` it moves `model`, on a local brain it moves that CLI's `--model` and leaves the API model where it was.

## `api`

`art30/loop.py` and the Messages API. Every request is hashed and, with `ART30_RECORD=1`, recorded; `--mode replay` plays the recording back through the same loop with no key and no socket. This is the brain the recorded sweeps and `make eval-replay` use, and the only one that is reproducible response by response.

## `claude`

`art30/brains/driver.py` starts `claude -p` as a subprocess in the repository under scan, converts its event stream into the trace line by line, and finishes the run in this process. The model reads the repository with the CLI's own `Read`, `Grep` and `Glob`, and submits through one MCP tool of ours.

What the CLI is given:

| Flag | Why |
|---|---|
| `--append-system-prompt <text>` | our instruction text, spliced by `art30.llm.system_prompt()`. The run's copy is written to `<out>/system-prompt.md` with the first user message under it |
| `--mcp-config <out>/mcp.json` `--strict-mcp-config` | one stdio server, `python -m art30.brains.mcp_server`, and none of the machine's other MCP configuration |
| `--tools Read,Grep,Glob` | the built-in tool set, not a permission list. MCP tools come from `--mcp-config` and are unaffected, so the run is the four-tool world the record is scored against |
| `--allowedTools Read,Grep,Glob,mcp__art30__submit_record` | the four, pre-approved, so a `-p` run never waits for a prompt it cannot show |
| `--disallowedTools Bash,Edit,Write,…,Task,TaskCreate,TaskGet,TaskList,TaskUpdate,ToolSearch,…` | a second lock on every name that writes, runs, fetches or spawns another agent (`art30/brains/claude.py:DENIED`) |
| `--restricted` | ignores the user, project and local settings files — which is what stops a **scanned** repository's `.claude/settings.json` hooks from executing and keeps your own `~/.claude` memory out — and confines the file tools to the working directory, so `Read` cannot leave the repository under scan |
| `--setting-sources ""` `--disable-slash-commands` | the same guarantee said twice, and no skill of yours inside a scan |
| `--effort <level>` | the run is made at the effort `run_start` and the record then claim it was made at |
| `--no-session-persistence` | a scan leaves no conversation on disk |
| `--output-format stream-json --verbose` | the event stream the trace is built from |

`ANTHROPIC_API_KEY` is removed from the child's environment, along with `CLAUDE_CONFIG_DIR` and the `CLAUDE_CODE_*` variables of any session that started the scan. A key present would bill that key; without one the CLI uses the login you already have, which is the point. `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` is set.

### Why `--restricted` rather than a longer deny list

Three things were measured on 2.1.251 rather than assumed, and each of them was true before the flag was added:

- **A scanned repository executed code.** A copy of D02 carrying a `.claude/settings.json` with a `SessionStart` hook ran that hook, because the driver sets `cwd` to the repository and `--setting-sources project` loaded that repository's settings. A deny list removes tools the *model* can call; it does not touch hooks the CLI runs on its own behalf before the model gets a turn.
- **The file tools were not confined.** `Read` on `/etc/hosts` returned the file. Under an untrusted repository — the whole point of a scanner — a prompt injection in the source was enough to aim it at `~/.ssh`, and whatever came back landed in `cli-stdout.jsonl`.
- **Your own memory was loaded into a measured run.** With `cwd` inside this checkout, the init line read `memory_paths: {"auto": "~/.claude/projects/<this repo>/memory/"}`. That is eval contamination before it is a privacy leak.

All three are closed by `--restricted`, and the third is also checked: the driver reads `memory_paths` off the `init` line and ends the run `api_error` if it is not empty, so a future build that stops honouring the flag fails loudly instead of quietly scoring a contaminated run. Pointing `CLAUDE_CONFIG_DIR` at a fresh directory empties the same field but loses the login on this machine (`Not logged in · Please run /login`), so it is stripped rather than repointed.

### `submit_record` over MCP

```
python -m art30.brains.mcp_server --arm advanced --repo <root> --spool <dir>
                                  --tool-budget 60 --submit-budget 5
```

JSON-RPC 2.0 over stdio, stdout for protocol traffic and stderr for logs. `tools/list` returns `art30.tools.SPEC[3]` — the same name, description and input schema the API brain sends — and every `tools/call` goes straight to `baseline/arm.py` or `advanced/arm.py`. A rejected claim comes back as the tool error the API brain would have seen, with the same strings.

The server owns three things the CLI cannot be trusted with: the submit budget (a call past it answers `no attempts left` and leaves `<spool>/exhausted`), the record of every attempt (`<spool>/submissions.jsonl`, one line per call with the verifier's full feedback), and the fact that acceptance happens once (`<spool>/accepted.json`; later calls answer `already accepted`). The gate does not run there — it runs in this process after the CLI exits, where a terminal exists.

## `codex`

Same driver, same MCP server, same gate, same record. `codex exec --json` is started in the repository under scan and its item stream is converted line by line by `art30/brains/codex_events.py`.

Two things are different from the `claude` brain, and both come from the CLI rather than from a choice of ours.

**The instruction text is the prompt.** Codex has no system-prompt flag, so `art30.llm.system_prompt()` and the first-turn text are concatenated and passed as the positional prompt. `<out>/system-prompt.md` is the run's copy and is the whole of what the model was told. stdin is closed, so the `Reading additional input from stdin...` notice codex prints resolves immediately.

The instruction text is shared with the API brain and names `grep` and `read_file`, and `read_file` is not a tool this brain serves. The prompt is frozen (ADR 0006), so the first turn reconciles the two instead: it says both are shell commands here — `rg`/`grep` to locate, `sed -n '<a>,<b>p'` to read a range.

**The model reads with `shell`, not with `Read`.** Codex's file tools are shell commands. Every one of them is recorded in the trace as a tool call named `shell`, with the command and `"sandbox": "read-only"` as its input and the command's output as its result.

What the CLI is given:

| Flag | Why |
|---|---|
| `exec --json` | the non-interactive run and the JSONL event stream the trace is built from |
| `-s read-only` | writes and network are refused by the sandbox. **Not** a jail — see below |
| `--skip-git-repo-check` `-C <repo>` | a scanned repository is often not a git checkout, and the working root is that repository, never this one |
| `-c mcp_servers.art30.command/args/env` | one stdio server, `python -m art30.brains.mcp_server`, spelled as per-invocation overrides. The `-c` syntax works on 0.148.0; the `CODEX_HOME` fallback (a temporary `config.toml` with `[mcp_servers.art30]`) was never needed |
| `-c mcp_servers.art30.default_tools_approval_mode="approve"` | not optional. Without it every `tools/call` comes back `MCP tool call requires approval, but approval policy is never` and the model never reaches the verifier |
| `--ignore-user-config` | your `$CODEX_HOME/config.toml` — your MCP servers, model, instructions — stays out of a measured run. The login in the same directory still works, which is why `CODEX_HOME` is not touched |
| `--ignore-rules` | no user or project execpolicy `.rules` file |
| `-c project_doc_max_bytes=0` | the **scanned** repository's `AGENTS.md` is not read into the prompt. A scanner that pastes an untrusted repository's instructions into its own context has no isolation left |
| `-c memories.use_memories=false` `generate_memories=false` | your notes stay out of a scored run, and the run leaves none behind |
| `-c tools.web_search=false` | a scan reads the repository, not the internet |
| `-c allow_login_shell=false` | shell commands do not go through a login shell. Without it `/etc/zprofile`, `~/.zprofile` and `~/.zlogin` are sourced inside a measured run, and the operator's PATH shims and exported variables decide which `rg`, `python` and `grep` the model gets |
| `-c model_reasoning_summary="detailed"` | without it the stream carries no `reasoning` item at all (probed both ways), and a trace with an empty `reasoning` field is a trajectory nobody can follow |
| `-c model_reasoning_effort=<effort>` | the run is made at the effort `run_start` and the record then claim it was made at |
| `--ephemeral` | no session file on disk |
| `-m <model>` | when `codex_model` is set; otherwise the CLI's own default |

`OPENAI_API_KEY` (with `OPENAI_BASE_URL` and `CODEX_API_KEY`) is removed from the child's environment, for the reason `ANTHROPIC_API_KEY` is removed from the other brain's: a key present would bill that key, and a local brain exists to run on the login you already have.

### The read-only sandbox is not a jail — stated as a limit

`-s read-only` blocks writes and blocks the network. It does **not** block *executing* the repository under scan: a read-only `python manage.py check` is still someone else's code running on your machine. Nothing in art30 prevents it either. What stands between a scan and that is the instruction text, which tells the model to read with `ls`, `cat`, `sed -n` and `rg` and to never execute the repository, install anything or write a file.

It does not confine *reads* either. `--restricted` keeps the other brain's file tools inside the working directory; `-s read-only` lets a shell command read anything the user can read. On one D02 run the model answered three schema rejections by reading this checkout — `docs/spec/record.schema.json` and `evals/fixtures/specs/D02.yaml`, the case's own answer key — from inside the scanned repository, and the trace shows it (`shell` calls with absolute paths outside `-C`). Nothing in codex's sandbox model can scope that, so a codex sweep over a fixture that has a manifest beside it is a sweep whose isolation from its own answers rests on the instruction text.

That is a weaker guarantee than the `claude` brain's `--restricted`, in both directions, and it is written here rather than implied because a scanner is pointed at repositories nobody has read yet. If that matters for your input, or for a scored sweep, run the `claude` brain, or run the scan inside a container.

Two things the sandbox *does* enforce were checked rather than assumed on 0.148.0: a write to `/tmp` was refused, and a `file_change` item never appeared. If one ever does, it is recorded as a tool call named `file_change` with an error result, so a scan that edited the repository under scan is visible in the trace rather than something a reader has to infer.

### Reading the item stream

Codex prints no assistant message and no per-item usage, so a step is rebuilt from the items: `reasoning` and `agent_message` accumulate into the open step, and the tool call that follows them closes it. That keeps every tool result in the same step as its call and gives one tool call per step, which is as much structure as the stream honestly supports.

| Item | In the trace |
|---|---|
| `thread.started` | the thread id, in `cli-stdout.jsonl`. It cannot reach `run_start`, which is written before the CLI starts |
| `reasoning` | the step's `reasoning` |
| `agent_message` | the step's `text` |
| `mcp_tool_call` | a tool call under the name the server serves (`submit_record`), with the arm's own answer as its result. A rejection arrives as `status: "failed"`, which is what the model sees too |
| `command_execution` | a tool call named `shell`, input `{command, sandbox: "read-only"}`, result the aggregated output |
| `file_change` | a tool call with an error result (see above) |
| `turn.completed` | the run's five token counts |
| `error` | kept, not fatal. Codex prints one for a retry as well as for a failure (`Reconnecting... 2/5 (unexpected status 401 …)`), so a run that goes on to submit has recovered; a run that does not ends with the CLI's own words in `run_end.note` |
| `turn.failed` | ends the run `api_error` |

Codex's own built-in MCP tools appear under their own names when the model calls them, and they count against the tool budget like any other call. A tool call that fails at the transport level records the CLI's own message as its result; only `submit_record` gets the verifier's `{"accepted": false, …}` shape, so a protocol error on some other tool is not counted as a rejected submission.

Codex probes `resources/list`, `resources/templates/list` and `prompts/list` on connect even though this server advertises none of those capabilities. Answering them `-32601` put `resources/list failed` and `resources/templates/list failed ... Unexpected response type` on codex's stderr, so the server now answers all three with an empty list — `{"resources": []}`, `{"resourceTemplates": []}` (the spec's key for that one) and `{"prompts": []}`. The stderr is clean on the run below. The model still spends a call or two on its own `list_mcp_resources` and `list_mcp_resource_templates`; that is its choice, not a gap here, and those calls now come back empty rather than as an error.

### Cost: unpriced unless you price it

Codex reports tokens and nothing else: no cost of its own, and no model name anywhere in its stream. There is no list price this repository could hard-code without inventing one, so **a codex run reports tokens and `n/a`** — `cost_source: "unpriced"` in `run_start.config` and in `provenance`, `cost_usd` `0.0`, `tokens <n> · n/a` on the terminal's last line, and `| Cost | n/a (no list price for this model) |` in `record.md` and `record.html`. A zero would say "free" where the truth is "unknown" (ADR 0008 item 3), and that has to hold on the surface a person signs as well as on the terminal.

The record's Model row names the brain, not the API model: `provenance.model` stays the configured `claude-opus-5` because the trace contract reads it there, so the row is built from `brain_label` and `brain_model` instead and reads `Codex (your login) — the CLI default model` when `codex_model` is unset. A record signed with a model that never read the repository is the one provenance error a reader cannot catch.

To price one, set `codex_prices` (`docs/settings.md`) and `codex_model`:

```
codex_prices = '{"gpt-5-codex": [1.25, 0.125, 10.0]}'
codex_model  = "gpt-5-codex"
```

Three numbers are `[input, cached_input, output]` in dollars per million tokens, as OpenAI publishes them; two are read as `[input, output]` and cached input then prices at the input rate, which overstates rather than flatters. `cache_write` has no rate of its own and prices as input. A model with no entry — and an unset `codex_model`, because nothing in the stream would name one — stays unpriced, and `run_start` says so on line one instead of contradicting its own `run_end`.

`run_end.note` carries the counts the contract's four `usage` keys have no home for: `tokens: 59285/186368/11840/5134 (input/cached/output/reasoning)`.

`cached_input_tokens` and `cache_write_input_tokens` are both read as parts of `input_tokens`, so the trace's `input`, `cache_read` and `cache_write` add up to what codex called input and a priced run cannot bill the same token twice. Both real runs reported a zero cache write, so that reading is the safe one rather than the confirmed one; the first run with a non-zero write settles it.

Because codex reports usage once per turn, every step's `usage` is zero and the run's totals settle on the last step. `run_start.config.usage_note` says that in every codex trace.

### The run that proves it

`evals/fixtures/synthetic/D02`, advanced arm, 2026-08-30, codex-cli 0.148.0 on a ChatGPT login:

```
uv run art30 scan evals/fixtures/synthetic/D02 --arm advanced --brain codex --approve auto
```

`accepted · 10 steps · 9 tool calls · 4 submits · 3 verify rounds · gate approved (simulated)`, 258 s, 257,493 tokens, `n/a`. The trace passes `evals/harness/trace_check.py` with no violations, `cli-stderr.log` carries nothing but codex's own `Reading additional input from stdin...`, and every shell command in the trace reads `/bin/zsh -c`, not `-lc`.

Three of the four submissions were rejected on schema errors while the model worked out the record's shape from the tool definition, where the `claude` brain's D02 run was accepted on its first attempt. That is a real difference between the two brains on the same case and the same prompt, and it is why `submit_budget` is five.

### Login

`codex login status` must say you are logged in. art30 never stores or asks for that credential and never reads `~/.codex/auth.json`; if the CLI is not logged in, the run ends `api_error` with the CLI's own words (`Not logged in`, or a `401 Unauthorized` off the stream). `art30.brains.detect()` reads the version string and one boolean out of `codex --version` and `codex login status` and keeps nothing else.

## What is enforced, and what is not

Enforced by us, from outside the CLI:

- **Tool calls.** Every `tool_use` block in the stream is counted against `tool_budget`. When the budget runs out the CLI is stopped (SIGINT, then SIGTERM) and the call that could not be bought is dropped from the trace as well, so `run_end.tool_calls_total` never exceeds the budget it reports.
- **Turns.** Counted the same way against `max_turns`. Neither CLI has a flag for it — `claude --help` on 2.1.251 has no `--max-turns` and that build ignores an unknown flag rather than refusing it, and `codex exec --help` on 0.148.0 has none either — so a ceiling on the command line would be a ceiling nobody applied.
- **Submissions.** The MCP server counts them, and the driver stops the run when the spool says the budget is gone.
- **Wall clock.** `ART30_BRAIN_TIMEOUT` seconds, 1800 by default, after which the run ends `timeout`.

Not enforced:

- **Sandboxing.** Isolation here is the CLI's own restricted or read-only mode, not a container. On `claude`, nothing in the repository is executed and nothing outside it is read — but that rests on `--restricted` behaving as its help text says, which is why the memory check above exists. On `codex` the bar is lower: `-s read-only` blocks writes and network but not *executing* the repository, and only the instruction text forbids that. A scan of a repository you do not trust is still a scan, not a sandbox, and on `codex` it is less of one.
- **The model's honesty about its own tools.** The trace records the names the CLI reported. Nothing cross-checks them against the process's actual syscalls.
- **Sampling.** Neither brain exposes temperature or a seed. `--seed` is a harness label.

## Cost

A subscription run bills no dollars, so cost is an **estimate at API list prices** and every surface says so: `cost_source: "cli_estimate"` in `run_start.config` and in `provenance`, and an `est` suffix on the CLI's last line. The rest of this section is the `claude` brain; a `codex` run is unpriced unless you configure `codex_prices`, and its own section above says how.

The estimate is computed from the tokens the CLI reports, with two corrections the first real run made necessary:

- Claude Code writes its prompt cache at the **one-hour TTL**, which costs twice the input price where `art30/llm.py`'s table carries the five-minute rate (1.25×). `art30/brains/pricing.py` prices the one-hour part separately.
- The per-message `output_tokens` in the stream is a placeholder (1, 3, 17 on a run that spent 9,553), while the input and cache counts are exact and sum to the run's totals. The final `result` line carries the run's true output count, so the last step of the trace carries whatever the run spent and no earlier message declared. Every number in the trace is then a count the CLI reported, and they sum to its own totals.

Both corrections make the run total honest and both make a *per-step* figure something a reader cannot reproduce from `docs/spec/00-contract.md` alone: the last step carries the whole output remainder (on the D02 run, 55% of the cost on a step with no tool calls), and the one-hour cache write is priced at 2x input where line 143 of the contract says 1.25x. Rather than leave that in the source only, `run_start.config.usage_note` says it in every local-brain trace.

A model with no entry in the price table is not priced at all. `cost_usd` stays `0.0`, `cost_source` reads `unpriced` in `run_start.config` and in `provenance`, and the terminal prints `tokens <n> · n/a` instead of `$0.00 est`, because a zero would say "free" where the truth is "unknown" (ADR 0008 item 3). A context-window suffix is stripped before the lookup, so `claude-opus-5[1m]` — what the init line reports — prices as `claude-opus-5`.

With both corrections the estimate reproduces the CLI's own number: the accepted D02 run reports `cost_usd 0.737277` against `cli_total_cost_usd 0.7372775`. Both are kept — ours in `cost_usd` and `run_end.cost_usd`, the CLI's in `provenance.cli_total_cost_usd`.

## The trace

Same contract, same validator (`evals/harness/trace_check.py`). Three differences, all of them in `run_start`:

- `config.brain`, `config.brain_model`, `config.cost_source` and `config.usage_note` say which brain ran, what it costed with, and which two per-step figures do not follow the contract's arithmetic. `model` stays the configured model, so a trace from either brain reads against the same name.
- `request_hash` is `null` on every step. The request was assembled inside the CLI, so there are no bytes for art30 to hash. Check 12 accepts null only when `run_start.config.brain` is not `api`; on an API run a missing hash is a lost replay and stays a violation.
- One model message can arrive as several `assistant` lines sharing a `message.id`. They are one step, because they were one request. The `codex` stream has no message boundaries at all, and how a step is rebuilt from its items is in that brain's section above.

The CLI's own stream and its stderr tail are kept beside the record as `cli-stdout.jsonl` and `cli-stderr.log`, which is what makes the conversion auditable.

## Reproducing a local-brain run

No brain can regenerate model output. What a local-brain run commits is its trace, every submitted record and every verifier answer (`submissions.jsonl`), and `make eval-replay` re-runs the deterministic verifier over all of them and re-scores every record (ADR 0008 item 4). The website calls this "play back", not "replay": the saved trace is replayed, not the model.

## Before you run one

> Local brains run the `claude` / `codex` command already installed and logged in on this machine. art30 never stores or asks for those credentials; if the CLI is not logged in, the run fails with the CLI's own login error. Anthropic does not allow third parties to offer claude.ai login or rate limits inside their products; this tool does not — it runs your own CLI on your own machine.

The brand is **"Claude (your login)"** and **"Codex (your login)"**, wherever a brain is named on a screen. Never "Claude Code".

## Known limits

- A subscription has rolling usage windows. A sweep can stall mid-way; the harness records the window and the stall is noted, never hidden.
- `--mode replay` is refused for a local brain, with the reason.
- The estimate is a list-price estimate of someone else's token counts. It is not your bill, and the two numbers in the record are there so nobody has to take one of them on faith.
- The step-level output tokens are the run's, settled at the end. A per-step cost from a local brain is coarser than a per-step cost from the API brain.
- On `codex` a step's *whole* usage is the run's, because that CLI reports tokens once per turn. There is no per-step cost from it at all unless `codex_prices` is set, and even then it is the last step that carries the run.
- `codex`'s read-only sandbox does not stop the repository under scan from being executed, and does not stop a shell command from reading files outside it — including this checkout, on a run that did exactly that. That is the weakest guarantee either brain offers and it is stated, not implied.
