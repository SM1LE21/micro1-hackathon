# Record of processing — pulsedeck

|  |  |
|---|---|
| Case | S05 (synthetic) |
| Arm | advanced |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `adv-S05-s1-ff7f069` |
| Code read | `evals/fixtures/synthetic/S05`, sha256 `1c7af597478a` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 15:35:36 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/advanced/S05-s1.jsonl` |
| Verification | 2 submissions, accepted on attempt 2, rule set `e9a260adc28b` |
| Approved | 2026-08-31 15:35:36 UTC without a person (--approve auto), 0 s at the checkpoint, risk HIGH |
| Cost | USD 0.515077 (estimate at list prices), 17 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects: account holders — inferred from model name (`models.py:11`).

### users — relational — `models.py:12`

The single SQLAlchemy table holding the account row.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:14` |  |
| `full_name` | identifier | `models.py:15` |  |
| `marketing_opt_in` | behavioural | `models.py:16` |  |
| `created_at` | behavioural | `models.py:17` |  |

Linked to the data subject at `models.py:11`.

### sessions: — cache — `cache.py:12`

Redis keyspace written by store_session at login.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `cache.py:12` | The Redis key is built as sessions:<user email>, so the address is part of the key. |
| `token` | technical | `cache.py:12` | The session token passed by login is stored as the value. |

Linked to the data subject at `cache.py:12`.

### mixpanel — third_party — `analytics.py:7`

Product analytics service called from the signup route.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `analytics.py:11` | The user's email address is passed as the Mixpanel distinct id. |
| `account_created` | behavioural | `analytics.py:11` | Event name recorded against the user. |

Linked to the data subject at `analytics.py:11`.

### sendgrid — third_party — `mail.py:7`

Transactional mail provider called from the signup route.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `full_name` | identifier | `mail.py:11` | The name is interpolated into the message body sent to the provider. |
| `email` | contact | `mail.py:12` | Recipient address of the welcome message. |

Linked to the data subject at `mail.py:12`.

### sentry — third_party — `app.py:18`

Error tracker initialised when app.py is imported.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `query_string` | technical | `app.py:10` | Listed in the repository's own SENTRY_DEFAULT_FIELDS as sent by default. |
| `request_body` | free_text_may_contain | `app.py:11` | A request body sent to an error tracker can carry whatever the person submitted. |
| `local_variables` | free_text_may_contain | `app.py:12` | Stack-frame locals captured with an exception can carry any value in scope. |

No link to a data subject found in code.

### stripe — third_party — `billing.py:11`

Stripe customer created from the signup route.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `billing.py:12` |  |
| `name` | identifier | `billing.py:13` | The user's full_name is sent as the Stripe customer name. |

Linked to the data subject at `billing.py:12`.

Not scanned:

- `README.md` (not Python).
- `requirements.txt` (not Python).

## B. Recipients

| Recipient | Fields disclosed | Evidence | Recipient kind |
|---|---|---|---|
| mixpanel | `email` (contact), `account_created` (behavioural) | `analytics.py:11`, `analytics.py:11` | UNKNOWN — requires human completion |
| sendgrid | `full_name` (identifier), `email` (contact) | `mail.py:11`, `mail.py:12` | UNKNOWN — requires human completion |
| sentry | `query_string` (technical), `request_body` (free_text_may_contain), `local_variables` (free_text_may_contain) | `app.py:10`, `app.py:11`, `app.py:12` | UNKNOWN — requires human completion |
| stripe | `email` (contact), `name` (identifier) | `billing.py:12`, `billing.py:13` | UNKNOWN — requires human completion |

Personal data flows into the call at the cited lines. Whether this recipient acts as a processor on the controller's instructions or as an independent controller, and whether a contract under Article 28(3) exists, is not visible in code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| users | — | NO TIMER EVIDENCED | — | requires human completion |
| sessions: | all categories | 1 days Session keys are written with a 86400-second expiry. | `cache.py:7` | requires human completion |
| mixpanel | — | NO TIMER EVIDENCED | — | requires human completion |
| sendgrid | — | NO TIMER EVIDENCED | — | requires human completion |
| sentry | — | NO TIMER EVIDENCED | — | requires human completion |
| stripe | — | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points: `delete_account` — route — `api/account.py:10` (Takes a session and a user_id and deletes the matching users row.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| sessions: | NOT ERASED | `api/account.py:10`<br>`cache.py:15` | purge_session deletes the key, but delete_account does not call it and nothing else in the repository does; the 86400-second TTL expires the key independently of the deletion path. |
| mixpanel | EXTERNAL MANUAL | `analytics.py:11`<br>`api/profile.py:17` | The repository sends the event and contains no Mixpanel deletion call. |
| sendgrid | EXTERNAL MANUAL | `api/profile.py:18`<br>`mail.py:12` | The repository sends the message and contains no call that removes it or the recipient from SendGrid. |
| sentry | EXTERNAL MANUAL | `app.py:18` | Sentry is initialised at import time and the repository contains no call that deletes events from it. |
| stripe | EXTERNAL MANUAL | `api/profile.py:16`<br>`billing.py:11` | The repository creates the Stripe customer and contains no call that deletes or redacts it. |
| users | ERASED | `api/account.py:12`<br>`api/account.py:13`<br>`api/account.py:14` | The route loads the User row and calls session.delete on it, then commits. |

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| analytics | `analytics.py` |
| billing | `billing.py` |
| mail | `mail.py` |
| cache | `cache.py` |
| catalog | `catalog.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

| Value | Evidence |
|---|---|
| `eu-central-1` | `config.py:9` |

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
| Recipient kind — sentry | (d) | requires human completion |
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
| `analytics.py:7` | `Mixpanel` | A |
| `analytics.py:11` | `email`, `account_created`, `mp.track` | A, B, D |
| `api/account.py:10` | `delete_account` | D |
| `api/account.py:12` | `session.get` | D |
| `api/account.py:13` | `session.delete` | D |
| `api/account.py:14` | `commit` | D |
| `api/profile.py:16` | `create_customer` | D |
| `api/profile.py:17` | `track_signup` | D |
| `api/profile.py:18` | `send_welcome` | D |
| `app.py:10` | `query_string` | A, B |
| `app.py:11` | `request_body` | A, B |
| `app.py:12` | `local_variables` | A, B |
| `app.py:18` | `sentry_sdk.init` | A, D |
| `billing.py:11` | `stripe.Customer.create` | A, D |
| `billing.py:12` | `email` | A, B |
| `billing.py:13` | `name` | A, B |
| `cache.py:7` | — | C |
| `cache.py:12` | `setex`, `email`, `token` | A |
| `cache.py:15` | `purge_session` | D |
| `config.py:9` | `eu-central-1` | E |
| `mail.py:7` | `SendGridAPIClient` | A |
| `mail.py:11` | `full_name` | A, B |
| `mail.py:12` | `email`, `sg.send` | A, B, D |
| `models.py:11` | — | A |
| `models.py:12` | `users` | A |
| `models.py:14` | `email` | A |
| `models.py:15` | `full_name` | A |
| `models.py:16` | `marketing_opt_in` | A |
| `models.py:17` | `created_at` | A |
