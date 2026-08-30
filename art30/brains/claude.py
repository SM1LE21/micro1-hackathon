"""The `claude` brain: the command line, the environment and the first message.

Everything specific to one CLI lives in a file like this one; `driver.py` spawns
what it is handed and knows neither binary. ADR 0008 item 2 is the isolation list
and this module is where it is spelled:

- `--append-system-prompt` carries our instruction text, so the record is drafted
  against `art30/prompts/system.md` and not against the CLI's own idea of a task.
- `--mcp-config` plus `--strict-mcp-config`: our stdio server and no other, so
  `submit_record` is the arm's handler and nothing else the machine has configured.
- `--tools Read,Grep,Glob` is the built-in tool set, not a permission list: the
  CLI offers no other built-in tool for the model to spend budget on. MCP tools
  come from `--mcp-config` and are untouched by it. `--allowedTools` still
  pre-approves the four so a `-p` run never waits for a prompt it cannot show,
  and `--disallowedTools` stays as a second lock on the names that write or run.
- `--restricted` does the two things a permission list cannot. It ignores the
  user, project and local settings files -- which is what keeps a *scanned*
  repository's `.claude/settings.json` hooks from executing, and what keeps the
  user's own `~/.claude` out of a measured run -- and it confines the file tools
  to the working directory, so `Read` cannot leave the repository under scan.
- `--setting-sources ""`: the same guarantee said twice, and the one that
  survives if a future build narrows what `--restricted` covers.
- `--disable-slash-commands`: no skill of the user's runs inside a scan.
- `--no-session-persistence`: a scan leaves no conversation on disk.
- `--effort`: the run is made at the effort the record then claims it was made at.

The user's auto-memory is kept out by `--restricted` and nothing else. Probed on
2.1.251 with cwd set to `evals/fixtures/synthetic/D02`, which sits inside this
checkout: without the flag the init line reads `memory_paths: {"auto":
"~/.claude/projects/<this repo>/memory/"}` -- the author's own notes about
building this tool, in the context of a model being scored on an eval case --
and with it that field is null. Relocating `CLAUDE_CONFIG_DIR` to a fresh
directory empties the same field, but on this machine it also loses the login
("Not logged in / Please run /login", exit 1), so the variable is stripped rather
than repointed and `driver.py` fails any run whose init line still names a memory
path. That check is what makes the guarantee testable instead of assumed.

`ANTHROPIC_API_KEY` is stripped from the child's environment on purpose. With a
key present the CLI bills that key; without one it uses the login the user already
has, which is the whole point of a local brain (ADR 0008 items 1 and 6). The
parent session's own `CLAUDE_CODE_*` variables go with it, so a scan started from
inside another Claude Code session is not a child of it.

One flag this build does not have, checked against `claude --help` on 2.1.251:
`--max-turns`. The CLI ignores unknown options silently rather than failing, so it
is not passed: the turn ceiling is enforced by the driver.
"""

from __future__ import annotations

import os
from pathlib import Path

NAME = "claude"
BINARY = "claude"
LABEL = "Claude (your login)"   # ADR 0008 item 6: never "Claude Code"
TOOLS = "Read,Grep,Glob"        # --tools: the built-in set, not a permission list
ALLOWED = "Read,Grep,Glob,mcp__art30__submit_record"
# Belt and braces behind `--tools`: every built-in name this build has that writes,
# runs, reaches the network or spawns another agent, including the `Task*` family
# that a bare `Task` never matched.
DENIED = ("Bash,Edit,Write,MultiEdit,NotebookEdit,WebFetch,WebSearch,Agent,Task,"
          "TaskCreate,TaskGet,TaskList,TaskUpdate,TaskStop,ToolSearch,Workflow,"
          "SendMessage,ListAgents,EnterWorktree,ExitWorktree,RemoteTrigger,"
          "ScheduleWakeup,CronCreate,CronDelete,CronList,TodoWrite,KillShell,BashOutput")
# The sentence the API brain does not need: there, the four tools are the whole
# world; here the CLI brings its own file tools and has to be pointed at ours.
FIRST_TURN_SUFFIX = (
    "Use Read, Grep and Glob to read the repository and mcp__art30__submit_record"
    " to submit. Do not run anything."
)
# Present in the 2.1.251 binary's own variable table; it turns off the
# non-essential network calls a scan has no use for.
QUIET_TRAFFIC = "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"
STRIPPED = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE", "CLAUDE_PID",
            "CLAUDE_EFFORT", "CLAUDE_CONFIG_DIR")


def argv(system_prompt: str, first_message: str, mcp_config: Path, model: str | None,
         effort: str | None = None) -> list[str]:
    """The whole command line. `cwd` (the repository) is the driver's to set."""
    command = [
        BINARY, "-p", first_message,
        "--output-format", "stream-json", "--verbose",
        "--append-system-prompt", system_prompt,
        "--mcp-config", str(mcp_config), "--strict-mcp-config",
        "--restricted",
        "--tools", TOOLS,
        "--allowedTools", ALLOWED,
        "--disallowedTools", DENIED,
        "--setting-sources", "",
        "--disable-slash-commands",
        "--no-session-persistence",
    ]
    if model:
        command += ["--model", model]
    if effort:
        command += ["--effort", effort]
    return command


def env(base: dict[str, str] | None = None) -> dict[str, str]:
    """The parent environment minus the keys that would change whose run this is.

    `CLAUDE_CONFIG_DIR` is removed rather than repointed: a fresh config directory
    does empty `projects/<slug>/memory/`, but it also loses the login this brain
    exists to use. `--restricted` empties that field with the login intact, and
    `driver.py` refuses a run whose init line disagrees (ADR 0008 item 2).
    """
    values = dict(os.environ if base is None else base)
    for name in STRIPPED:
        values.pop(name, None)
    for name in list(values):
        if name.startswith("CLAUDE_CODE_"):
            values.pop(name, None)
    values[QUIET_TRAFFIC] = "1"
    return values


def first_message(first_turn: str) -> str:
    return f"{first_turn}\n\n{FIRST_TURN_SUFFIX}"
