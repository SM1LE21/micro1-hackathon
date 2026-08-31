# art30 — the technical half of a GDPR record of processing, read out of the code

`art30` reads a Python repository and writes two things. An inventory of the personal data it
holds, store by store and field by field, with `file:line` on every cell. And an erasure table:
for each store, whether closing an account actually reaches it, or whether the data stays. Every
claim the model makes is re-checked against the call graph by deterministic code before the record
renders, and a person approves before anything is written.

Built solo for the micro1 Agentic Workflows Hackathon, 2026-08-28 to 2026-08-31.

**If you have five minutes:** `make setup && make smoke && make eval-replay-local`. No API key needed.

## Who has this problem?

The technical founder of a small EU SaaS, on the day somebody asks for the record of processing: a
co-founder running diligence, a customer's lawyer, a supervisory authority
(`.vault/adr/0002-gdpr-inventory-erasure-check.md`). The document was written by hand months ago
and the code has moved since. Nobody re-reads a spreadsheet against `models.py` every sprint.

Art. 30(5)'s 250-employee derogation does not settle it for them. Its conditions are alternatives,
any one of which triggers the obligation, and processing in the regular course of business is not
"occasional" (`docs/research/gdpr-sources.md` §6.10 [S9][S6]). Whether a particular controller is
exempt is a legal judgement, which is exactly the class of question this tool refuses to answer.

I have been that person: in a product I run, the hand-written record had two statements reversed,
and a soft delete never reached object storage for a month before anyone noticed.

## What bottleneck makes it worth solving?

Writing the document is not the hard part. Knowing whether it is still true is.

The EDPB's coordinated enforcement action on the right to erasure ran through 2025 across 32
supervisory authorities and 764 controllers, and reported on 10 February 2026 that "some responding
controllers do not even report relying on their record of processing activities ('ROPA')" when they
handle erasure requests, tracing the difficulty to "the absence of a structured process to map the
relevant personal data" (`docs/research/gdpr-sources.md` §3.1 and §6.10 [S11]). The same report found
that "certain controllers had difficulties with differentiating between closing an online user
account or profile and the right to erasure" (§6.9 [S11]).

A regulator has already priced that confusion. CNIL's deliberation SAN-2021-008 of 14 June 2021
fined Brico Privé EUR 500,000, of which EUR 300,000 covered breaches of Arts. 5-1-e), 13, 17 and 32;
the Art. 17 finding was that "lorsqu'une personne demande l'effacement de son compte, la société ne
supprime pas les données à caractère personnel mais procède uniquement à la désactivation du compte
en question" (`docs/research/gdpr-sources.md` §4 [S18]). Eval case S02 is that sentence rebuilt as a
repository. The Garante's EUR 2.6m Foodinho decision is the other half: the register omitted
categories of personal data the inspection found in the systems, and keeping it "non costituisce un
adempimento formale" (§4 [S16]).

Drift between the document and the system is the failure. The current fix is reading the code by
hand, under the protocol in `evals/CASES.md`; how long that takes was never measured here.

## Does the agent solve it well?

The agent reads the repository with three read-only tools (`list_tree`, `read_file`, `grep`; `Read`,
`Grep`, `Glob` on the `claude` brain) and submits through `submit_record`, served over MCP there
(`00-contract.md` §Tools, `docs/brains.md`). It drafts the record, the part needing judgement:
whether a `notes` column, a `metadata` blob or an IP in a log line is personal data is a semantic
call, not a grep (Art. 4(1), `docs/research/gdpr-sources.md` §1 [S1]). Every claim it submits is
re-checked by a deterministic verifier on stdlib `ast`, answering one structural question per store
— does a static call path run from the erasure entry point to a deletion primitive for that store —
and hands back the struck claim, the reason and the line as a tool result the model must answer
(`docs/spec/03-verifier.md`, `00-contract.md` §Feedback object). An unresolvable call renders
`unverified` rather than a guess either way, and a human gate fires before the record renders
(`.vault/AMBIGUITIES.md` rows 14 and 8; `00-contract.md` §Run phases 3, ground rule 04).

The baseline is the same model, the same instruction bytes, the same four tools and the same five
submission attempts, with the verifier and the gate removed. That is a good SKILL.md
(ADR 0003 §4). The comparison below is therefore the closed loop and nothing else, and the harness
refuses to write a report when the two arms' `prompt_sha` differ (`05-eval-harness.md` §7).

## Three ways to run it

One core, three surfaces (`.vault/adr/0007-three-surfaces-one-core.md`). The CLI is the only thing that runs the agent loop, the verifier and the renderer; the other two package it.

| Surface | Start | Needs a key | What it is |
|---|---|---|---|
| Claude Code skill | copy `skill/art30/` into your skills directory; `skill/art30/README.md` | no — your own session; the verifier is offline Python | the eval's baseline instruction text, generated from the same prompt files, plus `skill/art30/scripts/verify.py` (the same verifier, same strings) and a Stop hook that turns it into a gate |
| CLI | `uv run art30 scan <repo> --arm advanced --approve ask`; reference in `docs/cli.md` | with `--brain api` yes; with `--brain claude` or `--brain codex` no — your own logged-in CLI is the model (`docs/brains.md`) | the measured tool: the loop, both arms, the gate, traces, record/replay; cost is measured on the api brain and an estimate at list prices on a local one |
| Local website | `make serve` (or `uv run art30 serve --open`); `docs/web.md` | live yes, replay no | drives `art30 scan` as a subprocess and shows the run as one stage: what the scan is doing now, the budgets at the side, then what it found — the stores not proven erased, each cited, every citation opening its source line — and the two files it wrote (`docs/web.md` §The stage); a results view sits over `results/metrics.json` |

## Can another person reproduce the result?

`make setup && make smoke && make eval-replay-local` needs no key: `reverify` re-runs the verifier over
every submission recorded under `results/runs/` and re-scores every `record.json`, `report` rebuilds
`results/metrics.json`, `git diff --exit-code` compares it with the committed file (`Makefile`,
`docs/runbook-sweeps.md` §7). It cannot regenerate model outputs; what it proves is that the verifier
and the scorer still say what they said. Docker and live runs: [REPRODUCE.md](REPRODUCE.md).

## Results

Test split (S08–S10), mean over three runs per case. `±` is `f1_std_seeds`, the mean over cases of
the standard deviation across that case's three runs (`05-eval-harness.md` §7.3).

<!-- metrics:begin -->
| Metric | Simple baseline | Agent solution | Change |
|---|---|---|---|
| Erasure-inventory F1 (test, mean of seeds) | 0.88 ± 0.04 | 0.86 ± 0.03 | -0.01 |
| Human time per task | n/a | n/a | n/a |
| Cost per task (estimate at list prices) | $0.37 | $0.50 | +$0.13 |

| Row | Baseline | Advanced |
|---|---|---|
| Pass (runs) | 2/9 | 3/9 |
| Pass (cases, majority of seeds) | 1/3 | 1/3 |
| pass^3 | 0/3 | 1/3 |
| Regressions | n/a (no previous metrics.json) | n/a (no previous metrics.json) |
| False safe (matched) | 0 | 0 |
| Reaching claims on stores not in the manifest | 1 | 0 |
| False safe in a gate-rejected draft | 0 | 0 |
| Unverified per run | 0.00 | 0.00 |
| Invalid verdict for kind | 0 | 0 |
| Bad citations | 4 | 3 |
| Cost per run | $0.37 | $0.50 |
| Tokens per run (input · output · cache read · cache write) | 15 · 6,350 · 145,236 · 13,998 | 16 · 8,698 · 157,188 · 20,788 |
| Turns · tool calls | 7.6 · 16.4 | 8.1 · 16.9 |
| Machine minutes per run | n/a | n/a |
| success + failure = n | 5 + 4 = 9 | 6 + 3 = 9 |
<!-- metrics:end -->

False safe — the agent says a store is erased where the manifest says it is not — is the row that
matters more than F1, because it is the error that costs a founder a month:
0 against 0 on test.

Every scored run ran on `--brain claude`: the author's logged-in Claude Code CLI, `claude-opus-5`,
no API key (`docs/runbook-sweeps.md` §6a, ADR 0008). So the cost column is an estimate, not a bill:
a subscription run costs no marginal dollars, and the number is the CLI's own token counts over the
run's `step` lines at list prices, `cost_source: cli_estimate` (`art30/brains/pricing.py`,
`docs/judging/requirements-matrix.md` D2g). Both arms spend five `submit_record` attempts a run,
every one counted, rejected included: a user pays for retries (ADR 0003 §2).

Dev, and the secondary rows (pass, pass^3, regressions, unverified, bad citations, turns, tool
calls): `results/metrics.json` via `make report`. Runs: 52 success +
8 failure = 60; failures ship in `traces/failures/`.

Statistics: exact McNemar on the binary pass row, majority of three runs per case, dev
p = 1.0000 and test p = 1.0000. With three test
cases the exact test cannot reach 0.05 whatever the arms do, so the number is reported for shape.
F1 carries a paired bootstrap 95% interval over cases ([-0.061, +0.020]). This
model exposes no temperature and no seed (ADR 0003 §2).

The gate approves in every scored run (`--approve auto`, `by: "simulated"`), so none of the measured
difference comes from a human intervening; it is the verifier's (`05-eval-harness.md` §7.1).

## Improvement changelog

[CHANGELOG_EVAL.md](CHANGELOG_EVAL.md): one row per experiment in the official four columns, with
the evidence that drove the next decision, removed experiments included. End to end, test F1 went
0.88 → 0.86 and false safes
0 → 0; the largest single
contributor was Iteration 1, the closed loop itself — not for the mean but for delivery: the
citation rule reaches the model as feedback instead of a render wall, 25/30 → 27/30 records
delivered, the hard case S10 1/3 → 3/3.

## What existed before the competition

This repository was created after kickoff on 2026-08-28 15:00 UTC. Nothing in it predates that except:

- The tools: Claude Code (the coding agent that wrote most of the code; sessions rendered at
  `traces/build-trajectory.html.gz`), the `claude-opus-5` model both arms call, Python 3.12, uv, the
  `anthropic` SDK, `pyyaml`, `jsonschema`, `pytest`, `claude-code-log` 1.5.0, `gitleaks`, Docker.
- Four open-source repositories vendored at pinned SHAs, each keeping its upstream
  LICENSE and a `SOURCE.md` with url, sha, licence, date and what was stripped:
  `fastapi/full-stack-fastapi-template` @ `486f054` (MIT), `flaskbb/flaskbb` @ `fc64c74` (BSD-3),
  `pinry/pinry` @ `05476b1` (BSD-2), `miguelgrinberg/microblog` @ `a975ef6` (MIT); `evals/CASES.md`.
- Third-party text quoted rather than written: verbatim article and recital text of Reg. (EU)
  2016/679, 2024/1689 and 2026/1744 under `docs/research/sources/`, each file carrying its retrieval
  URL and date; the competition's own problem statement at `docs/problem/problem-statement.pdf`.

The scored set is S01–S10 from `evals/fixtures/specs/` (dev S01–S07, test S08–S10); R01–R04 were
never hand-labelled and were dropped from it, staying in the tree as material the CLI can scan
(`evals/CASES.md` errata, 2026-08-31). No prompt library, agent framework or rule set was carried in.

## Prior art

Bearer classifies personal data across 122 data types and calls its own output "RoPA **input**";
there is no deletion, erasure or retention concept in the 28 substantive pages of its documentation,
whose rendered text was grepped in full, nor in the slugs of the remaining 846 recipe and rule URLs
(`docs/research/prior-art.md` §0, §1 [S6][S1][S8][S8b]). Privado detects 110+ data elements and
scores `s3.delete_object` as evidence that data *arrived* at S3, the inverse of an erasure check
(§2 [S10][S13]). Fides executes real erasure, from a YAML declaration a human writes rather than
from the code (§3 [S17][S18]). Nothing found produces an erasure-path table from application
source: per store, reaches or does not, path cited (§7).

Two qualifiers, because the strong version of that claim is false. Privado Cloud generates an
Art. 30 record from code scans today, at no cost, using a fine-tuned LLM with no verification step
described in its own material, which is exactly the open-loop design used here as the baseline arm
(§2 [S10][S14]). Bearer's classifier, tuned on tens of thousands of open-source samples, should be
expected to beat this tool on inventory recall (§Honest weaknesses [S5][S6]). The claim here is
about the erasure half and about verification, not about finding a field called `email`.

## The AI Act

Not covered. Regulation (EU) 2026/1744 entered into force on 27 July 2026 and moved the Annex III
high-risk obligations of Chapter III Sections 1–3 to **2 December 2027**, so they do not apply until
then; Art. 50 transparency has applied since 2 August 2026 (`docs/research/ai-act-sources.md` §1
[S2][S3][S4]). An extension using the same verifier is scoped in `.vault/NON-GOALS.md`, gated behind
a locked GDPR number, and what it measured is a row in [CHANGELOG_EVAL.md](CHANGELOG_EVAL.md).

## What this is not

No legal basis, no purpose, no risk class: those cells render "requires human completion" and a
person fills them (`.vault/AMBIGUITIES.md` row 8), and the words "compliant" and "compliance" appear
nowhere in the output by rule (`00-contract.md` §Writing contract). It reads the target repository
and runs none of it. Fixing the code, or opening a pull request against it, is a consequential
action and out of scope by design. Python only, Django and SQLAlchemy/SQLModel idioms; anything else
is reported "unscanned" rather than guessed (`.vault/NON-GOALS.md`).

## Licence

micro1 owns the submission under the hackathon terms (`AGENTS.md` §Competition facts). No separate
licence file ships with it (`.vault/QUESTIONS.md` Q4); the vendored repositories keep their own.

## Agent trajectories

`traces/` holds one JSONL trace per run, both arms, failures included. Three are worth opening:

- `traces/advanced/S10-s2.jsonl` — the verifier hands back `storage.py:12` for `avatar_key`, the
  model corrects it, the record is delivered.
- `traces/baseline/S10-s2.jsonl` — the same repository, no verifier: the same citation reaches the
  renderer and the run dies (`traces/failures/baseline/S10-s2.diagnosis.txt`).
- `traces/advanced/S03-s1.jsonl` — the unenforced `ondelete` S03 plants renders three cells
  `unverified` rather than a guess in either direction.

`traces/failures/` holds every failed run with a one-line diagnosis.
`traces/build-trajectory.html.gz` is the rendered transcript of the Claude Code sessions that built
this repository (`make traces`, author-only; the HTML is committed).

## Main failure mode and hot take

**All eight failures in sixty runs were wrong line numbers, none were wrong judgements: the
reliability work was not making the model smarter, it was implementing each deterministic rule
exactly once and wiring its answer back as feedback instead of a wall.** The failure this project
actually hit, its traces under `traces/failures/`, the fix owed and the residual risk accepted:
[HOT_TAKE.md](HOT_TAKE.md).
