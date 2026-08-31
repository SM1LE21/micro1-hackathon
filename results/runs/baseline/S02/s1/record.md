# Record of processing — harbourdesk

|  |  |
|---|---|
| Case | S02 (synthetic) |
| Arm | baseline |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `base-S02-s1-df6db10` |
| Code read | `evals/fixtures/synthetic/S02`, sha256 `0fd7c397ff84` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 15:16:22 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/baseline/S02-s1.jsonl` |
| Verification | 1 submission, accepted on attempt 1 |
| Cost | USD 0.279069 (estimate at list prices), 12 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects:

- account holders — inferred from model name (`models.py:12`).
- support requesters — inferred from model name (`models.py:23`).

### tickets — relational — `models.py:24`

SQLAlchemy table of support tickets, each carrying a user_id foreign key to the users table.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `subject` | free_text_may_contain | `models.py:26` |  |
| `body` | free_text_may_contain | `models.py:27` |  |
| `opened_at` | behavioural | `models.py:28` |  |

Linked to the data subject at `models.py:29`.

### users — relational — `models.py:13`

SQLAlchemy table holding the account holder's contact details and account state.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:15` |  |
| `full_name` | identifier | `models.py:16` |  |
| `phone` | contact | `models.py:17` |  |
| `is_active` | behavioural | `models.py:18` |  |
| `deleted_at` | technical | `models.py:19` | Soft-delete marker the close_account route writes to. |

Linked to the data subject at `models.py:12`.

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

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points: `close_account` — route — `api/account.py:12` (Takes a session and a user_id, sets deleted_at and is_active on the user row, and commits.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| tickets | NOT ERASED | `api/account.py:15`<br>`models.py:20` | The only deletion route deletes no row, and the User.tickets relationship carries no cascade argument, so nothing propagates to this table. |
| users | NOT ERASED | `api/account.py:15`<br>`api/account.py:16`<br>`api/account.py:17` | close_account writes a timestamp to deleted_at and sets is_active to False; the row and its columns stay, and no scheduled job in the repository deletes them later. |

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| api.account | `api/account.py` |
| api.profile | `api/profile.py` |
| utils.text | `utils/text.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

| Value | Evidence |
|---|---|
| `eu-central-1` | `config.py:7` |

Security measures. Technical measures under Article 32(1)(a) only, one line each. The organisational half is in section F.

None.

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
| `api/account.py:16` | `is_active` | D |
| `api/account.py:17` | `commit` | D |
| `config.py:7` | `eu-central-1` | E |
| `models.py:12` | — | A |
| `models.py:13` | `users` | A |
| `models.py:15` | `email` | A |
| `models.py:16` | `full_name` | A |
| `models.py:17` | `phone` | A |
| `models.py:18` | `is_active` | A |
| `models.py:19` | `deleted_at` | A |
| `models.py:20` | `relationship` | D |
| `models.py:23` | — | A |
| `models.py:24` | `tickets` | A |
| `models.py:26` | `subject` | A |
| `models.py:27` | `body` | A |
| `models.py:28` | `opened_at` | A |
| `models.py:29` | — | A |
