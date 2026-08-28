# 02 — The agent loop

The exact loop `art30/loop.py` implements: how the message list is built, where the cache breakpoints go, how thinking blocks and parallel tool calls are carried, what the two arms do with a `submit_record` call, when the human gate fires, and every way a run can stop. The request shapes here are normative — the replay cache is keyed on their bytes, so an ambiguity in this document is a reproducibility bug rather than a documentation one.

**Reads with** `docs/spec/00-contract.md` (tools, budgets, feedback object, trace lines), `docs/spec/01-architecture.md` (modules, record/replay, cost, failure taxonomy), `.vault/adr/0003-runtime-and-api-decisions.md` (model and API surface), `evals/CASES.md` (budgets per case kind), and the Claude API reference under `claude-api/` (`shared/prompt-caching.md`, `shared/tool-use-concepts.md`, `python/claude-api/tool-use.md`, `python/claude-api/README.md`, `shared/model-migration.md`).

---

## 1. The loop

```python
def run(case, arm, seed, cfg) -> RunResult:                            # art30/loop.py
    ctx = RunCtx(case=case.id, arm=arm.name, seed=seed, root=case.root,
                 tools=ToolCtx(root=case.root), trace=Trace(trace_path(cfg, arm, case, seed)),
                 cfg=cfg)
    ctx.trace.run_start(run_id=run_id(arm.name, case.id, seed), arm=arm.name, case=case.id,
                        seed=seed, model=cfg.model, effort=cfg.effort, mode=cfg.mode)
    # run_id(arm, case, seed) -> "<arm prefix>-<case>-s<seed>-<git sha7>", e.g. adv-S10-s1-9f3ac1e
    # Arm prefixes: advanced -> adv, baseline -> base (01-architecture.md §2).
    try:
        return _run(ctx, case, arm, cfg)
    except Exception as exc:                # nothing leaves this function without a run_end line
        return stop(ctx, "api_error", note=f"{type(exc).__name__}: {exc}")

def _run(ctx, case, arm, cfg) -> RunResult:
    system   = [{"type": "text", "text": PROMPT, "cache_control": EPHEMERAL}]  # PROMPT is frozen
    messages = [user_text(FIRST_TURN.format(repo_name=case.name,
                                            tool_call_budget=cfg.tool_budget,
                                            submit_budget=cfg.max_submits))]   # never case.root
    step, nudges = 0, 0
    while True:
        step += 1
        req = build_request(cfg, system, arm.tools(), mark(messages))
        try:
            resp = llm.call(req, cfg=cfg, slot=Slot(ctx.case, ctx.arm, ctx.seed, step))
        except (LlmError, ReplayMiss) as exc:
            return stop(ctx, "api_error", note=str(exc))
        if resp.stop_reason == "refusal":                # checked BEFORE content is read
            trace_step(ctx, step, resp, [], [])
            return stop(ctx, "refusal", note=refusal_note(resp.stop_details))
        if resp.stop_reason == "max_tokens":
            trace_step(ctx, step, resp, [], [])
            return stop(ctx, "api_error", note=f"output truncated at max_tokens={cfg.max_tokens}")
        if resp.stop_reason == "pause_turn":             # no server tools: it cannot be resumed
            trace_step(ctx, step, resp, [], [])
            return stop(ctx, "api_error", note="pause_turn on a request with no server tools")
        messages.append({"role": "assistant", "content": resp.content})  # thinking blocks verbatim
        calls = [b for b in resp.content if b["type"] == "tool_use"]
        if not calls:                                    # end_turn with nothing to run
            trace_step(ctx, step, resp, [], [])
            nudges += 1
            if nudges > 2:
                return stop(ctx, "budget_exhausted", note="ended turn without submitting, 2 nudges")
            messages.append(user_text(NUDGE))
            continue
        results, phase, submitted = [], "agent", False
        for c in calls:                                  # response order, always
            if ctx.tool_calls >= ctx.cfg.tool_budget:                     # INVARIANT B
                trace_step(ctx, step, resp, calls, results, phase=phase)
                return stop(ctx, "budget_exhausted")
            ctx.tool_calls += 1
            if c["name"] != "submit_record":
                out, is_err = tools.dispatch(c["name"], c["input"], ctx.tools)
                results.append(tool_result(c["id"], out, is_error=is_err))
                continue
            phase = "verify"
            if submitted:                                                 # INVARIANT A
                results.append(tool_result(c["id"], SECOND_SUBMIT, is_error=True))
                continue
            submitted = True
            ctx.submits += 1                                              # INVARIANT A
            fb = arm.handle_submit(c["input"]["record"], ctx)
            if not fb.accepted:
                ctx.verify_rounds += 1                   # rejections only; no branch on arm.name
            results.append(tool_result(c["id"], fb.to_tool_result(), is_error=not fb.accepted))
            if fb.accepted:
                ctx.accepted = c["input"]["record"]
            elif ctx.submits >= ctx.cfg.max_submits:                      # INVARIANT A
                trace_step(ctx, step, resp, calls, results, phase=phase)
                return stop(ctx, "max_submits")
        trace_step(ctx, step, resp, calls, results, phase=phase)
        messages.append({"role": "user", "content": results})  # ALL results, ONE message
        if ctx.accepted:
            break
    record = ctx.accepted
    decision = arm.gate(record, ctx)                     # None in the baseline arm
    if decision is not None:
        ctx.trace.checkpoint(risk=decision.risk, summary=decision.summary, by=decision.by,
                             decision="approved" if decision.approved else "rejected")
        if not decision.approved:
            return stop(ctx, "gate_rejected")
        record = apply_edits(record, decision.edits)     # recipient_kind, set by the human
    paths = render_all(record, out_dir(cfg, arm, case, ctx.seed))
    return stop(ctx, "accepted", record_path=paths.json)
```

Eighty lines with ten exits, every one of them through `stop()`. `stop()` writes the `run_end` line, closes the trace and returns `RunResult`; `trace_step()` writes one `step` line with usage, per-step cost and cumulative cost.

The outer `try/except` is the reason `run` and `_run` are two functions rather than one. Without it, a raise from `arm.handle_submit`, `arm.gate`, `risk_rating` on a malformed-but-schema-valid record, `render_all` or the trace writer leaves `loop.run` with no `run_end` line and no artefacts, and the harness — whose rule keys on `stop_condition` — drops the run out of both the numerator and the denominator of `success + failure == n`. The one failure it cannot catch is a `stop()` that itself raises, which is why `report.py` also counts planned runs with no `run_end` line as `crashed` (`01-architecture.md` §9).

### Stop conditions, in the order they can fire

| Condition | Line | Reached when |
|---|---|---|
| `api_error` (unhandled) | 10 | Any exception from an arm, the verifier, the renderer or the trace writer |
| `api_error` | 24 | SDK error after its retries, or a replay miss |
| `refusal` | 27 | `stop_reason == "refusal"`, before `content` is read |
| `api_error` (truncation) | 30 | `stop_reason == "max_tokens"` |
| `api_error` (`pause_turn`) | 33 | `stop_reason == "pause_turn"` on a request that carries no server tools |
| `budget_exhausted` (no submit) | 40 | Three consecutive turns ended without a tool call and without an accepted record |
| `budget_exhausted` (tool calls) | 47 | The next call would exceed 60 (synthetic) or 120 (real) |
| `max_submits` | 66 | The fifth `submit_record` was rejected |
| `gate_rejected` | 77 | The approver declined |
| `accepted` | 80 | Record accepted, gate approved or absent, render finished (leaves the loop at line 70) |

---

## 2. Message list construction

**System.** One text block: `art30/prompts/system.md` with `art30/prompts/taxonomy.md` spliced in at the literal `<!-- include: taxonomy.md -->` marker, no substitution, read once at process start. `10-instructions.md` §0 and its Decision 1 own the assembly and `system.md` already carries the marker mid-document, so concatenating the two files instead would move the taxonomy behind the sections that refer back to it — different bytes, a different cached prefix, a different step-1 hash and a different `instruction_sha256`. Byte-identical in both arms (ADR 0003 item 4). `config.py` asserts the **spliced** string's sha256 against a constant committed with the prompt, so an accidental edit fails fast instead of silently invalidating every cache entry.

**First user turn.** One text block naming the scan target and the task, with no absolute path, no timestamp, no machine identifier and no seed. The template is `FIRST_TURN` in `10-instructions.md` §3 and that file is the source of the bytes; §8 below quotes it rendered rather than paraphrased, because the two documents disagreeing about this string is a reproducibility bug and not a documentation one.

`FIRST_TURN` is rendered from exactly three values — `case.name`, `cfg.tool_budget` and `cfg.max_submits`. `CaseRef.root` is never formatted into it; the fixture root reaches the tools through `ToolCtx` alone. `config.py` asserts that the rendered string contains no `os.sep`-prefixed token, so an absolute path cannot arrive through a future template edit either. This is what makes the step-1 request hash identical on the author's laptop and a judge's (`01-architecture.md` §4.5), and it is also why `ART30_TOOL_BUDGET` and `ART30_SUBMIT_BUDGET` change every request hash: both budgets are named in this message.

**Assistant turns.** `resp.content` appended whole and unmodified: thinking blocks, text blocks and `tool_use` blocks in the order the API returned them. Nothing is filtered, reordered or re-serialised.

**Tool result turns.** One user message per assistant turn, containing a `tool_result` block for every `tool_use` block in that turn, in the same order. Never a subset (`shared/tool-use-concepts.md` §Handling Tool Results: "Handle them all before continuing - send all results back in a single `user` message").

**History is never rewritten.** No compaction, no context editing, no summarisation. A real-repo run peaks near 90,000 tokens of conversation against a 1M context window (`shared/models.md`), so there is nothing to manage, and rewriting history would break replay by changing a prefix that was already recorded.

---

## 3. Cache breakpoints

Placement, per request:

| # | Where | When |
|---|---|---|
| A | Last (only) system text block | Always |
| B | Last content block of the newest user turn | Always |
| C | Last content block of the previous user turn | Every request after the first |

At most three of the four allowed breakpoints (`shared/prompt-caching.md` §API reference). The reasoning:

- Render order is tools → system → messages, so a marker on the last system block caches the tool schemas and the system prompt together (§The one invariant everything follows from). That is the expensive fixed prefix, about 4,000 tokens, and it is the same bytes in all 84 runs.
- The marker on the newest user turn is the documented multi-turn pattern: "Put a breakpoint on the last content block of the most-recently-appended turn. Each subsequent request reuses the entire prior conversation prefix" (§Placement patterns). The marker moves forward each turn; the previously marked block stays a valid read point, and a moving marker is not itself an invalidator (§Finding the invalidator).
- Breakpoint C exists for one failure mode: each breakpoint walks back at most 20 content blocks to find a prior entry, and a turn that appends many parallel `tool_use`/`tool_result` pairs can push the previous entry out of that window, after which every request silently rewrites the whole conversation (§20-block lookback window). The distance B has to walk is not the newest user turn's N `tool_result` blocks. It is those N blocks **plus the assistant turn that sits between the two markers**, which carries the same N `tool_use` blocks, a thinking block and a text block: 2N+2 in all. A threshold counting only the newest user turn gets this backwards. At N = 10 the distance is already 22, past the window, so a "more than 10 blocks" trigger loses the case it exists to catch at exactly the value that does not fire it. C is therefore placed on every request after the first. The position was written by the previous request's B, so C is a read at distance zero: no extra write, no extra cost, and the total stays at three of the four allowed breakpoints.
- Explicit markers only, no top-level automatic caching. Automatic placement is decided server-side; every byte of our request has to be predictable, because it is hashed.
- `mark(messages)` returns a copy. The stored `messages` list never carries a `cache_control` key, so markers cannot accumulate past the limit of four as the conversation grows.

Cache health is checked from `usage`, not assumed: in a healthy run `cache_read_input_tokens` grows turn over turn, `cache_creation_input_tokens` stays near the size of the last turn, and `input_tokens` is a small tail (§The healthy-loop signature). All four fields are in every `step` line, so a regression is visible in the trace of the run that caused it rather than only in the bill.

---

## 4. Thinking, parallel calls, errors

**Thinking.** `thinking: {"type": "adaptive", "display": "summarized"}` for every request in both arms. Raw thinking tokens are never returned on this model; `display: "summarized"` yields a readable summary (`shared/model-migration.md` §Migrating to Claude Opus 5), which is what the trace's `reasoning` field carries. Blocks are echoed back unchanged on the next turn with the same model — required by the API and also a cache property: on this model generation previous-turn thinking blocks are preserved rather than stripped, so the messages cache survives (`shared/prompt-caching.md` §Thinking blocks and the messages cache). `thinking` and `effort` are pinned for the life of a run; changing either mid-run invalidates the messages cache (§Invalidation hierarchy).

**Parallel tool use.** On by default: one assistant message can carry several `tool_use` blocks (`shared/tool-use-concepts.md` §Tool Choice Options). We do not set `disable_parallel_tool_use`; the model reading four files at once is the behaviour we want, it cuts round trips and it is the reason a 30-call run is not a 30-step run. Every call in the batch is dispatched in response order, every result goes back in one user message, and the whole batch is one `step` line in the trace with the `tool_calls` and `tool_results` arrays linked by call id.

**Errors.** A tool that fails returns `is_error: true` with a one-line message and never an exception through the loop: a jail escape, a missing path, an unreadable file, an invalid regex, a file over 2 MB. The result block is still returned for that call id, because a dropped result makes the next request invalid.

**Rejected submits are also `is_error: true`.** The tool ran fine; the claim did not survive. Marking it an error makes every rejection greppable in the trace, and it tells the model this attempt failed rather than leaving a large JSON object to be read as data. If the first runs show the model resubmitting an unchanged record after a rejection, flipping this flag to `false` is a one-variable changelog experiment.

---

## 5. The submit round trip

```
model                       loop                          arm
  |  tool_use submit_record  |                              |
  |------------------------->|  ctx.submits += 1            |
  |                          |----------------------------->| handle_submit(record, ctx)
  |                          |                              |   baseline: schema only
  |                          |                              |   advanced: schema, then
  |                          |                              |     verify/check.py
  |                          |<-----------------------------|  Feedback
  |  tool_result (is_error)  |                              |
  |<-------------------------|  if accepted: leave loop     |
```

**Baseline.** `{"accepted": false, "attempt": 2, "attempts_left": 3, "schema_errors": [...]}` and nothing else (contract §Feedback object: "Baseline feedback contains only `schema_errors`"). A schema-valid record is accepted, whatever it claims.

**Advanced.** Schema first — a record that does not validate never reaches the verifier, so the model gets the cheap error before the expensive one. Then `check.check(record, root, rules)` returns the full object: `rejected_claims`, `missing_stores`, `bad_citations`, `unverified`. The verifier never sees a manifest (contract §Verifier contract), so nothing in this channel can leak ground truth into the run.

**What the model sees when a submit is rejected:** the feedback object, verbatim, as the `tool_result` content for that call. That is the only place the difference between arms is visible to the model, and it is why the arms can share one prompt: the explanation travels in the rejection, not in the instructions (ADR 0003, options considered).

**What the model sees when it runs out:** nothing. On the fifth rejection and on budget exhaustion the loop returns before appending the user message, so no further request is made. The final `tool_result` is written to the trace — a judge can read the rejection the model never got — but it is never sent, and it is therefore not part of any request hash (`01-architecture.md` §4.5).

---

## 6. Invariants

**A — five submit attempts.** `ctx.submits` increments exactly once per handled `submit_record` block, before the handler runs, so a handler that raises cannot give a free attempt (and if one does raise, the outer `try/except` in §1 still writes a `run_end` line). The run ends with `max_submits` when a rejection arrives at `ctx.submits >= cfg.max_submits`. An accepted submit at attempt 5 is a success: the check is on rejection, not on the counter alone. Both arms carry the same limit (ADR 0003 item 2 — the retry ramp the original plan wanted does not exist on this model, so five attempts at fixed settings replaced it in *both* arms).

At most one `submit_record` per assistant turn is handled. Parallel tool use permits two in one batch, and the loop deliberately leaves parallel calls on; without a rule, both would be dispatched, both would burn an attempt, both might run the verifier, and the last accepted record would silently win. The second and any later `submit_record` block in the same batch returns `is_error: true` with `SECOND_SUBMIT` — `{"accepted": false, "reason": "one submit_record per turn"}` — and does not increment `ctx.submits`. The attempt counter stays meaningful and the accepted record stays unambiguous.

**B — tool-call budget.** `ctx.tool_calls` increments once per dispatched block, `submit_record` included, and the check runs before each dispatch. A parallel batch is not atomic: if the budget runs out at the third of five calls, the first two results are traced, the run stops, and no partial user message is ever sent. The budget is 60 for synthetic cases and 120 for real ones (contract §Budgets), selected in `config.py` from the case kind, never from the arm — a budget that differed by arm would be a resource difference between arms and would have to be explained in the README (AGENTS.md §Eval rules).

Both invariants live in `art30/loop.py` and nowhere else. Neither arm can raise its own limit, and the verifier cannot ask for another round.

---

## 7. The gate

Fires once, after acceptance, before render, harness-driven and never model-initiated (contract §Run phases 3). `arm.gate` returns `None` for the baseline and a `Decision` for the advanced arm. The risk rating comes from the accepted record, by the contract's rule: `high` if any store is `not_erased`, `pseudonymised`, `external_manual`, `no_schedule_evidenced` or `unverified` while carrying an `identifier` or `contact` field; `medium` if every store reaches erasure but at least one only after a timer; `low` otherwise. The gate fires at every rating — a low-risk record still gets a human — and the rating is recorded so the trace shows what triggered it.

`--approve ask` prints the summary (stores, verdicts, the legal cells left empty), reads one line per `third_party` store and then one keystroke, in that order. `--approve auto` records `by: "simulated"` and approves; that is the eval path, used for 42 advanced runs, and REPRODUCE.md says so plainly. Rejection ends the run with `gate_rejected`, which counts as a failure, not as a missing result.

**The gate is also where `recipient_kind` is set.** The contract says stores of kind `third_party` carry `recipient_kind: unknown | internal | processor | external_controller`, default `unknown`, "set by the human at the gate. The agent may never set it." An approve/reject gate has no mechanism for that, and an engineer building from these two documents would have to invent one, so `Decision` carries `edits: dict[str, str]` (`01-architecture.md` §1.3). Before the approval keystroke and only under `--approve ask`, the terminal asks one question per `third_party` store — four options, default `unknown` on an empty line — and the answers are applied to the record by `apply_edits` before render and summarised in the `checkpoint` line. The order is the printed one: `10-instructions.md` §5 owns the template and puts the recipient block above `You are approving a document you will sign. Render it? [y/N]`, and `07-ui.md` §3 prints it that way. Nobody should be asked to complete cells in a document they have already approved, and a rejection discards the answers with the record, so `apply_edits` has something to apply only on the approving path. Under `--approve auto` no question is asked, `edits` is empty, `recipient_kind` stays `unknown`, and the render prints "requires human completion" for it. That is the state of all 42 eval-mode records, including the Stripe row in `example-record-S10.md`, and the demo is the one place the filled value is shown.

The checkpoint is a trace line, not a tool call to the model: the model never learns whether a human approved, because by then its work is done.

---

## 8. Request shapes

### Step 1

```jsonc
{
  "model": "claude-opus-5",
  "max_tokens": 16000,
  "thinking": {"type": "adaptive", "display": "summarized"},
  "output_config": {"effort": "high"},
  "system": [
    {"type": "text",
     "text": "<art30/prompts/system.md, taxonomy.md spliced at the include marker>",
     "cache_control": {"type": "ephemeral"}}
  ],
  "tools": [
    {"name": "list_tree",  "description": "...", "strict": true,
     "input_schema": {"type": "object",
       "properties": {"path": {"type": "string"}, "max_depth": {"type": "integer"}},
       "required": ["path", "max_depth"], "additionalProperties": false}},
    {"name": "read_file",  "description": "...", "strict": true,
     "input_schema": {"type": "object",
       "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"},
                      "end_line": {"anyOf": [{"type": "integer"}, {"type": "null"}]}},
       "required": ["path", "start_line", "end_line"], "additionalProperties": false}},
    {"name": "grep",       "description": "...", "strict": true, "input_schema": {...}},
    {"name": "submit_record", "description": "...", "strict": true,
     "input_schema": {"type": "object",
       "properties": {"record": { /* art30/schema/record.schema.json, inlined */ }},
       "required": ["record"], "additionalProperties": false}}
  ],
  "messages": [
    {"role": "user", "content": [
      {"type": "text",
       "text": "Scan target: S10\n\nEvery path you cite is relative to the repository root, and every line number is 1-based. `repository` in the record is the name the code gives itself, not this label.\n\nDraft the Art. 30 record and the erasure table for this repository, then submit it with submit_record.\n\nBudget for this run: 60 tool calls and 5 submit_record attempts. Exceeding either ends the run with no record.\n\nNobody is watching this run and no one can answer a question before it ends. Before you end a turn, read your last paragraph: if it is a plan, a question or a promise about work you have not done, do that work now with a tool call instead.",
       "cache_control": {"type": "ephemeral"}}
    ]}
  ]
}
```

That message is `FIRST_TURN` from `10-instructions.md` §3 rendered with `repo_name="S10"`, `tool_call_budget=60`, `submit_budget=5`, quoted here in full rather than abbreviated. Two normative documents describing the same bytes differently is how a committed step-1 hash constant comes to pass for the author and miss for everyone else, so where they differ, `10-instructions.md` §3 holds the template and this section holds the rendering.

Fixed points that the hash depends on, in order: tools appear in the literal order `list_tree`, `read_file`, `grep`, `submit_record` — never sorted, never built from a dict or a set. `additionalProperties: false` is required for all objects under `strict: true` (`shared/tool-use-concepts.md` §JSON Schema Limitations). Listing every property in `required` is **not** an API rule; it is `00-contract.md` §Tools' own convention ("`strict: true` (`additionalProperties: false`, all `required` listed)"), adopted here so the model's tool inputs are shape-stable across steps and the request bytes for one intent do not vary with which optional keys the model chose to send. An optional argument is therefore a nullable required property, not an omitted key: `end_line` is `{"anyOf": [{"type": "integer"}, {"type": "null"}]}` — `anyOf` is supported in strict schemas (same section) — with `null` documented in the tool description as "to end of file (capped at 400 lines)". No `temperature`, `top_p`, `top_k`: those return 400 on this model (`shared/error-codes.md` §400 Validation Errors). No `tool_choice`: the model decides, and forcing a tool would change the loop's meaning.

### Step k

```jsonc
{
  "model": "claude-opus-5", "max_tokens": 16000,
  "thinking": {"type": "adaptive", "display": "summarized"},
  "output_config": {"effort": "high"},
  "system": [ /* byte-identical to step 1, marker still on the last block */ ],
  "tools":  [ /* byte-identical to step 1 */ ],
  "messages": [
    {"role": "user", "content": [{"type": "text", "text": "Scan target: S10\n\nEvery path ...",
                                  "cache_control": {"type": "ephemeral"}}]},   /* breakpoint C */
    {"role": "assistant", "content": [
      {"type": "thinking", "thinking": "...", "signature": "..."},
      {"type": "text", "text": "Reading the models and the account route."},
      {"type": "tool_use", "id": "toolu_01A...", "name": "read_file",
       "input": {"path": "models.py", "start_line": 1, "end_line": 120}},
      {"type": "tool_use", "id": "toolu_01B...", "name": "read_file",
       "input": {"path": "api/account.py", "start_line": 1, "end_line": 120}}
    ]},
    {"role": "user", "content": [
      {"type": "tool_result", "tool_use_id": "toolu_01A...", "content": "1: from sqlalchemy..."},
      {"type": "tool_result", "tool_use_id": "toolu_01B...", "content": "1: from fastapi...",
       "cache_control": {"type": "ephemeral"}}
    ]}
  ]
}
```

Two markers sit in `messages` and nowhere else: B on the last block of the newest user turn, C on the last block of the previous user turn (§3). C is a read at distance zero — the previous request wrote a breakpoint at exactly that position — so it costs no extra write and it keeps B's lookback inside the 20-block window however many parallel calls the assistant turn between them carried. Every earlier block is byte-identical to the previous request, which is the whole basis of the cache and of replay.

---

## 9. A worked trace

`traces/advanced/S10-s1.jsonl`, the same invented run `06-traces.md` §2 carries in full — `adv-S10-s1-9f3ac1e`, 14 steps, 21 tool calls, 2 submits, 1 verify round, 209 s, $0.41 — abridged here to the lines this document's rules decide: the first step, the grep that reaches two levels down, the rejected submit, the accepted resubmission, the checkpoint and the end. Tool outputs are truncated with `…`; the real file stores them in full. Five documents quote this one run (`04-output-schema.md` §5, `06-traces.md` §2, `07-ui.md` §3, `example-record-S10.md` and this section) and they are refreshed together, from the first real trace, in one commit.

```jsonl
{"type":"run_start","run_id":"adv-S10-s1-9f3ac1e","arm":"advanced","case":"S10","seed":1,"model":"claude-opus-5","effort":"high","mode":"replay","ts":"2026-08-30T14:02:11.004Z"}
{"type":"step","step":1,"phase":"agent","ts":"2026-08-30T14:02:19.882Z","request_id":"req_011CQx7…","reasoning":"Start with the shape of the repository, then the models, then whatever handles account closure.","text":"","tool_calls":[{"id":"toolu_01A","name":"list_tree","input":{"path":".","max_depth":4}}],"tool_results":[{"call_id":"toolu_01A","output":"api/\n  __init__.py  (0 B)\n  account.py  (1204 B)\n  profile.py  (988 B)\njobs/\n  __init__.py  (0 B)\n  backup.py  (742 B)\n  purge.py  (826 B)\napp.py  (311 B)\nconfig.py  (402 B)\ndb.py  (517 B)\nmodels.py  (863 B)\nstorage.py  (1391 B)\nbilling.py  (655 B)\nutils/text.py  (734 B)\nREADME.md  (128 B)\nrequirements.txt  (96 B)","is_error":false,"bytes":412}],"usage":{"input":2314,"cache_read":0,"cache_write":4180,"output":188},"cost_usd":0.0412,"cost_cum_usd":0.0412}
… step 2 elided (reads of models.py and api/account.py, the docstring among them) …
{"type":"step","step":3,"phase":"agent","ts":"2026-08-30T14:02:44.503Z","request_id":"req_011CQx9…","reasoning":"The docstring claims files are removed but close_account only writes deleted_at. Find every delete in the repository before believing either.","text":"","tool_calls":[{"id":"toolu_01D","name":"grep","input":{"pattern":"delete|cleanup|purge","path":".","glob":"*.py"}}],"tool_results":[{"call_id":"toolu_01D","output":"jobs/purge.py:14: def purge_closed_accounts() -> int:\njobs/purge.py:22:         session.delete(user)\nstorage.py:41: def cleanup_user_files(user_id: int) -> None:\nstorage.py:47:     s3.delete_object(Bucket=BUCKET, Key=_avatar_key(user_id))\n","is_error":false,"bytes":298}],"usage":{"input":1655,"cache_read":6082,"cache_write":0,"output":246},"cost_usd":0.0331,"cost_cum_usd":0.1032}
… 9 step lines elided (steps 4–12) …
{"type":"step","step":13,"phase":"verify","ts":"2026-08-30T14:05:02.771Z","request_id":"req_011CQxK…","reasoning":"cleanup_user_files does call delete_object, so the uploads bucket is handled and the docstring is accurate. Drafting the record.","text":"","tool_calls":[{"id":"toolu_01M","name":"submit_record","input":{"record":{"stores":[{"name":"users","kind":"relational","erasure":{"verdict":"erased_after_timer","timer_days":30,"evidence":"jobs/purge.py:22"}},{"name":"uploads","kind":"object_storage","erasure":{"verdict":"erased","evidence":"storage.py:47"}},{"name":"stripe","kind":"third_party","erasure":{"verdict":"external_manual"}},{"name":"nightly_backup","kind":"backup","erasure":{"verdict":"governed_by_retention","timer_days":35}}]}}}],"tool_results":[{"call_id":"toolu_01M","output":"{\"accepted\":false,\"attempt\":1,\"attempts_left\":4,\"schema_errors\":[],\"rejected_claims\":[{\"store\":\"uploads\",\"field\":null,\"claim\":\"erasure.verdict=erased\",\"reason\":\"no path from entry point close_account (api/account.py:12) to any object-storage deletion primitive; cleanup_user_files (storage.py:41) is defined but has no callers\",\"expected\":\"verdict not_erased, or cite the path\"}],\"missing_stores\":[],\"bad_citations\":[],\"unverified\":[]}","is_error":false,"bytes":447}],"usage":{"input":2088,"cache_read":11640,"cache_write":0,"output":1420},"cost_usd":0.0510,"cost_cum_usd":0.3520}
{"type":"step","step":14,"phase":"verify","ts":"2026-08-30T14:05:39.219Z","request_id":"req_011CQxL…","reasoning":"The helper exists but nothing calls it. Checked again with grep: cleanup_user_files appears once, at its definition. Changing the verdict to not_erased and citing the definition as the note.","text":"","tool_calls":[{"id":"toolu_01N","name":"submit_record","input":{"record":{"stores":[{"name":"uploads","kind":"object_storage","erasure":{"verdict":"not_erased","evidence":null,"note":"cleanup_user_files defined at storage.py:41, never called"}}]}}}],"tool_results":[{"call_id":"toolu_01N","output":"{\"accepted\":true}","is_error":false,"bytes":17}],"usage":{"input":2210,"cache_read":13728,"cache_write":0,"output":1602},"cost_usd":0.0580,"cost_cum_usd":0.4100}
{"type":"checkpoint","tool":"request_approval","caller":"harness","risk":"high","summary":"4 stores. uploads NOT ERASED (identifier: avatar_key). stripe EXTERNAL MANUAL (contact: email). nightly_backup GOVERNED BY RETENTION 35 d. users ERASED AFTER TIMER 30 d.","decision":"approved","by":"simulated","wait_s":0.0,"ts":"2026-08-30T14:05:40.004Z"}
{"type":"run_end","stop_condition":"accepted","steps":14,"tool_calls_total":21,"submits":2,"verify_rounds":1,"wall_s":209.0,"cost_usd":0.4100,"record_path":"results/runs/advanced/S10/s1/record.json"}
```

Steps 13 and 14 are the demo's 0:40 beat (`docs/demo-script.md`) and the answer to anticipated question 12: the wrong claim, the reason it was struck, and the revision are three consecutive lines of one file.

Two details are load-bearing and neither is free. The `grep` call at step 3 passes `glob: "*.py"` and gets back `jobs/purge.py:14`, one level down, which only happens under the recursive reading: on this repository `Path('fx').glob('*.py')` returned six root files and `rglob('*.py')` returned eight, the extra two being `fx/api/account.py` and `fx/jobs/purge.py`. Implemented non-recursively, `grep` would hide from both arms exactly the two files S10 and S03 turn on. That does not break fairness — both arms lose them — but it empties the eval of its meaning and it reads in the trace as a model failure. `01-architecture.md` §1.3 fixes the reading as `rglob`; the tool description in `10-instructions.md` §1b and the tool unit tests owe the same. And step 1's `list_tree` output is in name order because §7 of `01` requires every traversal to be sorted before it is emitted — filesystem order would put a different byte string in that `tool_result`, and therefore a different request hash on step 2, on any machine but the one that recorded it.

The `checkpoint` line's `wait_s` is not in the contract yet; `06-traces.md` §1 and `05-eval-harness.md` proposal 1 ask for it (`PROPOSED-CONTRACT-CHANGES.md` P-10) and the line is quoted here as those documents write it.

`run_end` reads `submits: 2, verify_rounds: 1`: two `submit_record` calls, one of which came back `accepted: false` (Decision 15).

---

## Decisions taken here

1. The loop is 80 lines with ten stop paths, all in `art30/loop.py`; no arm and no verifier can end a run. The tenth is an outer `try/except Exception` around the whole body, so an unhandled raise anywhere below `run()` still writes a `run_end` line and stays inside `success + failure == n`.
2. `stop_reason` is inspected before `response.content` in every branch, because a refusal on this model is an HTTP 200 with no usable content.
3. Three cache breakpoints: system always, newest user turn always, previous user turn on every request after the first. The distance breakpoint B walks back is 2N+2, not N, because the assistant turn sits between the two markers; a threshold on N alone fires after the window is already lost. No top-level automatic caching, so every byte of the request is decided by our code.
4. `mark()` copies the message list; stored messages never carry a `cache_control` key.
5. Parallel tool use stays on. One assistant turn with N tool calls is one trace step with N linked results.
6. A rejected `submit_record` returns `is_error: true`. Flipping it is a one-variable experiment if the model starts resubmitting unchanged records.
7. Schema validation runs before the verifier in the advanced arm, so a malformed record costs a cheap error rather than a verifier pass.
8. The submit counter increments before the handler runs; a raising handler cannot buy an extra attempt.
9. The budget check runs per call inside a parallel batch, so exhaustion mid-batch stops the run with the executed results traced and nothing sent.
10. Three consecutive turns with no tool call and no accepted record end the run rather than looping on nudges.
11. `tool_choice` is never set and `disable_parallel_tool_use` is never set.
12. Optional tool arguments are modelled as nullable required properties (`anyOf` integer-or-null, supported in strict schemas), with the absent meaning documented in the tool description and the out-of-range clamping fixed in `tools.py`. The all-required rule is the contract's own convention for shape-stability, not an API requirement; only `additionalProperties: false` is required by the API.
13. The gate is a trace line, not a message; the model never learns the outcome.
14. No compaction and no context editing. A real-repo run peaks near 90k tokens against a 1M window, and rewriting history would break replay.
15. The loop never branches on `arm.name`. `verify_rounds` counts the handled `submit_record` calls that came back `accepted: false` — the reading of `06-traces.md` §1, which its validator check 9 asserts and which `04`, `05` and `07` already use. Counting rejections needs no branch on the arm either: a baseline run rejected on schema errors increments it exactly as an advanced run rejected by the verifier does, so the arm-neutrality argument of `01-architecture.md` §3 survives unchanged, and a baseline that submits once and is accepted reports `submits: 1, verify_rounds: 0` rather than a round that decided nothing. The contract names the field and defines neither reading; `PROPOSED-CONTRACT-CHANGES.md` P-01 asks for this one.
16. At most one `submit_record` per assistant turn is handled; a second block in the same batch returns `is_error: true` and does not spend an attempt.
17. `pause_turn` ends the run with `api_error` and a note naming its own cause. Continuing would re-send a `messages` list ending in an assistant turn, which 400s on this model, so the old defensive branch turned a request-shape bug into an infrastructure-looking failure.
18. `FIRST_TURN` is rendered from `repo_name`, `tool_call_budget` and `submit_budget` and nothing else; `10-instructions.md` §3 holds the template, §8 here holds the rendering, and `config.py` asserts the result carries no `os.sep`-prefixed token.
19. The `--approve ask` gate collects `recipient_kind` per `third_party` store into `Decision.edits`, applied before render. Under `--approve auto` it stays `unknown` and renders as "requires human completion".

## Open risks

1. **Nudge handling is untested against the model.** Three quiet turns ending a run assumes the model does not routinely finish a turn to "think out loud" before submitting. If it does, runs will die at `budget_exhausted` for a cosmetic reason. First live runs settle it; the fix is a prompt line, not a loop change.
2. **`is_error: true` on rejection may push the model toward re-running the tool rather than revising the record.** Cheap to measure, listed as an experiment, but it lands in the primary metric if it goes unnoticed.
3. **Breakpoint C is now unconditional, which removes the threshold guess but not the failure mode.** A single assistant turn carrying more than nine parallel calls still puts B more than 20 blocks from C's position. The symptom is unchanged and visible in the trace: `cache_creation_input_tokens` near full conversation size on every step. The reference's other remedy — an intermediate breakpoint every ~15 blocks inside a long turn (`shared/prompt-caching.md` §20-block lookback window) — needs the fourth marker and is the fix if the first live runs show it.
4. **The model's choice of value for an absent argument no longer changes the bytes, but the clamping is untested.** `end_line: null` is the documented absence and `tools.py` clamps `0`, negatives, and anything below `start_line` to the same thing. If the model instead sends `999999`, the 400-line cap makes it identical to `null` for any file under 400 lines and different for a longer one; the golden-output tool test has to cover that case.
5. **Opus 5 writes longer deliverables than earlier models and verifies its own work unprompted** (`shared/model-migration.md`). Two consequences for the prompt, not the loop: the record may run long enough to approach `max_tokens`, and instructions telling the model to double-check are now counterproductive. The system prompt spec has to know this.
6. **`pause_turn` should not occur at all** (no server-side tools are configured). It is now an explicit stop rather than a resume, because the documented resume works by the API detecting a trailing `server_tool_use` block and this request can never carry one — a `continue` would re-send a `messages` list ending in an assistant turn, and last-assistant-turn prefills still 400 on this model (`shared/model-migration.md` § Migrating to Claude Opus 5). If it ever fires, something in the request is not what this document says it is, and the diagnosis now says that instead of blaming a 400 on the network.
7. **`max_tokens` is a hard cap on thinking plus response text on this model**, and the contract fixes it at 16,000 while the record alone is estimated at 4,000–8,000. A truncation ends the run as a failure and lands asymmetrically — the advanced arm emits the full record up to five times per run, the baseline usually once — so a systematic truncation rate would inflate the advanced arm's failure count against the baseline's. `01-architecture.md` proposal 5 asks to raise it, and it has to be decided before the first recording because `max_tokens` is inside the request hash.
8. **`SECOND_SUBMIT` is a model-facing string that `10-instructions.md` does not yet carry.** It is shared by both arms and lives in `art30/tools.py` with the other invariant strings, but until it is written down there it is a string an implementer invents, which is the same class of problem as the first user message.

## Proposed contract changes

1. **`stop_condition` value `max_tokens`** — same request as `01-architecture.md` proposal 2, repeated here because this document is where the truncation is detected. A record truncated at 16,000 output tokens currently reports as `api_error`.
2. **`stop_condition` value `no_submission`** for a run where the model ends its turn without ever calling `submit_record`. Today it maps to `budget_exhausted`, which reads in the failure table as "ran out of tool calls" and hides a different problem: the model thought it was finished.
3. **Trace `step` line: add `stop_reason` and `request_hash`.** The contract's `step` line records usage, cost, calls and results but not why the turn ended, and not the hash the whole replay layer turns on. `stop_reason` makes truncation, refusal and `pause_turn` visible per step instead of only in `run_end`. `request_hash` is `01-architecture.md` proposal 4: it is the only data path by which the harness can check that the two arms' step-1 requests really are identical, which is the claim the whole comparison rests on. Both cost nothing.

4. **`run_end`: add `note: string|null`.** The loop already passes `note=` on six of its ten exits and the contract's `run_end` line has nowhere to put it. Without the field, `traces/failures/**.diagnosis.txt` can carry only the run id, the stop condition and the trace path — three of the five lines `01-architecture.md` §9 specifies, and thinner than the rubric's "failures are shipped with a one-line diagnosis each". Same request as `01-architecture.md` proposal 6, which also asks for the `crashed` stop condition.
