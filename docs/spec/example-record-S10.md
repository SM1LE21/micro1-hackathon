# Example record — eval case S10, rendered

The target artefact, written by hand before the renderer exists. This is what `record.md` should look like for the hard case (`evals/CASES.md` S10) when the product is finished: the same document the author holds the real output against, and the one on screen at 1:15 of the video. Everything below the rule is the artefact itself, generated from the record in `docs/spec/record.schema.json` shape; nothing in it is prose the model wrote about its own work. The repository name is `tidewharf`, the package `evals/fixtures/specs/S10.yaml` declares.

**Regenerated 2026-08-29.** Every `file:line` below was re-read out of the committed fixture at `evals/fixtures/synthetic/S10/` and now resolves there; the prose is the original. The provenance rows under the title — run id, the two shas, the timestamps, the gate wait, the cost and the tool-call count — are still the invented run of `docs/spec/06-traces.md` §2 and stay invented until the first real S10 run replaces them. Where that worked run shows a line (`models.py:12 class User`, the four `grep` hits) it now disagrees with the fixture; the fixture wins, and `06-traces.md` §2 is refreshed from the same trace that fills the provenance rows.

**Reads with** `docs/spec/04-output-schema.md` (which section is which and who fills it), `docs/spec/record.schema.json`, `evals/CASES.md` (S10 and the manifest shape), `docs/writing-rules.md`, `docs/spec/07-ui.md` (the run that produced it), `.vault/AMBIGUITIES.md` rows 4, 6, 7, 8.

**The run this was produced by** is the invented one in `docs/spec/06-traces.md` §2 — `adv-S10-s1-9f3ac1e`, 14 steps, 21 tool calls, 2 submits, 1 verify round, 209 s, $0.41 — the same run `docs/spec/07-ui.md` §3 prints, `docs/spec/02-agent-loop.md` §9 abridges and `docs/spec/04-output-schema.md` §5 carries in `provenance`. When the first real S10 run lands, all five documents are refreshed from that one trace in a single commit — and with them every other place the invented run is quoted: `00-contract.md` §Feedback object and the four documents that quote it verbatim (`03-verifier.md` §7.3, `04-output-schema.md` §5, `10-instructions.md` §4, `07-ui.md` §3 and §6), plus `09-narrative.md`, `evals/CASES.md` and `docs/demo-script.md`. The contract line needs an ADR; the rest move with it (`docs/spec/DEVIATIONS.md` D-18).

**Confirmed 2026-08-29:** S10's fixture is the fifteen-file SQLAlchemy template of `docs/spec/fixture-generator.md` §3.1 — `README.md`, `requirements.txt`, `app.py`, `config.py`, `db.py`, `models.py`, `api/__init__.py`, `api/account.py`, `api/profile.py`, `storage.py`, `billing.py`, `jobs/__init__.py`, `jobs/purge.py`, `jobs/backup.py`, `utils/text.py`. There is no `catalog.py`: §3.1 emits that file only for a model marked `negative: true`, and `evals/fixtures/specs/S10.yaml` declares none, while `jobs/__init__.py` is emitted whenever `jobs[]` is non-empty, which S10's is. All fifteen files are on disk. The record below is truthful about that repository and about nothing else.

---

# Record of processing — tidewharf

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

Data subjects: account holders — inferred from model name (`models.py:11`).

### users — relational — `models.py:11`

SQLAlchemy model backing the accounts table.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:14` | |
| `full_name` | identifier | `models.py:15` | |
| `signup_ip` | technical | `models.py:16` | |
| `last_seen_at` | behavioural | `models.py:17` | |
| `deleted_at` | technical | `models.py:18` | soft-delete marker; its presence is what the purge job filters on |

Linked to the data subject at `models.py:11`.

### uploads — object_storage — `storage.py:7`

Avatar objects written to the bucket the `BUCKET` constant names, under keys `avatar_key` builds from the user id.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `avatar_key` | identifier | `storage.py:11` | object key is built from the user id |
| `original_filename` | free_text_may_contain | `storage.py:23` | the uploader's own file name is stored as object metadata |

Linked to the data subject at `storage.py:11`.

### nightly_backup — backup — `jobs/backup.py:8`

Full database dump written to the backup bucket.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `jobs/backup.py:9` | carried in the users table of the dump |
| `full_name` | identifier | `jobs/backup.py:9` | carried in the users table of the dump |

Linked to the data subject at `jobs/backup.py:9`.

### stripe — third_party — `billing.py:11`

Payment processor; a customer object is created at signup.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `billing.py:12` | |
| `name` | identifier | `billing.py:13` | |

Linked to the data subject at `billing.py:11`.

Not scanned: `README.md` (not Python), `requirements.txt` (not Python).

## B. Recipients

| Recipient | Fields disclosed | Evidence | Recipient kind |
|---|---|---|---|
| stripe | `email` (contact), `name` (identifier) | `billing.py:12`, `billing.py:13` | UNKNOWN — requires human completion |

Personal data flows into the call at the cited lines. Whether this recipient acts as a processor on the controller's instructions or as an independent controller, and whether a contract under Article 28(3) exists, is not visible in code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| users | contact | 30 days after `deleted_at` | `jobs/purge.py:10` | requires human completion |
| uploads | — | NO TIMER EVIDENCED | — | requires human completion |
| nightly_backup | contact | 35 days | `jobs/backup.py:12` | requires human completion |
| stripe | — | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

The category cell names the category the timer covers, which is the category the manifest and `evals/fixtures/specs/S10.yaml` carry: `contact`. The other categories held on `users` and `nightly_backup` — identifier, technical, behavioural — carry no timer in this code, and neither does any category on `uploads` or `stripe`, whose rows are synthesised because those stores have no retention item at all.

## D. Erasure

Erasure entry points: `close_account` — route — `api/account.py:12` (the only deletion surface in the repository).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| uploads | NOT ERASED | `storage.py:29`<br>`api/account.py:13` | `cleanup_user_files` is defined at `storage.py:29` and has no caller in this repository; no path from `close_account` (`api/account.py:12`) reaches `delete_object`; the docstring at `api/account.py:13` states the opposite |
| stripe | EXTERNAL MANUAL | `billing.py:11` | no `Customer.delete` call anywhere in the repository; deletion is an action in the vendor's system |
| nightly_backup | GOVERNED BY RETENTION (35 days) | `jobs/backup.py:12` | the job that writes the dump declares `BACKUP_RETENTION_DAYS = 35`; nothing in this repository acts on it |
| users | ERASED AFTER TIMER (30 days) | `api/account.py:15`<br>`jobs/purge.py:14`<br>`jobs/purge.py:18` | `close_account` writes `deleted_at` only; `purge_closed_accounts` hard-deletes rows whose `deleted_at` is older than 30 days |

No `ERASED` or `NOT ERASED` verdict is rendered for a store of kind backup; it carries a retention verdict instead. This tool reports the retention schedule it found in code and cites it; whether that schedule and the procedure applied to restored systems are adequate is not visible here.

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
| `eu-central-1` | `config.py:11` |

Security measures. Technical measures under Article 32(1)(a) only, one line each. The organisational half is in section F.

| Measure | Evidence | Symbol |
|---|---|---|
| encryption at rest | `storage.py:21` | `ServerSideEncryption` |

One row, not two. The fixture's `DATABASE_URL` is `sqlite:///./tidewharf.db` (`config.py:7`) and carries no TLS parameter, so there is no line to cite for encryption in transit and the row is absent rather than empty.

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
| 1 | uploads | `erasure.verdict=erased` | no path from entry point `close_account` (`api/account.py:12`) to any object-storage deletion primitive; `cleanup_user_files` (`storage.py:29`) is defined but has no callers | NOT ERASED |

Stores the record did not contain, found by the scan of the repository.

| Round | Store | Kind | Evidence | Added |
|---|---|---|---|---|
| 1 | nightly_backup | backup | `jobs/backup.py:9` lists the user columns written into the dump | round 2 |

Citations that did not resolve: none. Claims that could not be decided: none.

## H. Evidence index

| Evidence | Symbol | Sections |
|---|---|---|
| `api/account.py:12` | `close_account` | D |
| `api/account.py:13` | `including uploaded files` | D |
| `api/account.py:15` | `deleted_at` | D |
| `billing.py:11` | `Customer` | A, D |
| `billing.py:12` | `email` | A, B |
| `billing.py:13` | `name` | A, B |
| `config.py:7` | `DATABASE_URL` | E |
| `config.py:11` | `eu-central-1` | E |
| `jobs/backup.py:8` | `BACKUP_NAME` | A |
| `jobs/backup.py:9` | `DUMP_COLUMNS`, `email`, `full_name` | A, G |
| `jobs/backup.py:12` | `BACKUP_RETENTION_DAYS` | C, D |
| `jobs/purge.py:10` | `RETENTION_DAYS` | C |
| `jobs/purge.py:14` | `purge_closed_accounts` | D |
| `jobs/purge.py:18` | `session.delete` | D |
| `models.py:11` | `User` | A |
| `models.py:14` | `email` | A |
| `models.py:15` | `full_name` | A |
| `models.py:16` | `signup_ip` | A |
| `models.py:17` | `last_seen_at` | A |
| `models.py:18` | `deleted_at` | A |
| `storage.py:7` | `BUCKET` | A |
| `storage.py:11` | `avatar_key` | A |
| `storage.py:21` | `ServerSideEncryption` | E |
| `storage.py:23` | `original_filename` | A |
| `storage.py:29` | `cleanup_user_files` | D, G |

---

## Decisions taken here

1. The rendered record for S10 covers four stores and eleven fields: `users`, `uploads`, `stripe`, `nightly_backup`, matching the manifest example in `evals/CASES.md` rather than inventing extra stores for a fuller-looking page.
2. Erasure evidence is cited for verdicts that do not reach erasure as well: `uploads` cites the dead helper and the docstring that contradicts it. An empty evidence cell is reserved for the case where there is nothing to point at.
3. The contradicting docstring is a citation (`api/account.py:13`, the line section D and the evidence index both cite), not a sentence in a note. It appears in the evidence index like any other line of code, so a reader can open it.
4. Retention rows exist for every store, including the two with no number in the code, which render `NO TIMER EVIDENCED` with an empty evidence cell. The `(users, financial, criteria)` row of the CASES.md shape example is not rendered: it describes a financial field kept for an accounting period on a table the same fixture hard-deletes at 30 days, and `docs/spec/fixture-generator.md` §9 drops it from the S10 spec for the same reason.
5. A table with no link to a data subject is not in the record, and listing it would cost precision in the score as well as space on the page. S10 does not contain one — it declares no `negative` model, so the fixture has no `catalog.py` and no `products` table — and the case that measures the rule is S07, which does carry a negative table. The rule is stated here because it decides what section A omits on every case, not because this case exercises it.
6. Section F is the longest section. That is the honest shape of this artefact: the machine fills the columns a machine can fill, and the page shows how much is left.
7. The provenance block carries the instruction hash and the fixture sha, so the artefact names the exact code and the exact prompt it came from without a reader opening the trace. It also carries the run id in the hash form (contract §Trace contract, ADR 0004 P-02) and the time the approver spent at the gate, which is the number lead decision G-01 reports next to hand-labelling minutes.
7a. Each store carries its `subject_link` as one line under its table (`04-output-schema.md` §6 A), because the link to a person is what puts the store in this document at all. `users` cites its own model declaration; the other three cite the line where the subject's data arrives.
8. Each store's `declared_at` renders in its own heading in section A, so the one place a reader meets the store is not the one place its declaration is missing. *Amended 2026-08-29:* the fixture as generated does declare the bucket on one line — `BUCKET = "uploads"` at `storage.py:7` — so `uploads` cites it and the null branch is not exercised by this case. The renderer still owes the null branch a shape; S10 no longer demonstrates it.
9. Every Symbol cell in section H is a name or a literal that is on the cited line. The contradicting docstring is cited by a fragment of itself (`including uploaded files`) rather than by a description of it, because the verifier reads the line and looks for the symbol; a prose description would be rejected as a bad citation and, if it reached the renderer, would stop the render (`07-ui.md` §6, `render_failed`).
10. The backup note says what this tool did and did not look at. The regulator sources for the rule (ICO "beyond use", EDPB Issue 6) stay in `04-output-schema.md` §6, where a specification can cite them; the artefact states no rule of its own.
11. Section F carries a row for personal data held outside this repository. Section A is an inventory of one codebase, and a record that does not say so reads as an inventory of the company.

## Open risks

- **The category cell on a store with no retention item is this document's reading.** `04-output-schema.md` §6 C says a null category renders `all categories` and, separately, that a store with no retention item gets a `NO TIMER EVIDENCED` row; it does not say what that synthesised row's category cell holds. Rendering an em dash rather than `all categories` is the choice made here, because "all categories" on a row that evidences nothing reads as a finding about every category. The renderer and 04 owe one sentence agreeing with this or overriding it. F1 scores no retention cell in any case.
- **Line numbers: resolved 2026-08-29.** Every citation was regenerated from the committed fixture by reading it, and each one now carries a symbol that is on the line it names. The risk the first draft of this bullet named — the target quietly becoming whatever the tool produced — was avoided by regenerating against the *fixture*, not against a run: no agent output was consulted, because none exists. What changed materially rather than numerically: `uploads` is declared at `storage.py:7` instead of nowhere, `original_filename` is object metadata at `storage.py:23` rather than a field near the key builder, and the encryption-in-transit row is gone because the fixture's database URL is SQLite with no TLS parameter to cite. The provenance rows are the part still owed a real run.
- **`last_seen_at` as behavioural.** A timestamp on a user row is personal data under AMBIGUITIES row 1 reading B, and its category is arguable — `technical` is defensible. The manifest decides; this file follows it.
- **Table width.** The erasure table's note column is long enough to wrap awkwardly at 80 columns in a terminal preview. It reads correctly in the HTML render and in any Markdown viewer, which is where the document is meant to be read.
