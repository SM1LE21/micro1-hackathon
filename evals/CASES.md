# Eval cases — proposal (ADR 0002)

Status: proposed 2026-08-28, before any harness or solution code. Manifests and fixtures get built from this file; the file is then frozen except for a dated errata section at the bottom.

## Rules

- Same cases, same instructions, same read-only tools for both arms. The advanced arm's verifier calls count as steps and are reported.
- Split by repository. Dev is iterated on; test is touched twice (baseline once, final once).
- 3 runs per case per arm, labelled s1–s3. Mean ± std. The model exposes no sampling parameters and no seed; the three runs measure sampling variance (ADR 0003).
- Every manifest is committed before the first agent run on that repository. Corrections after that go into the errata section with a date and apply to both arms.
- `success + failure == n` reported per arm. Runs that crash or exceed the step budget are failures, never dropped.

## Primary metric

A **tuple** is `(store, field, reaches_erasure)`.

- *store*: a named place personal data lives — relational table, object-storage bucket/prefix, cache namespace, search index, queue payload, third-party service, log sink, backup target.
- *field*: a personal-data attribute in that store. For third-party, log, cache and queue stores the field is what is sent or written (e.g. `email`).
- *reaches_erasure*: `true` if the verdict is `erased`, `erased_after_timer` or `anonymised`; `false` for `pseudonymised`, `not_erased`, `external_manual`, `no_entry_point`, `governed_by_retention`, `no_schedule_evidenced`, `unverified`.

Names are normalised (snake_case, table prefixes stripped) before matching. A predicted tuple is a true positive only if store, field and `reaches_erasure` all match the manifest. Per case: precision, recall, F1. Aggregate: mean F1 across cases, dev and test reported separately.

Secondary rows, all reported, never folded into F1:

| Row | Definition |
|---|---|
| False safe | predicted `reaches_erasure=true` where the manifest says `false`. Must be zero on test for the advanced arm; reported either way. This is the error that gets a founder fined. |
| Pass | F1 = 1.0 and false safe = 0 for that run |
| pass^3 | pass on all three seeds |
| Regressions | cases that passed in the previous changelog iteration and fail in this one |
| Unverified | tuples the advanced arm rendered `unverified` (count) |
| Human time per task | minutes to hand-label a real repo under the protocol below (the manual process) |
| Cost per task | USD from per-step token counts in the trace |
| Turns, tool calls | per run, from the trace |

Fine-grained verdicts and retention timers are rendered in the artifact and checked in the manifest, but they are not part of F1. One primary metric.

## Definition of a good result (written before any run)

For the founder who signs the record: nothing in it is wrong, nothing that the code evidences is missing, and no store is called erased when the code does not erase it.

Targets, committed before the first baseline run:

- Advanced arm, dev: mean F1 ≥ 0.85. Test: mean F1 ≥ 0.75 (real repos are in test and will be harder).
- Advanced arm, false safe: 0 on test, 0 on dev. One false safe on test is a headline failure regardless of F1 and goes in HOT_TAKE.md.
- pass^3 on at least half the dev cases.
- Unsignable regardless of score: any legal cell filled by the agent, any claim without `file:line`, the word "compliant" anywhere in the record.
- Baseline: no target. It is measured, not tuned. If the baseline matches the advanced arm on F1 and false safe, that result is reported as the finding.

Statistics: the significance test runs on the binary `pass` row (exact McNemar over paired cases, each case's outcome = majority of its three runs); F1 differences carry a paired bootstrap 95% interval over cases. README's "exact McNemar" sentence refers to `pass` only.

## Manifest shape (one per case)

```yaml
case: S10
split: test
source: synthetic          # or real
entry_points:
  - {name: close_account, file: api/account.py, line: 12, kind: route}
stores:
  - name: users
    kind: relational
    subject_link: {file: models.py, line: 9}   # the citation that ties the store to a data subject; nullable
    fields:
      - {name: email,     category: contact,    file: models.py, line: 14}
      - {name: full_name, category: identifier, file: models.py, line: 15}
    erasure: {verdict: erased_after_timer, timer_days: 30, evidence: jobs/purge.py:22}
  - name: uploads
    kind: object_storage
    fields:
      - {name: avatar_key, category: identifier, file: storage.py, line: 9}
    erasure: {verdict: not_erased, evidence: null,
              note: "cleanup_user_files defined at storage.py:41, never called"}
  - name: stripe
    kind: third_party
    recipient_kind: unknown          # human sets at the gate; never the agent
    fields:
      - {name: email, category: contact, file: billing.py, line: 30}
    erasure: {verdict: external_manual, evidence: null}
  - name: nightly_backup
    kind: backup
    fields:
      - {name: email, category: contact, file: jobs/backup.py, line: 8}
    erasure: {verdict: governed_by_retention, timer_days: 35, evidence: jobs/backup.py:12}
retention:
  - {store: users, category: contact, days: 30, file: jobs/purge.py, line: 22}
  - {store: users, category: financial, criteria: "kept for the statutory accounting period", file: null, line: null}
negatives:                 # tables with no personal data; predicting them costs precision
  - products
```

Field categories: `identifier · contact · financial · behavioural · free_text_may_contain · technical`. Same taxonomy in the agent's output schema.

## Synthetic cases

Built by a spec-driven generator (`evals/fixtures/gen.py`, to be written): one YAML spec per case produces both the repository and its manifest, so the ground truth cannot drift from the fixture. Each repo is 8–15 Python files: `models.py`, `api/account.py`, `storage.py`, `billing.py`, `jobs/`, `middleware.py`, plus one or two files with no personal data at all. Two flavours: SQLAlchemy (S01–S07 except S06) and Django (S06, S09).

| ID | Split | What is planted | Truth | What it tests | Expected baseline behaviour |
|---|---|---|---|---|---|
| S01 | dev | SQLAlchemy `User`/`Order`; hard delete with cascade on the delete route | every store `erased` | precision: no false alarms on a clean repo | correct; establishes the floor |
| S02 | dev | `deleted_at = now()` and nothing else; no purge job | every store `not_erased` | soft delete is not erasure (AMBIGUITIES 4) | says "users are deleted" |
| S03 | dev | soft delete plus `jobs/purge.py` that hard-deletes rows older than 30 days | `erased_after_timer`, timer 30 d cited | multi-hop path route → job; retention timer parsing | finds the job or not; timer usually uncited |
| S04 | dev | avatars in object storage via a boto-style client; delete route calls `delete_object` | `erased` incl. uploads | object-store primitive detection | correct or vague ("files are cleaned up") |
| S05 | dev | Stripe customer created with email; Redis session cache keyed by email; analytics events with email; delete route removes rows only; transactional mail SDK imported and used | rows `erased`; stripe `external_manual`; cache and analytics `not_erased`; mail is a recipient, not a store | third-party recipients (AMBIGUITIES 7); non-relational stores; multiple misses in one repo | reports the DB, forgets the cache and analytics, calls Stripe "handled" |
| S06 | dev | Django: FK `on_delete=CASCADE`, `ImageField` avatar, `post_delete` receiver on the right sender deleting the file | every store `erased` | Django cascade semantics and signal-wired file deletion (AMBIGUITIES 13) | usually correct; may not cite the receiver |
| S07 | dev | `notes` text on a support ticket with a comment "may contain phone numbers"; `metadata` JSON on `User`; `ip_address` written in a middleware log line; a `Product` table with no personal data | the three hidden fields are personal data; `products` is a negative | semantic classification a grep cannot do; precision on the negative | misses at least one hidden field; sometimes lists `products` |
| S08 | test | five stores, no deletion feature anywhere (no route, no CLI, no admin) | every store `no_entry_point` | the agent must say "there is no way to delete a user" rather than invent one; completeness guard | invents a path or hedges |
| S09 | test | Django decoy: a `post_delete` receiver that deletes files exists but is registered for a different sender (`Comment`, not `Avatar`) | rows `erased`; uploads `not_erased` | the verifier must check the receiver's sender, not just its existence | "files are deleted on delete via signals" |
| **S10** | **test** | **The hard case.** Soft delete on `close_account`; `jobs/purge.py` hard-deletes rows after 30 days; avatars in object storage; `cleanup_user_files()` defined in `storage.py` and never called; `close_account` docstring says "removes all user data including files"; Stripe customer never deleted | rows `erased_after_timer`; uploads `not_erased`; stripe `external_manual` | existence vs reachability; a docstring that contradicts the call graph | reads the docstring and the helper, reports uploads as deleted — a false safe |

### What S10 is designed to reveal

Whether the loop distinguishes "a deletion function exists" from "a deletion function is reachable from the entry point," and whether the model trusts a docstring over a call graph. It is the shape of the bug the author shipped: the purge job cleaned the database on schedule, the object store kept every file, and the hand-written record said otherwise for a month. The PDF asks for a written note on what the challenging case revealed; that note is written after the first runs, in the errata section here and in `CHANGELOG_EVAL.md`, with the trace IDs.

## Real cases

Vendored at the pinned SHA under `evals/fixtures/real/<name>/` with the upstream LICENSE file, `.git`, tests and docs stripped. Sizes and licences verified 2026-08-28 by shallow clone; not vendored yet.

| ID | Split | Repository | SHA | Licence | Non-test .py | Why this one | Expected shape |
|---|---|---|---|---|---|---|---|
| R01 | dev | `fastapi/full-stack-fastapi-template` | `486f054` | MIT | 43 (all) | SQLModel `User`/`Item`; `delete_user_me` and `delete_user` routes; `sentry_sdk` as a possible recipient | mostly `erased`; whether item cascade and Sentry user context are handled is the labelling question |
| R02 | dev | `flaskbb/flaskbb` | `fc64c74` | BSD-3 | 110 | Flask-SQLAlchemy forum; `User.delete()` is a bare `db.session.delete(self)`, so propagation to posts, topics, private messages and any stored IPs depends on relationship cascade config; also `DeleteUser` admin view and a CLI command — several entry points | partial; the honest answer depends on cascade config the baseline will not read |
| R03 | test | `pinry/pinry` | `05476b1` | BSD-2 | 75 (all) | Django; `Pin` → `User` FK; `ImageField`; `post_delete` receiver on `Pin` deletes the image, a second receiver deletes thumbnails; no in-app account deletion, admin only | if Django admin delete counts as an entry point (AMBIGUITIES 15): cascade → signals → files `erased`. A real positive file case, the mirror of S10. |
| R04 | test | `miguelgrinberg/microblog` | `a975ef6` | MIT | 24 | SQLAlchemy; stores nobody remembers: Elasticsearch post index, Redis/RQ export task that serialises a user's posts, mail, Gravatar (email hash sent to a third party); no account deletion | every store `no_entry_point`; the inventory is the test, the search index is the field most likely missed |
| R05 | reserve (test) | `HackSoftware/Django-Styleguide-Example` | `a70ef43` | MIT | 128 | Django; boto3 S3 uploads in a `files` app; celery; sentry; no account deletion | `no_entry_point`; S3 store must appear in the inventory. Run only if the full eval stays under ~30 min wall-clock. |

Dropped after the size check: `healthchecks/healthchecks` (653 .py) and `MicroPyramid/Django-CRM` (609 .py), both far over the cap.

### Labelling protocol (the manual process; also the human-time row)

1. Vendor at the SHA. Strip `.git`, tests, docs. Keep LICENSE.
2. Start a timer. Editor and grep only — no agent, no verifier.
3. List stores by kind. For each store list personal-data fields with category and `file:line`.
4. Find entry points by convention (routes, views, CLI commands, Django admin). For each store, trace by hand from each entry point to a deletion primitive; record verdict and evidence line, or `no_entry_point` / `not_erased` with a note.
5. Stop the timer. Record minutes in the manifest header.
6. Commit manifest and minutes before any agent run on that repository. Cap: 2 h per repo. If the cap is hit, the repo is dropped, not half-labelled.

Test-set discipline: R03 and R04 manifests are labelled by Saturday morning and the repos are not opened again until the final run.

## Counts and budget

- Core: 14 cases — dev 9 (S01–S07, R01, R02), test 5 (S08–S10, R03, R04). Reserve: R05.
- Of the five test cases, three have no complete erasure path (S08, R04, and S10 partially). Said up front so the false-safe row is read correctly.
- Full eval: 14 × 2 arms × 3 seeds = 84 runs. Synthetic runs ~15–30 tool calls, real ~40–80. Rough cost $20–40 per full eval with a mid-tier model; refined after the first baseline run and recorded in `REPRODUCE.md`. Wall-clock ~10–20 min with cases in parallel.
- Step budget per run: 60 tool calls synthetic, 120 real. Exceeding it is a failure.

## Errata

- 2026-08-28: verdict enum extended after research (`pseudonymised`, `governed_by_retention`, `no_schedule_evidenced`, all on the false side); field-level `erasure` override allowed; retention per `(store, category)`; `recipient_kind` on third-party stores. Sources: docs/research/gdpr-sources.md §3 and §6. Applies before any manifest is written, so no run is affected.
- 2026-08-28 (after the spec pass, ADR 0004):
  1. Cost and time: the "$20–40 per full eval" and "10–20 min" lines are superseded by `docs/spec/01-architecture.md` §10: $80–$176 for one 84-run live sweep, ≈107 min at concurrency 4; an advanced real-repo run $1.85–$3.73 (≈$4.40 with a rejected submit). Replays cost nothing.
  2. Pass also requires `stop_condition == accepted`.
  3. The synthetic set carries 90 tuples (38 reaching, 52 not) after the S10 reconciliation (`docs/spec/fixture-generator.md` §9).
  4. S08 and R04 manifests carry `no_schedule_evidenced` on the backup store and `external_manual` on third-party stores, not `no_entry_point`; `reaches_erasure` is false either way.
  5. The illustrative manifest's null-cited retention row is a shape example only; every submitted retention item carries `file` and `line`. S10's `(users, financial, criteria)` row is dropped — the same table is hard-deleted at 30 days.
  6. S05: the transactional mail service is a `third_party` store under the contract's vocabulary, not "a recipient, not a store".
  7. Failure traces live at `traces/failures/<arm>/<case>-s<seed>.jsonl`.
- 2026-08-28 (ADR 0005): the test split is swept live once, both arms in one recording window (Sweep C, Sunday after the freeze); the second of the two ledger slots is held for a re-record. "Touched twice" reads: at most two live sweeps, the reported comparison from one window. The baseline arm is frozen from Saturday 18:15 UTC before any test case is run.
- 2026-08-28: two rules (`no_entry_point`, `no_schedule_evidenced`) are first exercised on the test split; their dev rehearsal is unit tests under `tests/verify/`; the admin-only entry point is rehearsed on S06 (dev) (`docs/spec/fixture-generator.md` §9).
- 2026-08-28: every manifest store carries `subject_link {file, line}` (nullable); Django file fields are stores of their own named `<model>.<field>` (`docs/spec/fixture-generator.md` §7); the scorer matches a predicted store to a file store by its `declared_at` line when names differ (`docs/spec/05-eval-harness.md` §3).
- 2026-08-29 (before any run; fixture-generator.md §8 freeze rule): the fixtures fixer amended S03 and S10 — purge jobs gain `schedule: "0 4 * * *"` so the job has a registration citation (`03-verifier.md` §6.2: without one nothing runs the job and `users` would be `not_erased`) — and S06/S09 — Django file stores derive `upload_to` from the store identity `<model>.<field>` instead of `key_template` (`fixture-generator.md` §7 rule 1). Manifests regenerated; tuple counts unchanged (90 / 38 reaching / 52 not).
- 2026-08-31 (manifest drop decision, `08-plan.md` §2 row "14:45"): R01–R04 are dropped from the scored evaluation — their hand-labelled manifests were never produced (the labelling was the author's task and the weekend went to the three surfaces instead). The scored sets are dev S01–S07 and test S08–S10; the real repositories stay vendored as demo material the CLI can scan. Reported as a scope reduction in `CHANGELOG_EVAL.md`, not hidden.
