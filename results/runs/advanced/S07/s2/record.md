# Record of processing — quillrest

|  |  |
|---|---|
| Case | S07 (synthetic) |
| Arm | advanced |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `adv-S07-s2-c4d159e` |
| Code read | `evals/fixtures/synthetic/S07`, sha256 `8cf9dccbd006` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 15:53:48 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/advanced/S07-s2.jsonl` |
| Verification | 2 submissions, accepted on attempt 2, rule set `e9a260adc28b` |
| Approved | 2026-08-31 15:53:48 UTC without a person (--approve auto), 0 s at the checkpoint, risk HIGH |
| Cost | USD 0.467141 (estimate at list prices), 16 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects:

- account holders — inferred from model name (`models.py:12`).
- support requesters — inferred from model name (`models.py:22`).

### tickets — relational — `models.py:23`

Table holding support tickets, each carrying a foreign key to users.id.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `subject` | free_text_may_contain | `models.py:25` |  |
| `notes` | free_text_may_contain | `models.py:26` | The column comment says the free text may contain phone numbers. |
| `opened_at` | behavioural | `models.py:27` |  |

Linked to the data subject at `models.py:28`.

### users — relational — `models.py:13`

Table holding the account record for each user.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:15` |  |
| `full_name` | identifier | `models.py:16` |  |
| `metadata_json` | free_text_may_contain | `models.py:17` | The column comment says the client sets arbitrary key/value pairs and that support pastes contact details in here. |
| `deleted_at` | technical | `models.py:18` | Column the application would use to mark a row closed; no code in the repository writes it. |

Linked to the data subject at `models.py:14`.

### request_log — log — `middleware.py:5`

Python logger that writes the client IP address and request path for every request.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `ip_address` | technical | `middleware.py:9` |  |
| `path` | behavioural | `middleware.py:10` | The requested URL path is logged on the same line as the caller's IP address. |

Linked to the data subject at `middleware.py:9`.

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

Erasure entry points:

- `close_account` — route — `api/account.py:11` (Loads the user row, calls anonymize_user and commits; no row is deleted.).
- `anonymize_user` — unknown — `privacy.py:8` (Helper the close_account route calls; it overwrites two columns on the user object passed to it.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| users | PSEUDONYMISED | `api/account.py:14`<br>`privacy.py:9`<br>`privacy.py:10` | close_account overwrites email with its SHA-256 hash and full_name with the constant "removed"; the row and its primary key survive, and the hashed email still points back to the person. |
| ↳ `metadata_json` | NOT ERASED | `models.py:17`<br>`privacy.py:8` | anonymize_user writes only email and full_name; metadata_json is never overwritten or deleted. |
| ↳ `deleted_at` | NOT ERASED | `api/account.py:14`<br>`models.py:18` | close_account does not set deleted_at and no other module writes the column. |
| request_log | NOT ERASED | `api/account.py:14`<br>`middleware.py:11` | No code in the repository removes or rotates entries written by log_request, and the account-closing route does not touch the log. |
| tickets | NOT ERASED | `api/account.py:14`<br>`models.py:19`<br>`models.py:28` | The only deletion path anonymises two columns on the user row and deletes nothing, and the User.tickets relationship carries no cascade string, so ticket rows keep their subject, notes and user_id. |

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
| hashing | `privacy.py:9` | `hashlib` |
| pseudonymisation | `privacy.py:9` | `sha256` |

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

Claims rejected and what replaced them.

| Round | Store | Claim | Reason | Rendered instead |
|---|---|---|---|---|
| — | — | — | none | — |

Stores the record did not contain, found by the scan of the repository.

| Round | Store | Kind | Evidence | Added |
|---|---|---|---|---|
| — | — | — | none | — |

Citations that did not resolve: 1. Claims that could not be decided: none.

## H. Evidence index

| Evidence | Symbol | Sections |
|---|---|---|
| `api/account.py:11` | `close_account` | D |
| `api/account.py:14` | `anonymize_user` | D |
| `config.py:7` | `eu-central-1` | E |
| `middleware.py:5` | `request_log` | A |
| `middleware.py:9` | `ip_address` | A |
| `middleware.py:10` | `path` | A |
| `middleware.py:11` | `logger` | D |
| `models.py:12` | — | A |
| `models.py:13` | `users` | A |
| `models.py:14` | — | A |
| `models.py:15` | `email` | A |
| `models.py:16` | `full_name` | A |
| `models.py:17` | `metadata_json` | A, D |
| `models.py:18` | `deleted_at` | A, D |
| `models.py:19` | `tickets` | D |
| `models.py:22` | — | A |
| `models.py:23` | `tickets` | A |
| `models.py:25` | `subject` | A |
| `models.py:26` | `notes` | A |
| `models.py:27` | `opened_at` | A |
| `models.py:28` | `user_id` | A, D |
| `privacy.py:8` | `anonymize_user` | D |
| `privacy.py:9` | `hashlib`, `sha256` | D, E |
| `privacy.py:10` | `ANONYMISED_NAME` | D |
