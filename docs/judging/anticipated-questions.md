# Anticipated judge questions

Thirty-five questions a judge could ask about this project, with the answer we would give. Every answer is grounded in what is already decided and written down: `.vault/adr/0002-gdpr-inventory-erasure-check.md`, `.vault/adr/0003-runtime-and-api-decisions.md`, `docs/spec/00-contract.md`, `.vault/AMBIGUITIES.md`, `.vault/NON-GOALS.md`, `evals/CASES.md`, `AGENTS.md`. Where an answer depends on a number that does not exist yet, it carries a bracketed placeholder and names the artifact that will fill it.

Written 2026-08-28, hour ~3. Placeholders get replaced from `results/metrics.json` and `CHANGELOG_EVAL.md` after the runs, not before.

---

## Problem and value

**1. Who has this problem, specifically?**

The technical founder of a small EU SaaS who has to hand a record of processing and a deletion guarantee to a co-founder, a lawyer, or a data protection authority (ADR 0002). They wrote the document by hand, months ago, and the code has moved since. The author has been that person: a hand-written record with two statements reversed, and a soft delete that never reached object storage, unnoticed for a month. No product name, client, or dataset from that work enters this repo (AGENTS.md §Competition facts, NON-GOALS).

**2. Article 30(5) exempts organisations with fewer than 250 employees. Is your user even in scope?**

Art. 30(5) is conditional: the obligation stands unless the processing is occasional, carries no risk to the rights and freedoms of data subjects, and involves no special categories [S1]. Whether those conditions are met for a given controller is a legal judgement, and the tool never makes it — that is exactly the class of cell it leaves as "requires human completion" (AMBIGUITIES 8, NON-GOALS: "No legal conclusions"). What the tool produces is the technical half either way, and the erasure half answers Art. 17, which carries no headcount threshold: the controller "shall have the obligation to erase personal data without undue delay" on the listed grounds [S2]. Assumption: the README quotes the exemption and stops there.

**3. Why not use Bearer, Privado, or Fides?**

They solve neighbouring problems and we use the same discovery idea they do. Bearer is a SAST tool to "discover, filter and prioritize security and privacy risks" [S3]. Privado is "an open-source static code analysis tool to discover data flows in the code", mapping personal data from collection point to sinks [S4]. Fides is "an open-source privacy engineering platform for managing the fulfillment of data privacy requests in your runtime environment" [S5]. None of them answers the question this tool answers: when `close_account` runs, does a static call path exist from it to a deletion primitive for *this* store, and if not, which line proves it. Discovery is the part we treat as a heuristic (AMBIGUITIES 7); the erasure verdict with `file:line` evidence is the part that is missing.

**4. Why an LLM at all? This looks like a static analysis problem.**

Two thirds of it is, and that two thirds runs statically. The part that is not: deciding what counts as personal data. Art. 4(1) defines it as "any information relating to an identified or identifiable natural person" [S6], which for a codebase means judging a `notes` column with a comment saying it may contain phone numbers, a `metadata` JSON blob, an IP address written into a log line. Case S07 plants exactly those three. Drafting a record a person will sign is judgement too. The reachability claim is where a model is least reliable, and that is the part it does not get to decide.

**5. Is this legal advice?**

No, by construction. Purpose, legal basis, and risk class are never filled by the agent; those cells render "requires human completion" (AMBIGUITIES 8, NON-GOALS). The word "compliant" appears nowhere in the output. The tool reports what the code does with a line number attached, so a lawyer disagrees with a reading of the code rather than with an invisible inference. A wrong legal basis is the most harmful sentence this tool could write, so it cannot write one.

**6. What does the user actually do with the output?**

Two things. Hand the technical half of the Art. 30 record to whoever asked for it, with the legal columns still open for the person qualified to fill them. Then work the erasure table: every row marked `not_erased` or `external_manual` is a bug or a manual step, with the evidence line already attached. The tool never edits the code and never opens a PR (NON-GOALS: "No fixing the code"). Cost comparison for that second job today: [minutes to hand-label one repo, from the CASES.md labelling protocol] against [advanced arm runtime per case].

**7. Why erasure rather than access requests or consent tracking?**

One slice had to fit in 75 hours, and Art. 15 export is explicitly out (NON-GOALS) even though it reuses the same inventory. Erasure was chosen because it is the claim in a hand-written record most likely to be false, and because it has a crisp deterministic check underneath it: a call path exists, or it does not. Consent tracking has no equivalent check that does not become an opinion.

---

## Agent engineering

**8. Isn't this just a skill for Claude Code?**

That is precisely the baseline, on purpose (ADR 0002). Same model, same read-only tools, same instruction text, open loop, five attempts. A skill is instructions the model may follow; it cannot reject the claim "user data is deleted in `delete_user()`" after the model has read `deleted_at = now()`. The verifier rejects it regardless of what the model wrote. So the changelog answers "what does a closed loop add over a good SKILL.md" with numbers: F1 [baseline dev F1] → [advanced dev F1], false safe [baseline FS] → [advanced FS], from `results/metrics.json`.

**9. What does the verifier actually check?**

`path_exists(graph, entry, target, must_pass_through=None)` over a name-based, intra-repo call graph built with stdlib `ast`, with store kinds, deletion primitives, and recipient SDKs as data rather than code. An erasure claim survives only if a static path runs from the erasure entry point to a deletion primitive for that store. Django `on_delete=CASCADE` counts for relational rows; `FileField` and `ImageField` need an explicit storage delete on the path (AMBIGUITIES 13), because Django's own documentation says "when a model is deleted, related files are not deleted" [S7]. It is four files under `art30/verify/` — `callgraph.py`, `rules.py`, `reach.py`, `check.py` — plus the rule sets as YAML, each file under ~300 lines (`docs/spec/00-contract.md` §Repository layout).

**10. Can the model just retry until the verifier passes?**

The verifier does not score the answer, it rejects the claim and says why (`docs/spec/00-contract.md` §Feedback object: the rejected claim, the reason, and what it expected instead). A claim with no static path cannot be accepted at all: the model either revises it to `not_erased` or `unverified` with the evidence line, or burns its five `submit_record` attempts and the run is recorded as a failure (`stop_condition: max_submits`, contract §Budgets). Unresolvable edges — dynamic dispatch, decorator magic, missing imports — become `unverified` and count as not-reaching in the false-safe row (AMBIGUITIES 14). Looping cannot manufacture a path, so the cheapest way out is to report the miss.

**11. Why a single-threaded loop and no orchestration?**

The PDF's own line: "Purposeful choices matter more than the number of components" (p.2). The task splits into phases with one goal (scan, classify, draft, verify, gate), not into agents with different goals. NON-GOALS blocks orchestration "unless a measured iteration shows the single-threaded loop failing for a reason orchestration fixes". If that shows up in an eval run it gets a changelog row with a number; otherwise a second agent buys a diagram and costs tokens.

**12. What happens when the model and the verifier disagree?**

The verifier wins, and the disagreement stays visible. The rejection appears in the trace as a tool response and on screen as the CLI prints it (`docs/spec/07-ui.md` §3):

```
  REJECT   uploads · erasure.verdict=erased
           no path from entry point close_account (api/account.py:12) to any
           object-storage deletion primitive; cleanup_user_files (storage.py:41)
           is defined but has no callers
           expected: verdict not_erased, or cite the path
```

The store and the claim are on the first line, the verifier's reason on the continuation lines, and what it expected instead under that; the CLI prints the verifier's strings unchanged. The revised draft follows in the next step. Both the first answer and the reason it was struck are in the trajectory, which is what deliverable 04 asks for and what the demo shows at 0:40 (`docs/demo-script.md`).

**13. Where is the human, and who is qualified to be there?**

A gate before the record renders, appearing in the trace as a tool call annotated with the risk rating that triggered it (AGENTS.md §Trace rules). It covers the erasure entry point the agent discovered, which the human confirms (AMBIGUITIES 3), and the legal cells the agent refused to fill. Ground rules 04 and 05 require it. The qualified reviewer is whoever signs the record; the tool's job is to make that review cheap by putting `file:line` on every cell and by distinguishing ten erasure verdicts instead of yes/no (`erased`, `erased_after_timer`, `anonymised`, `pseudonymised`, `not_erased`, `external_manual`, `no_entry_point`, `governed_by_retention`, `no_schedule_evidenced`, `unverified` — `docs/spec/00-contract.md` §Record vocabulary; the first three are the only ones that count as reaching erasure). Assumption: during batch evaluation the approver is simulated and logged as simulated — the gate fires on 42 advanced-arm runs and nobody approves those by hand — while the demo path uses a real prompt. `--approve auto` records `by: "simulated"`, `--approve ask` prompts on the terminal (`docs/spec/00-contract.md` §Run phases 3), and REPRODUCE.md states the difference.

**14. Why not run the target repositories?**

Executing unknown code is a consequential action, and an eval that builds repos measures whether repos build (NON-GOALS, ground rule 04). Static reads keep the run reproducible on a machine with no database, no object store, and no network. The price is honest and visible: what the call graph cannot resolve becomes `unverified` rather than a guess, and the unverified count is a reported row.

**15. Why Python only?**

Seventy-five hours. Django and SQLAlchemy/SQLModel cover the idioms in every fixture and all four real repositories (CASES.md). Anything else is reported "unscanned" rather than guessed (NON-GOALS), which also protects the metric: an unscanned file cannot produce a false safe, only a gap the reader can see. A second language is a rule-set addition, since store kinds and deletion primitives are data, not code.

---

## Evaluation

**16. Why F1 and not accuracy?**

Accuracy over `(store, field, reaches_erasure)` tuples is dominated by true negatives, so a tool that says almost nothing scores well. F1 makes finding stores and not inventing them both cost something, and every manifest carries a negatives list (a `products` table with no personal data) so precision has teeth (CASES.md). A tuple counts as a true positive only when store, field, and the erasure verdict all match, because that combination is what the founder signs.

**17. Why is "false safe" a separate row instead of part of the metric?**

The errors are not symmetric. Claiming `reaches_erasure=true` where the manifest says false is the sentence that gets a founder fined; missing a store is embarrassing. The PDF requires one primary metric, so false safe is a must-be-zero secondary reported for both arms (AMBIGUITIES 9). Expect it to be the headline of the comparison: [baseline false safe] against [advanced false safe] on the test split.

**18. You wrote the synthetic repos and their answer key. Isn't that rigged?**

Partly, which is why they are not the whole set. The generator emits repository and manifest from one spec, so ground truth cannot drift from the fixture, and the planted traps are bug classes that occur in real frameworks: Django not deleting files on cascade [S7], soft delete with no purge job, a `post_delete` receiver registered on the wrong sender. Four real repositories at pinned SHAs are hand-labelled before any agent run, and the test split is where they sit: R03 and R04 alongside the three hardest synthetic cases, S08–S10. If the advanced arm separates only on synthetic cases, the test table shows it: [dev F1] against [test F1].

**19. How was the test set protected?**

Split by repository, and the test split is capped at two live sweeps (AGENTS.md §Eval rules, CASES.md). ADR 0005 spends the first on one sweep carrying both arms in a single recording window and holds the second for a re-record: `report.py` refuses to write `metrics.json` when the two arms' recording windows do not overlap, so a baseline-only sweep on Saturday against a final sweep on Sunday would be unreportable. The baseline arm is frozen before any test case runs, so its cases are uncontaminated by running in the same window. The ledger `results/test-runs.log` is hash-chained and committed, the harness exits 2 on the test split without `--unlock-test` and 3 on a third live sweep unless an ADR names it. R03 and R04 manifests are labelled Saturday morning and those repositories are not opened again until that sweep. The dev/test gap will be real, and the README states the test number is expected to be lower before a judge has to notice.

**20. Who says your hand labels are right?**

A written protocol, timed: vendor at the SHA, editor and grep only, no agent and no verifier, list stores and fields with `file:line`, trace each entry point by hand, cap of two hours per repository, and a repo that hits the cap is dropped rather than half-labelled (CASES.md). Manifests are committed with the SHA before the first agent run on that repository; corrections afterwards go in a dated errata section and apply to both arms. Taking ground truth from the verifier's own output was considered and rejected, because then the metric measures the verifier rather than the agent (AMBIGUITIES 12).

**21. What can the verifier not see?**

Everything outside the Python call graph, and we list it rather than hide it: database-level cascades declared in a migration or the schema rather than the ORM, triggers and stored procedures, deletion driven by an external cron or a queue consumer living in another service, object-store lifecycle rules, versioned buckets where a delete leaves earlier versions readable, and backups, which are inventoried as stores of kind `backup` with their retention timer. AMBIGUITIES 6 puts a backup out of scope for an erasure judgement, and the vocabulary has two verdicts for saying so rather than none: a backup store renders `governed_by_retention` where a schedule is in the code and cited, `no_schedule_evidenced` where there is none, and those are the only two verdicts it can take (contract §Record vocabulary) — never `unverified`, which would fold a finding about a missing schedule into the bucket for calls the parser could not resolve. Dynamic dispatch, decorator semantics, and `getattr` indirection are out by design (NON-GOALS). Everything in the first list renders `unverified` — one of the ten verdicts in `docs/spec/00-contract.md` §Record vocabulary (`erased`, `erased_after_timer`, `anonymised`, `pseudonymised`, `not_erased`, `external_manual`, `no_entry_point`, `governed_by_retention`, `no_schedule_evidenced`, `unverified`), counted as not reaching erasure — so the residual failure mode is a false alarm, not a false safe.

**22. Then couldn't the advanced arm win by marking everything `unverified`?**

It would destroy F1, which is the primary metric: `unverified` counts as not-reaching, so every store that genuinely is erased becomes a wrong tuple. The unverified count is reported as its own row precisely so a judge can check that the false-safe zero was not bought with recall. Read [advanced unverified count] next to [advanced recall].

**23. Three seeds is not many. What about nondeterminism?**

Three seeded runs per case per arm, mean ± std, plus pass^3 reported separately so a judge sees how often an arm is right on all three rather than on average (CASES.md). Temperature is not a determinism control: the API documentation states that "even with `temperature` of `0.0`, the results will not be fully deterministic", and models released after Claude Opus 4.6 reject the parameter outright, with only 1.0 accepted for backwards compatibility [S8]. REPRODUCE.md says this rather than implying a repeatability we do not have.

**24. What does a run cost?**

[USD per case, advanced] and [USD per case, baseline], derived from the per-step `usage` counts recorded in the traces at $5 input and $25 output per MTok, cache write ×1.25 and cache read ×0.1 (`docs/spec/00-contract.md` §API configuration). CASES.md budgeted $20–40 for the full 84 runs against a mid-tier model; ADR 0003 §1 then pinned `claude-opus-5` at high effort, so that estimate is superseded and the measured figure from the traces is the only number quoted (REPRODUCE.md). The baseline arm's retry attempts are billed into its number rather than excluded, because a user pays for retries. Against that sits the human row: [minutes] to hand-label the same repository under the protocol.

**25. Is the baseline a straw man?**

It has the same model, the same read-only tools, the same instruction text, and five `submit_record` attempts per run (AMBIGUITIES 11 for the resource parity, ADR 0003 §2 and `docs/spec/00-contract.md` §Budgets for the attempt count). The only differences are the verifier, the output schema, the completeness guard, and the gate. Verifier calls count as steps in the advanced arm and appear in the reported tool-call counts, so the extra resource the advanced arm gets is visible rather than buried. A straw-man baseline (one prompt over a tree dump, no tools) was considered and rejected on that ground. If the baseline turns out to be strong on the clean cases, that is a finding and it goes in the changelog.

**26. What is a good result, and did you define it before running?**

The PDF requires that, and the target line goes into `evals/CASES.md` before the first baseline run: [target dev F1], [target test F1], false safe zero on test for the advanced arm, and a statement of what makes the artifact unsignable regardless of F1 (a fabricated `file:line`, or a legal cell filled by the agent). It is not committed yet — tracked as gap G-03 in `docs/judging/requirements-matrix.md` — and the commit has to be timestamped before the first run file under `traces/baseline/`.

**27. What did the challenging case reveal?**

S10 plants a soft delete on `close_account`, a purge job that hard-deletes rows after 30 days, avatars in object storage, a `cleanup_user_files()` that is defined and never called, and a docstring claiming the route "removes all user data including files". It asks whether the loop can tell "a deletion function exists" from "a deletion function is reachable", and whether the model believes prose over a call graph. The written note goes into the CASES.md errata section and a `CHANGELOG_EVAL.md` row with trace IDs from both arms after the first runs: [what S10 revealed]. It is the shape of the bug the author shipped.

---

## Reproducibility

**28. Can a judge reproduce the numbers without an API key?**

`make setup && make smoke && make eval-replay`. The replay path regenerates `results/metrics.json` from recorded model responses, so no account with any provider is needed; `docker run --rm hackathon make eval-replay` is the second path for a machine without uv. Live re-runs need a key and take [runtime]. The recording layer is specified in ADR 0003 §6 — every request hashed on its canonical JSON, the response committed to a cache under `evals/cache/`, replay running cache-only and failing loudly on a miss — and is unbuilt as of Friday night.

**29. The real repositories move. What happens to your eval?**

Nothing. They are vendored into `evals/fixtures/real/<name>/` at a pinned SHA with the upstream LICENSE, with `.git`, tests, and docs stripped, and no live web or GitHub API is used at evaluation time (CASES.md, NON-GOALS). Sizes and licences were verified by shallow clone on 2026-08-28 and the SHAs are recorded in CASES.md. Upstream can change; the case cannot.

**30. How long does the whole evaluation take, and what if a run misbehaves?**

Full evaluation is 14 cases × 2 arms × 3 seeds = 84 runs, estimated at roughly 107 minutes at concurrency 4 and $80–$176 live (`docs/spec/01-architecture.md` §10, which supersedes CASES.md's "10–20 minutes" and "$20–40" — see its errata), and replaced by the measured [runtime] in REPRODUCE.md. A replay is minutes and costs nothing. The step budget is 60 tool calls for a synthetic case and 120 for a real one; a run that crashes or exceeds the budget is a failure, never dropped, and `success + failure == n` is printed and stated (AGENTS.md §Evidence discipline). Failed runs ship in `traces/failures/` with a one-line diagnosis each.

**31. How do we know the README numbers came from the committed artifacts?**

Every number is produced by `make report` from `results/metrics.json` and pasted rather than typed, and every claim in README and REPRODUCE cites a file path, test name, or trace ID (AGENTS.md §Evidence discipline). Traces for both arms are committed, failures included. Everything in the repo was created after kickoff on 2026-08-28 15:00 UTC, with the exception of the four vendored open-source repositories, which carry their own licences and recorded SHAs (ground rule 02).

---

## Legal and ethical

**32. Does a user's code leave their machine?**

In this project the inputs are generated fixtures and public repositories, so nothing sensitive moves at all. For a real user the honest answer is that the model reads their source, which is their decision to make; the tool sends code, never records, performs no writes, and executes nothing (NON-GOALS). Fixtures contain schemas and field names, not personal data, which is also what keeps ground rules 06 and 07 satisfied.

**33. Could this tool cause harm when it is wrong?**

The dangerous direction is one-way. A false alarm costs an engineer an hour of reading code; a false safe costs a founder a month of believing files were deleted. That asymmetry is why false safe is a separate must-be-zero row, why unresolved edges render `unverified` instead of a guess, why the legal cells stay empty, and why the artifact never says "compliant". The design is deliberately biased toward saying "I could not prove this".

**34. Why is the AI Act work gated instead of built?**

The same primitive covers it: `path_exists(..., must_pass_through=approval)` maps onto Art. 14(1), which requires that high-risk AI systems "can be effectively overseen by natural persons during the period in which they are in use" [S9]. It also doubles the fixture set and the ontology before a single GDPR number exists, so NON-GOALS gates it behind a locked GDPR test number (target Saturday ~22:00 UTC) and admits it as one changelog iteration. If it cannot be evaluated on planted cases, or does not move a metric, it is removed and the row stays in the changelog as a removed experiment, which is what the PDF asks for on p.3.

---

## Hot take

**35. What is the main failure mode you hit, what did you learn, and what would you build next?**

Failure mode: [the observed failure, with its trace ID from `traces/failures/`, the cause, the fix, and the residual risk accepted]. Written from what actually happened, not picked in advance (HOT_TAKE.md). Candidate lesson, to be earned or discarded by the runs: the model wrote most of the code, and the engineering that mattered was the harness and the verification loop around it; the second thing to watch is evaluation drift, improvements that turn out to be artifacts of the eval rather than the agent. Next, in order: a second language rule set (the rules are data), infrastructure and database evidence so cascades and lifecycle rules stop rendering `unverified`, and the Art. 15 export path, which reuses the same inventory. Not a fixer and not a PR opener; the tool's value is that it does not touch the code.

---

## Sources

| ID | Title | URL | Accessed | Used for |
|---|---|---|---|---|
| S1 | Art. 30 GDPR – Records of processing activities | https://gdpr-info.eu/art-30-gdpr/ | 2026-08-28 | Q2: Art. 30(1)(c),(d),(f) content of the record, and 30(5): "shall not apply to an enterprise or an organisation employing fewer than 250 persons unless… the processing is not occasional…" |
| S2 | Art. 17 GDPR – Right to erasure ('right to be forgotten') | https://gdpr-info.eu/art-17-gdpr/ | 2026-08-28 | Q2: "the controller shall have the obligation to erase personal data without undue delay where one of the following grounds applies" |
| S3 | GitHub - Bearer/bearer: Code security scanning tool (SAST) to discover, filter and prioritize security and privacy risks | https://github.com/Bearer/bearer | 2026-08-28 | Q3: what Bearer is, and its language list (Go, Java, JavaScript, TypeScript, PHP, Python, Ruby) |
| S4 | GitHub - Privado-Inc/privado: Open Source Static Scanning tool to detect data flows in your code | https://github.com/Privado-Inc/privado | 2026-08-28 | Q3: "Privado is an open-source static code analysis tool to discover data flows in the code. It detects more than 110 personal data elements being processed and further maps the data flow from the point of collection to 'sinks' such as external third parties, databases, logs, and internal APIs." |
| S5 | GitHub - ethyca/fides: The Privacy Engineering & Compliance Framework | https://github.com/ethyca/fides | 2026-08-28 | Q3: "an open-source privacy engineering platform for managing the fulfillment of data privacy requests in your runtime environment, and the enforcement of privacy regulations in your code" |
| S6 | Art. 4 GDPR – Definitions | https://gdpr-info.eu/art-4-gdpr/ | 2026-08-28 | Q4: "'personal data' means any information relating to an identified or identifiable natural person ('data subject')…" |
| S7 | Model field reference — Django documentation (FileField) | https://docs.djangoproject.com/en/5.2/ref/models/fields/#filefield | 2026-08-28 | Q9, Q18: "Note that when a model is deleted, related files are not deleted. If you need to cleanup orphaned files, you'll need to handle it yourself…" |
| S8 | Messages — Claude API reference | https://platform.claude.com/docs/en/api/messages | 2026-08-28 | Q23: "Note that even with `temperature` of `0.0`, the results will not be fully deterministic." and "Models released after Claude Opus 4.6 do not support setting temperature. A value of 1.0 of will be accepted for backwards compatibility, all other values will be rejected with a 400 error." |
| S9 | Article 14: Human Oversight — EU Artificial Intelligence Act | https://artificialintelligenceact.eu/article/14/ | 2026-08-28 | Q34: "High-risk AI systems shall be designed and developed in such a way, including with appropriate human-machine interface tools, that they can be effectively overseen by natural persons during the period in which they are in use." |
| L1 | Official problem statement (text extract) | `docs/problem/problem-statement.txt` | 2026-08-28 | Quoted lines on pages 2, 3 and 4 (purposeful choices, removed experiments, one primary metric) |
| L2 | ADR 0002, AMBIGUITIES, NON-GOALS, CASES.md, AGENTS.md | `.vault/`, `evals/CASES.md`, `AGENTS.md` | 2026-08-28 | Every answer's project-internal grounding |
| L3 | ADR 0003 — Runtime and API decisions for both arms | `.vault/adr/0003-runtime-and-api-decisions.md` | 2026-08-28 | Q10, Q13, Q23, Q24, Q25, Q28: model pin, no sampling parameters, five `submit_record` attempts in both arms, record/replay design |
| L4 | 00 — Interface contract | `docs/spec/00-contract.md` | 2026-08-28 | Q9, Q10, Q13, Q21, Q24, Q25: verifier layout, feedback object, budgets, run phases and the gate, record vocabulary, per-step cost |
