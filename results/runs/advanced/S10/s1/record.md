# Record of processing — tidewharf

|  |  |
|---|---|
| Case | S10 (synthetic) |
| Arm | advanced |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `adv-S10-s1-b25adb4` |
| Code read | `evals/fixtures/synthetic/S10`, sha256 `fc7e6e53f234` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 16:16:11 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/advanced/S10-s1.jsonl` |
| Verification | 1 submission, accepted on attempt 1, rule set `e9a260adc28b` |
| Approved | 2026-08-31 16:16:11 UTC without a person (--approve auto), 0 s at the checkpoint, risk HIGH |
| Cost | USD 0.524052 (estimate at list prices), 17 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects: account holders — inferred from model name (`models.py:11`).

### users — relational — `models.py:12`

SQLAlchemy table holding the account holder record.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:14` |  |
| `full_name` | identifier | `models.py:15` |  |
| `signup_ip` | technical | `models.py:16` | IP address recorded at signup. |
| `last_seen_at` | behavioural | `models.py:17` |  |
| `deleted_at` | technical | `models.py:18` | Soft-delete marker the purge job filters on. |

Linked to the data subject at `models.py:11`.

### avatars/ — object_storage — `storage.py:17`

Prefix in the S3 bucket named by BUCKET where avatars are put.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `avatar_key` | identifier | `storage.py:11` | Object key built from the user id, as avatars/<user_id>.jpg. |
| `original_filename` | free_text_may_contain | `storage.py:23` | Filename supplied by the uploader, stored as S3 object metadata. |

Linked to the data subject at `storage.py:12`.

### nightly_backup — backup — `jobs/backup.py:8`

JSON dump of the users table written to DUMP_PATH by dump_database.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `jobs/backup.py:9` | Listed in DUMP_COLUMNS and written to the dump file. |
| `full_name` | identifier | `jobs/backup.py:9` | Listed in DUMP_COLUMNS and written to the dump file. |

Linked to the data subject at `jobs/backup.py:18`.

### stripe.Customer — third_party — `billing.py:11`

Stripe customer created from the user row during signup.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `billing.py:12` |  |
| `name` | identifier | `billing.py:13` | The user's full_name is sent as the Stripe customer name. |

Linked to the data subject at `billing.py:10`.

Not scanned:

- `README.md` (not Python).
- `requirements.txt` (not Python).

## B. Recipients

| Recipient | Fields disclosed | Evidence | Recipient kind |
|---|---|---|---|
| stripe.Customer | `email` (contact), `name` (identifier) | `billing.py:12`, `billing.py:13` | UNKNOWN — requires human completion |

Personal data flows into the call at the cited lines. Whether this recipient acts as a processor on the controller's instructions or as an independent controller, and whether a contract under Article 28(3) exists, is not visible in code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| users | all categories | 30 days rows whose deleted_at is older than the cutoff are deleted | `jobs/purge.py:10` | requires human completion |
| avatars/ | — | NO TIMER EVIDENCED | — | requires human completion |
| nightly_backup | all categories | 35 days | `jobs/backup.py:12` | requires human completion |
| stripe.Customer | — | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points: `close_account` — route — `api/account.py:12` (Sets deleted_at on the user row; its docstring says uploaded files are removed, but the function makes no storage call.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| avatars/ | NOT ERASED | `api/account.py:15`<br>`storage.py:30` | cleanup_user_files deletes the object but no module calls it; close_account and purge_closed_accounts touch only the database. |
| stripe.Customer | EXTERNAL MANUAL | `api/profile.py:14`<br>`billing.py:11` | The repository creates the Stripe customer at signup and contains no call that deletes it. |
| nightly_backup | GOVERNED BY RETENTION (35 days) | `jobs/backup.py:11`<br>`jobs/backup.py:12` | BACKUP_RETENTION_DAYS is defined beside the dump but no code in the repository reads it or removes the dump file. |
| users | ERASED AFTER TIMER (30 days) | `api/account.py:15`<br>`config.py:16`<br>`jobs/purge.py:10`<br>`jobs/purge.py:17`<br>`jobs/purge.py:18` | close_account only writes deleted_at; the Celery beat task purge_closed_accounts deletes rows whose deleted_at is older than RETENTION_DAYS days. |

No erasure verdict is rendered for a store of kind backup; it carries a retention verdict instead. This tool reports the retention schedule it found in code and cites it; whether that schedule and the procedure applied to restored systems are adequate is not visible here.

Object storage: where bucket versioning is enabled, a delete that passes no `versionId` leaves the previous version of the object in place.

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| billing | `billing.py` |
| storage | `storage.py` |
| jobs.purge | `jobs/purge.py` |
| jobs.backup | `jobs/backup.py` |
| api.account | `api/account.py` |
| api.profile | `api/profile.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

| Value | Evidence |
|---|---|
| `eu-central-1` | `config.py:11` |

Security measures. Technical measures under Article 32(1)(a) only, one line each. The organisational half is in section F.

| Measure | Evidence | Symbol |
|---|---|---|
| encryption at rest | `storage.py:21` | `ServerSideEncryption` |
| backup configuration | `jobs/backup.py:11` | `SCHEDULE` |

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
| Recipient kind — stripe.Customer | (d) | requires human completion |
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
| — | — | — | none | — |

Stores the record did not contain, found by the scan of the repository.

| Round | Store | Kind | Evidence | Added |
|---|---|---|---|---|
| — | — | — | none | — |

Citations that did not resolve: none. Claims that could not be decided: 1.

## H. Evidence index

| Evidence | Symbol | Sections |
|---|---|---|
| `api/account.py:12` | `close_account` | D |
| `api/account.py:15` | `deleted_at` | D |
| `api/profile.py:14` | `create_customer` | D |
| `billing.py:10` | — | A |
| `billing.py:11` | `stripe.Customer.create` | A, D |
| `billing.py:12` | `email` | A, B |
| `billing.py:13` | `name` | A, B |
| `config.py:11` | `eu-central-1` | E |
| `config.py:16` | `jobs.purge.purge_closed_accounts` | D |
| `jobs/backup.py:8` | `BACKUP_NAME` | A |
| `jobs/backup.py:9` | `email`, `full_name` | A |
| `jobs/backup.py:11` | `SCHEDULE` | D, E |
| `jobs/backup.py:12` | `BACKUP_RETENTION_DAYS` | C, D |
| `jobs/backup.py:18` | — | A |
| `jobs/purge.py:10` | `RETENTION_DAYS` | C, D |
| `jobs/purge.py:17` | `deleted_at` | D |
| `jobs/purge.py:18` | `session.delete` | D |
| `models.py:11` | — | A |
| `models.py:12` | `users` | A |
| `models.py:14` | `email` | A |
| `models.py:15` | `full_name` | A |
| `models.py:16` | `signup_ip` | A |
| `models.py:17` | `last_seen_at` | A |
| `models.py:18` | `deleted_at` | A |
| `storage.py:11` | `avatar_key` | A |
| `storage.py:12` | — | A |
| `storage.py:17` | `put_object` | A |
| `storage.py:21` | `ServerSideEncryption` | E |
| `storage.py:23` | `original_filename` | A |
| `storage.py:30` | `delete_object` | D |
