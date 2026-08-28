# Example record — eval case S10, rendered

The target artefact, written by hand before the renderer exists. This is what `record.md` should look like for the hard case (`evals/CASES.md` S10) when the product is finished: the same document the author holds the real output against, and the one on screen at 1:15 of the video. Everything below the rule is the artefact itself, generated from the record in `docs/spec/record.schema.json` shape; nothing in it is prose the model wrote about its own work. File names and line numbers are invented to match the case description and the manifest example in `evals/CASES.md`, and the S10 fixture spec is expected to be generated to match them.

**Reads with** `docs/spec/04-output-schema.md` (which section is which and who fills it), `docs/spec/record.schema.json`, `evals/CASES.md` (S10 and the manifest shape), `docs/writing-rules.md`, `docs/spec/07-ui.md` (the run that produced it), `.vault/AMBIGUITIES.md` rows 4, 6, 7, 8.

**The run this was produced by** is the invented one in `docs/spec/06-traces.md` §2 — `adv-S10-s1-9f3ac1e`, 14 steps, 21 tool calls, 2 submits, 1 verify round, 209 s, $0.41 — the same run `docs/spec/07-ui.md` §3 prints, `docs/spec/02-agent-loop.md` §9 abridges and `docs/spec/04-output-schema.md` §5 carries in `provenance`. When the first real S10 run lands, all five documents are refreshed from that one trace in a single commit.

**Assumption:** S10's fixture is the fifteen-file SQLAlchemy template of `docs/spec/fixture-generator.md` §3.1 — `README.md`, `requirements.txt`, `app.py`, `config.py`, `db.py`, `models.py`, `api/__init__.py`, `api/account.py`, `api/profile.py`, `storage.py`, `billing.py`, `jobs/__init__.py`, `jobs/purge.py`, `jobs/backup.py`, `utils/text.py`. There is no `catalog.py`: §3.1 emits that file only for a model marked `negative: true`, and `evals/fixtures/specs/S10.yaml` declares none, while `jobs/__init__.py` is emitted whenever `jobs[]` is non-empty, which S10's is. The record below is truthful about that repository and about nothing else.

---

# Record of processing — acme_saas

| | |
|---|---|
| Case | S10 (synthetic) |
| Arm | advanced |
| Model | claude-opus-5, effort high |
| Run | `adv-S10-s1-9f3ac1e` |
| Code read | `evals/fixtures/synthetic/S10`, sha256 `9f3c41ab7e02` |
| Instructions | sha256 `c4d81f60a92b` |
| Generated | 2026-08-30 14:05:41 UTC |
| Trace | `traces/advanced/S10-s1.jsonl` |
| Verification | 2 submissions, accepted on attempt 2, rule set `3f9ac1d2` |
| Approved | 2026-08-30 14:05:40 UTC at the terminal, 34 s at the checkpoint, risk HIGH |
| Cost | USD 0.41, 21 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects: account holders — inferred from model name (`models.py:9`).

### users — relational — `models.py:9`

SQLAlchemy model backing the accounts table.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:14` | |
| `full_name` | identifier | `models.py:15` | |
| `signup_ip` | technical | `models.py:17` | |
| `last_seen_at` | behavioural | `models.py:18` | |
| `deleted_at` | technical | `models.py:19` | soft-delete marker; its presence is what the purge job filters on |

### uploads — object_storage — declaration not on a single line

Avatar objects written under the key prefix `AVATAR_PREFIX`.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `avatar_key` | identifier | `storage.py:9` | object key is built from the user id |
| `original_filename` | free_text_may_contain | `storage.py:10` | the uploader's own file name is stored as object metadata |

### nightly_backup — backup — `jobs/backup.py:8`

Full database dump written to the backup bucket.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `jobs/backup.py:8` | carried in the users table of the dump |
| `full_name` | identifier | `jobs/backup.py:8` | carried in the users table of the dump |

### stripe — third_party — `billing.py:30`

Payment processor; a customer object is created at signup.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `billing.py:30` | |
| `name` | identifier | `billing.py:31` | |

Not scanned: `README.md` (not Python), `requirements.txt` (not Python).

## B. Recipients

| Recipient | Fields disclosed | Evidence | Recipient kind |
|---|---|---|---|
| stripe | `email` (contact), `name` (identifier) | `billing.py:30`, `billing.py:31` | UNKNOWN — requires human completion |

Personal data flows into the call at the cited lines. Whether this recipient acts as a processor on the controller's instructions or as an independent controller, and whether a contract under Article 28(3) exists, is not visible in code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| users | all categories | 30 days after `deleted_at` | `jobs/purge.py:14` | requires human completion |
| uploads | all categories | NO TIMER EVIDENCED | — | requires human completion |
| nightly_backup | all categories | 35 days | `jobs/backup.py:12` | requires human completion |
| stripe | all categories | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points: `close_account` — route — `api/account.py:12` (the only deletion surface in the repository).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| uploads | NOT ERASED | `storage.py:41`<br>`api/account.py:13` | `cleanup_user_files` is defined at `storage.py:41` and has no caller in this repository; no path from `close_account` (`api/account.py:12`) reaches `delete_object`; the docstring at `api/account.py:13` states the opposite |
| stripe | EXTERNAL MANUAL | `billing.py:30` | no `Customer.delete` call anywhere in the repository; deletion is an action in the vendor's system |
| nightly_backup | GOVERNED BY RETENTION (35 days) | `jobs/backup.py:12` | dumps older than `RETENTION_DAYS` are removed by the same job |
| users | ERASED AFTER TIMER (30 days) | `api/account.py:31`<br>`jobs/purge.py:14`<br>`jobs/purge.py:22` | `close_account` writes `deleted_at` only; `purge_closed_accounts` hard-deletes rows whose `deleted_at` is older than 30 days |

No erasure verdict is rendered for a store of kind backup. This tool reports the retention schedule it found in code and cites it; whether that schedule and the procedure applied to restored systems are adequate is not visible here.

Object storage: where bucket versioning is enabled, a delete that passes no `versionId` leaves the previous version of the object in place. No versioning declaration was found in this repository.

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| billing | `billing.py` |
| jobs | `jobs/purge.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

| Value | Evidence |
|---|---|
| `eu-central-1` | `config.py:9` |

Security measures. Technical measures under Article 32(1)(a) only, one line each. The organisational half is in section F.

| Measure | Evidence | Symbol |
|---|---|---|
| encryption in transit | `config.py:6` | `sslmode=require` |
| encryption at rest | `storage.py:22` | `ServerSideEncryption` |

## F. Requires human completion

| Cell | Article 30(1) | Value |
|---|---|---|
| Controller — name, contact | (a) | requires human completion |
| Joint controller — name, contact | (a) | requires human completion |
| Representative — name, contact | (a) | requires human completion |
| Data protection officer — name, contact | (a) | requires human completion |
| Purposes of the processing | (b) | requires human completion |
| Confirmation of data-subject categories | (c) | requires human completion |
| Categories of personal data held outside this repository | (c) | requires human completion |
| Recipient kind — stripe | (d) | requires human completion |
| Transfer to a third country — occurs | (e) | requires human completion |
| Transfer to a third country — countries | (e) | requires human completion |
| Transfer to a third country — safeguards | (e) | requires human completion |
| Justification for each retention period | (f) | requires human completion |
| Organisational security measures | (g) | requires human completion |
| Special categories of data (Article 9) | — | requires human completion |
| Legal basis | — | requires human completion |

Processing activities. Article 30 records processing activities; this document records stores. No activity grouping is derived from code. The stores in section A are the input to the fiche below, one copy per activity.

| Fiche field | Value |
|---|---|
| Activity name | requires human completion |
| Purposes | requires human completion |
| Categories of data subjects | requires human completion |
| Categories of personal data | requires human completion |
| Categories of recipients | requires human completion |
| Transfers outside the EU | requires human completion |
| Retention | requires human completion |
| Security measures | requires human completion |

## G. Verification appendix

Claims rejected and what replaced them.

| Round | Store | Claim | Reason | Rendered instead |
|---|---|---|---|---|
| 1 | uploads | `erasure.verdict=erased` | no path from entry point `close_account` (`api/account.py:12`) to any object-storage deletion primitive; `cleanup_user_files` (`storage.py:41`) is defined but has no callers | NOT ERASED |

Stores the record did not contain, found by the scan of the repository.

| Round | Store | Kind | Evidence | Added |
|---|---|---|---|---|
| 1 | nightly_backup | backup | `jobs/backup.py:8` writes the users table into the dump | round 2 |

Citations that did not resolve: none. Claims that could not be decided: none.

## H. Evidence index

| Evidence | Symbol | Sections |
|---|---|---|
| `api/account.py:12` | `close_account` | D |
| `api/account.py:13` | `including uploaded files` | D |
| `api/account.py:31` | `deleted_at` | D |
| `billing.py:30` | `Customer`, `email` | A, B, D |
| `billing.py:31` | `name` | A, B |
| `config.py:6` | `sslmode=require` | E |
| `config.py:9` | `eu-central-1` | E |
| `jobs/backup.py:8` | `email`, `full_name` | A, G |
| `jobs/backup.py:12` | `RETENTION_DAYS` | C, D |
| `jobs/purge.py:14` | `timedelta` | C, D |
| `jobs/purge.py:22` | `delete` | D |
| `models.py:9` | `User` | A |
| `models.py:14` | `email` | A |
| `models.py:15` | `full_name` | A |
| `models.py:17` | `signup_ip` | A |
| `models.py:18` | `last_seen_at` | A |
| `models.py:19` | `deleted_at` | A |
| `storage.py:9` | `AVATAR_PREFIX`, `avatar_key` | A |
| `storage.py:10` | `original_filename` | A |
| `storage.py:22` | `ServerSideEncryption` | E |
| `storage.py:41` | `cleanup_user_files` | D, G |

---

## Decisions taken here

1. The rendered record for S10 covers four stores and eleven fields: `users`, `uploads`, `stripe`, `nightly_backup`, matching the manifest example in `evals/CASES.md` rather than inventing extra stores for a fuller-looking page.
2. Erasure evidence is cited for verdicts that do not reach erasure as well: `uploads` cites the dead helper and the docstring that contradicts it. An empty evidence cell is reserved for the case where there is nothing to point at.
3. The contradicting docstring is a citation (`api/account.py:13`, the line section D and the evidence index both cite), not a sentence in a note. It appears in the evidence index like any other line of code, so a reader can open it.
4. Retention rows exist for every store, including the two with no number in the code, which render `NO TIMER EVIDENCED` with an empty evidence cell. The `(users, financial, criteria)` row of the CASES.md shape example is not rendered: it describes a financial field kept for an accounting period on a table the same fixture hard-deletes at 30 days, and `docs/spec/fixture-generator.md` §9 drops it from the S10 spec for the same reason.
5. A table with no link to a data subject is not in the record, and listing it would cost precision in the score as well as space on the page. S10 does not contain one — it declares no `negative` model, so the fixture has no `catalog.py` and no `products` table — and the case that measures the rule is S07, which does carry a negative table. The rule is stated here because it decides what section A omits on every case, not because this case exercises it.
6. Section F is the longest section. That is the honest shape of this artefact: the machine fills the columns a machine can fill, and the page shows how much is left.
7. The provenance block carries the instruction hash and the fixture sha, so the artefact names the exact code and the exact prompt it came from without a reader opening the trace. It also carries the run id in the hash form (`04-output-schema.md` §Proposed contract changes 2) and the time the approver spent at the gate, which is the number lead decision G-01 reports next to hand-labelling minutes.
8. Each store's `declared_at` renders in its own heading in section A, so the one place a reader meets the store is not the one place its declaration is missing. `uploads` shows the null branch: its key prefix is built in code and no single line declares the bucket.
9. Every Symbol cell in section H is a name or a literal that is on the cited line. The contradicting docstring is cited by a fragment of itself (`including uploaded files`) rather than by a description of it, because the verifier reads the line and looks for the symbol; a prose description would be rejected as a bad citation and, if it reached the renderer, would stop the render (`07-ui.md` §6, `render_failed`).
10. The backup note says what this tool did and did not look at. The regulator sources for the rule (ICO "beyond use", EDPB Issue 6) stay in `04-output-schema.md` §6, where a specification can cite them; the artefact states no rule of its own.
11. Section F carries a row for personal data held outside this repository. Section A is an inventory of one codebase, and a record that does not say so reads as an inventory of the company.

## Open risks

- **The video narration does not match this case.** `docs/demo-script.md` at 0:25–0:40 says "twelve fields, six stores" and describes a `notes` column on a support ticket, which is case S07. S10 as specified has eleven fields and four stores and no support ticket. `07-ui.md` §9 lists that and four more drifts with their timestamps. Either the narration is re-recorded against the real counts, or the S10 fixture spec grows two stores — and growing a test case to fit a voice-over changes the false-safe denominator on the test split. The narration is the cheap side.
- **The retention row's category needs a CASES.md errata line.** `evals/CASES.md`'s illustrative manifest gives S10 `{store: users, category: contact, days: 30}`, a shape that made sense while a second `financial` row existed; `fixture-generator.md` §9 drops that row, which leaves one limit covering the whole table. This document renders `all categories` on that basis. The errata is requested in `04-output-schema.md` §Proposed contract changes 4 and belongs to the lead; until it lands, this cell and the manifest disagree on a field that F1 does not score.
- **Invented line numbers.** Every citation here is a guess about a fixture that does not exist yet. When `evals/fixtures/gen.py` lands, either the generator is written to place these symbols on these lines, or this file is regenerated from the first real run and re-read for tone. The second path risks the target quietly becoming whatever the tool produced.
- **`last_seen_at` as behavioural.** A timestamp on a user row is personal data under AMBIGUITIES row 1 reading B, and its category is arguable — `technical` is defensible. The manifest decides; this file follows it.
- **Table width.** The erasure table's note column is long enough to wrap awkwardly at 80 columns in a terminal preview. It reads correctly in the HTML render and in any Markdown viewer, which is where the document is meant to be read.
