# Changelog

## 2026-08-31 16:55 UTC — The budgets ride on top; the stage centres on the page

- Tool calls, submit attempts, turns and the estimated cost sit in one centred row under the header; the cost's pricing note is a single centred line under them; the side column is gone, so the Now line and the findings own the full width, centred on the page both ways
- Paths are relativised at render time with a third fallback: when neither the server nor a tree listing named the root, the directory every absolute read shares stands in; the page also asks `GET /api/runs/<id>` for the repo when the row arrived without one

## 2026-08-31 16:10 UTC — A record the verifier vouched for must render

- R01 demo run: the verifier accepted `utils.py:95` for a `password` on line 96 (7.2 span rule), the human approved, and the render check — which read only the cited line plus its forward continuation — refused it: `render failed` after 670 s and a human approval. The render check now reads the smallest enclosing ast statement span, exactly as the verifier does (DEVIATIONS D-22); the strict side after acceptance protects nobody
- The gate card now states what Approve writes and what Reject ends (previous entry); together these close the two confusions of the first real-repo demo run

## 2026-08-31 16:00 UTC — The strip folds to the simple case

- The Run view centres and asks only what a first run needs: Case, a path, Brain, Start. Arm, Mode, Model and Seed sit behind an Advanced options fold with one hint explaining the arms and the modes; the case intent and the mode reasons moved in with them; the credentials note folds behind "Your own login, not a key" and only unfolds its summary when a local brain is selected
- The intro is one sentence with the mechanics behind "How a scan works"; the gate card now says what Approve does (writes record.json/md/html with your recipient choices) and what Reject does (ends the run, nothing written); the button reads "Approve and write the record"; the recipient-kind rows explain that the processor-or-controller call is the human's
- On a wide screen the stage's centre column sits on the centre of the page (a spacer mirrors the side column)

## 2026-08-31 15:50 UTC — The run view is one stage

- Details is gone, and with it the page's own record renderer: a run takes the view — what the child is doing now, large and centred, the agent's tool calls read back as sentences that rotate through a step's files; the budgets at the side; at the checkpoint the findings card and the gate, the CLI's text folded; at the finish the card again from `record.json`, **Open the full report** and `record.md`, the totals, New scan
- Codex is not offered on the page for now; the CLI and the harness keep `--brain codex`. The no-key callout gains Dismiss (this page load only)
- The on-page record tests go with the renderer; `tests/test_web_simple_view.py` reads the stage as text through the Node DOM stub; 892 tests green
- Paths on the stage are relative to the repository under scan: the server names it on the `POST /api/runs` answer and in the runs listing, and the page falls back to the root the child's first tree listing was asked for; the big line wraps inside its column; files read are chips; once the checkpoint or the finish is on screen the step count and the files step aside for the findings

## 2026-08-31 15:30 UTC — Simple view on the website

- The Run view opens in Simple: one card for what the scan is doing now (the tool calls read back as a sentence, the files read so far) and one for what it found (stores not proven erased, each with kind, verdict, declaration, reason and cited evidence; the entry points; the stores that reach erasure; timers; the human cells), drawn from the accepted submission while the checkpoint waits and again from `record.json` once rendered; Details is the page as it was
- Status chips in plain words (`scanning`, `waiting for your approval`, `finished`); the end card says `record written`; the "every recipient kind left unknown" line only when there was a kind to set
- Verified by replaying the D01 trace through the page script in Node against a DOM stub (no browser on this machine); 888 tests green

## 2026-08-30 07:05 UTC — Three brains and one settings layer (ADR 0008)

- `--brain api|claude|codex`: local brains run the user's own logged-in CLI with the arms served as an MCP `submit_record` tool; isolation flags (no Bash, jailed reads, no user memory, our MCP only); traces converted line by line; cost as a labelled estimate reproducing Claude's own `total_cost_usd`
- Settings shared by CLI, harness and website: `art30 config`, `art30.toml`, key written to `.env` write-only; harness cells pin every request setting; `make eval-replay-local` re-verifies every recorded submission and re-scores every record
- Website: Settings view, brains panel with login detection, brain and model selectors, play back of saved runs, runs listed from disk
- Acceptance: real D02 runs on this machine's Claude and Codex logins; both brains read the D02 helper/call mismatch correctly, which is now fixed in the generator; 887 tests green

## 2026-08-30 00:22 UTC — Three surfaces: skill, CLI, local website

- ADR 0007: one core, three surfaces; the website drives the CLI as a subprocess (same seam as the harness), never a second loop
- `--approve file` gate mode; skill package generated from the prompt files with the verifier as a script and a Stop hook; CLI polish for arbitrary repositories; wheel ships both arms
- `art30 serve`: stdlib server, SSE trace stream, file gate relay, jailed source excerpts, results view; one inlined page, bundled OFL font, no external requests
- Advanced records now carry their verification history and rule-set sha (ADR 0006 addendum); 750 offline tests green; pixels unverified (no browser here)

## 2026-08-29 20:13 UTC — Phase 3 built and audited: v1 ready for review

- Evidence tooling (`verify-docs`, failure index, gate targets), spec-vs-code audit (`docs/spec/DEVIATIONS.md`, 21 rows, specs amended to the code), example record regenerated from the generated S10, hardening and record→replay tests; README and REPRODUCE materialised; build trajectory committed (main session, gzipped)
- Independent end-to-end audit: clean clone passes in ~10 s, no SDK mismatch, no false safe on four hand-run repos; five defects fixed before any recording (trace dir seam, sweep scoping, cost ceiling, report scope, D02 emitter)
- 656 offline tests green; live sweeps wait on the API key, the cost ceiling and the hand-labelled real-repo manifests

## 2026-08-29 15:34 UTC — Phase 2 built: the verifier and the advanced arm

- `art30/verify/` on stdlib ast: call graph, entry points, store detection, synthetic edges, reachability over (node, mode, passed) states, the 6.1 verdict table, claim checking with the contract's feedback object; `advanced/arm.py` and gate
- Acceptance: all twelve synthetic fixtures reproduce every manifest verdict; twelve adversarial false safes closed with regression tests; 590 offline tests green
- Harness refactored under the 300-line rule with byte-identical CLI help; two demo repos D01/D02 for hand testing; R01 PEP 758 syntax noted (upstream, not a vendoring artefact)
- Phase 2 restarted once after the machine slept mid-response; the build machine is held awake for the rest of the weekend

## 2026-08-29 01:02 UTC — Phase 1 built: fixtures, runtime, baseline arm, harness

- R01–R04 vendored at pinned SHAs (LICENSE kept, SOURCE.md each); fixture generator + ten generated repos and manifests, `make fixtures` clean; 90 tuples as the spec's table
- art30 runtime (config, trace, tools, llm, loop, cli, render, prompts, schema), baseline/arm.py, harness (score, trace_check, run, report); 221 offline tests, `make smoke` green; Makefile recipes real
- Four fixture specs amended before any run (CASES.md errata); ADR 0006 freezes the baseline and shared runtime at 7681cb6 so the verifier can be built before Sweep A while no API key is available
- Verified Opus subagents throughout: builder → adversarial verifier → fixer per module; the lead commits per file

## 2026-08-29 22:15 UTC — v1 accepted

- Author reviewed all 428 v1 decisions through the review ledger and accepted every one; Q2–Q5 closed with their defaults
- `.gitattributes` pins fixture bytes (plan item 0) before any fixture is generated
- Next: the build, in the order of docs/spec/08-plan.md §7

## 2026-08-28 21:09 UTC — v1 concept, research and spec

- Three verified agent workflows (42 Opus subagents): research with re-fetched sources (docs/research/), judge mapping (docs/judging/), specs 00–10 + fixture generator + example record (docs/spec/), ten fixture specs and the split (evals/fixtures/specs/, evals/split.yaml), build plan and narrative drafts
- ADR 0003 (runtime: Opus 5, no temperature/seed, identical prompt across arms), ADR 0004 (every contract change the spec pass asked for), ADR 0005 (kill switch 2 narrowed, freeze 19:30 UTC, one-window test sweep, $300 ceiling)
- Tooling: dependencies and art30 console script, Docker path with make and git, Makefile stubs for every contract target incl. gate checks; make smoke green
- Open for the author: Q2 video tooling, Q3 anecdote wording, Q4 licence, Q5 budget — defaults recorded

## 2026-08-28 16:02 UTC — Direction chosen: GDPR inventory + erasure check

- ADR 0002: codebase → Art. 30 technical inventory + erasure-path table, closed over an ast reachability verifier; baseline is the skill (same tools, open loop)
- AMBIGUITIES (15 rows) and NON-GOALS filled for the slice; AI Act rule set gated behind a locked GDPR test number
- evals/CASES.md: 14 cases (10 synthetic, 4 real at pinned SHAs) + 1 reserve; hard case S10 = soft delete whose purge job never reaches object storage
- docs/demo-script.md: 90-second execution segment

## 2026-08-28 15:20 UTC — Repo skeleton

- Problem statement saved to docs/problem/; read in full
- Conventions scaffold: CLAUDE.md pointer, AGENTS.md spec, .vault/ decision log with ADR 0001
- Deliverable stubs (README, REPRODUCE, CHANGELOG_EVAL, HOT_TAKE) and eval/trace directory structure
- Direction decision open as .vault/QUESTIONS.md Q1
