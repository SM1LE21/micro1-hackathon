"""Test doubles for the local brains: a stdio MCP client and a fake `claude`.

Neither talks to a network and neither needs a login. `mcp_client.py` speaks the
protocol our server answers, so `tests/test_mcp_server.py` exercises the server the
way the CLI does; `fake_claude.py` is a `claude` binary that reads a scripted
conversation from a file, calls the real MCP server for every submission and prints
the event stream shapes the real CLI prints (`tests/test_brain_claude.py`).
"""
