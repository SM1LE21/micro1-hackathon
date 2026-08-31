# Video script — the take (3:00–3:30, hard ceiling 5:00)

Recorded 2026-08-31 with QuickTime (⌘⇧5 → record the external display, microphone on). One
continuous take; QuickTime trims ends only, so a mistake means a retake, not a cut. The shots are
ordered as the problem statement orders them (p.7, deliverable 03): problem and simple baseline,
one execution start to finish, the comparison, the changelog, the change that contributed most,
one experiment removed. Every number spoken is on screen at the moment it is spoken. Never say
"compliant". Never speak a number that is not in `results/metrics.json` or on the terminal.

## Pre-flight (10 minutes before the take)

- [ ] Both sweeps finished; `make report` run; README block pasted; everything committed.
- [ ] `uv run art30 serve --open` running (it is: port 8734). Safari at 125%, Run view, brain
      **Claude (your login)**, mode **play back**. The newest finished Claude run is the D01 run
      with the human gate (`results/web/advanced-D01-s1-19858b`). Press Start once now to check
      it streams, set the pace slider to fast, then reload the page.
- [ ] Terminal: font 20pt, dark theme, 120 columns, one tab per command below, each pre-typed
      and not yet run. Working directory the repo root.
- [ ] Editor tabs open: `evals/fixtures/synthetic/S10/api/account.py` (scrolled to line 12),
      `evals/fixtures/synthetic/S10/storage.py` (line 29).
- [ ] Do Not Disturb on. Dock hidden. Nothing with a name in it on screen (`check-clean` words).
- [ ] Read this script aloud once against a stopwatch; it should land at 3:10 ± 15 s.

## Shot list

| Time | On screen | Say |
|---|---|---|
| 0:00–0:15 | `S10/api/account.py` at line 12: `def close_account` and its docstring "Close the account and remove all user data, including uploaded files." Then `storage.py:29` `def cleanup_user_files`. Then in the terminal: `grep -rn cleanup_user_files evals/fixtures/synthetic/S10` → one line, the definition. | "A synthetic repository built to the shape of a bug I shipped. The docstring says closing the account removes the uploaded files. The function that would delete them exists. Nothing calls it. The hand-written record of processing said the files were deleted, for a month." |
| 0:15–0:35 | README section "What bottleneck makes it worth solving?" (scroll slowly; the EDPB and CNIL sentences visible). | "The person with this problem is the technical founder of a small EU SaaS on the day someone asks for the Article 30 record: a lawyer, a buyer, an authority. Writing it is not the hard part; knowing whether it is still true is. The EDPB's 2026 erasure report found controllers who don't even use their record when they handle erasure requests, and CNIL has already fined a company 300,000 euros for deactivating accounts instead of deleting them. Eval case S02 is that decision rebuilt as code." |
| 0:35–0:55 | `skill/art30/SKILL.md` head, then `baseline/arm.py` (short: schema check, nothing else). Then `less results/report.md` is NOT yet shown. | "The simple baseline is the same model, the same instructions, the same three read-only tools and the same five submit attempts, with no verifier and no gate. It is a good skill file, and it ships as one. Everything you are about to see the agent do, the baseline can also do; the difference is whether anything checks it." |
| 0:55–1:15 | Safari: Run view, Simple. Press Start (play back). The card reads *Reading `members/models.py`, `members/views.py`…*, step counter and files read climbing. | "One realistic run, on a Django membership site with avatar uploads. The agent reads the repository the way you would: list the tree, read files, grep. It runs nothing. Every read is a tool call in the trace, and the page is drawing the same JSONL lines a judge reads in `traces/`." |
| 1:15–1:40 | The finding card appears: *1 store not proven erased* — `member.avatar`, object storage, NOT ERASED, `members/models.py:14`, the reason. Click the citation → the source drawer opens on the `ImageField` line. Below: the entry points, the three stores that do reach erasure. | "The verifier accepted the draft and the checkpoint opened. Four stores. The member row, the notes and the orders are erased — cascade, database cascade, a delete in the view — and each verdict cites the line. The avatar is not: deleting the row leaves the file, no signal receiver, no storage delete, no django-cleanup in INSTALLED_APPS. That is my bug, found by reading." |
| 1:40–1:55 | The gate card: risk HIGH, the two buttons, the legal cells listed as *requires human completion*; in play back the recorded decision (approved, by a person, the wait) shows. Then the record card with `Open the rendered record`; open it, scroll section D. | "Before anything renders a person approves. The legal columns are empty on purpose: the agent never writes a legal basis. What it signs is the technical half, and every cell in it points at a line of code." |
| 1:55–2:20 | Terminal: `uv run python skill/art30/scripts/verify.py --repo evals/fixtures/synthetic/D01 --record docs/demo/d01-false-claim.json` → `REJECT   member.avatar · erasure.verdict=erased` and the reason: *no path from entry point admin_delete_model (members/admin.py:7) to any object-storage deletion primitive; member.avatar (members/models.py:14) is a file field; a row cascade does not delete the file* — *expected: verdict not_erased, or cite the path*. | "This is the closed loop, run by hand on the same record with one claim flipped to *erased*. The verifier walks the call graph from the entry point to a deletion primitive for that store, finds no path, strikes the claim and hands back the reason and the line as the tool result the model has to answer. Inside the loop this is `submit_record` being refused; in the skill it is a Stop hook. Deterministic, stdlib `ast`, no model in it." |
| 2:20–2:45 | Terminal: `less results/report.md` — the test table first, then dev. Hold four seconds on each. | "Ten synthetic cases, seven dev and three test, three runs per case, both arms in one window, on my own Claude Code login, so cost is an estimate at list prices from the CLI's token counts. [READ the test F1 row, then the false-safe row, exactly as printed. If the two arms tie, say so: "The two arms tie on F1 and both have zero false safes on this set: with this model the open loop already reads the call graph correctly on these ten repositories. What the verifier changes is not the mean but the floor — every *erased* in the advanced record was proven, not believed."] |
| 2:45–3:05 | `CHANGELOG_EVAL.md` whole table (4 s), then the row named "the change that contributed most" highlighted, then the removed-experiment row. | "One row per experiment, official four columns, with the incident that killed the first sweep kept in. The change that contributed most: [READ its Evidence cell]. The experiment removed: [READ its Decision cell — the lesson, not the removal]." |
| 3:05–3:20 | Terminal: `make eval-replay-local` already run before the take; show its last three lines: `reverified N submissions and M records in K runs, 0 mismatches` · `wrote results/metrics.json` · `eval-replay-local reproduced results/metrics.json`. | "Reproduction needs no key: the verifier re-runs over every recorded submission, the scorer over every delivered record, and the committed `metrics.json` comes back byte for byte. What no one can regenerate is the model's own output, and the guide says so." |
| 3:20–3:30 | README, last section on screen. | "Main failure mode and hot take are the last section of the README. Thanks." |

## If it has to come in at 3:00

Cut 0:15–0:35 to one sentence ("The founder who has to hand this document to a lawyer; CNIL has
already priced getting it wrong at 300,000 euros") and drop the `SKILL.md` half of 0:35–0:55.
Never cut the removed-experiment shot; the problem statement names it.

## After the take

1. QuickTime → File → Export As → 1080p. Watch it once at 1.5× for a name or a key on screen.
2. Upload: YouTube, **Unlisted** (fastest to process a 3-minute 1080p file), or Google Drive with
   "anyone with the link". Paste the URL into the form's Video URL field.
3. Note the URL in `docs/submission.md` and commit.
