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

## Q2 — Video tooling

What does Tun want to record with (QuickTime screen recording + mic, or something else)? Needed by Sunday, not blocking.

## Q3 — How much of the lived bug story goes in the README?

The "who has this problem" section is strongest with the real anecdote (hand-written report with two statements reversed; soft-delete not reaching object storage for a month). Proposed wording: "in a product the author runs", no product name, no dates, no stack detail. Confirm or tighten. Not blocking; needed before README is written Sunday night.

## Q4 — Repository licence

No `LICENSE` file exists. The prior-art comparison lists this project as "licence: to be decided". micro1 owns the submission under the hackathon terms; whether to also publish under an OSI licence (MIT or Apache-2.0) is your call, not the agents'. Needed before the README's prior-art table is final (Sunday night). Not blocking.
