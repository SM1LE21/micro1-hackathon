"""The `codex` brain: the command line, the environment and the first message.

`driver.py` spawns what this module hands it and knows neither binary. ADR 0008
item 2 is the isolation list; this is where it is spelled for codex, checked flag
by flag against codex-cli 0.148.0 on 2026-08-30:

- `exec --json` is the non-interactive run and the JSONL event stream the trace is
  built from (`art30/brains/codex_events.py`).
- `-s read-only` is the sandbox. It blocks writes and network. It does **not**
  block *executing* the repository under scan -- a read-only `python -c ...` is
  still a process running someone else's code -- so the instruction text forbids
  it and `docs/brains.md` states the limit rather than implying a jail.
- `--skip-git-repo-check` and `-C <repo>`: a scanned repository is often not a
  git checkout, and the working root is the repository, never this one.
- MCP through `-c mcp_servers.art30.*`. The per-invocation override syntax works
  on this build (probed; the `CODEX_HOME` fallback in the docstring below was not
  needed), and `default_tools_approval_mode="approve"` is required: without it
  every `tools/call` comes back `MCP tool call requires approval, but approval
  policy is never` and the model never reaches the verifier.
- `--ignore-user-config` keeps `$CODEX_HOME/config.toml` out of a measured run --
  the user's own MCP servers, model choice and instructions -- while the login in
  the same directory still works, which is what `claude --restricted` does for the
  other brain. `--ignore-rules` drops user and project execpolicy files.
- `-c project_doc_max_bytes=0`: the **scanned** repository's `AGENTS.md` is not
  read into the prompt. A scanner that pastes an untrusted repository's
  instructions into its own system context has no isolation left.
- `-c memories.use_memories=false` and `generate_memories=false`: the author's own
  notes stay out of a scored run, and the run leaves none behind.
- `-c tools.web_search=false`: a scan reads the repository, not the internet.
- `-c allow_login_shell=false`: shell commands do not go through a login shell, so
  the operator's `~/.zprofile` cannot decide which `rg` or `python` the model gets
  inside a measured run.
- `--ephemeral`: no session file on disk, the counterpart of the other brain's
  `--no-session-persistence`.
- `-c model_reasoning_effort=<effort>`: the run is made at the effort `run_start`
  and the record then claim it was made at. Every value `art30/settings.py` allows
  (`low` through `max`) is one this build accepts.
- `-m <model>` when `codex_model` is set, else the CLI's own default.

Codex has no system-prompt flag, so **the instruction text is the prompt**:
`art30.llm.system_prompt()` and the first-turn text are concatenated and passed as
the positional argument. `<out>/system-prompt.md` holds the run's copy, and it is
the whole of what the model was told. stdin is closed by the driver, so the
`Reading additional input from stdin...` notice codex prints resolves immediately.

`OPENAI_API_KEY` is stripped from the child's environment for the reason
`ANTHROPIC_API_KEY` is stripped from the other brain's: with a key present the CLI
bills that key, and a local brain exists to run on the login the user already has
(ADR 0008 items 1 and 6). `CODEX_HOME` is *not* stripped -- that is where the
login lives, and `--ignore-user-config` already keeps the configuration out.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from art30.brains import pricing
from art30.brains.codex_events import CodexStepper

NAME = "codex"
BINARY = "codex"
LABEL = "Codex (your login)"     # ADR 0008 item 6: never a product name that is not ours
SERVER = "art30"
STEPPER = CodexStepper           # `driver.py` reads this instead of `convert.Stepper`
SANDBOX = "read-only"
# The sentence the sandbox cannot enforce. `-s read-only` stops writes and network;
# nothing stops `python manage.py` from running, so it is forbidden in words and the
# documentation says so plainly instead of calling this a sandbox (ADR 0008 item 2).
FIRST_TURN_SUFFIX = (
    "Read the repository with shell commands that only read it -- ls, cat, sed -n, rg,"
    " grep -- and submit with the submit_record tool from the art30 MCP server."
    " Never execute the repository's own code, never install anything, and never write"
    " to a file: the sandbox is read-only and a write would fail."
    " The instructions above name `grep` and `read_file`; on this run both are shell"
    " commands -- `rg`/`grep` to locate and `sed -n '<a>,<b>p'` to read a range."
)
# Config overrides that do not depend on the run. Kept as pairs so the argv reads in
# one place and `tests/test_brain_codex.py` can assert on the list rather than a string.
FIXED_CONFIG: tuple[tuple[str, str], ...] = (
    # Without this the stream carries no `reasoning` item at all -- probed both ways
    # on 0.148.0 -- and a trace whose steps have an empty `reasoning` field is a
    # trajectory a reader cannot follow (AGENTS.md, Trace rules).
    ("model_reasoning_summary", '"detailed"'),
    ("project_doc_max_bytes", "0"),
    ("memories.use_memories", "false"),
    ("memories.generate_memories", "false"),
    ("tools.web_search", "false"),
    # Every shell command codex runs goes through a login shell unless this is set:
    # `/etc/zprofile`, `~/.zprofile` and `~/.zlogin` are sourced inside a measured
    # run, so the operator's PATH shims and exported variables decide which `rg`,
    # `python` and `grep` the model gets. That is the contamination `--restricted`
    # closes on the other brain (ADR 0008 item 2). Verified a real key on 0.148.0:
    # `--strict-config` accepts it and rejects a misspelling.
    ("allow_login_shell", "false"),
)
STRIPPED = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY")


def argv(system_prompt: str, first_message: str, mcp_config: Path, model: str | None,
         effort: str | None = None) -> list[str]:
    """The whole command line. `cwd` (the repository) is the driver's to set.

    `mcp_config` is the `mcpServers` JSON the driver wrote for the other brain; the
    server definition is read back out of it and re-spelled as `-c` overrides, so
    both brains start the same process with the same arguments and there is one
    place where that command is decided.
    """
    spec = _server_spec(mcp_config)
    command = [
        BINARY, "exec", "--json",
        "-s", SANDBOX,
        "--skip-git-repo-check",
        "--ignore-user-config", "--ignore-rules", "--ephemeral",
        "-C", _repo_of(spec),
    ]
    for key, value in (*_server_config(spec), *FIXED_CONFIG):
        command += ["-c", f"{key}={value}"]
    if effort:
        command += ["-c", f'model_reasoning_effort="{effort}"']
    if model:
        command += ["-m", model]
    command.append(prompt(system_prompt, first_message))
    return command


def _server_spec(mcp_config: Path) -> dict:
    """The `mcpServers.art30` object the driver wrote, or an empty one."""
    try:
        spec = json.loads(Path(mcp_config).read_text(encoding="utf-8"))["mcpServers"][SERVER]
    except (OSError, ValueError, KeyError, TypeError):   # the driver writes it; a broken
        return {}                                        # file is the CLI's error to report
    return spec if isinstance(spec, dict) else {}


def _repo_of(spec: dict) -> str:
    """The repository under scan, read back off the server's own `--repo`.

    `argv` is handed the MCP config and no case, and the working root has to be the
    repository rather than this checkout. The one place that path is already written
    down is the server command the driver built, so it is read from there instead of
    being passed a second time and allowed to disagree. `.` is the fallback, and the
    driver has set `cwd` to the same directory.
    """
    args = [str(a) for a in (spec.get("args") or [])]
    if "--repo" in args and args.index("--repo") + 1 < len(args):
        return args[args.index("--repo") + 1]
    return "."


def _server_config(spec: dict) -> list[tuple[str, str]]:
    """`<out>/mcp.json` as the four `-c mcp_servers.art30.*` overrides codex takes.

    The value of a `-c` is parsed as TOML, so a string is quoted, a list is JSON
    (which TOML accepts for arrays of strings) and the environment is an inline
    table. `default_tools_approval_mode="approve"` is the one that is not optional:
    an MCP call under `--json` is refused without it, because there is no terminal
    to approve it on.
    """
    if not spec:
        return []
    prefix = f"mcp_servers.{SERVER}"
    pairs = [(f"{prefix}.command", json.dumps(str(spec.get("command") or ""))),
             (f"{prefix}.args", json.dumps(list(spec.get("args") or []))),
             (f"{prefix}.default_tools_approval_mode", '"approve"')]
    environment = spec.get("env")
    if isinstance(environment, dict) and environment:
        body = ", ".join(f"{k} = {json.dumps(str(v))}" for k, v in sorted(environment.items()))
        pairs.append((f"{prefix}.env", "{ " + body + " }"))
    return pairs


def priced(model: str | None) -> bool:
    """Whether `run_start` can already say a codex run will carry dollars.

    `pricing.priced` answers `None` optimistically, because the other CLI names on
    its init line whichever model it chose and the verdict can wait for that. Codex
    names no model anywhere in its stream, so an unconfigured `codex_model` is a
    model nothing will ever be able to price, and the trace says so on line one
    rather than contradicting its own `run_end` (ADR 0008 item 3).
    """
    return model is not None and pricing.priced(model)


def prompt(system_prompt: str, first_message: str) -> str:
    """The instruction text and the first turn as one prompt, because codex has no
    system-prompt flag. Same separator `driver.py` writes into `system-prompt.md`."""
    return f"{system_prompt}\n\n---\n\n{first_message}"


def env(base: dict[str, str] | None = None) -> dict[str, str]:
    """The parent environment minus the keys that would change whose run this is."""
    values = dict(os.environ if base is None else base)
    for name in STRIPPED:
        values.pop(name, None)
    return values


def first_message(first_turn: str) -> str:
    return f"{first_turn}\n\n{FIRST_TURN_SUFFIX}"


def run_note(stepper: CodexStepper, note: str | None = None) -> str | None:
    """What `run_end.note` carries for a codex run, beside `note` from the driver.

    Codex reports four token counts and the trace has room for three of them: the
    contract's `usage` has no `reasoning` key, and an unpriced run has no dollars
    either, so the run's own numbers are said once in words where a reader will find
    them next to the stop condition.

    `note` is the stop condition's own words, and it is `None` exactly when the run
    ended with an accepted record. That is what says whether an `error` line the CLI
    printed mattered: a run that finished had recovered from it.
    """
    usage = (getattr(stepper, "totals", None) or {}).get("usage") or {}
    reasoning = getattr(stepper, "reasoning_tokens", 0)
    parts = []
    if any(usage.values()) or reasoning:
        counts = "/".join(str(usage.get(key, 0)) for key in ("input", "cache_read", "output"))
        parts.append(f"tokens: {counts}/{reasoning} (input/cached/output/reasoning)")
    # An `error` line the run recovered from says nothing; one it did not is the only
    # explanation a `no_submission` run has, and it is codex's own words.
    if getattr(stepper, "last_error", None) and note is not None:
        parts.append(f"codex reported {stepper.last_error}")
    return " · ".join(parts) or None


# `run_start.config.usage_note`: which per-step figures a reader cannot reproduce
# from `docs/spec/00-contract.md` alone. Codex's are different from the other
# brain's -- it reports no per-item usage at all -- so it says its own.
USAGE_NOTE = (
    "codex reports token counts once per turn and never per item, so every step's"
    " usage is zero and the run's totals are settled on the last step; reasoning"
    " tokens have no usage key and are in run_end.note"
)
