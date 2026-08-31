# Record of processing — slatecove

|  |  |
|---|---|
| Case | S09 (synthetic) |
| Arm | baseline |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `base-S09-s3-a79cc26` |
| Code read | `evals/fixtures/synthetic/S09`, sha256 `8b63c6537a8d` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 16:12:14 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/baseline/S09-s3.jsonl` |
| Verification | 1 submission, accepted on attempt 1 |
| Cost | USD 0.228726 (estimate at list prices), 14 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects: account holders — inferred from model name (`gallery/models.py:9`).

### gallery_account — relational — `gallery/models.py:16`

Table holding one row per account holder.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `gallery/models.py:11` |  |
| `full_name` | identifier | `gallery/models.py:12` |  |
| `joined_at` | behavioural | `gallery/models.py:13` |  |

Linked to the data subject at `gallery/models.py:9`.

### gallery_comment — relational — `gallery/models.py:37`

Table of comments, each pointing at one account.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `body` | free_text_may_contain | `gallery/models.py:32` | Text field written by the account holder; the schema does not constrain its contents. |
| `posted_at` | behavioural | `gallery/models.py:33` |  |

Linked to the data subject at `gallery/models.py:34`.

### gallery_photo — relational — `gallery/models.py:27`

Table of photos, each pointing at one account.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `caption` | free_text_may_contain | `gallery/models.py:22` | Free-text field typed by the account holder; the schema does not constrain its contents. |
| `taken_at` | behavioural | `gallery/models.py:23` |  |
| `image` | identifier | `gallery/models.py:21` | Column holds the storage path of the uploaded file; the file itself is recorded as the store photo.image. |

Linked to the data subject at `gallery/models.py:24`.

### photo.image — object_storage — `gallery/models.py:21`

Files written by the ImageField on Photo under the upload_to prefix photo/images/.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `image` | identifier | `gallery/models.py:21` | Uploaded file stored under photo/images/ and reachable from the account's photo row. |

Linked to the data subject at `gallery/models.py:24`.

Not scanned:

- `README.md` (not Python).
- `requirements.txt` (not Python).

## B. Recipients

No store of kind third_party was found in the code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| gallery_account | — | NO TIMER EVIDENCED | — | requires human completion |
| gallery_comment | — | NO TIMER EVIDENCED | — | requires human completion |
| gallery_photo | — | NO TIMER EVIDENCED | — | requires human completion |
| photo.image | — | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points:

- `delete_account` — view — `gallery/views.py:9` (Routed at gallery/<int:pk>/delete/ in slatecove/urls.py line 10.).
- `Account` — admin — `gallery/admin.py:7`, admin only (Account is registered with the default Django admin, which offers a delete action.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| photo.image | NOT ERASED | `gallery/models.py:21`<br>`gallery/signals.py:9`<br>`slatecove/settings.py:12` | Deleting the Photo row leaves the uploaded file in storage: the only post_delete receiver that calls image.delete() is registered with sender=Comment, and django_cleanup is not in INSTALLED_APPS. |
| gallery_account | ERASED | `gallery/views.py:12` | The delete_account view calls delete() on the Account instance, which removes the row. |
| gallery_comment | ERASED | `gallery/models.py:34`<br>`gallery/views.py:12` | The foreign key to Account uses on_delete=models.CASCADE, so deleting the account row deletes the comment rows. |
| gallery_photo | ERASED | `gallery/models.py:24`<br>`gallery/views.py:12` | The foreign key to Account uses on_delete=models.CASCADE, so deleting the account row deletes the photo rows. |

Object storage: where bucket versioning is enabled, a delete that passes no `versionId` leaves the previous version of the object in place.

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| gallery | `gallery/models.py` |
| catalog | `catalog/models.py` |
| slatecove | `slatecove/settings.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

None.

Security measures. Technical measures under Article 32(1)(a) only, one line each. The organisational half is in section F.

| Measure | Evidence | Symbol |
|---|---|---|
| encryption in transit | `slatecove/settings.py:10` | `SECURE_SSL_REDIRECT` |

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
| `gallery/admin.py:7` | `Account` | D |
| `gallery/models.py:9` | — | A |
| `gallery/models.py:11` | `email` | A |
| `gallery/models.py:12` | `full_name` | A |
| `gallery/models.py:13` | `joined_at` | A |
| `gallery/models.py:16` | `gallery_account` | A |
| `gallery/models.py:21` | `image`, `ImageField` | A, D |
| `gallery/models.py:22` | `caption` | A |
| `gallery/models.py:23` | `taken_at` | A |
| `gallery/models.py:24` | `CASCADE` | A, D |
| `gallery/models.py:27` | `gallery_photo` | A |
| `gallery/models.py:32` | `body` | A |
| `gallery/models.py:33` | `posted_at` | A |
| `gallery/models.py:34` | `CASCADE` | A, D |
| `gallery/models.py:37` | `gallery_comment` | A |
| `gallery/signals.py:9` | `sender=Comment` | D |
| `gallery/views.py:9` | `delete_account` | D |
| `gallery/views.py:12` | `account.delete` | D |
| `slatecove/settings.py:10` | `SECURE_SSL_REDIRECT` | E |
| `slatecove/settings.py:12` | `INSTALLED_APPS` | D |
