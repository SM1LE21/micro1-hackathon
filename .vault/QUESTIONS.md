# QUESTIONS

Open decisions waiting on Tun. Mark `[RESOLVED YYYY-MM-DD]` with the answer, never delete.

## Q1 — Which project direction? [RESOLVED 2026-08-28]

**Answer: codebase → GDPR Art. 30 inventory + erasure-path check.** Recorded in `adr/0002`. Baseline is the skill (same model, same read-only tools, same instructions, open loop); advanced arm is the closed loop over a reachability verifier. Eval corpus is mixed: spec-generated synthetic repos with planted traps plus real OSS repos at pinned SHAs. AI Act rule set gated as a Sunday extension (see NON-GOALS).

Original shortlist from the kickoff research (full reasoning in the session report of 2026-08-28):

1. **Verified B2B prospect researcher** — agent finds prospects, a deterministic verifier fetches every claimed page and confirms the contact/signal exists before a lead is accepted; human approval gates the final list. Primary metric: verified-contact precision. Was recommended: strongest fit between rubric, micro1's taste for verification, and Tun's own daily bottleneck. Now the fallback (ADR 0002 kill switch 2), on a synthetic local corpus.
2. **Receipt/invoice extraction with audit gate** — dual-agent extract + independent verify on synthetic receipts; hallucination rate as headline metric. Safest eval design. Dropped: ceiling effect.
3. **Repo due-diligence agent** — twist on the PDF's own example 1; strong skill fit, weaker originality. Dropped: one-rater ground truth, must execute repos.

Added during the Q1 discussion (2026-08-28 evening):

4. **GDPR Art. 30 inventory + erasure-path check** — chosen.
5. **Annotation-quality reviewer** — dropped: statistical rather than agentic, and too close to Tun's own QC IP.
6. **Migration safety reviewer** — reserve.

## Q2 — Video tooling [RESOLVED 2026-08-29]

**Answer: default accepted — QuickTime screen recording + mic.**

What does Tun want to record with (QuickTime screen recording + mic, or something else)? Needed by Sunday, not blocking.

## Q3 — How much of the lived bug story goes in the README? [RESOLVED 2026-08-29]

**Answer: ship the sentence as drafted in `docs/spec/09-narrative.md` §6** ("in a product I run", no product name, no dates, no stack detail).

The "who has this problem" section is strongest with the real anecdote (hand-written report with two statements reversed; soft-delete not reaching object storage for a month). Proposed wording: "in a product the author runs", no product name, no dates, no stack detail. Confirm or tighten. Not blocking; needed before README is written Sunday night. Default if unanswered: ship the sentence as drafted in `docs/spec/09-narrative.md` §6.

## Q4 — Repository licence [RESOLVED 2026-08-29]

**Answer: default accepted — no LICENSE file.** README says the submission is owned by micro1 under the hackathon terms; the prior-art row reads "no licence file".

No `LICENSE` file exists. The prior-art comparison lists this project as "licence: to be decided". micro1 owns the submission under the hackathon terms; whether to also publish under an OSI licence (MIT or Apache-2.0) is your call, not the agents'. Needed before the README's prior-art table is final (Sunday night). Not blocking. Default if unanswered: no LICENSE file; the README says the submission is owned by micro1 under the hackathon terms and the prior-art row reads "no licence file".

## Q5 — Live-API ceiling for the weekend [RESOLVED 2026-08-29]

**Answer: $300, as planned** (ADR 0005 item 4).

`docs/spec/08-plan.md` §3 spends against **$300** (planned $142–$286; Sweeps B and C reserved at $81–$176; three to five changelog iterations depending on the Saturday 15:15 UTC calibration). The figure is an assumption recorded in ADR 0005 item 4. Confirm, raise or lower it; the plan re-derives the iteration count from whatever you set. Not blocking; the first live call is Saturday ~15:00 UTC.

## v1 review

Tun reviewed the v1 concept, research and spec through the review ledger on 2026-08-29 and accepted every card (428 decisions). The specs, ADRs 0002–0005, AMBIGUITIES, NON-GOALS, CASES.md and the plan are the design of record; changes from here go through ADRs and CHANGELOG_EVAL rows.
