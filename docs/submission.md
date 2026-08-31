# Submission form — what goes in each field

Filled in on 2026-08-31 before 17:30 UTC. Deadline 18:00 UTC.

## Title

art30 — a GDPR Article 30 record read out of the code, every erasure claim checked against the call graph

## Description (paste; the editor takes links and bold)

**Who has this problem.** The technical founder of a small EU SaaS on the day somebody asks for the
record of processing — a buyer's lawyer, a customer's DPO, a supervisory authority. The document was
written by hand months ago and the code has moved. I have been that founder: in a product I run the
record had two statements reversed, and a soft delete never reached object storage for a month.

**The bottleneck.** Writing the record is not the hard part; knowing whether it is still true is. The
EDPB's 2026 report on the right to erasure found controllers who do not use their record when they
handle erasure requests; CNIL fined a company EUR 300,000 for deactivating accounts instead of deleting
them. Reading `models.py` against a spreadsheet every sprint is the current fix, and nobody does it.

**What the agent does.** `art30` reads a Python repository with three read-only tools (`list_tree`,
`read_file`, `grep`) and submits a record through a fourth, `submit_record`. The record is the
technical half of Article 30(1): a data inventory store by store and field by field, and an erasure
table — for each store, whether closing an account actually reaches it — with `file:line` on every
cell. Every claim the model submits is re-checked by a deterministic verifier on stdlib `ast` (is there
a static call path from the erasure entry point to a deletion primitive for that store?); a struck
claim comes back as the tool result with the reason and the line, and a person approves at a
checkpoint before anything renders. The legal cells are left empty on purpose; the tool never writes
a legal basis and never says "compliant".

**Baseline and measurement.** The baseline is the same model, the same instruction bytes, the same
tools and the same five submit attempts with the verifier and the gate removed — a good SKILL.md,
which also ships as one. Ten synthetic repositories with planted erasure bugs (7 dev, 3 test), three
runs per case per arm, both arms in one window, on the author's own Claude Code login. Primary metric:
erasure-inventory F1 against a manifest generated from the same spec as the fixture; the row that
matters more is false safes — "erased" where the data stays. The numbers — dev and test, exact McNemar and a
paired bootstrap — are in the README results table and `results/metrics.json`, and every one of them
regenerates with `make eval-replay-local`.

**Reproduce.** `make setup && make smoke && make eval-replay-local` — no API key. The verifier
re-runs over every recorded submission and the scorer over every delivered record, and the committed
`results/metrics.json` comes back byte for byte. Traces for every run, both arms, are in `traces/`;
the coding-agent session that built the repository is in `traces/build-trajectory.html.gz`.

**Links.** Repository: https://github.com/SM1LE21/micro1-hackathon · README (the four questions):
https://github.com/SM1LE21/micro1-hackathon/blob/main/README.md · Reproduction guide:
https://github.com/SM1LE21/micro1-hackathon/blob/main/REPRODUCE.md · Improvement changelog:
https://github.com/SM1LE21/micro1-hackathon/blob/main/CHANGELOG_EVAL.md · Failure mode and hot take:
https://github.com/SM1LE21/micro1-hackathon/blob/main/HOT_TAKE.md

Built solo, 2026-08-28 15:00 UTC to 2026-08-31, with Claude Code as the coding agent (disclosed in
every commit trailer). Public and synthetic data only.

## Video URL

[FILL — YouTube unlisted or Google Drive link, after `docs/video-script.md`]

## Source code (zip ≤ 50 MB)

Built from the final commit so that the zip equals the repository at the tagged SHA:

```
git archive --format=zip -o art30-$(git rev-parse --short HEAD).zip HEAD
```

Tracked files only: `results/runs/`, `traces/` and `results/metrics.json` must be committed before
the archive is cut. Size check: `du -h art30-*.zip` (the tree at 08bf747 archived to 16.6 MB).
