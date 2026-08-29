# ADR 0007 — Three surfaces, one core: skill, CLI, local website

status: accepted
date: 2026-08-29

## Decision

art30 ships on three surfaces. **The CLI is the only thing that runs the agent loop, the verifier and the renderer.** The other two are packagings of it, never re-implementations:

1. **Skill** (`skill/art30/`): `SKILL.md` is generated from `art30/prompts/system.md` + `taxonomy.md` by `make skill` and asserted byte-identical to the eval's instruction text, so the skill *is* the baseline arm the eval measures. `scripts/verify.py` wraps `art30.verify.check` (stdlib `ast`, offline, no key) and prints the same feedback strings the advanced arm returns; `scripts/render.py` wraps the renderer; a documented Claude Code Stop hook turns the advisory verifier into a gate on the user's own session. Codex is served through an `AGENTS.md` include of the same body; the README says exactly that and nothing more until their skill mechanism is read.
2. **CLI** (`art30 scan`): as built. Polish only: budget by repository size when the path is not an evaluation case, an output default outside the project tree, a plain "no `ANTHROPIC_API_KEY`" message, an install path (`uv tool install`) that ships the rules YAML, the schema, the prompts and the web page in the wheel.
3. **Local website** (`art30 serve`): a stdlib `http.server` on 127.0.0.1 that **spawns `art30 scan` as a subprocess** — the same seam `evals/harness/cells.py` uses — with `--approve file` and its own `--out`, tails the trace the CLI flushes line by line into a server-sent event stream, and exchanges the human gate through `<out>/gate/request.json` → `decision.json`. The page (one inlined HTML file, no CDN, works offline) shows the run as it happens — tool calls, the model's reasoning summaries, budget and cost, the verifier's rejections, the gate — and the record as it resolves, with every citation opening the source line. A results view reads `results/metrics.json`. Replay of a recorded case needs no key and is the demo path.

A new gate mode **`--approve file`** is added to `advanced/gate.py`: the gate writes the request, polls for the decision (`ART30_GATE_TIMEOUT`, default 1800 s; timeout is `gate_rejected` with a note), records `by: "human"` and the real `wait_s`. It adds `"file"` to the `approve` literal in frozen `art30/config.py` and to the CLI choices — before any recording exists (ADR 0006 addendum). No hashed request byte changes.

The eval is untouched: same arms, same prompt bytes, same tools, same harness. The website and the skill are outside the measurement; the README says so.

## Context

Q1's framing question ("what is the difference between this product and a skill?") was answered by making the skill the baseline. The author now wants the skill shipped as a file, and a visual surface for the demo and the End-to-End Quality line. Rebuilding the loop for the website would fork the one thing the score rests on; driving the CLI keeps one implementation and lets the website show a real trace rather than a reconstruction.

## Options considered

- A web framework (FastAPI/uvicorn) — cleaner SSE, three more dependencies in the judge's install; the server is ~250 lines of stdlib.
- The website importing `art30.loop` in-process — loses the subprocess isolation the harness already relies on, and the gate would need threads instead of files.
- A stdin-piped gate (`--approve ask` with the server feeding `y`) — fragile parsing of stdout; a file exchange is inspectable and testable.
- Replay pacing on the server — the page paces playback instead, so the server stays dumb and the trace bytes are untouched.

## Consequences

- NON-GOALS amended: product polish is allowed on the website; the output formats list gains the served page. Still no execution of target repositories, no network from tools, no LLM-judge, no DOCX/PDF.
- The core freeze (Sunday 19:30 UTC) covers `art30/` except `art30/web/`, which freezes Monday 09:00 UTC before the video.
- Design brief for the page: white ground, near-black navy ink, one teal accent, bold headings, rounded solid buttons, generous space, tabular numerals — the feel of the organiser's site, never its logo, name or copy. One bundled OFL typeface as a data URI. Light theme only, painted explicitly. No emoji. `docs/writing-rules.md` binds every string on the page.
- `results/web/` is git-ignored; nothing the website writes enters the eval's `results/` or `traces/`.
