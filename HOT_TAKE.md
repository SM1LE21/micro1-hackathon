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
most. Fix: none to the model; the check is deterministic and sits in two places, at submit in the
closed loop and at render in both arms, so a wrong line never reaches the page. Residual risk
accepted: in the open loop the render check is a wall rather than feedback, and a baseline run that
hits it is a failure, counted as one.

A second, smaller one, from the local brain: `traces/baseline/S01-s3.jsonl`, where the first
`submit_record` call carried no record object and the second nested the record under a second
`record` key; three attempts, 80 s and $0.41 against 48 s and $0.27 for its siblings. Bounded by the
five-attempt budget and priced per attempt (`00-contract.md` §Budgets). Its summary counter was
wrong in the trace and `make smoke` said so; commit da891dc.

The two defects that cost the most time on the last day were in the harness, not the agent: a
relative path that killed sixty cells in 0.2 s, and the counter above. Both are rows in
[CHANGELOG_EVAL.md](CHANGELOG_EVAL.md), and both were found by the harness's own checks.

## The hot take

[WRITE after `make report`: one sentence, copied verbatim into README.md's last section. Candidate,
to be kept only if the numbers say so: **A verifier that never fires is still the reason you can
sign.** On ten repositories the open loop and the closed loop [tie / differ by Δ] on F1 and neither
produced a false safe; an eval built around the mean would call the verifier dead weight. It is the
only reason each `erased` in the record is a proven call path rather than a believed docstring, and
the only thing that turns an unresolvable call into `unverified` instead of a guess. Build the
harness so the safety row is the headline, expect a strong model to tie on the mean, and keep the
verifier for the repository you have not tested.]
