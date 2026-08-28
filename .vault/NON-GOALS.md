# NON-GOALS

What we deliberately do not build, so scope stays fixed. Additions allowed; removals need an ADR.

## Standing

- No product polish beyond what the demo path and eval need.
- No multi-agent orchestration unless a measured iteration shows the single-threaded loop failing for a reason orchestration fixes.
- No live external side effects: consequential actions are sandboxed or simulated, human approval before anything irreversible.
- No private or client data. Public or synthetic only.
- No feature that does not map to a rubric line.

## Slice-specific (ADR 0002)

- No legal conclusions. The tool never states a purpose, legal basis, risk class, or the word "compliant". Those cells are human-only, always.
- No execution of target repositories. Static reads only: no build, no tests, no migrations, no database introspection, no runtime tracing.
- Python only. Django and SQLAlchemy/SQLModel idioms only. Other ORMs, raw SQL beyond simple `DELETE FROM` patterns, JS/TS front-ends: reported as "unscanned", not analysed.
- No type inference, no dynamic-dispatch resolution, no decorator semantics in the call graph. Name-based, intra-repo. Unresolved edges become `unverified`, never a guess.
- No fixing the code. The tool reports the missing `storage.delete`; the human adds it. Opening a PR is a consequential action and out.
- No AI Act rule set in the core. Gated extension: only after the GDPR test-set number is locked (target Saturday 2026-08-29 ~22:00 UTC), as one changelog iteration using the same `path_exists(..., must_pass_through=approval)` verifier. If it cannot be evaluated on planted cases or does not move a metric, it is removed and the row stays.
- No subject-access (Art. 15) export generator. Same machinery, separate scope.
- No live web or GitHub API at eval time. Real repos are vendored at a pinned SHA under `evals/fixtures/real/` with their LICENSE files.
- No more than 5 real repos, none over ~150 non-test Python files, none without an OSI licence (MIT/BSD/Apache). Labelling cap 2 h each.
- No LLM-as-judge anywhere in the primary metric.
- No output formats beyond Markdown (and the validated JSON it renders from). No DOCX, no PDF, no DPA portal integration.
- No English-only apologies: the record is English only.
