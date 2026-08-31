# Record of processing — orderly

|  |  |
|---|---|
| Case | S01 (synthetic) |
| Arm | advanced |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `adv-S01-s2-1598362` |
| Code read | `evals/fixtures/synthetic/S01`, sha256 `14c529bf05bc` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 15:13:31 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/advanced/S01-s2.jsonl` |
| Verification | 1 submission, accepted on attempt 1, rule set `e9a260adc28b` |
| Approved | 2026-08-31 15:13:31 UTC without a person (--approve auto), 0 s at the checkpoint, risk LOW |
| Cost | USD 0.267597 (estimate at list prices), 13 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects:

- account holders — inferred from model name (`models.py:12`).
- account holders placing orders — inferred from route name (`api/profile.py:15`).

### orders — relational — `models.py:22`

SQLAlchemy table with a user_id foreign key to the users table.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `shipping_address` | contact | `models.py:24` |  |
| `amount_cents` | financial | `models.py:25` |  |
| `placed_at` | behavioural | `models.py:26` |  |

Linked to the data subject at `models.py:27`.

### users — relational — `models.py:13`

SQLAlchemy table holding one row per account holder.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:15` |  |
| `full_name` | identifier | `models.py:16` |  |
| `created_at` | behavioural | `models.py:17` |  |

Linked to the data subject at `models.py:12`.

Not scanned:

- `README.md` (not Python).
- `requirements.txt` (not Python).

## B. Recipients

No store of kind third_party was found in the code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| orders | — | NO TIMER EVIDENCED | — | requires human completion |
| users | — | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points: `delete_account` — route — `api/account.py:10` (Module docstring describes these functions as HTTP routes registered by app.py.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| orders | ERASED | `api/account.py:13`<br>`models.py:18` | The User.orders relationship carries cascade="all, delete", so deleting the user row through the session deletes the order rows too. |
| users | ERASED | `api/account.py:13`<br>`api/account.py:14` | The delete_account route loads the User row and passes it to session.delete, then commits. |

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| api.account | `api/account.py` |
| api.profile | `api/profile.py` |

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

Claims rejected and what replaced them.

| Round | Store | Claim | Reason | Rendered instead |
|---|---|---|---|---|
| — | — | — | none | — |

Stores the record did not contain, found by the scan of the repository.

| Round | Store | Kind | Evidence | Added |
|---|---|---|---|---|
| — | — | — | none | — |

Citations that did not resolve: none. Claims that could not be decided: none.

## H. Evidence index

| Evidence | Symbol | Sections |
|---|---|---|
| `api/account.py:10` | `delete_account` | D |
| `api/account.py:13` | `session.delete` | D |
| `api/account.py:14` | `session.commit` | D |
| `api/profile.py:15` | — | A |
| `config.py:7` | `eu-central-1` | E |
| `models.py:12` | — | A |
| `models.py:13` | `users` | A |
| `models.py:15` | `email` | A |
| `models.py:16` | `full_name` | A |
| `models.py:17` | `created_at` | A |
| `models.py:18` | `cascade` | D |
| `models.py:22` | `orders` | A |
| `models.py:24` | `shipping_address` | A |
| `models.py:25` | `amount_cents` | A |
| `models.py:26` | `placed_at` | A |
| `models.py:27` | — | A |
