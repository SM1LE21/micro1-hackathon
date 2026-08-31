# Record of processing — pulsedeck

|  |  |
|---|---|
| Case | S05 (synthetic) |
| Arm | baseline |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `base-S05-s3-06a9963` |
| Code read | `evals/fixtures/synthetic/S05`, sha256 `1c7af597478a` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 15:39:18 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/baseline/S05-s3.jsonl` |
| Verification | 1 submission, accepted on attempt 1 |
| Cost | USD 0.373988 (estimate at list prices), 18 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects:

- account holders — inferred from model name (`models.py:11`).
- account holders — inferred from route name (`api/profile.py:14`).

### users — relational — `models.py:12`

SQLAlchemy table holding the account row.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:14` |  |
| `full_name` | identifier | `models.py:15` |  |
| `marketing_opt_in` | behavioural | `models.py:16` |  |
| `created_at` | behavioural | `models.py:17` |  |

Linked to the data subject at `models.py:11`.

### sessions: — cache — `cache.py:12`

Redis key namespace written on login with a 86400 second expiry.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `token` | technical | `cache.py:12` | The session token is stored as the value under a key built from the user's email address. |
| `user.email` | contact | `cache.py:12` | The email address is part of the Redis key. |

Linked to the data subject at `cache.py:12`.

### mixpanel — third_party — `analytics.py:11`

Product analytics call made from the signup route.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `user.email` | contact | `analytics.py:11` | The email address is passed as the Mixpanel distinct id. |
| `account_created` | behavioural | `analytics.py:11` | The event name records that the person created an account. |

Linked to the data subject at `api/profile.py:17`.

### sendgrid — third_party — `mail.py:12`

Transactional mail sent during signup.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `to` | contact | `mail.py:12` | The recipient address is the user's email. |
| `body` | identifier | `mail.py:11` | The message body is built from the user's full name. |

Linked to the data subject at `api/profile.py:18`.

### sentry_sdk — third_party — `app.py:18`

Error tracker initialised when app.py is imported.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `url` | technical | `app.py:9` | Listed in this module as a field Sentry sends by default. |
| `query_string` | free_text_may_contain | `app.py:10` | Listed in this module as a field Sentry sends by default. |
| `request_body` | free_text_may_contain | `app.py:11` | Listed in this module as a field Sentry sends by default. |
| `local_variables` | free_text_may_contain | `app.py:12` | Stack-frame locals listed in this module as a field Sentry sends by default. |

No link to a data subject found in code.

### stripe.Customer — third_party — `billing.py:11`

Stripe customer created during signup.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `billing.py:12` |  |
| `name` | identifier | `billing.py:13` |  |

Linked to the data subject at `api/profile.py:16`.

Not scanned:

- `requirements.txt` (not Python).
- `README.md` (not Python).

## B. Recipients

| Recipient | Fields disclosed | Evidence | Recipient kind |
|---|---|---|---|
| mixpanel | `user.email` (contact), `account_created` (behavioural) | `analytics.py:11`, `analytics.py:11` | UNKNOWN — requires human completion |
| sendgrid | `to` (contact), `body` (identifier) | `mail.py:12`, `mail.py:11` | UNKNOWN — requires human completion |
| sentry_sdk | `url` (technical), `query_string` (free_text_may_contain), `request_body` (free_text_may_contain), `local_variables` (free_text_may_contain) | `app.py:9`, `app.py:10`, `app.py:11`, `app.py:12` | UNKNOWN — requires human completion |
| stripe.Customer | `email` (contact), `name` (identifier) | `billing.py:12`, `billing.py:13` | UNKNOWN — requires human completion |

Personal data flows into the call at the cited lines. Whether this recipient acts as a processor on the controller's instructions or as an independent controller, and whether a contract under Article 28(3) exists, is not visible in code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| users | — | NO TIMER EVIDENCED | — | requires human completion |
| sessions: | all categories | 1 days Redis key written with SESSION_TTL_SECONDS = 86400 seconds of expiry. | `cache.py:7` | requires human completion |
| mixpanel | — | NO TIMER EVIDENCED | — | requires human completion |
| sendgrid | — | NO TIMER EVIDENCED | — | requires human completion |
| sentry_sdk | — | NO TIMER EVIDENCED | — | requires human completion |
| stripe.Customer | — | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points: `delete_account` — route — `api/account.py:10` (Loads the User row by id and deletes it through the SQLAlchemy session.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| sessions: | NOT ERASED | `api/account.py:13`<br>`cache.py:15` | purge_session is defined in cache.py but no module in this repository calls it, and delete_account touches only the database row. |
| mixpanel | EXTERNAL MANUAL | `analytics.py:11` | track_signup sends the event to Mixpanel; no deletion call to Mixpanel exists in this repository. |
| sendgrid | EXTERNAL MANUAL | `mail.py:12` | send_welcome hands the address and the body to the SendGrid client; this repository has no call that removes them. |
| sentry_sdk | EXTERNAL MANUAL | `app.py:18`<br>`app.py:21` | init_observability runs at import and initialises the Sentry client; no deletion call to Sentry exists in this repository. |
| stripe.Customer | EXTERNAL MANUAL | `billing.py:11` | The signup route creates a Stripe customer from the user's email and name; this repository contains no Stripe deletion call. |
| users | ERASED | `api/account.py:13`<br>`api/account.py:14` | The delete_account route calls session.delete on the User row and commits. |

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| billing | `billing.py` |
| analytics | `analytics.py` |
| mail | `mail.py` |
| cache | `cache.py` |
| catalog | `catalog.py` |
| api.account | `api/account.py` |
| api.profile | `api/profile.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

| Value | Evidence |
|---|---|
| `eu-central-1` | `config.py:9` |
| `sqlite:///./pulsedeck.db` | `config.py:5` |
| `redis://localhost:6379/0` | `config.py:10` |

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

Verification: none. This record was accepted on schema validity alone.

## H. Evidence index

| Evidence | Symbol | Sections |
|---|---|---|
| `analytics.py:11` | `mp.track`, `user.email`, `account_created` | A, B, D |
| `api/account.py:10` | `delete_account` | D |
| `api/account.py:13` | `session.delete` | D |
| `api/account.py:14` | `session.commit` | D |
| `api/profile.py:14` | — | A |
| `api/profile.py:16` | — | A |
| `api/profile.py:17` | — | A |
| `api/profile.py:18` | — | A |
| `app.py:9` | `url` | A, B |
| `app.py:10` | `query_string` | A, B |
| `app.py:11` | `request_body` | A, B |
| `app.py:12` | `local_variables` | A, B |
| `app.py:18` | `sentry_sdk.init` | A, D |
| `app.py:21` | `init_observability` | D |
| `billing.py:11` | `stripe.Customer.create` | A, D |
| `billing.py:12` | `email` | A, B |
| `billing.py:13` | `name` | A, B |
| `cache.py:7` | — | C |
| `cache.py:12` | `setex`, `token`, `user.email` | A |
| `cache.py:15` | `purge_session` | D |
| `config.py:5` | `sqlite:///./pulsedeck.db` | E |
| `config.py:9` | `eu-central-1` | E |
| `config.py:10` | `redis://localhost:6379/0` | E |
| `mail.py:11` | `body` | A, B |
| `mail.py:12` | `sg.send`, `to` | A, B, D |
| `models.py:11` | — | A |
| `models.py:12` | `__tablename__` | A |
| `models.py:14` | `email` | A |
| `models.py:15` | `full_name` | A |
| `models.py:16` | `marketing_opt_in` | A |
| `models.py:17` | `created_at` | A |
