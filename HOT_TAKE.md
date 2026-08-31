# Main failure mode and hot take

## The failure mode we hit

The citation that is one line off. `traces/failures/baseline/S05-s1.jsonl`: the baseline read S05
correctly — six stores, the dead cache-delete helper spotted, every verdict as the manifest has it,
F1 0.90 on the record it submitted — and cited `cache.py:16` as the evidence for `purge_session`,
which is defined at line 15. The renderer re-reads every cited line before it writes the document
and refuses one whose symbol is not on it (`art30/render/`), so the run ended `render_failed` after
75 s and $0.40, with no record for anyone to sign
(`traces/failures/baseline/S05-s1.diagnosis.txt`). The same error in the advanced arm is a
`bad_citations` entry in the tool result the model gets back, and it was fixed in one more attempt
every time it happened (`traces/advanced/S05-s3.jsonl` attempt 2, `S06-s1` attempts 2 and 3).

Cause: line numbers are the one thing a language model reads worst and a document like this needs
most. The check is deterministic and sits in two places — at submit in the closed loop, at render in
both arms — so a wrong line never reaches the page. In the open loop the render check is a wall
rather than feedback, and a baseline run that hits it is a failure, counted as one.

Then the closed loop hit the wall too. `traces/failures/advanced/S08-s1.jsonl`: the verifier
accepted the submission with `bad_citations: []`, and the renderer refused `queue.py:20` for
`email`, which sits on line 19 inside a dictionary literal spanning lines 18 to 21. The two places
implement one rule — the symbol must be on the cited logical line — two ways: the verifier takes the
whole `ast` statement that contains the cited line (`art30/verify/citations.py`, `logical`), the
renderer extends the cited line forward by bracket depth and never looks up
(`art30/render/html.py`, `_logical`). A citation to the closing brace of a multi-line literal passes
the first and fails the second. On S08 that gap killed all three advanced runs — the verifier said
`bad_citations: []`, the renderer refused the same record — and every one of the sweep's eight
failures, both arms, is this one rule at render time (`traces/failures/INDEX.md`: eight rows, one
diagnosis). The fix is one function called from both
places, and it landed after the sweeps (`ff8bfea`, the renderer now reads the statement span the
verifier reads): the numbers stand as measured on the frozen code, and under the fixed renderer
five of the eight refused records render — the three that still refuse are the baseline's own
one-line-off citations, which is the check doing its job.

A second, smaller one, from the local brain: `traces/baseline/S01-s3.jsonl`, where the first
`submit_record` call carried no record object and the second nested the record under a second
`record` key; three attempts, 80 s and $0.41 against 48 s and $0.27 for its siblings. Bounded by the
five-attempt budget and priced per attempt (`00-contract.md` §Budgets). Its summary counter was
wrong in the trace and `make smoke` said so; commit da891dc.

The two defects that cost the most time on the last day were in the harness, not the agent: a
relative path that killed sixty cells in 0.2 s, and the counter above. Both are rows in
[CHANGELOG_EVAL.md](CHANGELOG_EVAL.md), and both were found by the harness's own checks.

## The hot take

**All eight failures in sixty runs were wrong line numbers, none were wrong judgements: the
reliability work was not making the model smarter, it was implementing each deterministic rule
exactly once and wiring its answer back as feedback instead of a wall.**

The verifier never had to strike a call-graph verdict — zero false safes, either arm, either split —
and the F1 comparison is a tie inside its interval (test 0.88 → 0.86, 95% CI −0.06 … +0.02, dev
0.86 → 0.90, CI −0.01 … +0.09). What the closed loop measurably moved is delivery: 27 of 30 records
signed against 25, and the hard case S10 three of three against one of three, because the citation
rule reached the model as `bad_citations` feedback it could answer instead of a render wall it died
on. Where the rule's two implementations disagree (S08), the loop died exactly like the baseline. An
eval built around mean F1 would call this verifier dead weight; what it buys is the floor — every
`erased` a proven path, every unresolvable call an `unverified`, and delivery under the same rule
that kills the open loop.
