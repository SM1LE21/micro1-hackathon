# Record of processing — civicbeam

|  |  |
|---|---|
| Case | S08 (synthetic) |
| Arm | baseline |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `base-S08-s1-cdae8e6` |
| Code read | `evals/fixtures/synthetic/S08`, sha256 `11b624f57f0e` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 15:57:45 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/baseline/S08-s1.jsonl` |
| Verification | 1 submission, accepted on attempt 1 |
| Cost | USD 0.387401 (estimate at list prices), 17 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects:

- account holders — inferred from model name (`models.py:12`).
- document authors — inferred from model name (`models.py:22`).

### documents — relational — `models.py:23`

Rows joined to the account holder by user_id.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `title` | free_text_may_contain | `models.py:25` | Text the account holder supplies; the schema does not constrain its contents. |
| `body` | free_text_may_contain | `models.py:26` |  |

Linked to the data subject at `models.py:27`.

### users — relational — `models.py:13`

SQLAlchemy table holding the account holder record.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:15` |  |
| `full_name` | identifier | `models.py:16` |  |
| `phone` | contact | `models.py:17` |  |
| `created_at` | behavioural | `models.py:18` | Timestamp on the row that represents the person. |

Linked to the data subject at `models.py:12`.

### uploads — object_storage — `storage.py:7`

S3 bucket written by upload_document.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `Key` | identifier | `storage.py:19` | The object key is built as docs/{user_id}/{document_id}.pdf at storage.py:12. |
| `Body` | free_text_may_contain | `storage.py:20` | The uploaded document bytes passed through from the create_document route. |

Linked to the data subject at `storage.py:12`.

### doc_search — search_index — `search.py:7`

Elasticsearch index written on document creation.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `owner_email` | contact | `search.py:15` |  |
| `title` | free_text_may_contain | `search.py:16` |  |

Linked to the data subject at `search.py:15`.

### events — queue — `queue.py:9`

RabbitMQ queue receiving a document-created event.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `queue.py:19` | The account holder's email is placed in the published message body. |

Linked to the data subject at `queue.py:19`.

### nightly_dump — backup — `jobs/dump.py:8`

JSON file written from the users and documents tables by jobs/dump.py.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `jobs/dump.py:9` |  |
| `full_name` | identifier | `jobs/dump.py:9` |  |
| `phone` | contact | `jobs/dump.py:9` |  |

Linked to the data subject at `jobs/dump.py:16`.

Not scanned:

- `README.md` (not Python).
- `requirements.txt` (not Python).

## B. Recipients

No store of kind third_party was found in the code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| documents | — | NO TIMER EVIDENCED | — | requires human completion |
| users | — | NO TIMER EVIDENCED | — | requires human completion |
| uploads | — | NO TIMER EVIDENCED | — | requires human completion |
| doc_search | — | NO TIMER EVIDENCED | — | requires human completion |
| events | — | NO TIMER EVIDENCED | — | requires human completion |
| nightly_dump | — | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points: none found.

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| doc_search | NO ENTRY POINT | — | search.py defines es.index only; no delete on the index exists and no account-deletion path calls one. |
| documents | NO ENTRY POINT | — | User.documents carries cascade="all, delete" at models.py:19, but no code anywhere deletes a User, so the cascade never runs. |
| events | NO ENTRY POINT | — | The message is published at queue.py:14 and nothing in the repository removes or expires it. |
| uploads | NO ENTRY POINT | — | storage.py defines put_object only; there is no delete call and no account-deletion path to reach one. |
| users | NO ENTRY POINT | — | The repository has no route, command or job that deletes a user; api/account.py defines only create_document and get_profile. |
| nightly_dump | NO SCHEDULE EVIDENCED | — | write_dump overwrites nightly_dump.json on each run, and the repository carries no cron entry, timer or retention constant for the file. |

No erasure verdict is rendered for a store of kind backup; it carries a retention verdict instead. This tool reports the retention schedule it found in code and cites it; whether that schedule and the procedure applied to restored systems are adequate is not visible here.

Object storage: where bucket versioning is enabled, a delete that passes no `versionId` leaves the previous version of the object in place.

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| api.account | `api/account.py` |
| jobs.dump | `jobs/dump.py` |
| search | `search.py` |
| queue | `queue.py` |
| storage | `storage.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

| Value | Evidence |
|---|---|
| `eu-central-1` | `config.py:9` |
| `http://localhost:9200` | `config.py:10` |
| `amqp://localhost` | `config.py:11` |

Security measures. Technical measures under Article 32(1)(a) only, one line each. The organisational half is in section F.

| Measure | Evidence | Symbol |
|---|---|---|
| encryption at rest | `storage.py:21` | `ServerSideEncryption` |

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
| `config.py:9` | `eu-central-1` | E |
| `config.py:10` | `http://localhost:9200` | E |
| `config.py:11` | `amqp://localhost` | E |
| `jobs/dump.py:8` | `BACKUP_NAME` | A |
| `jobs/dump.py:9` | `email`, `full_name`, `phone` | A |
| `jobs/dump.py:16` | — | A |
| `models.py:12` | — | A |
| `models.py:13` | `users` | A |
| `models.py:15` | `email` | A |
| `models.py:16` | `full_name` | A |
| `models.py:17` | `phone` | A |
| `models.py:18` | `created_at` | A |
| `models.py:22` | — | A |
| `models.py:23` | `documents` | A |
| `models.py:25` | `title` | A |
| `models.py:26` | `body` | A |
| `models.py:27` | — | A |
| `queue.py:9` | `QUEUE` | A |
| `queue.py:19` | `email` | A |
| `search.py:7` | `INDEX` | A |
| `search.py:15` | `owner_email` | A |
| `search.py:16` | `title` | A |
| `storage.py:7` | `BUCKET` | A |
| `storage.py:12` | — | A |
| `storage.py:19` | `Key` | A |
| `storage.py:20` | `Body` | A |
| `storage.py:21` | `ServerSideEncryption` | E |
