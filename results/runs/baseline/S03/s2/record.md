# Record of processing — atlaslane

|  |  |
|---|---|
| Case | S03 (synthetic) |
| Arm | baseline |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `base-S03-s2-5c014a5` |
| Code read | `evals/fixtures/synthetic/S03`, sha256 `6e14bf39f53f` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 15:23:44 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/baseline/S03-s2.jsonl` |
| Verification | 1 submission, accepted on attempt 1 |
| Cost | USD 0.372942 (estimate at list prices), 13 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects: account holders — inferred from model name (`models.py:12`).

### invoices — relational — `models.py:22`

Invoice rows joined to a user by user_id; a comment on the reference column says the purge job does not touch this table.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `billing_name` | financial | `models.py:24` |  |
| `reference` | financial | `models.py:25` |  |
| `amount_cents` | financial | `models.py:26` |  |

Linked to the data subject at `models.py:27`.

### users — relational — `models.py:13`

The user table, written by the account and profile routes.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `id` | identifier | `models.py:14` |  |
| `email` | contact | `models.py:15` |  |
| `full_name` | identifier | `models.py:16` |  |
| `deleted_at` | technical | `models.py:17` | The column the close_account route writes and the purge job filters on. |

Linked to the data subject at `models.py:12`.

### nightly_backup — backup — `jobs/backup.py:10`

A JSON dump of selected user and invoice columns written to a file on disk.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `jobs/backup.py:9` | Named in DUMP_COLUMNS and read off each row with getattr before being written to the JSON file. |
| `full_name` | identifier | `jobs/backup.py:9` |  |
| `reference` | financial | `jobs/backup.py:9` | The invoice reference column, copied into the same dump. |

Linked to the data subject at `jobs/backup.py:18`.

Not scanned:

- `README.md` (not Python).
- `requirements.txt` (not Python).

## B. Recipients

No store of kind third_party was found in the code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| invoices | all categories | no job in the repository selects rows from this table for deletion | `models.py:25` | requires human completion |
| users | all categories | 30 days | `jobs/purge.py:10` | requires human completion |
| nightly_backup | all categories | 35 days | `jobs/backup.py:12` | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points: `close_account` — route — `api/account.py:12` (Sets a deleted_at timestamp on the user row and commits; it issues no delete.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| nightly_backup | GOVERNED BY RETENTION (35 days) | `jobs/backup.py:11`<br>`jobs/backup.py:12`<br>`jobs/backup.py:21` | The module declares a 35-day backup retention and a nightly cron string, but no code in this repository reads BACKUP_RETENTION_DAYS or removes the dump file; dump_database rewrites nightly_backup.json in place. |
| invoices | UNVERIFIED | `config.py:5`<br>`jobs/purge.py:18`<br>`models.py:18`<br>`models.py:27` | The User.invoices relationship carries no cascade string, so the ORM delete in the purge job does not propagate; the only delete path is the database-level ondelete="CASCADE", and the SQLite URL in config.py comes with no PRAGMA foreign_keys=ON listener anywhere in the repository, so the source does not settle whether the child rows go. |
| users | ERASED AFTER TIMER (30 days) | `api/account.py:15`<br>`config.py:13`<br>`jobs/purge.py:10`<br>`jobs/purge.py:17`<br>`jobs/purge.py:18` | The route only stamps deleted_at; the Celery beat task purge_closed_accounts selects users whose deleted_at is older than 30 days and calls session.delete on each row. |

No erasure verdict is rendered for a store of kind backup; it carries a retention verdict instead. This tool reports the retention schedule it found in code and cites it; whether that schedule and the procedure applied to restored systems are adequate is not visible here.

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| api.account | `api/account.py` |
| api.profile | `api/profile.py` |
| jobs.purge | `jobs/purge.py` |
| jobs.backup | `jobs/backup.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

| Value | Evidence |
|---|---|
| `eu-central-1` | `config.py:9` |

Security measures. Technical measures under Article 32(1)(a) only, one line each. The organisational half is in section F.

| Measure | Evidence | Symbol |
|---|---|---|
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

Verification: none. This record was accepted on schema validity alone.

## H. Evidence index

| Evidence | Symbol | Sections |
|---|---|---|
| `api/account.py:12` | `close_account` | D |
| `api/account.py:15` | `deleted_at` | D |
| `config.py:5` | `DATABASE_URL` | D |
| `config.py:9` | `eu-central-1` | E |
| `config.py:13` | `jobs.purge.purge_closed_accounts` | D |
| `jobs/backup.py:9` | `email`, `full_name`, `reference` | A |
| `jobs/backup.py:10` | `DUMP_PATH` | A |
| `jobs/backup.py:11` | `SCHEDULE` | D, E |
| `jobs/backup.py:12` | `BACKUP_RETENTION_DAYS` | C, D |
| `jobs/backup.py:18` | — | A |
| `jobs/backup.py:21` | `open` | D |
| `jobs/purge.py:10` | `RETENTION_DAYS` | C, D |
| `jobs/purge.py:17` | `deleted_at` | D |
| `jobs/purge.py:18` | `session.delete` | D |
| `models.py:12` | — | A |
| `models.py:13` | `users` | A |
| `models.py:14` | `id` | A |
| `models.py:15` | `email` | A |
| `models.py:16` | `full_name` | A |
| `models.py:17` | `deleted_at` | A |
| `models.py:18` | `relationship` | D |
| `models.py:22` | `invoices` | A |
| `models.py:24` | `billing_name` | A |
| `models.py:25` | `reference` | A, C |
| `models.py:26` | `amount_cents` | A |
| `models.py:27` | `ondelete` | A, D |
