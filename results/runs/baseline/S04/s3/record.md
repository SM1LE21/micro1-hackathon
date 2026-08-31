# Record of processing — snapledger

|  |  |
|---|---|
| Case | S04 (synthetic) |
| Arm | baseline |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `base-S04-s3-c001776` |
| Code read | `evals/fixtures/synthetic/S04`, sha256 `6ce5791cc14f` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 15:31:44 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/baseline/S04-s3.jsonl` |
| Verification | 1 submission, accepted on attempt 1 |
| Cost | USD 0.267394 (estimate at list prices), 12 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects: account holders — inferred from model name (`models.py:11`).

### users — relational — `models.py:12`

SQLAlchemy table holding one row per account holder.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:14` |  |
| `full_name` | identifier | `models.py:15` |  |
| `created_at` | behavioural | `models.py:16` | Timestamp on the row that represents the account holder. |

Linked to the data subject at `models.py:11`.

### uploads/avatars — object_storage — `storage.py:7`

S3 bucket named uploads, avatar objects under the avatars/ prefix.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `avatar_key` | identifier | `storage.py:11` | The object key is built from the user id, so the key itself points at one account holder. |

Linked to the data subject at `storage.py:12`.

Not scanned:

- `README.md` (not Python).
- `requirements.txt` (not Python).

## B. Recipients

No store of kind third_party was found in the code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| users | — | NO TIMER EVIDENCED | — | requires human completion |
| uploads/avatars | — | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points: `delete_account` — route — `api/account.py:11` (Takes a session and a user id, calls delete_avatar and then deletes the User row.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| uploads/avatars | ERASED | `api/account.py:14`<br>`storage.py:27` | delete_account calls delete_avatar, which calls s3.delete_object on the key built from the user id. |
| users | ERASED | `api/account.py:15`<br>`api/account.py:16` | delete_account calls session.delete on the User row and commits, so the row is removed. |

Object storage: where bucket versioning is enabled, a delete that passes no `versionId` leaves the previous version of the object in place.

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| catalog | `catalog.py` |
| storage | `storage.py` |
| api.account | `api/account.py` |
| api.profile | `api/profile.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

| Value | Evidence |
|---|---|
| `eu-central-1` | `config.py:7` |

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
| `api/account.py:11` | `delete_account` | D |
| `api/account.py:14` | `delete_avatar` | D |
| `api/account.py:15` | `session.delete` | D |
| `api/account.py:16` | `session.commit` | D |
| `config.py:7` | `eu-central-1` | E |
| `models.py:11` | — | A |
| `models.py:12` | `users` | A |
| `models.py:14` | `email` | A |
| `models.py:15` | `full_name` | A |
| `models.py:16` | `created_at` | A |
| `storage.py:7` | `BUCKET` | A |
| `storage.py:11` | `avatar_key` | A |
| `storage.py:12` | — | A |
| `storage.py:21` | `ServerSideEncryption` | E |
| `storage.py:27` | `delete_object` | D |
