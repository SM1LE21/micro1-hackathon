# Record of processing — northgate

|  |  |
|---|---|
| Case | S06 (synthetic) |
| Arm | advanced |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `adv-S06-s2-5a98be5` |
| Code read | `evals/fixtures/synthetic/S06`, sha256 `ccaec9511690` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 15:46:45 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/advanced/S06-s2.jsonl` |
| Verification | 1 submission, accepted on attempt 1, rule set `e9a260adc28b` |
| Approved | 2026-08-31 15:46:45 UTC without a person (--approve auto), 0 s at the checkpoint, risk LOW |
| Cost | USD 0.366872 (estimate at list prices), 14 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects: account holders — inferred from model name (`accounts/models.py:9`).

### accounts_account — relational — `accounts/models.py:17`

Table holding one row per account holder.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `accounts/models.py:11` |  |
| `full_name` | identifier | `accounts/models.py:12` |  |
| `joined_at` | behavioural | `accounts/models.py:14` |  |

Linked to the data subject at `accounts/models.py:9`.

### accounts_address — relational — `accounts/models.py:37`

Postal addresses attached to an account.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `street` | contact | `accounts/models.py:32` |  |
| `postcode` | contact | `accounts/models.py:33` |  |

Linked to the data subject at `accounts/models.py:34`.

### accounts_comment — relational — `accounts/models.py:27`

Comments written by an account holder.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `body` | free_text_may_contain | `accounts/models.py:22` | Free text typed by the account holder; the schema does not constrain what it holds. |
| `posted_at` | behavioural | `accounts/models.py:23` |  |

Linked to the data subject at `accounts/models.py:24`.

### account.avatar — object_storage — `accounts/models.py:13`

Files written by the ImageField on Account.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `avatar` | identifier | `accounts/models.py:13` | Image file stored under the account/avatars/ prefix and referenced from the account row. |

Linked to the data subject at `accounts/models.py:13`.

Not scanned:

- `README.md` (not Python).
- `requirements.txt` (not Python).

## B. Recipients

No store of kind third_party was found in the code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| accounts_account | — | NO TIMER EVIDENCED | — | requires human completion |
| accounts_address | — | NO TIMER EVIDENCED | — | requires human completion |
| accounts_comment | — | NO TIMER EVIDENCED | — | requires human completion |
| account.avatar | — | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points:

- `delete_account` — view — `accounts/views.py:9` (Routed at accounts/<int:pk>/delete/ in northgate/urls.py line 10.).
- `Account` — admin — `accounts/admin.py:7`, admin only (Account is registered with the default Django admin, which offers per-object and bulk delete.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| accounts_comment | UNVERIFIED | `accounts/models.py:24`<br>`accounts/views.py:12`<br>`northgate/settings.py:22` | The foreign key delegates the delete to the database rather than the Django collector, and the repository runs on SQLite with no PRAGMA foreign_keys=ON connect listener, so the source does not show whether the comment rows are removed. |
| account.avatar | ERASED | `accounts/signals.py:9`<br>`accounts/signals.py:11`<br>`accounts/views.py:12` | Deleting the instance fires post_delete, and the receiver registered with sender=Account deletes the stored file; the receiver module is imported in AccountsConfig.ready at accounts/apps.py line 11. |
| accounts_account | ERASED | `accounts/views.py:12` | The delete_account view loads the Account and calls delete() on the instance, which removes the row. |
| accounts_address | ERASED | `accounts/models.py:34`<br>`accounts/views.py:12` | The foreign key uses Django's own on_delete=CASCADE, so the delete collector removes the address rows with the account row. |

Object storage: where bucket versioning is enabled, a delete that passes no `versionId` leaves the previous version of the object in place.

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| accounts | `accounts/models.py` |
| catalog | `catalog/models.py` |
| northgate | `northgate/settings.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

None.

Security measures. Technical measures under Article 32(1)(a) only, one line each. The organisational half is in section F.

| Measure | Evidence | Symbol |
|---|---|---|
| encryption in transit | `northgate/settings.py:10` | `SECURE_SSL_REDIRECT` |

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
| `accounts/admin.py:7` | `Account` | D |
| `accounts/models.py:9` | — | A |
| `accounts/models.py:11` | `email` | A |
| `accounts/models.py:12` | `full_name` | A |
| `accounts/models.py:13` | `avatar` | A |
| `accounts/models.py:14` | `joined_at` | A |
| `accounts/models.py:17` | `accounts_account` | A |
| `accounts/models.py:22` | `body` | A |
| `accounts/models.py:23` | `posted_at` | A |
| `accounts/models.py:24` | `DB_CASCADE` | A, D |
| `accounts/models.py:27` | `accounts_comment` | A |
| `accounts/models.py:32` | `street` | A |
| `accounts/models.py:33` | `postcode` | A |
| `accounts/models.py:34` | `CASCADE` | A, D |
| `accounts/models.py:37` | `accounts_address` | A |
| `accounts/signals.py:9` | `post_delete` | D |
| `accounts/signals.py:11` | `instance.avatar.delete` | D |
| `accounts/views.py:9` | `delete_account` | D |
| `accounts/views.py:12` | `account.delete` | D |
| `northgate/settings.py:10` | `SECURE_SSL_REDIRECT` | E |
| `northgate/settings.py:22` | `django.db.backends.sqlite3` | D |
