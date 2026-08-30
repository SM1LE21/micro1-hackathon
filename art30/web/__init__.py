"""The local website: a stdlib server that drives `art30 scan` as a subprocess.

ADR 0007: the CLI is the only thing that runs the loop, the verifier and the
renderer. Nothing under here re-implements any of the three. The server spawns
the same child `evals/harness/cells.py` spawns, tails the trace the child
flushes line by line, relays the child's own stdout, and exchanges the human
gate through `<out>/gate/request.json` and `decision.json`.

`server.py` is the socket and the routing table, `api.py` the JSON handlers,
`runs.py` the child processes and their directories, `sse.py` the event stream,
`catalog.py` the case list. `index.html` is the page.
"""
