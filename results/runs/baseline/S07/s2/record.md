# Record of processing — quillrest

|  |  |
|---|---|
| Case | S07 (synthetic) |
| Arm | baseline |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `base-S07-s2-c9dfb27` |
| Code read | `evals/fixtures/synthetic/S07`, sha256 `8cf9dccbd006` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 15:52:16 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/baseline/S07-s2.jsonl` |
| Verification | 1 submission, accepted on attempt 1 |
| Cost | USD 0.349494 (estimate at list prices), 15 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects:

- account holders — inferred from model name (`models.py:12`).
- support requesters — inferred from model name (`models.py:22`).

### tickets — relational — `models.py:23`

Support tickets, each carrying a foreign key to the user.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `subject` | free_text_may_contain | `models.py:25` |  |
| `notes` | free_text_may_contain | `models.py:26` | The comment on the column says the free text may contain phone numbers. |
| `opened_at` | behavioural | `models.py:27` | Timestamp on a row carrying a foreign key to the user. |

Linked to the data subject at `models.py:28`.

### users — relational — `models.py:13`

Table of user accounts defined with SQLAlchemy.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:15` |  |
| `full_name` | identifier | `models.py:16` |  |
| `metadata_json` | free_text_may_contain | `models.py:17` | The comment on the column says the value is an arbitrary key/value set by the client and that support pastes contact details into it. |
| `deleted_at` | technical | `models.py:18` | Soft-delete marker column on the user row. |

Linked to the data subject at `models.py:12`.

### request_log — log — `middleware.py:5`

Python logging logger that records the client IP address and the request path for every request.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `ip_address` | technical | `middleware.py:9` | Read from the request client host and written to the log line at middleware.py:11. |

No link to a data subject found in code.

Not scanned:

- `README.md` (not Python).
- `requirements.txt` (not Python).

## B. Recipients

No store of kind third_party was found in the code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| tickets | — | NO TIMER EVIDENCED | — | requires human completion |
| users | — | NO TIMER EVIDENCED | — | requires human completion |
| request_log | — | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points: `close_account` — route — `api/account.py:11` (Loads the user row, calls anonymize_user and commits.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| users | PSEUDONYMISED | `api/account.py:11`<br>`api/account.py:14`<br>`api/account.py:15`<br>`privacy.py:9` | close_account replaces email with its SHA-256 hash and leaves the row in place, so the row still points at the same person; no delete statement is issued anywhere in the repository. |
| ↳ `full_name` | ANONYMISED | `api/account.py:14`<br>`privacy.py:10` | close_account overwrites full_name with the constant string "removed", which does not carry the previous value. |
| ↳ `metadata_json` | NOT ERASED | `privacy.py:8` | anonymize_user writes only email and full_name; no code writes or clears metadata_json. |
| ↳ `deleted_at` | NOT ERASED | `api/account.py:14`<br>`models.py:18` | The column is declared but no code in the repository sets it, and no job reads it. |
| request_log | NOT ERASED | `api/account.py:11`<br>`middleware.py:11` | The deletion route touches only the user row; nothing in the repository removes or rotates the log records written by log_request. |
| tickets | NOT ERASED | `api/account.py:14`<br>`models.py:19`<br>`models.py:28` | close_account deletes no row, and the User.tickets relationship carries no cascade argument, so the ticket rows and their columns stay as they are. |

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| privacy | `privacy.py` |
| api.account | `api/account.py` |
| api.profile | `api/profile.py` |
| middleware | `middleware.py` |
| catalog | `catalog.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

| Value | Evidence |
|---|---|
| `eu-central-1` | `config.py:7` |

Security measures. Technical measures under Article 32(1)(a) only, one line each. The organisational half is in section F.

| Measure | Evidence | Symbol |
|---|---|---|
| pseudonymisation | `privacy.py:9` | `sha256` |
| hashing | `privacy.py:3` | `hashlib` |

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
| `api/account.py:11` | `close_account` | D |
| `api/account.py:14` | `anonymize_user` | D |
| `api/account.py:15` | `commit` | D |
| `config.py:7` | `eu-central-1` | E |
| `middleware.py:5` | `request_log` | A |
| `middleware.py:9` | `ip_address` | A |
| `middleware.py:11` | `logger` | D |
| `models.py:12` | — | A |
| `models.py:13` | `users` | A |
| `models.py:15` | `email` | A |
| `models.py:16` | `full_name` | A |
| `models.py:17` | `metadata_json` | A |
| `models.py:18` | `deleted_at` | A, D |
| `models.py:19` | `relationship` | D |
| `models.py:22` | — | A |
| `models.py:23` | `tickets` | A |
| `models.py:25` | `subject` | A |
| `models.py:26` | `notes` | A |
| `models.py:27` | `opened_at` | A |
| `models.py:28` | `user_id` | A, D |
| `privacy.py:3` | `hashlib` | E |
| `privacy.py:8` | `anonymize_user` | D |
| `privacy.py:9` | `hashlib`, `sha256` | D, E |
| `privacy.py:10` | `ANONYMISED_NAME` | D |
