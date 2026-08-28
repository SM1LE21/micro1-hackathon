# 06 — Traces

Two different things are called a trace in this project and both are deliverables. The **runtime trace** is what the product's own loop writes, one JSONL line per step, and it is what a judge reads to see the agent think, call a tool, get rejected and try again. The **build trajectory** is the Claude Code transcript of the weekend that produced the project. This document fixes the first one's format with a complete worked run, specifies the validator that stops a malformed trace reaching a judge, and settles how the second one gets into the repository rather than staying on the author's laptop.

**Reads with** `docs/spec/00-contract.md` (§Trace contract, §Run phases, §Budgets, §Feedback object — it wins), `docs/spec/05-eval-harness.md` (the runner that writes these files and the report that reads them back), `docs/spec/01-architecture.md` (§9 failure taxonomy and the generated diagnosis, proposals 3 and 6 — where the two documents proposed different amendments to the same contract line, that one wins and this one is amended), `AGENTS.md` §Trace rules, `docs/judging/requirements-matrix.md` (X13–X16, X26, G-02, and the "missing or unreadable traces" qualification risk).

---

## 1. The contract, restated

`traces/<arm>/<case>-s<seed>.jsonl`. One JSON object per line, UTF-8, LF, no trailing blank line. Four line types, in this order: exactly one `run_start`, then `step` lines, an optional `checkpoint`, then exactly one `run_end`.

| Type | Fields |
|---|---|
| `run_start` | `run_id`, `arm`, `case`, `seed`, `model`, `effort`, `mode` (`live`\|`replay`), `ts` |
| `step` | `step`, `phase` (`agent`\|`verify`), `ts`, `request_id`, `reasoning`, `text`, `tool_calls[{id,name,input}]`, `tool_results[{call_id,output,is_error,bytes}]`, `usage{input,cache_read,cache_write,output}`, `cost_usd`, `cost_cum_usd` |
| `checkpoint` | `tool` (`request_approval`), `caller` (`harness`), `risk` (`low`\|`medium`\|`high`), `summary`, `decision` (`approved`\|`rejected`), `by` (`human`\|`simulated`), `wait_s`, `ts` |
| `run_end` | `stop_condition`, `steps`, `tool_calls_total`, `submits`, `verify_rounds`, `wall_s`, `cost_usd`, `record_path` |

Three readings the contract leaves open, fixed here so the writer and the validator agree:

- **`phase` is a function of the step, not a stage the harness announces.** A step is `verify` when its `tool_calls` contain `submit_record`; otherwise `agent`. There is no separate verifier step line: the verifier runs inside the `submit_record` handler and its feedback object *is* that step's `tool_result`. This keeps one line per model turn and puts the cost of a submit on the turn that caused it.
- **`submits` counts `submit_record` calls; `verify_rounds` counts the ones that came back `accepted: false`.** A run that submits twice and is rejected once has `submits: 2, verify_rounds: 1`.
- **`reasoning` is the summarised thinking text** (ADR 0003 §1: `display: "summarized"`), and may be empty. It is not raw chain of thought and README says so.

`wait_s` on the checkpoint line is new; see proposed change 1 at the end (`PROPOSED-CONTRACT-CHANGES.md` P-10). It is quoted as a field in the table above because `05-eval-harness.md` §9 reads it for `human_time.gate_minutes` and `04-output-schema.md` §5 mirrors it into `provenance.gate` — but `01-architecture.md` §1.3's writer signature is `checkpoint(self, *, risk, summary, decision, by)`, so no code path writes it yet. P-10 carries the signature with the field: `checkpoint(..., wait_s: float, human_completions: dict | None)`, the second half being `07-ui.md` proposal 1. Neither is contract until the lead applies them, and neither should be implemented before then.

---

## 2. A complete run

`traces/advanced/S10-s1.jsonl`, abridged: nine of the fourteen step lines are elided at the marked point, and everything shown is internally consistent with `run_end`. Tool outputs are truncated here with `…`; **in the file they are stored in full** (contract §Trace contract), which is what makes the trace re-readable and the replay exact.

```jsonl
{"type":"run_start","run_id":"adv-S10-s1-9f3ac1e","arm":"advanced","case":"S10","seed":1,"model":"claude-opus-5","effort":"high","mode":"replay","ts":"2026-08-30T14:02:11.004Z"}
{"type":"step","step":1,"phase":"agent","ts":"2026-08-30T14:02:19.882Z","request_id":"req_011CQx7…","reasoning":"Start with the shape of the repository, then the models, then whatever handles account closure.","text":"","tool_calls":[{"id":"toolu_01A","name":"list_tree","input":{"path":".","max_depth":4}}],"tool_results":[{"call_id":"toolu_01A","output":"api/\n  __init__.py  (0 B)\n  account.py  (1204 B)\n  profile.py  (988 B)\njobs/\n  __init__.py  (0 B)\n  backup.py  (742 B)\n  purge.py  (826 B)\napp.py  (311 B)\nconfig.py  (402 B)\ndb.py  (517 B)\nmodels.py  (863 B)\nstorage.py  (1391 B)\nbilling.py  (655 B)\nutils/text.py  (734 B)\nREADME.md  (128 B)\nrequirements.txt  (96 B)","is_error":false,"bytes":412}],"usage":{"input":2314,"cache_read":0,"cache_write":4180,"output":188},"cost_usd":0.0412,"cost_cum_usd":0.0412}
{"type":"step","step":2,"phase":"agent","ts":"2026-08-30T14:02:31.117Z","request_id":"req_011CQx8…","reasoning":"models.py first: it decides what stores exist. Then account.py, which the tree suggests is the closure route.","text":"","tool_calls":[{"id":"toolu_01B","name":"read_file","input":{"path":"models.py"}},{"id":"toolu_01C","name":"read_file","input":{"path":"api/account.py"}}],"tool_results":[{"call_id":"toolu_01B","output":"1: from datetime import datetime\n…\n12: class User(Base):\n13:     __tablename__ = \"users\"\n14:     id = Column(Integer, primary_key=True)\n15:     email = Column(String, nullable=False)\n16:     full_name = Column(String)\n17:     signup_ip = Column(String)\n18:     last_seen_at = Column(DateTime)\n19:     deleted_at = Column(DateTime)\n","is_error":false,"bytes":863},{"call_id":"toolu_01C","output":"1: from datetime import datetime, timezone\n…\n12: def close_account(user_id: int) -> dict:\n13:     \"\"\"Close the account and remove all user data, including uploaded files.\"\"\"\n14:     user = session.get(User, user_id)\n15:     user.deleted_at = datetime.now(timezone.utc)\n16:     session.commit()\n17:     return {\"status\": \"closed\"}\n","is_error":false,"bytes":1204}],"usage":{"input":1902,"cache_read":4180,"cache_write":0,"output":214},"cost_usd":0.0289,"cost_cum_usd":0.0701}
{"type":"step","step":3,"phase":"agent","ts":"2026-08-30T14:02:44.503Z","request_id":"req_011CQx9…","reasoning":"The docstring claims files are removed but close_account only writes deleted_at. Find every delete in the repository before believing either.","text":"","tool_calls":[{"id":"toolu_01D","name":"grep","input":{"pattern":"delete|cleanup|purge","path":".","glob":"*.py"}}],"tool_results":[{"call_id":"toolu_01D","output":"jobs/purge.py:14: def purge_closed_accounts() -> int:\njobs/purge.py:22:         session.delete(user)\nstorage.py:41: def cleanup_user_files(user_id: int) -> None:\nstorage.py:47:     s3.delete_object(Bucket=BUCKET, Key=_avatar_key(user_id))\n","is_error":false,"bytes":298}],"usage":{"input":1655,"cache_read":6082,"cache_write":0,"output":246},"cost_usd":0.0331,"cost_cum_usd":0.1032}
… 9 step lines elided (steps 4–12: reads of storage.py, billing.py, jobs/purge.py, jobs/backup.py, config.py and two greps) …
{"type":"step","step":13,"phase":"verify","ts":"2026-08-30T14:05:02.771Z","request_id":"req_011CQxK…","reasoning":"cleanup_user_files does call delete_object, so the uploads bucket is handled and the docstring is accurate. Drafting the record.","text":"","tool_calls":[{"id":"toolu_01M","name":"submit_record","input":{"record":{"stores":[{"name":"users","kind":"relational","erasure":{"verdict":"erased_after_timer","timer_days":30,"evidence":"jobs/purge.py:22"}},{"name":"uploads","kind":"object_storage","erasure":{"verdict":"erased","evidence":"storage.py:47"}},{"name":"stripe","kind":"third_party","erasure":{"verdict":"external_manual"}},{"name":"nightly_backup","kind":"backup","erasure":{"verdict":"governed_by_retention","timer_days":35}}]}}}],"tool_results":[{"call_id":"toolu_01M","output":"{\"accepted\":false,\"attempt\":1,\"attempts_left\":4,\"schema_errors\":[],\"rejected_claims\":[{\"store\":\"uploads\",\"field\":null,\"claim\":\"erasure.verdict=erased\",\"reason\":\"no path from entry point close_account (api/account.py:12) to any object-storage deletion primitive; cleanup_user_files (storage.py:41) is defined but has no callers\",\"expected\":\"verdict not_erased, or cite the path\"}],\"missing_stores\":[],\"bad_citations\":[],\"unverified\":[]}","is_error":false,"bytes":447}],"usage":{"input":2088,"cache_read":11640,"cache_write":0,"output":1420},"cost_usd":0.0510,"cost_cum_usd":0.3520}
{"type":"step","step":14,"phase":"verify","ts":"2026-08-30T14:05:39.219Z","request_id":"req_011CQxL…","reasoning":"The helper exists but nothing calls it. Checked again with grep: cleanup_user_files appears once, at its definition. Changing the verdict to not_erased and citing the definition as the note.","text":"","tool_calls":[{"id":"toolu_01N","name":"submit_record","input":{"record":{"stores":[{"name":"uploads","kind":"object_storage","erasure":{"verdict":"not_erased","evidence":null,"note":"cleanup_user_files defined at storage.py:41, never called"}}]}}}],"tool_results":[{"call_id":"toolu_01N","output":"{\"accepted\":true}","is_error":false,"bytes":17}],"usage":{"input":2210,"cache_read":13728,"cache_write":0,"output":1602},"cost_usd":0.0580,"cost_cum_usd":0.4100}
{"type":"checkpoint","tool":"request_approval","caller":"harness","risk":"high","summary":"4 stores. uploads NOT ERASED (identifier: avatar_key). stripe EXTERNAL MANUAL (contact: email). nightly_backup GOVERNED BY RETENTION 35 d. users ERASED AFTER TIMER 30 d.","decision":"approved","by":"simulated","wait_s":0.0,"ts":"2026-08-30T14:05:40.004Z"}
{"type":"run_end","stop_condition":"accepted","steps":14,"tool_calls_total":21,"submits":2,"verify_rounds":1,"wall_s":209.0,"cost_usd":0.4100,"record_path":"results/runs/advanced/S10/s1/record.json"}
```

What a reader is supposed to see in it, and what the video pauses on: step 13 says the docstring is accurate and the bucket is handled; the tool result disagrees with a reason that names a line number; step 14 changes the verdict. That is the whole argument of the project inside two lines of a file, which is why this trace is the one the README links first.

The `checkpoint` line carries `by: "simulated"` because an eval sweep runs `--approve auto` (contract §Run phases 3). A live `--approve ask` run records `by: "human"` and a real `wait_s`; the baseline arm has no checkpoint line at all.

That last difference is easy to over-read, so it is stated here in the same place it is visible: **in every scored run the gate approves by construction.** `--approve auto` never declines, so no measured part of the advanced-versus-baseline delta is the gate's — the delta is the verifier's (`05-eval-harness.md` §7.1). What the gate contributes to the evidence is this line: that a checkpoint exists, at what risk rating, with what summary, and how long a person took over it in the gate-timing pass.

---

## 3. The validator

`evals/harness/trace_check.py`, run by `make smoke` over every committed trace and by `run.py` after each run before the file is considered written. Pure stdlib, no model, exit 1 on the first failure with the file, the line number and what was expected.

| # | Check | Why it exists |
|---|---|---|
| 1 | Every line parses as JSON; file is UTF-8 with LF and no trailing blank line | A half-flushed trace is the qualification risk in the matrix, not a cosmetic issue |
| 2 | Exactly one `run_start` first and one `run_end` last | A truncated run must be recognisable as truncated |
| 3 | `step` numbers are 1, 2, 3, … with no gaps or repeats | Monotonic steps (AGENTS.md §Trace rules) |
| 4 | Every `tool_results[].call_id` matches a `tool_calls[].id` **in the same step**, and every `tool_calls[].id` has exactly one result | AGENTS.md: "tool responses linked back to their call id". The one exception is the final step of a run that did not end `accepted` |
| 5 | `tool_calls[].id` is unique across the whole file | A repeated id makes the pairing ambiguous even when it validates |
| 6 | `cost_cum_usd` is non-decreasing, and `\|cum[i] − (cum[i−1] + cost_usd[i])\| < 1e-6` | Cost sums that do not add up make every cost row in the report unciteable |
| 7 | `\|run_end.cost_usd − cum[last]\| < 1e-6`; `run_end.steps` equals the number of `step` lines; `run_end.tool_calls_total` equals the sum of `len(tool_calls)` | The report reads `run_end` and nothing else, so `run_end` has to be true |
| 8 | `submits` equals the number of `submit_record` calls and is ≤ 5; `tool_calls_total` ≤ 60 synthetic / 120 real | Contract §Budgets, checked after the fact as well as enforced during |
| 9 | `verify_rounds` equals the number of `submit_record` results with `accepted: false` | §1's reading, asserted |
| 10 | An advanced run ending `accepted` has exactly one `checkpoint` with `caller: "harness"`; a baseline run has none | The gate is harness-driven and never model-initiated (contract §Run phases 3) |
| 11 | `checkpoint.risk` equals the rating recomputed from `record.json` by the contract's rule, when the record exists | X15 asks that the checkpoint be "annotated with the risk rating that triggered them"; an annotation nobody checks drifts |
| 12 | Every `usage` has `input`, `cache_read`, `cache_write`, `output`, all integers ≥ 0 | Per-step token counts are a required trace field |
| 13 | `run_start.arm/case/seed` match the file's path and name; `mode` ∈ {live, replay}; `model` equals the configured model | Stops a mislabelled file being quoted as evidence for the wrong arm |
| 14 | `stop_condition` ∈ the contract's six values plus `timeout` | See proposed change 2. Four values written by specified code paths are not in the enum — `timeout` (§5.3 of `05`), `crashed` (§9 of `01`), `replay_miss` and `render_failed` (§6 of `07`) — and this check runs inside `run.py` after every run, so an unlisted value fails the validator on a run that did exactly what its own document says. Until `PROPOSED-CONTRACT-CHANGES.md` P-08 replaces this row with one enum, the writer records the other three as `api_error` with the cause in `run_end.note`, and only `timeout` is admitted here, because check 16 needs to key on it |
| 15 | Every failure trace has a `.diagnosis.txt` beside it, whose first line matches the four-field form of §4. **Scope: `traces/failures/` only** | AGENTS.md: "failures are shipped… with a one-line diagnosis each". A directory of failures with no diagnoses is a directory nobody reads |
| 16 | A trace whose `stop_condition` is `timeout` may carry exactly one truncation, recorded as a byte count in `run_end.note`; every other trace must carry none | A child killed mid-write leaves a partial line, and the parent's repair (`05-eval-harness.md` §5.3) has to be visible rather than silent. Without the repair, check 1 rejects every timed-out run and `make smoke` fails on a clean clone — the red target this project is otherwise careful to avoid |

`make smoke` calls it as `uv run python -m evals.harness.trace_check traces/` and exits 0 when the directory holds no traces, so the target works on a clean clone before any run exists. Checks 1–14 run over every trace; 15 and 16 are scoped as their rows say.

---

## 4. Failures

AGENTS.md: "Failures are shipped, not hidden: `traces/failures/` with a one-line diagnosis each."

Every run whose `stop_condition` is not `accepted` has its trace copied — not moved; the arm directory keeps the original so the sweep stays complete — to:

```
traces/failures/<arm>/<case>-s<seed>.jsonl
traces/failures/<arm>/<case>-s<seed>.diagnosis.txt
```

The directory form, not the `<arm>-<case>` filename prefix an earlier draft of this document proposed: `01-architecture.md` proposed the directory form for the same contract line, the two amendments are incompatible, and the lead can apply only one. The failures tree then mirrors `traces/<arm>/`, which is also what makes the README's link legible.

The diagnosis file's **first line** is exactly one line, at most 160 characters, four fields separated by ` · `:

```
<arm>/<case>-s<seed> · <stop_condition> · <what happened, one clause, past tense> · <where to look>
```

That line is what AGENTS.md means by "a one-line diagnosis each", and it is the line `traces/failures/README.md` quotes. Below it the file carries the four generated context lines of `01-architecture.md` §9 — run id, the rule from that document's failure table, the last step's tool calls, and the path of the full trace in `traces/<arm>/`:

```
advanced/S08-s2 · max_submits · the completeness guard kept re-adding the events queue the model then dropped · step 19, rejected_claims[0]
run_id: adv-S08-s2-9f3ac1e
rule: 5 submits rejected; last rejection: store events (queue) is absent from the record
last step: grep(pattern="publish"), submit_record(record={...})
trace: traces/advanced/S08-s2.jsonl
```

Both halves are **generated** by `run.py` from a fixed rule table over the last trace lines (`01-architecture.md` Decision 11), including the first line's third field. A hand-written line reads better and drifts: eighty-four runs a sweep, a code freeze on Sunday night, and one file per failure is the shape of a promise nobody keeps at hour 68. Where the author wants to say more than the rule table can, the sentence goes in `CHANGELOG_EVAL.md`, which is where a human reading is expected.

Two more shapes the first line takes:

```
baseline/R02-s3 · budget_exhausted · read 41 files of flaskbb without reaching a delete path; 120 tool calls, no submit · steps 96-120
advanced/R04-s1 · max_submits · the record kept citing the Elasticsearch index write as its own deletion evidence · step 27, bad_citations[0]
```

The second replaces an earlier example that showed `gate_rejected` on R04. No sweep can produce it: every scored run uses `--approve auto`, which approves by construction, so a `gate_rejected` trace would have to come from a `--approve ask` pass and never from the numbers the README quotes. An example of a failure the harness cannot produce teaches a reader the wrong shape of the system.

`traces/failures/README.md` is an index table — file, arm, case, seed, stop condition, the diagnosis line — regenerated by `run.py` so it cannot fall behind the directory. A diagnosis file missing for any failure trace is a `make smoke` failure (check 15 in `trace_check.py`, over the failures directory only).

Failures are not an embarrassment to be minimised in the README: `success + failure == n` is a reported identity (`05-eval-harness.md` §4.4), and a directory with nothing in it after 84 runs would say the sweep was curated.

---

## 5. Representative trajectories

Deliverable 4 asks for trajectories that are "representative, easy to follow from instructions to final result, tool responses included, retries and human checkpoints visible". This project has two agents in the sense the deliverable means — the two arms — and "representative for every agent" is read here as:

- **at least one complete trace per arm on a dev case and one per arm on a test case**, so a reader can compare the same code read two ways; and
- **every failure trace**, without selection.

One thing these traces do not show, and the README says it rather than letting a reader infer it: the gate approves in every scored run, because the eval runs `--approve auto` (contract §Run phases 3). The measured delta between the arms is the verifier's. The gate is evidenced by the checkpoint line, its risk rating and the gate-timing pass of `05-eval-harness.md` §9, and it is not part of the comparison.

Four traces are linked from the README by name, chosen so that each shows something the others do not:

| Trace | Why it is linked |
|---|---|
| `traces/advanced/S10-s1.jsonl` | The rejection and the revision (§2). The video's 0:40–1:00 beat is this file. |
| `traces/baseline/S10-s1.jsonl` | The same repository, the same instructions, no verifier: the run that reads `cleanup_user_files`, believes the docstring, and submits `erased` — the false safe, unedited. |
| `traces/advanced/S05-s1.jsonl` | A dev case with six stores and no headline trap: the completeness guard adding the session cache the model had not listed, and a `medium` risk gate. |
| `traces/advanced/R04-s1.jsonl` | A real repository (microblog) where the honest answer is that no deletion feature exists, and the Elasticsearch index is the store most likely to be missed. |

Plus everything in `traces/failures/`, linked as a directory with its index table.

The pairing matters more than the count. Two files reading the same repository and disagreeing is the entire measured claim, and it is legible in under a minute; a directory of eighty-four traces is not.

---

## 6. The build trajectory

`make traces` renders the Claude Code transcripts of this project's own build. Two problems with it as written in the Makefile today, both flagged as G-02 in the requirements matrix:

- It reads `~/.claude/projects/-Users-tun-Documents-micro1-hackathon`, a path that exists on one machine.
- It runs `claude-code-log@latest`, which is unpinned and needs the network, so two runs a day apart can produce different HTML.

Both are fixed by treating the **rendered HTML as the deliverable** and the command as the author's tool for producing it:

```make
CLAUDE_PROJECT_DIR ?= $(HOME)/.claude/projects/-Users-tun-Documents-micro1-hackathon

# author-only: the transcripts live outside the repository. Judges read the committed HTML.
traces:
	@test -d "$(CLAUDE_PROJECT_DIR)" || { \
	  echo "author-only target; transcripts not present."; \
	  echo "the rendered trajectory is committed at traces/build-trajectory.html"; \
	  exit 0; }
	uvx claude-code-log@1.5.0 "$(CLAUDE_PROJECT_DIR)" -o traces/build-trajectory.html
	@echo "rendered traces/build-trajectory.html"
```

`claude-code-log` converts Claude Code transcript JSONL files to HTML; 1.5.0 is the current release [`docs/judging/requirements-matrix.md` §Sources, S1]. The version is pinned so the render is repeatable, and the target exits 0 rather than failing on a judge's machine, because a red target that is working as designed teaches a judge to ignore red targets.

`traces/build-trajectory.html` is committed and re-rendered at each session boundary, last before the code freeze. README states plainly that it is the transcript of the sessions that built the project, that sessions are named by day and focus (AGENTS.md §Trace rules), and that it is a rendering of files that live outside the repository.

---

## Decisions taken here

1. `phase` is derived: a step carrying a `submit_record` call is `verify`, everything else is `agent`. There is no separate verifier step line, so the cost of a submit sits on the turn that caused it.
2. `submits` counts submit calls; `verify_rounds` counts rejections. Both are asserted by the validator against the step lines. `02-agent-loop.md` §1 and its Decision 15 counted every handled submit; they now count rejections, so `trace_check.py` check 9 and the loop that writes the file agree, and `make smoke` is green on a clean clone. The contract names the field and defines neither reading (`PROPOSED-CONTRACT-CHANGES.md` P-01).
3. The validator is a separate module (`evals/harness/trace_check.py`), runs inside `run.py` after every run and inside `make smoke` over the committed traces, and exits 0 on an empty directory so a clean clone passes.
4. Sixteen checks, of which three are the ones AGENTS.md names literally: call-id pairing within a step, monotonic steps, and cost sums that reconcile with `run_end`. Checks 15 (a diagnosis exists) and 16 (a timeout's truncation is recorded) are scoped to the failures directory and to timed-out runs respectively.
5. The checkpoint's risk rating is recomputed from the record and compared, so the annotation cannot drift from the record it describes.
6. Failure traces are **copied**, not moved, into `traces/failures/<arm>/`, so the two arms' failures on the same case coexist and the failures tree mirrors `traces/<arm>/`. This is `01-architecture.md`'s form; this document's earlier filename-prefix proposal is withdrawn so one amendment reaches the contract.
7. The diagnosis file's first line is the four-field, 160-character line; the rest is `01-architecture.md` §9's generated context. The whole file is generated from a rule table, not written by hand, and a missing one fails `make smoke`.
8. "Representative for every agent" is one complete trace per arm on dev and on test, plus every failure. Four traces are linked by name from the README, chosen as two pairs that disagree.
9. The build trajectory is committed HTML; `make traces` is author-only, pins `claude-code-log@1.5.0`, and exits 0 with a pointer when the transcript directory is absent.
10. A trace whose run was killed on wall clock is repaired before `run_end` is appended, and the discarded byte count is recorded (`05-eval-harness.md` §5.3). A timeout that shipped a trace failing check 1 would turn `make smoke` red on a clean clone for a reason that is not a defect in the run.
11. The `gate_rejected` example is removed, and §2 and §5 say in one sentence each that the gate approves in every scored run. The worked failures are ones the harness can actually produce, and the delta the README quotes is the verifier's.

## Open risks

- **Full tool outputs make traces large.** A real-repo run reads dozens of files at up to 400 lines each; `traces/advanced/R02-s1.jsonl` could reach several megabytes, and 84 of them will dominate the repository's size. The contract requires full outputs and they are what make the trace re-readable, so the mitigation is scope, not truncation: commit all traces from the final sweep and the four linked traces from earlier sweeps, and say so in the README. If the repository becomes unclonable, the honest fix is fewer committed sweeps, never a truncated trace.
- **The diagnosis's third field is only as good as the rule table.** A generated clause cannot say what a reader of the trace would say, and the failure it describes worst is the one nobody anticipated — an unhandled exception, where the rule table can offer only the exception class. `CHANGELOG_EVAL.md` is where that gets a sentence, and nothing enforces that it does.
- **Check 16 depends on a contract change that has not landed.** The truncation count is recorded in `run_end.note`, which is `01-architecture.md` proposal 6. If the lead declines it, the count has nowhere to live and the check degrades to "a timeout trace parses", which is weaker than it sounds: a repair that silently discarded half a step would then pass.
- **Check 11 needs `record.json` to exist.** A run that fails after the gate has no record and the risk rating goes unchecked. That is exactly the run where a wrong rating would matter least, but it is a hole.
- **The build trajectory contains the whole weekend, including the wrong turns.** That is the point, and it also means it contains every ambiguity the author reasoned through in public. It is read before commit for anything proprietary (AGENTS.md §Competition facts), and that read is a manual step nobody has scheduled.
- **`wait_s` measures the terminal prompt, not the reviewer's attention.** A gate left open while the author makes coffee records the coffee. The gate-timing pass (`05-eval-harness.md` §9) is a single deliberate sitting for that reason, and the README calls the number a lower bound.

## Proposed contract changes

1. **`00-contract.md` §Trace contract — add `wait_s` (float, seconds) to the `checkpoint` line.** `0.0` when `by: "simulated"`. Reason: lead decision G-01 requires the gate's approval time next to the human-time row, and no trace line currently carries a duration. Consumed by `05-eval-harness.md` §9.
2. **`00-contract.md` §Trace contract — add `timeout` to the `stop_condition` enum.** Reason: the runner kills a run on wall clock (`05-eval-harness.md` §5.3); folding that into `api_error` erases the distinction between "raise the budget" and "fix a bug".
3. **`00-contract.md` §Repository layout — failure traces are `traces/failures/<arm>/<case>-s<seed>.jsonl`, with `<same>.diagnosis.txt` beside each.** The layout's `traces/failures/<same>.jsonl` collides between arms on the same case and seed, which is precisely the case worth keeping both halves of. This is the same amendment `01-architecture.md` proposal 3 asks for; the filename-prefix variant this document proposed in its first draft is withdrawn, so the lead applies one change and `make smoke`, the README link and the AGENTS.md line all point at the same tree.
4. **`00-contract.md` §Repository layout — add `evals/harness/trace_check.py`.** Reason: the validator has to live somewhere, and putting a reader inside `art30/trace.py` (specified as the writer) breaks the one-responsibility-per-file rule in the same section.
