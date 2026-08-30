"""`art30 config` — list, get, set and unset the settings every surface shares (ADR 0008).

Split out of `art30/cli.py` for the ~300-line rule; the parser is attached to the CLI's
subparsers by `config_parser(subs)` and `config_command(args)` runs the subcommand.
"""

from __future__ import annotations

import argparse
import json
import sys

from art30 import settings


def config_parser(subs) -> None:
    """`art30 config ...`: the same settings the harness and the website read (ADR 0008)."""
    parser = subs.add_parser("config", help="read and write the settings every surface shares")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="every key, its value and the layer it came from")
    actions.add_parser("path", help="the files that are read, in precedence order")
    actions.add_parser("get", help="one value").add_argument("key")
    setter = actions.add_parser("set", help="write one value")
    setter.add_argument("key")
    setter.add_argument("value")
    remove = actions.add_parser("unset", help="drop one value")
    remove.add_argument("key")
    for sub in (setter, remove):
        sub.add_argument("--user", action="store_true",
                         help="write ~/.config/art30/config.toml instead of ./art30.toml")




def config_command(args: argparse.Namespace) -> int:
    """`list|get|set|unset|path`. A bad key or value is a usage error, never a traceback."""
    scope = "user" if getattr(args, "user", False) else "project"
    try:
        if args.action == "list":
            for row in settings.describe():
                print(f"{row['key']:<18}{_shown(row['value']):<26}{row['source']}")
        elif args.action == "get":
            name = settings.key_for(args.key).name
            print(_shown(next(r["value"] for r in settings.describe() if r["key"] == name)))
        elif args.action == "path":
            resolved = settings.read()
            for label in ("user", "project", settings.DOTENV_NAME):
                path = resolved.files[label]
                print(f"{label:<10}{path}" + ("" if path.is_file() else "   (not there yet)"))
        elif args.action == "set" and settings.key_for(args.key).secret:
            settings.write_secret(args.key, args.value)
            print("written to .env (not echoed)")
        elif args.action == "set":
            print(f"{settings.write(args.key, args.value, scope)}: {args.key} = {args.value}")
        else:
            print(f"{settings.unset(args.key, scope)}: {settings.key_for(args.key).name} unset")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return USAGE_EXIT
    return 0




def _shown(value: object) -> str:
    """A value as a person reads it: an unset key is blank, not `None`."""
    if value is None:
        return "(unset)"
    return json.dumps(value, sort_keys=True) if isinstance(value, dict) else str(value)
