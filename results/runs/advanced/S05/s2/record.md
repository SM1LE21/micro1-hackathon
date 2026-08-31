# Record of processing — pulsedeck

|  |  |
|---|---|
| Case | S05 (synthetic) |
| Arm | advanced |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `adv-S05-s2-9420146` |
| Code read | `evals/fixtures/synthetic/S05`, sha256 `1c7af597478a` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 15:38:14 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/advanced/S05-s2.jsonl` |
| Verification | 1 submission, accepted on attempt 1, rule set `e9a260adc28b` |
| Approved | 2026-08-31 15:38:14 UTC without a person (--approve auto), 0 s at the checkpoint, risk HIGH |
| Cost | USD 0.401877 (estimate at list prices), 16 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects:

- account holders — inferred from model name (`models.py:11`).
- people who sign up — inferred from route name (`api/profile.py:14`).

### users — relational — `models.py:12`

SQLAlchemy table holding the account row.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:14` |  |
| `full_name` | identifier | `models.py:15` |  |
| `marketing_opt_in` | behavioural | `models.py:16` |  |
| `created_at` | behavioural | `models.py:17` |  |

Linked to the data subject at `models.py:13`.

### sessions: — cache — `cache.py:12`

Redis keys written at login, one per account email address.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `cache.py:12` | The cache key is built from the account email address. |
| `token` | technical | `cache.py:12` | The session token stored as the cache value. |

Linked to the data subject at `cache.py:12`.

### mixpanel — third_party — `analytics.py:11`

Product analytics service called from the signup route.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `analytics.py:11` | The account email address is passed as the Mixpanel distinct id. |
| `account_created` | behavioural | `analytics.py:11` | The event name recorded against that person. |

Linked to the data subject at `analytics.py:11`.

### sendgrid — third_party — `mail.py:12`

Transactional mail provider called from the signup route.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `mail.py:12` | Passed as the recipient address. |
| `body` | free_text_may_contain | `mail.py:11` | The message body is built from the account full name. |

Linked to the data subject at `mail.py:12`.

### sentry_sdk — third_party — `app.py:18`

Error tracker initialised when app.py is imported.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `url` | technical | `app.py:9` | Listed in SENTRY_DEFAULT_FIELDS as sent by default. |
| `query_string` | free_text_may_contain | `app.py:10` | Listed in SENTRY_DEFAULT_FIELDS as sent by default. |
| `request_body` | free_text_may_contain | `app.py:11` | Listed in SENTRY_DEFAULT_FIELDS as sent by default. |
| `local_variables` | free_text_may_contain | `app.py:12` | Stack-frame locals listed in SENTRY_DEFAULT_FIELDS as sent by default. |

No link to a data subject found in code.

### stripe — third_party — `billing.py:11`

Stripe customer created from the account row at signup.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `billing.py:12` |  |
| `name` | identifier | `billing.py:13` | The account full name is sent as the customer name. |

Linked to the data subject at `billing.py:12`.

Not scanned:

- `README.md` (not Python).
- `requirements.txt` (not Python).

## B. Recipients

| Recipient | Fields disclosed | Evidence | Recipient kind |
|---|---|---|---|
| mixpanel | `email` (contact), `account_created` (behavioural) | `analytics.py:11`, `analytics.py:11` | UNKNOWN — requires human completion |
| sendgrid | `email` (contact), `body` (free_text_may_contain) | `mail.py:12`, `mail.py:11` | UNKNOWN — requires human completion |
| sentry_sdk | `url` (technical), `query_string` (free_text_may_contain), `request_body` (free_text_may_contain), `local_variables` (free_text_may_contain) | `app.py:9`, `app.py:10`, `app.py:11`, `app.py:12` | UNKNOWN — requires human completion |
| stripe | `email` (contact), `name` (identifier) | `billing.py:12`, `billing.py:13` | UNKNOWN — requires human completion |

Personal data flows into the call at the cited lines. Whether this recipient acts as a processor on the controller's instructions or as an independent controller, and whether a contract under Article 28(3) exists, is not visible in code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| users | — | NO TIMER EVIDENCED | — | requires human completion |
| sessions: | all categories | 1 days Session keys are written with a time to live of 86400 seconds. | `cache.py:7` | requires human completion |
| mixpanel | — | NO TIMER EVIDENCED | — | requires human completion |
| sendgrid | — | NO TIMER EVIDENCED | — | requires human completion |
| sentry_sdk | — | NO TIMER EVIDENCED | — | requires human completion |
| stripe | — | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points: `delete_account` — route — `api/account.py:10` (Loads the User row by id and deletes it in the session.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| sessions: | NOT ERASED | `api/account.py:13`<br>`cache.py:16` | purge_session deletes the key, but no module calls it; the deletion route touches only the database row. The 86400-second time to live on the key is a retention timer, not a call on this path. |
| mixpanel | EXTERNAL MANUAL | `analytics.py:11` | The signup route sends the event; no Mixpanel deletion call exists in the repository. |
| sendgrid | EXTERNAL MANUAL | `mail.py:12` | The welcome mail is sent through SendGrid; the repository has no call that removes anything held there. |
| sentry_sdk | EXTERNAL MANUAL | `app.py:18` | Sentry is initialised at import time and receives event data; no deletion call for it exists in the repository. |
| stripe | EXTERNAL MANUAL | `billing.py:11` | The repository creates a Stripe customer at signup and contains no Stripe deletion call. |
| users | ERASED | `api/account.py:12`<br>`api/account.py:13`<br>`api/account.py:14` | The route deletes the User row itself and commits. |

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| analytics | `analytics.py` |
| billing | `billing.py` |
| cache | `cache.py` |
| mail | `mail.py` |
| catalog | `catalog.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

| Value | Evidence |
|---|---|
| `eu-central-1` | `config.py:9` |
| `redis://localhost:6379/0` | `config.py:10` |
| `sqlite:///./pulsedeck.db` | `config.py:5` |

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
| Recipient kind — mixpanel | (d) | requires human completion |
| Recipient kind — sendgrid | (d) | requires human completion |
| Recipient kind — sentry_sdk | (d) | requires human completion |
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
| — | — | — | none | — |

Stores the record did not contain, found by the scan of the repository.

| Round | Store | Kind | Evidence | Added |
|---|---|---|---|---|
| — | — | — | none | — |

Citations that did not resolve: none. Claims that could not be decided: none.

## H. Evidence index

| Evidence | Symbol | Sections |
|---|---|---|
| `analytics.py:11` | `mp.track`, `email`, `account_created` | A, B, D |
| `api/account.py:10` | `delete_account` | D |
| `api/account.py:12` | `session.get` | D |
| `api/account.py:13` | `session.delete` | D |
| `api/account.py:14` | `commit` | D |
| `api/profile.py:14` | — | A |
| `app.py:9` | `url` | A, B |
| `app.py:10` | `query_string` | A, B |
| `app.py:11` | `request_body` | A, B |
| `app.py:12` | `local_variables` | A, B |
| `app.py:18` | `sentry_sdk.init` | A, D |
| `billing.py:11` | `stripe.Customer.create` | A, D |
| `billing.py:12` | `email` | A, B |
| `billing.py:13` | `name` | A, B |
| `cache.py:7` | — | C |
| `cache.py:12` | `setex`, `email`, `token` | A |
| `cache.py:16` | `cache.delete` | D |
| `config.py:5` | `sqlite:///./pulsedeck.db` | E |
| `config.py:9` | `eu-central-1` | E |
| `config.py:10` | `redis://localhost:6379/0` | E |
| `mail.py:11` | `body` | A, B |
| `mail.py:12` | `sg.send`, `email` | A, B, D |
| `models.py:11` | — | A |
| `models.py:12` | `__tablename__` | A |
| `models.py:13` | — | A |
| `models.py:14` | `email` | A |
| `models.py:15` | `full_name` | A |
| `models.py:16` | `marketing_opt_in` | A |
| `models.py:17` | `created_at` | A |
