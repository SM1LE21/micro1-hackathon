# 09 — The judge-facing narrative

Every judge-facing word, drafted before the runs so that Sunday night is pasting numbers into
slots rather than writing prose at 02:00. Nothing here is committed to `README.md`,
`REPRODUCE.md`, `HOT_TAKE.md` or `CHANGELOG_EVAL.md` by this document; the fenced blocks are the
paste source and the surrounding text says what has to be true before each one is pasted.

Written 2026-08-28, hour ~5. Read with `docs/writing-rules.md` (which binds every block below),
`docs/judging/requirements-matrix.md` (the rows these documents satisfy),
`docs/judging/anticipated-questions.md` (the same claims at answer length), and
`docs/spec/00-contract.md` (the vocabulary; it wins).

**Placeholder convention.** Every bracketed slot names the artifact field it is filled from, rooted
at `results/metrics.json` unless another file is named: `[arms.advanced.test.f1_mean]` is `arms` →
`advanced` → `test` → `f1_mean`, produced by `make report` (`05-eval-harness.md` §6). `[..field]`
inside a line repeats the path of the slot before it. A slot that names no field is a sentence
somebody has to write from a trace they actually read, marked `[WRITE:` … `]`. A slot waiting on a
decision is marked `[Qn:` … `]` and points at `.vault/QUESTIONS.md`.

**Rule for every number in every block:** it is pasted from an artifact, never typed from memory
(AGENTS.md §Evidence discipline). If a run does not produce it, the sentence containing it is cut
rather than softened.

---

## 1. `README.md`

Complete draft, in the order the problem statement asks for (`docs/problem/problem-statement.txt`
p.1 four questions, p.7 deliverable 01), closing on the failure mode and the hot take because
deliverable 01 says to and `docs/judging/requirements-matrix.md` D1f makes it a checked row. 197
lines as written, seventeen over the ~180 budget; if it has to come down, the prior-art paragraph's
second qualifier goes first and the fourth trajectory bullet second. Every factual claim carries a
path or a source ID.

Three things in it are not yet true and must be checked before it is pasted: the four vendored
repositories exist under `evals/fixtures/real/` with their LICENSE files, `traces/` holds the four
named files, and `.vault/QUESTIONS.md` Q3 and Q4 are resolved.

```markdown
# art30 — the technical half of a GDPR record of processing, read out of the code

`art30` reads a Python repository and writes two things. An inventory of the personal data it
holds, store by store and field by field, with `file:line` on every cell. And an erasure table:
for each store, whether closing an account actually reaches it, or whether the data stays. Every
claim the model makes is re-checked against the call graph by deterministic code before the record
renders, and a person approves before anything is written.

Built solo for the micro1 Agentic Workflows Hackathon, 2026-08-28 to 2026-08-31.

**If you have five minutes:** `make setup && make smoke && make eval-replay`. No API key needed.

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
and a soft delete never reached object storage for a month before anyone noticed. [Q3: confirm
this sentence — .vault/QUESTIONS.md]

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

Drift between the document and the system is the failure. Reading the code by hand is the current
fix, and it costs [human_time.manual_minutes.mean] minutes per repository under the written
protocol in `evals/CASES.md`.

## Does the agent solve it well?

The agent reads the repository with three read-only tools — `list_tree`, `read_file`, `grep` — and
submits through a fourth, `submit_record` (`00-contract.md` §Tools). It drafts the record, which is
the part that needs judgement: whether a `notes` column, a `metadata` JSON blob or an IP in a log
line is personal data is a semantic call, not a grep (Art. 4(1),
`docs/research/gdpr-sources.md` §1 [S1]).
Every claim it submits is re-checked by a deterministic verifier on stdlib `ast`, which answers one
structural question per store — does a static call path run from the erasure entry point to a
deletion primitive for that store — and hands back the struck claim, the reason and the line, as a
tool result the model has to answer (`docs/spec/03-verifier.md`, `00-contract.md` §Feedback object).
An unresolvable call renders `unverified` rather than a guess in either direction, and a human gate
fires before the record renders (rows 14 and 8 of `.vault/AMBIGUITIES.md`; the gate itself is
`00-contract.md` §Run phases 3, ground rule 04).

The baseline is the same model, the same instruction bytes, the same four tools and the same five
submission attempts, with the verifier and the gate removed. That is a good SKILL.md
(ADR 0003 §4). The comparison below is therefore the closed loop and nothing else, and the harness
refuses to write a report when the two arms' `prompt_sha` differ (`05-eval-harness.md` §7).

## Can another person reproduce the result?

`make setup && make smoke && make eval-replay` regenerates `results/metrics.json` from recorded API
responses with no key, and ends in `git diff --exit-code` against the committed file. Commands, the
Docker path and the live runs: [REPRODUCE.md](REPRODUCE.md).

## Results

Test split, mean over three runs per case. `±` is `f1_std_seeds`, the mean over cases of the
standard deviation across that case's three runs (`05-eval-harness.md` §7.3).

| Metric | Simple baseline | Agent solution | Change |
|---|---|---|---|
| Erasure-inventory F1 (test) | [arms.baseline.test.f1_mean] ± [arms.baseline.test.f1_std_seeds] | [arms.advanced.test.f1_mean] ± [arms.advanced.test.f1_std_seeds] | [comparison.test.f1_bootstrap.delta_mean] (95% CI [comparison.test.f1_bootstrap.ci95]) |
| Human time per task | [human_time.manual_minutes.mean] min (hand-labelling) | [human_time.machine_minutes.advanced] machine min + [human_time.gate_minutes.mean] min at the gate | −[human_time.manual_minutes.mean − human_time.gate_minutes.mean] min of a person's time (the machine minutes are unattended and are not subtracted from it) |
| Cost per task | $[arms.baseline.test.cost_usd_mean] | $[arms.advanced.test.cost_usd_mean] | $[arms.advanced.test.cost_usd_mean − arms.baseline.test.cost_usd_mean] |

False safe — the agent says a store is erased where the manifest says it is not — is the row that
matters more than F1, because it is the error that costs a founder a month:
[arms.baseline.test.false_safe_total] against [arms.advanced.test.false_safe_total] on test.

Both arms are billed for every `submit_record` attempt they spend, rejected ones included — five per
run in each arm (`00-contract.md` §Budgets, ADR 0003 §2) — because a user pays for retries. Cost per
run is the sum over the trace's `step` lines at list prices, with nothing netted out
(ADR 0003 §Consequences; `docs/judging/requirements-matrix.md` D2g).

Dev, and the secondary rows (pass, pass^3, regressions, unverified, bad citations, turns, tool
calls): `results/metrics.json` via `make report`. Runs: [identity_check.success] success +
[identity_check.failure] failure = [identity_check.n]; failures ship in `traces/failures/`.

Statistics: exact McNemar on the binary pass row, majority of three runs per case, dev
p = [comparison.dev.mcnemar.p_exact] and test p = [comparison.test.mcnemar.p_exact]. With five test
cases the smallest attainable two-sided p is 0.0625, so the test split cannot reach 0.05 and the
number is reported for shape. F1 carries a paired bootstrap 95% interval over cases
([comparison.test.f1_bootstrap.ci95]). This model exposes no temperature and no seed (ADR 0003 §2).

The gate approves in every scored run (`--approve auto`, `by: "simulated"`), so none of the measured
difference comes from a human intervening; it is the verifier's (`05-eval-harness.md` §7.1).

## Improvement changelog

[CHANGELOG_EVAL.md](CHANGELOG_EVAL.md): one row per experiment in the official four columns, with
the evidence that drove the next decision, removed experiments included. End to end, test F1 went
[arms.baseline.test.f1_mean] → [arms.advanced.test.f1_mean] and false safes
[arms.baseline.test.false_safe_total] → [arms.advanced.test.false_safe_total]; the largest single
contributor was [WRITE: the row named in CHANGELOG_EVAL.md's Final cell, copied from it].

## What existed before the competition

This repository was created after kickoff on 2026-08-28 15:00 UTC. Nothing in it predates that except:

- The tools: Claude Code (the coding agent that wrote most of the code; sessions rendered at
  `traces/build-trajectory.html`), the `claude-opus-5` model both arms call, Python 3.12, uv, the
  `anthropic` SDK, `pyyaml`, `jsonschema`, `pytest`, `claude-code-log` 1.5.0, `gitleaks`, Docker.
- Four open-source repositories vendored as eval cases at pinned SHAs, each keeping its upstream
  LICENSE and a `SOURCE.md` with url, sha, licence, date and what was stripped:
  `fastapi/full-stack-fastapi-template` @ `486f054` (MIT), `flaskbb/flaskbb` @ `fc64c74` (BSD-3),
  `pinry/pinry` @ `05476b1` (BSD-2), `miguelgrinberg/microblog` @ `a975ef6` (MIT); `evals/CASES.md`.
- Third-party text quoted rather than written: verbatim article and recital text of Reg. (EU)
  2016/679, 2024/1689 and 2026/1744 under `docs/research/sources/`, each file carrying its retrieval
  URL and date; the competition's own problem statement at `docs/problem/problem-statement.pdf`.

Cases S01–S10 are generated from the YAML specs in `evals/fixtures/specs/`. No pre-existing prompt
library, agent framework or rule set was carried in.

## Prior art

Bearer classifies personal data across 122 data types and calls its own output "RoPA **input**";
there is no deletion, erasure or retention concept in the 28 substantive pages of its documentation,
whose rendered text was grepped in full, nor in the slugs of the remaining 846 recipe and rule URLs
(`docs/research/prior-art.md` §0, §1 [S6][S1][S8][S8b]). Privado detects 110+ data elements and
scores `s3.delete_object` as evidence that data *arrived* at S3, the inverse of an erasure check
(§2 [S10][S13]). Fides executes real erasure, from a YAML declaration a human writes rather than
from the code (§3 [S17][S18]). Nothing found produces
an erasure-path table from application source: per store, reaches or does not, path cited (§7).

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

[Q4: no LICENSE file exists yet. micro1 owns the submission under the hackathon terms; whether this
also ships under MIT or Apache-2.0 is the author's call — .vault/QUESTIONS.md]

## Agent trajectories

`traces/` holds one JSONL trace per run, both arms, failures included. Four are worth opening:

- `traces/advanced/S10-s1.jsonl` — the rejection and the revision on the hard case.
- `traces/baseline/S10-s1.jsonl` — the same repository, no verifier: the false safe, unedited.
- `traces/advanced/S05-s1.jsonl` — the completeness guard adding a store the model had not listed.
- `traces/advanced/R04-s1.jsonl` — a real repository where the honest answer is that no deletion
  feature exists.

`traces/failures/` holds every failed run with a one-line diagnosis.
`traces/build-trajectory.html` is the rendered transcript of the Claude Code sessions that built
this repository (`make traces`, author-only; the HTML is committed).

## Main failure mode and hot take

[WRITE: the chosen candidate's one-sentence lesson, copied verbatim from HOT_TAKE.md §2 so the two
cannot drift.] The failure this project actually hit, its trace under `traces/failures/`, the fix and
the residual risk accepted: [HOT_TAKE.md](HOT_TAKE.md).
```

### Notes on the README block

- The results table is the PDF's own three rows (`problem-statement.txt` p.4) and nothing else;
  everything secondary sits below it or in `metrics.json` (`05-eval-harness.md` §7.2).
- The human-time row deliberately does not sum machine minutes and gate minutes into one number.
  `05-eval-harness.md` §9 is explicit that they are different quantities and that the manual
  comparator is hand-labelling under the CASES.md protocol.
- The Deutsche Wohnen fine is **not** in the block. It is the most quotable enforcement story in the
  research (an archive system with no facility to remove data) and it is contested: the Kammergericht
  referred to the CJEU and C-807/21 was decided 5 December 2023 with the fine still under challenge
  (`gdpr-sources.md` §4 [S14][S15]). A judge who knows the case and reads it stated flatly stops
  trusting the rest. Brico Privé and Foodinho carry the paragraph without that risk.
- "Erasure-inventory F1" is the metric's name in the table because `(store, field, reaches_erasure)`
  does not fit in a cell. `evals/CASES.md` §Primary metric is the definition and the README links it.
- D1c's ordering (user → bottleneck → value → changelog → failure mode → hot take) holds for the
  sections the PDF names; five sections the PDF does not name sit between the changelog and the hot
  take. Licence was moved above "Agent trajectories" so that D1f's "final section" reading is
  literally true rather than nearly true.

---

## 2. `REPRODUCE.md` — the delta

The current file is the right skeleton with six holes. Below is each section that changes, as a
paste-ready block. Sections not listed here stay as they are.

### 2.1 Setup and the replay path

Replaces everything from "## Setup" to the end of "## Reproduce the results (no API key)".

````markdown
## Setup

Requirements: git, and [uv](https://docs.astral.sh/uv/) (or Docker — see below). uv installs
Python 3.12 itself; nothing else is needed and no API key is needed for the path below.

```
git clone <repo-url>
cd <repo>
make setup     # uv sync --locked; fails loudly if the lockfile is stale
make smoke     # under 60 s: interpreter version, imports, trace validation over the committed traces
```

`make smoke` runs `evals/harness/trace_check.py` over `traces/`, so a broken trace fails the wiring
check rather than surfacing later as a missing deliverable.

## Reproduce the results (no API key)

```
make eval-replay
```

It replays every recorded API response from `evals/cache/`, re-scores all [identity_check.n] runs,
regenerates `results/metrics.json` and then runs `git diff --exit-code` against the committed file.
A cache miss fails loudly rather than falling back to a live call (ADR 0003 §6).

Expected runtime: [timing.replay.json — under a minute on the reference machine; state the machine].
Expected final lines, verbatim:

```
[identity_check.n] runs: [identity_check.success] success, [identity_check.failure] failure  (success + failure == n: ok)
dev   baseline F1 [arms.baseline.dev.f1_mean] ± [..f1_std_seeds] | advanced F1 [arms.advanced.dev.f1_mean] ± [..f1_std_seeds] | false safe [arms.baseline.dev.false_safe_total] → [arms.advanced.dev.false_safe_total]
test  baseline F1 [arms.baseline.test.f1_mean] ± [..f1_std_seeds] | advanced F1 [arms.advanced.test.f1_mean] ± [..f1_std_seeds] | false safe [arms.baseline.test.false_safe_total] → [arms.advanced.test.false_safe_total]
McNemar (pass, majority of 3): dev b=[comparison.dev.mcnemar.b] c=[comparison.dev.mcnemar.c] p=[comparison.dev.mcnemar.p_exact] | test b=[comparison.test.mcnemar.b] c=[comparison.test.mcnemar.c] p=[comparison.test.mcnemar.p_exact]
wrote results/metrics.json
metrics.json unchanged
```

The last two lines are the reproducibility claim. `metrics.json unchanged` means the replay produced
the committed numbers byte for byte.
````

The block's shape is fixed by `05-eval-harness.md` §10, which also lists what is excluded from
`metrics.json` so the diff can pass on another machine: `generated_at` and `git_sha` written as
`null` under `ART30_REPRODUCIBLE=1`, wall-clock and timestamps absent entirely, every float rounded
to six places. `REPRODUCE.md` states that list in one sentence rather than reproducing the table.

### 2.2 Live runs

````markdown
## Live runs (API key required)

```
cp .env.example .env   # add ANTHROPIC_API_KEY
make baseline          # baseline arm over the dev split, 3 runs per case
make advanced          # advanced arm over the dev split, 3 runs per case
make eval              # the full sweep, both arms, dev + test
```

Model: `claude-opus-5`, adaptive thinking with summarised display, `output_config.effort: high`,
`max_tokens` 32000, streamed (ADR 0004 P-11, amending ADR 0003 §1). This model accepts no
`temperature`, `top_p` or `top_k` — the request is rejected with a 400 — and has no seed parameter
at all (ADR 0003 §2). "Seeds" `s1`–`s3` are harness
labels, and the three runs per case measure sampling variance, reported as mean ± std. A live sweep
therefore does not reproduce the committed numbers exactly; `make eval-replay` does, and that is the
path a judge should use.

Approximate live cost for one full sweep: [timing.json + metrics.json — the measured figure from the
recorded sweep; before it exists, docs/spec/01-architecture.md §10 estimates $80–$176]. Approximate
wall clock: [timing.json wall_s_mean summed; 01-architecture.md §10 estimates ≈107 min at
concurrency 4]. A single advanced run on a real repository is [per_case cost_usd].
````

Two things this section must not do. It must not quote `evals/CASES.md`'s original "$20–40" and
"10–20 min": both are superseded by `01-architecture.md` §10 and by the CASES.md errata, and the
10–20 minutes holds only for replay. And it must not promise determinism from the live path.

### 2.3 Data

```markdown
## Data

Two kinds, both in the repository. Neither contains any user's data: the synthetic cases carry
schemas, field names and planted bugs; the real cases are public open-source trees at pinned SHAs,
stripped of `.git`, tests and docs, keeping their upstream LICENSE and copyright notice.

**Synthetic cases S01–S10.** Generated by `evals/fixtures/gen.py` from the YAML specs in
`evals/fixtures/specs/`, committed under `evals/fixtures/synthetic/`. One spec produces both the
repository and its manifest, so the answer key cannot drift from the fixture. `make fixtures`
regenerates them and must leave a clean `git diff`. They contain schemas, field names and planted
bugs; no data about any person.

**Real cases R01–R04.** Four open-source repositories vendored at pinned SHAs under
`evals/fixtures/real/`, each with its upstream LICENSE file and a `SOURCE.md` recording the url,
sha, licence, vendoring date and what was stripped (`.git`, tests, docs):

| Case | Repository | SHA | Licence |
|---|---|---|---|
| R01 | `fastapi/full-stack-fastapi-template` | `486f054` | MIT |
| R02 | `flaskbb/flaskbb` | `fc64c74` | BSD-3-Clause |
| R03 | `pinry/pinry` | `05476b1` | BSD-2-Clause |
| R04 | `miguelgrinberg/microblog` | `a975ef6` | MIT |

Ground truth for the real cases is hand-labelled under the protocol in `evals/CASES.md`, with the
timer running, and committed before the first agent run on that repository. The "human time per
task" row is six cases, not four: R01–R04 plus S03 and S05, which the author blind-labelled before
seeing their manifests so the row does not change denominator between dev and test
(`05-eval-harness.md` §9). No network access and no GitHub API call happens at evaluation time.
```

### 2.4 Which numbers came from where

```markdown
## Which numbers came from where

| Number | Produced by | Committed at |
|---|---|---|
| Everything in `results/metrics.json` | `make eval` (live, recorded) then `make report`; reproduced byte-for-byte by `make eval-replay` | [commit sha] |
| Wall clock, machine minutes | the recorded live sweep, `results/timing.json` — never regenerated by replay | [commit sha] |
| Gate review minutes | `make gate-timing`, one `--approve ask` replay pass, hand-recorded in `results/gate-timing.yaml` | [commit sha] |
| Hand-labelling minutes | the CASES.md protocol, recorded in each real manifest's header as `labelling_minutes`, and for S03 and S05 in `evals/fixtures/manifests/<case>.labelling.yaml` | before the first run on that case |
| Every number in README and CHANGELOG_EVAL | pasted from the files above, never typed | — |

Live sweeps against the test split are logged in `results/test-runs.log`, a chained ledger: each
line carries the sha256 of the previous line and the runner verifies the chain before appending.
Two live test sweeps were budgeted (baseline, final) and the log shows what was spent. A direct
`art30 scan` at a test fixture refuses with exit 2 unless `ART30_UNLOCK_TEST=1` is in the
environment; replay is exempt (`05-eval-harness.md` §5.4).

Gate review minutes come from one dedicated `--approve ask` replay pass, not from a live run: the
record is identical, but the reviewer already knows the case, so the number is a lower bound
(`05-eval-harness.md` §9 and §Open risks).
```

### 2.5 Docker and versions

````markdown
## Docker path

For a machine without uv:

```
docker build -t art30 .
docker run --rm art30 make eval-replay
```

The image is `python:3.12-slim` with uv [pinned version/digest] copied in, `uv sync --locked` at
build time, and `make eval-replay` as the default command.

## Versions

Python 3.12 (`.python-version`, asserted by `make smoke`). Runtime dependencies and their resolved
versions are in `uv.lock`, which `make setup` installs with `--locked`: `anthropic`, `pyyaml`,
`jsonschema`; `pytest` in the dev group. The verifier uses stdlib `ast` and no parser dependency.
Model `claude-opus-5` as configured above.
````

---

## 3. `HOT_TAKE.md` — three candidate framings

The file has two sections and the PDF scores the second: "turns an observed failure mode into a
practical lesson for building more reliable agents" (`problem-statement.txt` p.5, 5 points).

**The candidates below are not ranked by how good the sentence sounds. They are ranked by whether
the evidence for them will exist on Sunday night.** Do not pick one now. Run the eval, read the
traces, then take the candidate whose evidence column is full. If two are full, take the one whose
failure the *advanced arm* also made at least once: a hot take about a failure only the baseline
made is a hot take about prompting, not about building reliable agents.

### Candidate A — a deletion function that exists is not a deletion function that is reached

*Case:* S10 (test), fifteen files (`fixture-generator.md` §3.3). *Rules:* R26 (unresolved or absent
caller, never a guess), R12 (the static analogue: a `signals.py` nothing imports), verifier unit
test 38 `test_s10_dead_helper` (`03-verifier.md` §test plan).

The shape: `close_account` writes `deleted_at` and returns. `cleanup_user_files()` is defined at
`storage.py:41`, calls `s3.delete_object`, and has no caller anywhere in the repository. The
docstring on `close_account` says the route "removes all user data including files". A reader who
greps for `delete` finds the function and believes the docstring. The call graph does not.

The lesson, if the runs support it: an agent's claim is only as good as the question the checker
asks, and "does this symbol exist" is the wrong question for every claim of the form "X happens
when Y". Existence is cheap to check and nearly always true; reachability is the property anybody
actually cares about, and it is the one a language model is worst at holding in its head while
reading fifteen files.

*Evidence it needs:* the baseline trace `traces/baseline/S10-s1.jsonl` submitting
`uploads: erased` with `storage.py:47` as its evidence, at least once; the advanced trace
`traces/advanced/S10-s1.jsonl` carrying the rejection and the revised verdict; both counted in
`arms.*.test.false_safe_total`. Ideally also one *advanced* run that made the same mistake in its
first submission, which is what makes the take about the loop rather than about the model.

*Why it is currently the strongest.* It is a scored test case, both arms run it three times, the
trace pair is committed and legible in a minute, the demo already turns on this exact beat
(`docs/demo-script.md` 0:40–1:00), and the failure is the author's own lived bug (ADR 0002
§Context). Every other candidate needs evidence that may not exist.

*What would sink it:* the baseline getting S10 right in all three runs. Then there is no observed
failure, only a designed one, and the take has to move.

### Candidate B — `DB_CASCADE` silently disables every signal-based cleanup

*Case:* S06 (dev) carries the `DB_CASCADE` edge; the false-safe half is verifier unit test 6,
`test_r04_db_cascade_kills_cleanup`. *Rules:* R4, R8, R10 (`framework-behaviour.md` §6, §4.4(b)).

Django 6.1 added `on_delete=DB_CASCADE`, which pushes the cascade into the database and, in Django's
own words, means `pre_delete` and `post_delete` "won't be sent" (`framework-behaviour.md` §1 [S1]).
A team adopting it for performance silently disables every file cleanup wired to a delete signal,
django-cleanup included. The rows go, the files stay, and the code that used to delete them still
reads as correct. Reproduced by execution: `Avatar rows after DB_CASCADE: 0`, the sender absent from
the signal list, `file exists after delete: True` (§4.4(b)).

The lesson, if the evidence exists: the dangerous changes to a system are the ones that keep every
line of the old code visible while removing the mechanism that made it run. A checker that reads
what is written cannot catch it; only a checker that models the framework's behaviour can.

*Evidence it needs:* a run — either arm — that claims a file store is erased on the strength of a
receiver that `DB_CASCADE` prevents from firing. **The eval as designed cannot supply this.**
`fixture-generator.md` §9 records the decision: S06 carries `DB_CASCADE` as a row-propagation edge
only, and its signal-killing half stays in the verifier's unit tests so S09 keeps one planted
variable. So this take rests on a unit test unless a real repository (R03 is Django with
`post_delete` receivers) happens to show the shape. State that honestly or drop it.

*Rank:* second. Strong story, thin evidence, and a judge who checks will find the evidence is a unit
test rather than a measured failure.

### Candidate C — "we deleted it" on a versioned bucket means a delete marker

*Case:* none, currently. *Rule:* R13 (`framework-behaviour.md` §6, `03-verifier.md` R13, unit tests
25, 26 and 60).

S3's own documentation says that a delete against a versioned bucket without a `versionId` leaves
the object: the service "behaves as though the object has been deleted (even though it has not been
erased)" (`framework-behaviour.md` §6 R13 [S22]). The code calls `delete_object`, the log says 204,
the bytes are still readable at the previous version. R13 therefore searches for a versioning
declaration in Terraform, CloudFormation, YAML and in Python bootstrap code read as text, and
downgrades the verdict to `not_erased` when it finds one and no `versionId` is passed.

The lesson, if it lands: the boundary where an agent's static reading ends is the boundary where its
confidence should end too, and a verifier that only reads the language the application is written in
will confidently pass a claim that infrastructure falsifies.

*Evidence it needs:* a case where versioning is declared. Every synthetic spec that has an object
store sets `versioning_declared: false` (`S04.yaml`, `S08.yaml`, `S10.yaml`), so the qualifier never
fires on the scored set. Unless a real repository declares versioning, the evidence is unit tests 25
and 60 plus a documentation quote.

*Rank:* third as a hot take, first as a paragraph in the "what the verifier cannot see" list. It is
an honest limitation, well sourced, and it is not an observed failure.

### The meta-lesson, available regardless of which candidate wins

Usable as the second half of the hot take under any of A, B or C, because its evidence is the
repository itself rather than a run:

> The model wrote nearly all of the code. The engineering that decided the outcome was the harness
> around it: a verifier the model cannot talk past, an eval whose ground truth is generated from the
> same spec as the fixture, a test split with a chained ledger that makes a third live sweep visible,
> and a request hash that makes a replay a proof rather than a claim. Two decision records exist for
> the same reason, which is that assumptions got written down before anyone checked them. ADR 0003
> threw out a planned retry-with-temperature ramp the API does not accept at all. ADR 0004 fixed
> sixteen places where the interface contract named something it had not defined or contradicted a
> specified code path — `max_tokens`, the `stop_condition` enum, `submits` versus `verify_rounds`,
> `path_exists`'s signature. Every one of those was found by an agent reading another agent's
> document, not by running code. Generating the system was the cheap part. Being able to tell
> whether it worked was not.

*Evidence:* `.vault/adr/0003-runtime-and-api-decisions.md`, `.vault/adr/0004-contract-amendments-after-spec-pass.md`,
`traces/build-trajectory.html`, the commit history.

*The risk to watch, and to name if it happens:* evaluation drift. An iteration that moves F1 by
changing what the scorer counts rather than what the agent does. The defences are in place
(manifests committed before the first run on a case, dated errata that apply to both arms, the
test-split lock) and if one of them catches something, that catch is a better hot take than any of
A, B or C, because it is a failure of the measurement rather than of the model.

### Section 1 of the file: the failure we hit

Cannot be drafted. It is filled from `traces/failures/` after the runs, and the file's shape is:

```markdown
## The failure mode we hit

[WRITE: what failed, in one sentence. Then: the trace ID under traces/failures/, the stop_condition
on its run_end line, what the transcript showed at the step it went wrong, the fix, and the residual
risk accepted. If the fix was a changelog row, link the row.]
```

Do not write "we hit no failures". `01-architecture.md` §9 lists twelve stop conditions and three
failures are already assumed in the identity check example. If the sweep genuinely produces none,
the honest section describes the worst *accepted* run instead: the lowest-F1 advanced run on test,
with its trace, and why it was accepted rather than fixed.

---

## 4. Video outline — 3:00 to 3:30

Deliverable 03 (`problem-statement.txt` p.7): problem and simple baseline first, then one realistic
execution start to finish, the final comparison, the changelog briefly, the change that contributed
most, and one experiment that was removed. All six appear below. Recording tool is Q2.

The middle 90 seconds are `docs/demo-script.md`, embedded verbatim in §4.2 with a +1:00 offset. That
file is the source; if the two ever disagree, the demo script wins, and `07-ui.md` §9 wins over both
on what the terminal actually prints.

### 4.1 Shot list

| Time | On screen | Voice (one sentence each) |
|---|---|---|
| 0:00–0:12 | `evals/fixtures/synthetic/S10/api/account.py` open at `close_account`, docstring visible: "Close the account and remove all user data, including uploaded files." | "This is a synthetic case built to the shape of a bug I shipped, and its docstring is wrong." |
| 0:12–0:24 | Split: the docstring left, `storage.py:41` `cleanup_user_files` right, then a `grep -rn cleanup_user_files` returning one line — the definition | "The function that deletes the uploaded files exists. Nothing calls it." |
| 0:24–0:40 | The EDPB quote on a plain slide, one line: "the absence of a structured process to map the relevant personal data", with the citation `EDPB CEF 2026, right to erasure`, and below it a second line held silent for the rest of the video to point back to: `CNIL SAN-2021-008, 14 June 2021 — EUR 300,000 for Arts. 5-1-e), 13, 17, 32` (`gdpr-sources.md` §4 [S18]) | "A founder has to hand a record of processing to a lawyer or an authority, and when the EDPB asked 764 controllers how they handle erasure requests, some of them did not report using that record at all." |
| 0:40–1:00 | [CONDITIONAL on a baseline S10 run that actually returns `uploads · ERASED` — check `arms.baseline.test.false_safe_cases` before recording; if S10 is absent, substitute the baseline case with the most false safes and re-word the line.] `ART30_UNLOCK_TEST=1 art30 scan evals/fixtures/synthetic/S10 --arm baseline --mode replay` tail (`07-ui.md` §5), then `record.md` section D with `uploads · ERASED` on screen. Replay, like the advanced shot at 1:10, because a live scan of a test fixture on recording day spends test-split exposure the two-sweep budget has not allowed for (`05-eval-harness.md` §5.4) | "Here is the baseline: same model, same tools, same instructions, no verifier. It read the helper, believed the docstring, and signed off on files that are still there." |
| 1:00–2:30 | **the execution segment, verbatim from `docs/demo-script.md`** (§4.2) | as scripted |
| 2:30–2:50 | `make report` output, the three-row table, dev and test | "Same fourteen cases, three runs each, both arms. F1 [arms.baseline.test.f1_mean] to [arms.advanced.test.f1_mean] on the test split, and false safes [arms.baseline.test.false_safe_total] to [arms.advanced.test.false_safe_total] — that second row is the one a regulator has already priced." The pricing is the CNIL line put on screen at 0:24; §4.3 keeps this shot to the report output and nothing else, so the citation is not repeated here |
| 2:50–3:08 | The whole `CHANGELOG_EVAL.md` table for four seconds, then scrolled to the row that moved the number most, its Evidence cell highlighted | "One row per change, and every Evidence cell in them was computed by `make report --diff`. [WRITE: the change that contributed most, from a real row — name it and read its evidence cell.]" |
| 3:08–3:22 | The removed row, its Decision cell highlighted | "[WRITE: one experiment removed and what it taught — from a real row.]" |
| 3:22–3:30 | Terminal: `make eval-replay` final two lines, `metrics.json unchanged` | "Every number on screen reproduces from recorded responses with no API key." |

Rules for the take. Never say "compliant". Never speak a number that differs from the one visible on
screen (`07-ui.md` §9: the run tail prints its own seconds and cost). Numbers that are not on screen
— the gate minutes at 2:15 — are read from `results/metrics.json` or cut. A shot marked CONDITIONAL
is checked against the artifact it names before the camera runs, and the substitution it describes is
made before recording rather than discovered during it. Do not show the baseline's wrong answer again
after 1:00 — it belongs at 0:40 and in the comparison, not in the execution segment. Do not say the
AI Act requires anything today.

The middle 90 seconds are fixed. The shot list totals 210 s. If the take needs to come in at 3:00
rather than 3:30, thirty seconds have to go: 0:12–0:24 (12 s, the grep, which the verifier repeats at
1:40), 3:22–3:30 (8 s, the replay line, which is the first line of the README) and 10 s off 0:24–0:40
by showing the EDPB slide without reading the second clause. That lands at 3:00 with the 90-second
segment intact. Never cut the removed-experiment shot: the PDF names it.

### 4.2 The embedded segment (verbatim from `docs/demo-script.md`, offset +1:00)

| Video time | Script time | On screen | Voice |
|---|---|---|---|
| 1:00–1:10 | 0:00–0:10 | Repo tree of the case: `models.py`, `storage.py`, `billing.py`, `jobs/purge.py`, `jobs/backup.py`, `api/account.py` | "A small SaaS: users, avatar uploads in object storage, a payment customer, a nightly purge job, a nightly backup. Two questions: what personal data does it hold, and when someone closes their account, is it gone?" |
| 1:10–1:25 | 0:10–0:25 | `ART30_UNLOCK_TEST=1 make run CASE=S10 MODE=replay OUT=results/.demo` (`08-plan.md`, Monday 09:45) — tool calls scroll: `list_tree`, `read_file`, `grep`. The step counter is the first column of every line. | "The agent reads the code the way you would. It doesn't run anything. Every read is a tool call in the trace." |
| 1:25–1:40 | 0:25–0:40 | `record.md` section A in the right-hand pane: the inventory, four stores, eleven fields, each with `file:line` | "Eleven fields across four stores. `original_filename` on the uploads store is flagged as free text that may contain personal data — the uploader's own file name, kept as object metadata. A grep would not have listed it." |
| 1:40–2:00 | 0:40–1:00 | The `[verify] attempt 1` block, exactly as the CLI prints it: `REJECT   uploads · erasure.verdict=erased` with the verifier's reason on the continuation lines — no path from entry point `close_account` (`api/account.py:12`) to any object-storage deletion primitive; `cleanup_user_files` (`storage.py:41`) is defined but has no callers. Then `attempt 2 … accepted`. | "Here's the moment. The first draft said uploads are deleted, because a cleanup function exists and the docstring says so. The verifier walked the call graph from `close_account` and found no path to it. The function is dead code. The claim is struck, the agent revises." |
| 2:00–2:15 | 1:00–1:15 | The `[gate]` block: risk HIGH, the entry point to confirm, the recipient kind to set, the legal cells listed as `requires human completion`. Type `y`. | "Before anything renders, a person approves. The legal columns are empty on purpose — the agent never writes a legal basis." |
| 2:15–2:30 | 1:15–1:30 | `record.html`, section D: the erasure table with one `NOT ERASED` row, every cell carrying `file:line`. Hover a citation → the line of code. | "Every line in this document points at a line of code. The red row is the bug I shipped in my own product and found a month later. Here it took [human_time.machine_minutes.advanced] machine minutes and [human_time.gate_minutes.mean] minutes of mine at the gate." |

Corrections carried from `07-ui.md` §9, which the narration must respect: the step counter is in the
first column on the left, S10 has eleven fields and four stores (not twelve and six), the `notes`
column with the phone-number comment is case S07 and not S10, and the verifier's on-screen string is
`REJECT   uploads · erasure.verdict=erased` with the reason on continuation lines.

Two changes this document makes to the embedded segment, both owed back to `docs/demo-script.md`,
which no spec document may edit (`docs/spec/README.md`). They are raised in §8 below.

First, the two numbers at 1:15–1:30 are slots: both are read from `results/metrics.json` after the
recorded sweep, and if either is unmeasured at recording time the clause is cut, not rounded.
`07-ui.md` §9's `209s` is a worked example rather than a measured run, so "three and a half minutes"
is not a number that may be spoken. Second, `ART30_UNLOCK_TEST=1` is in the 1:10 command because S10
is a test case: the `run` recipe passes `CASE` straight into `art30 scan
evals/fixtures/synthetic/$(CASE)`, and `art30/cli.py` exits 2 on a direct scan of a test fixture
unless the variable is set (`05-eval-harness.md` §5.4). `08-plan.md`'s Monday 09:45–11:45 row already
writes the shot that way and adds the rest of it: `ART30_UNLOCK_TEST=1 make run CASE=S10 MODE=replay
OUT=results/.demo`, a replay of the Sweep C run, with `traces/advanced/S10-s1.jsonl` copied aside
before the first take. §5.4 exempts replay from the refusal, so on that command the variable is
belt-and-braces rather than load-bearing; it is in the shot because the plan puts it there and
because a take that falls back to a live scan then still runs. That is the command to show.

### 4.3 The comparison shot

One screen, `make report --markdown` output, dev and test tables side by side, nothing else visible.
Numbers pasted nowhere: the shot is the terminal. If the table does not fit legibly, show test only
and say "dev is in the README", rather than shrinking the font.

### 4.4 Changelog shots — candidates for the two named rows

Both must be chosen from rows that exist in `CHANGELOG_EVAL.md` when the video is recorded. The
candidates the specs already point at:

*The change that contributed most* — most likely the verifier itself (iteration 1), which is the
whole design claim; if a later row moves the number more, use that one instead. Others in play: the
completeness guard (`missing_stores`, `00-contract.md` §Verifier contract), R9's `sender=` comparison
(`05-eval-harness.md` §8 uses it as the worked example), R13's versioning search over Python read as
text (`03-verifier.md` §1.1).

*One removed experiment* — the candidates, in order of how likely they are to actually be run and
removed: `is_error: false` on a rejected submit (`02-agent-loop.md` decision 6 and open risk 2 flag
it as a one-variable experiment), the nudge budget (`02-agent-loop.md` §1, three no-tool-call turns
end the run), the AI Act Art. 50 rule set (`.vault/NON-GOALS.md` commits to removing it and keeping
the row if it does not move a metric), and a feedback-wording change to the `expected` strings
(`10-instructions.md` §feedback strings).

Say what the removed experiment taught, not that it was removed. The PDF asks for the lesson.

---

## 5. `CHANGELOG_EVAL.md` — the baseline row and the planned rows

The official four columns (`problem-statement.txt` p.3). Row discipline from AGENTS.md: one change
per row, dev numbers with the paired interval, cost delta, regressions reported even at zero, one
trace ID actually read, one sentence on what that transcript showed.

**Everything below the Baseline row is marked `PLANNED — not yet run`, and that marker is deleted
only when the row's Evidence cell holds real numbers.** A planned row that never runs is deleted, not
left in with empty brackets. Order will change: the rows run in whatever order the evidence demands.

```markdown
# Improvement changelog

The story of how the solution evolved, in the official format. One entry per meaningful experiment,
measured with the same evaluation wherever possible. Removed experiments stay in — they taught us
something.

| Stage | What you tried and why | Evidence | Decision / learning |
|---|---|---|---|
| Baseline | The skill: `claude-opus-5`, the four read-only tools, the shared instruction text, five `submit_record` attempts, schema validation only, no verifier and no gate (ADR 0003 §4). This is what a good `SKILL.md` in Claude Code or Codex gets you, and it is the thing the closed loop has to beat. | dev F1 [arms.baseline.dev.f1_mean] ± [arms.baseline.dev.f1_std_seeds]; false safe [arms.baseline.dev.false_safe_total] over [arms.baseline.dev.n_runs] runs; pass [arms.baseline.dev.pass_runs]; cost/run $[arms.baseline.dev.cost_usd_mean]; trace `traces/baseline/S10-s1.jsonl` | Established the starting point. [WRITE: one sentence on what the S10 baseline transcript actually showed at the submit step.] |
| Iteration 1 — verifier on `PLANNED` | Turn on the deterministic check inside `submit_record`: every erasure claim must survive `path_exists(entry, primitive)` over the `ast` call graph, and a failed claim returns the feedback object with its reason and `expected` (`00-contract.md` §Feedback object). One variable: nothing else changes, the prompt bytes included. | will read `arms.advanced.dev.f1_mean` and `f1_std_seeds`, `false_safe_total`, `unverified_mean`, `cost_usd_mean`, `turns_mean`, `comparison.dev.f1_bootstrap.delta_mean` and `ci95`; regressions from the previous `metrics.json`; trace `traces/advanced/S10-s1.jsonl` | |
| Iteration 2 — completeness guard `PLANNED` | The verifier's own scan finds stores with personal-data-looking fields that the record omits and returns them as `missing_stores`. Aimed at S05 and S08, where the failure is silence rather than a wrong claim. | will read `arms.advanced.dev.recall_mean`, `f1_mean`, `false_safe_total`, `unverified_mean`, `cost_usd_mean`; regressions; trace `traces/advanced/S05-s1.jsonl` | |
| Iteration 3 — `sender=` on delete receivers `PLANNED` | Receivers were matched by signal only, so any connected receiver read as file cleanup for every model. Add the `sender=` comparison (R9, `framework-behaviour.md` §6), developed against a `tests/verify/` fixture rather than a case, because its failure shape lives on a test-split case (S09). | will read `arms.advanced.dev.f1_mean` with the paired bootstrap interval, `false_safe_total`, `cost_usd_mean`, regressions; trace `traces/advanced/S06-s2.jsonl` | |
| Iteration 4 — S3 versioning search `PLANNED` | R13: search Terraform, CloudFormation, YAML **and** Python bootstrap code read as text for a versioning declaration, and downgrade an object-store delete that passes no `VersionId` (`03-verifier.md` §1.1). Guards a false safe the language-only scan cannot see. | will read `false_safe_total`, `invalid_verdict_for_kind_total`, `f1_mean`, `citation_bad_total`; unit tests 25, 26, 60; regressions | |
| Iteration 5 — feedback wording `PLANNED` | Every rejection list item carries `expected` (ADR 0004). Test whether saying what the record should contain instead reduces attempts spent per accepted record. | will read `turns_mean`, `tool_calls_mean`, `verify_rounds` from the traces, `cost_usd_mean`, `f1_mean` unchanged-or-better; regressions | |
| Iteration 6 — `is_error: false` on rejection `PLANNED` | A rejected submit currently returns `is_error: true` so every rejection is greppable in the trace. `02-agent-loop.md` open risk 2 says this may push the model to re-run the tool rather than revise the record. One-variable flip. | will read `verify_rounds` and repeated-identical-submit count from the traces, `f1_mean`, `false_safe_total`, `cost_usd_mean` | [expected outcome: kept or removed on the evidence; if removed, the row stays with what it taught] |
| Iteration 7 — AI Act Art. 50 rule set `PLANNED, GATED` | The same `path_exists(call_site, write, must_pass_through=approval)` verifier over a second rule set, on two or three planted fixtures (`ai-act-sources.md` §5). Gated behind a locked GDPR test number (`.vault/NON-GOALS.md`). | will read the planted-case verdicts and whether any GDPR metric moves; if it cannot be evaluated or moves nothing, it is removed | [if removed: the row stays and says the extension was cut for lack of a measurable effect, which is the honest result] |
| Final | [WRITE: the combination that shipped, and the single largest contributor named from the rows above] | test F1 [arms.baseline.test.f1_mean] → [arms.advanced.test.f1_mean]; false safe [arms.baseline.test.false_safe_total] → [arms.advanced.test.false_safe_total]; McNemar p [comparison.test.mcnemar.p_exact]; `identity_check` [identity_check.success]+[identity_check.failure]=[identity_check.n] | Identified the main contribution |

<!-- Row discipline (AGENTS.md): one change per row · dev-set numbers with paired SE ·
     cost delta · regressions (report even at zero) · one trace ID actually read ·
     one sentence on what the transcript showed. Commit each row as docs(changelog). -->
```

Two constraints on this table that are easy to break under time pressure.

`make report --diff results/metrics.prev.json results/metrics.json --stage "..."` computes the whole
Evidence cell (`05-eval-harness.md` §8). Use it. A hand-typed evidence cell is the one place a number
can drift away from the artifact it claims to come from.

No row may be developed by reading a test-case trace. Where a rule's failure shape only exists on a
test case — S09's decoy receiver, S08's absent entry point — the fixture that drives the iteration is
a `tests/verify/` fixture, and the row says so (`05-eval-harness.md` §5.4 and §8).

---

## 6. Q3 — proposed sentence

`.vault/QUESTIONS.md` Q3 asks how much of the lived bug story goes in the README. Proposed answer,
for the author to confirm or tighten. One sentence in the README, one clause in the video at 2:15.

> **README, closing the "Who has this problem?" section:**
> "I have been that person: in a product I run, the hand-written record had two statements reversed,
> and a soft delete never reached object storage for a month before anyone noticed."
>
> **Video, 2:15–2:30 (already in `docs/demo-script.md`):**
> "The red row is the bug I shipped in my own product and found a month later."

What the wording deliberately withholds: the product's name, the client, the stack, the dates, the
scale, the industry. "A product I run" is the whole disclosure (QUESTIONS.md Q3, AGENTS.md
§Competition facts: nothing proprietary enters this repo, and micro1 may train on the submission).

What it buys: the "Problem & User Value" row (15 points) asks who experiences the bottleneck, and a
first-person answer with a specific failure shape is worth more than a persona sketch. The same
sentence also explains why S10 is the hard case and why the false-safe row exists as a separate
must-be-zero metric rather than being folded into F1.

Assumption if Q3 is not answered before the README is written: use the sentence above as drafted. It
already contains no proprietary detail, so the risk of shipping it unconfirmed is low, and the risk
of dropping it is a weaker answer to question 01.

---

## 7. Sentences we must never write

Each row: the sentence, why it is forbidden, and the source that settles it. This list binds
`README.md`, `REPRODUCE.md`, `HOT_TAKE.md`, `CHANGELOG_EVAL.md`, the video narration, and the
product's own rendered output.

**Legal conclusions**

| Never write | Why | Source |
|---|---|---|
| "This repository is GDPR compliant" / "compliant with Article 30" | The tool states no legal conclusion and the word is banned from the output by contract. Compliance depends on cells the tool leaves empty. | `00-contract.md` §Writing contract; `.vault/NON-GOALS.md`; AMBIGUITIES 8 |
| "This code violates Article 17" | A finding of breach is a legal determination. The tool reports that no call path exists and cites the line. | AMBIGUITIES 8; `gdpr-sources.md` §6.2 — an absent timer is evidence, not a finding of breach |
| "The legal basis here is consent" / "the purpose of this processing is marketing" | Purpose, legal basis and risk class are human-only cells, always. A wrong legal basis is the most harmful sentence this tool could produce. | AMBIGUITIES 8; ground rule 05; `00-contract.md` §Record vocabulary |
| "You are exempt under Article 30(5)" (or "you are not") | The derogation's conditions are alternatives and applying them to a controller is a legal judgement. State the text, stop. | `gdpr-sources.md` §6.10 [S9][S6]; anticipated-questions Q2 |
| "This is a transfer to a third country" from a region string | A region string says where a service was configured. Art. 30(1)(e) is a human cell; region hints render under a heading that says they are not a finding. | `00-contract.md` §Record vocabulary; `example-record-S10.md` §E |

**In-force claims**

| Never write | Why | Source |
|---|---|---|
| "The AI Act's high-risk obligations apply today" / "Annex III systems must now…" | Regulation (EU) 2026/1744 moved Chapter III Sections 1–3 for Annex III systems to 2 December 2027. They are not in force on the submission date. | `ai-act-sources.md` §1 [S2][S3] |
| "The AI Act was delayed, so nothing applies yet" | Art. 50 transparency has applied since 2 August 2026, GPAI obligations since August 2025, prohibitions since February 2025. The deferral is partial. | `ai-act-sources.md` §1 [S2][S4] |
| An AI Act row with no date stamp | The December 2027 date is a deferral, not a repeal, and a record produced now will be read after it lapses. | `ai-act-sources.md` §5.7 |
| "The 750-employee threshold means small companies are exempt" | That is a proposal in the fourth simplification Omnibus, not law. | `gdpr-sources.md` §6.10 [S20] |
| "Deutsche Wohnen was fined EUR 14.5m for having no way to delete data" (stated flat) | The fine was challenged, referred by the Kammergericht, and was still contested at the CJEU's 5 December 2023 judgment in C-807/21. Cite it as issued and under challenge, or leave it out. | `gdpr-sources.md` §4 [S14][S15] |
| "Brico Privé was fined EUR 500,000 for soft delete" | EUR 300,000 covered four GDPR breaches including Art. 17; EUR 200,000 was under French law that is not the GDPR. The round number overstates it. | `gdpr-sources.md` §4 [S18] |

**Absolute claims about prior art**

| Never write | Why | Source |
|---|---|---|
| "No tool generates an Art. 30 record from source code" | Privado Cloud does, today, free, from code scans, using a fine-tuned LLM. The true claim adds "with verification, and without a cloud upload". | `prior-art.md` §2, §7 [S10][S14] |
| "We find personal data better than Bearer" | Untested, and unlikely: Bearer ships 122 curated data types and heuristics tuned on tens of thousands of samples. Expect it to win on inventory recall. | `prior-art.md` §Honest weaknesses [S5][S6] |
| "Fides is dead" | It was archived on 2026-08-28, three weeks after its vendor launched a new commercial product. That is evidence about one vendor's open-source strategy, not about demand. | `prior-art.md` §3, §Honest weaknesses [S16][S36] |
| "Static analysis alone would solve this" | GDPR-Bench-Android's Formal-AST baseline scored 1.86% against 61.60% for the best LLM on line-level Accuracy@1. The design works because the verifier constrains the model, not because it replaces it. | `prior-art.md` §Honest weaknesses [S32] |

**Claims about our own results**

| Never write | Why | Source |
|---|---|---|
| "The results are deterministic" / "reproducible run to run" | No temperature, no seed, and the API documents that even at temperature 0 results are not fully deterministic. Replay is exact; a live re-run is not. | ADR 0003 §2; anticipated-questions Q23 [S8] |
| "The human gate improved the score" | Every scored run uses `--approve auto` and the gate never declines. The measured delta is the verifier's. | `05-eval-harness.md` §7.1; `06-traces.md` §5 |
| "The improvement is statistically significant" (on test) | With five test cases the smallest attainable two-sided exact-McNemar p is 0.0625. The test split cannot reach 0.05 by construction. | `05-eval-harness.md` §7.3 |
| "The agent found all the personal data in the repository" | Completeness is not knowable from a static Python read. Non-Python files, dynamic dispatch and unparsed sources render "unscanned" or `unverified`. | `.vault/NON-GOALS.md`; AMBIGUITIES 14; anticipated-questions Q21 |
| "The backup is erased" / "backups are out of scope" | Backup stores render `governed_by_retention` or `no_schedule_evidenced`, both counting as not reaching erasure. They are in the inventory and out of the erasure verdict. | AMBIGUITIES 6; `gdpr-sources.md` §3.1 [S10][S11] |
| "The email was anonymised, so it is erased" where the code hashes it | Hashing, tokenising, UUID substitution and masking are pseudonymisation, which is reversible with additional information and is the false side of the tuple. The EDPB found controllers making exactly this substitution. | AMBIGUITIES 5; `gdpr-sources.md` §3.2 [S11][S12] |
| "We call `delete_object`, so the file is gone" | On a versioned bucket with no `versionId`, S3 "behaves as though the object has been deleted (even though it has not been erased)". | `framework-behaviour.md` §6 R13 [S22] |
| "Stripe data is deleted" | Deleted Stripe customers can still be retrieved through the API; transactions cannot be deleted and are only redactable after 90 days. Stripe is `external_manual`, never `erased`. | `framework-behaviour.md` §6 R22 [S28][S29] |
| "84 runs, 81 scored" without the failures | `success + failure == n` is reported explicitly and errors are never folded into accuracy. | AGENTS.md §Evidence discipline; `05-eval-harness.md` §6 |

**Confidentiality**

| Never write | Why | Source |
|---|---|---|
| The name of the author's product, company, or any client; the stack, sector, dates or scale of the lived bug | micro1 owns the submission and may train on it. "In a product the author runs" is the whole disclosure. | AGENTS.md §Competition facts; QUESTIONS.md Q3 |
| Any real personal data, in a fixture, a trace, a screenshot or the video | Public or synthetic only, ground rules 06 and 07. Fixtures carry schemas and field names. | `.vault/NON-GOALS.md`; problem statement ground rules 06, 07 |
| An API key, in a trace, a screenshot, a `.env`, or a shell prompt in the video | Ground rule 08. `make check-secrets` runs gitleaks over full history before the final push. | AGENTS.md §Code rules; ground rule 08 |

---

## 8. Owed edits outside `docs/spec/`

`PROPOSED-CONTRACT-CHANGES.md` is closed: it records that every owed edit from the 2026-08-28 spec
pass was applied, and says new proposals go in the raising document's own section. This is that
section, and it holds two, both against `docs/demo-script.md`, which §4.2 declares the source of
truth and which no spec document may edit.

| Line in `docs/demo-script.md` | Change | Why |
|---|---|---|
| 0:10–0:25, the command | `make run CASE=S10` → `ART30_UNLOCK_TEST=1 make run CASE=S10 MODE=replay OUT=results/.demo`, the form `08-plan.md`'s Monday 09:45–11:45 row already uses | S10 is a test case and `art30/cli.py` exits 2 on a direct scan of one without the variable (`05-eval-harness.md` §5.4). `MODE=replay` is exempt from that refusal, but the demo script's bare `make run CASE=S10` is not a replay, so as written the shot exits 2 on camera |
| 1:15–1:30, the voice line | "three and a half minutes of machine time and thirty seconds of mine at the gate" → "[human_time.machine_minutes.advanced] machine minutes and [human_time.gate_minutes.mean] minutes of mine at the gate" | Neither number is measured. `05-eval-harness.md` §9 defines both fields; §9's illustrative gate mean is 0.7 min, and "three and a half minutes" tracks `07-ui.md` §9's worked-example `209s`, which is documentation rather than a run |

Until they are made, §4.2 and `docs/demo-script.md` disagree, and §4.2's own rule says the demo
script wins. That rule is suspended for these two rows and nowhere else; the note stays here until
the file is edited.

## Decisions taken here

1. **The README quotes the EDPB and CNIL rather than asserting the bottleneck.** The strongest
   sentence available is a regulator's, from February 2026, about the exact failure the tool
   addresses (`gdpr-sources.md` §6.9, §6.10). An assertion in our own voice is weaker and
   unverifiable.
2. **Deutsche Wohnen is cut from the README** despite being the best story, because the fine is
   contested and a judge who knows that discounts everything around it (§1 notes).
3. **Both prior-art qualifiers are in the README body, not a footnote.** Privado Cloud generates an
   Art. 30 record today; Bearer's classifier is better than ours. `prior-art.md` §Honest weaknesses
   says these must be stated in the demo rather than buried, and stating them first is also the
   cheapest defence against a judge finding them.
4. **The hot take is not chosen here.** Three candidates with their evidence requirements, ranked by
   whether that evidence can exist. Candidate A is marked strongest and the reason is evidence
   availability, not rhetoric.
5. **Candidate B's evidence gap is written down rather than papered over.** `DB_CASCADE`'s
   signal-killing half is a verifier unit test by deliberate fixture design
   (`fixture-generator.md` §9), so it cannot be presented as a measured failure.
6. **Every changelog row below Baseline is marked `PLANNED`**, and the marker is the thing that gets
   deleted when numbers arrive. A row that never runs is deleted rather than shipped with brackets.
7. **The video embeds the demo script verbatim** with an offset column, so the two files cannot drift.
   Four of `07-ui.md` §9's corrections are repeated at the bottom of §4.2 because they are the ones
   that would put a spoken number next to a different visible one. The fifth — the run tail's `209s`
   — is not a correction any more but a deletion: it was a worked example being spoken as a
   measurement, so the number became a slot and the change is owed back to the demo script (§8).
8. **Q3's wording is proposed as the default**, to be used unconfirmed if the author does not answer,
   because it already contains nothing proprietary.

## Open risks

1. **Every number in this document is a slot.** If `make report` names a field differently from the
   `metrics.json` sketch in `05-eval-harness.md` §6, every bracket here has to be re-keyed. Cheapest
   fix: run `make report` once on partial results and re-key before Sunday night.
2. **The README block is 197 lines against a ~180 budget** and the results table has to stay three
   rows. Adding a secondary row to it dilutes the PDF's own format as well as costing lines. §1 names
   the two cuts that pay for the overrun and neither has been made, because the first of them is a
   prior-art qualifier that `prior-art.md` §Honest weaknesses says must not be buried.
3. **`docs/spec/08-plan.md` was written in the same pass as this document** and nothing here has been
   checked against it. Its sweep times — SWEEP A at 17:30–18:15 Saturday, SWEEP B at 19:30–21:00
   Sunday, SWEEP C at 21:00–22:00 Sunday — are the schedule every number in the README block depends
   on, and its Monday 09:45–11:45 row is the only window in which the video gets recorded. Where the
   two documents already overlap they agree (that row's `ART30_UNLOCK_TEST=1 make run CASE=S10
   MODE=replay` is now §4.2's command), but the rest of the overlap is unread.
4. **`example-record-S10.md` cites `models.py:14` for `email` while the worked trace in
   `06-traces.md` §2 shows line 14 as `id` and 15 as `email`.** The video's inventory shot and the
   README's example both draw on those files. Whichever the generated fixture produces wins, and all
   five documents get refreshed from the first real S10 run in one commit (`example-record-S10.md`
   header already commits to this).
5. **The hot take could end up being about the eval rather than the agent.** That is a better hot
   take, not a worse one, but it needs the same evidence discipline: the drift has to be caught by an
   artifact, not remembered.
