# Main failure mode and hot take

## The failure mode we hit

`traces/baseline/S01-s3.jsonl`. The model's first `submit_record` call carried no record object
(step 5, the MCP server's own refusal: `arguments must carry a record object`). Its second had the
whole record nested under a second `record` key, and the schema check answered with every required
property missing and `'record' was unexpected` (step 6). The third was the same document at the
right depth, and it was accepted (step 7). Three attempts, 80 s and $0.41 at list prices, against
48 s and $0.27 for its two siblings `S01-s1` and `S01-s2`.

Cause: on a local brain the CLI assembles the tool call, and a tool whose single argument is one
large object invites one level of wrapping too many. Nothing in the model's reading of the code was
wrong; the record it finally submitted scored 1.0. What caught it was the two checks in front of the
arm, and what priced it was the rule that every attempt is billed (`00-contract.md` §Budgets).

Fix: none to the model. The five-attempt budget bounds it, the cost column carries it, and
`run_end.verify_rounds` now counts those refusals so the trace's summary agrees with its own lines
(commit da891dc; it did not, and `make smoke` said so). Residual risk accepted: a run that spends all
five attempts on shape ends `max_submits` and ships in `traces/failures/`. [WRITE: how many did, in
this sweep — from `identity_check`.]

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
