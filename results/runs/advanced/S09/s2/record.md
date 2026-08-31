# Record of processing — slatecove

|  |  |
|---|---|
| Case | S09 (synthetic) |
| Arm | advanced |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `adv-S09-s2-f73aecc` |
| Code read | `evals/fixtures/synthetic/S09`, sha256 `8b63c6537a8d` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 16:11:16 UTC |
| Trace | `/Users/tun/Documents/micro1-hackathon/traces/advanced/S09-s2.jsonl` |
| Verification | 4 submissions, accepted on attempt 4, rule set `e9a260adc28b` |
| Approved | 2026-08-31 16:11:16 UTC without a person (--approve auto), 0 s at the checkpoint, risk LOW |
| Cost | USD 0.708609 (estimate at list prices), 18 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects: account holders — inferred from model name (`gallery/models.py:9`).

### gallery_account — relational — `gallery/models.py:16`

Table holding the account holder record.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `gallery/models.py:11` |  |
| `full_name` | identifier | `gallery/models.py:12` |  |
| `joined_at` | behavioural | `gallery/models.py:13` |  |

Linked to the data subject at `gallery/models.py:9`.

### gallery_comment — relational — `gallery/models.py:37`

Table of comments, tied to an account holder through the account foreign key.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `body` | free_text_may_contain | `gallery/models.py:32` | Text column the account holder writes into. |
| `posted_at` | behavioural | `gallery/models.py:33` |  |

Linked to the data subject at `gallery/models.py:34`.

### gallery_photo — relational — `gallery/models.py:27`

Table of photos, one account holder per row through the account foreign key.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `caption` | free_text_may_contain | `gallery/models.py:22` | Free-text field filled in by the account holder. |
| `taken_at` | behavioural | `gallery/models.py:23` |  |

Linked to the data subject at `gallery/models.py:24`.

### photo.image — object_storage — `gallery/models.py:21`

Uploaded image files written under the upload_to prefix photo/images/.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `image` | free_text_may_contain | `gallery/models.py:21` | Image file uploaded by the account holder under the prefix photo/images/; the schema does not constrain what it shows. |

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

- `delete_account` — view — `gallery/views.py:9` (HTTP route gallery/<int:pk>/delete/ calls delete() on the Account row.).
- `admin.site.register` — admin — `gallery/admin.py:7`, admin only (Registering Account in the Django admin gives both admin_delete_model, the single-object delete view, and admin_delete_selected, the bulk action, as ways to delete an account row.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| photo.image | NOT ERASED | `gallery/models.py:24`<br>`gallery/signals.py:9`<br>`gallery/signals.py:11`<br>`gallery/views.py:12` | The only receiver that deletes a stored file is registered for the sender Comment, and Comment has no image field, so deleting the Photo row leaves the uploaded file on storage; django_cleanup is not installed. |
| gallery_account | ERASED | `gallery/views.py:12` | The delete_account view calls delete() on the Account instance, which removes the row. |
| gallery_comment | ERASED | `gallery/models.py:34`<br>`gallery/views.py:12` | The foreign key to Account uses on_delete=models.CASCADE, so deleting the account removes the comment rows. |
| gallery_photo | ERASED | `gallery/models.py:24`<br>`gallery/views.py:12` | The foreign key to Account uses on_delete=models.CASCADE, so deleting the account removes the photo rows. |

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

Claims rejected and what replaced them.

| Round | Store | Claim | Reason | Rendered instead |
|---|---|---|---|---|
| — | — | — | none | — |

Stores the record did not contain, found by the scan of the repository.

| Round | Store | Kind | Evidence | Added |
|---|---|---|---|---|
| — | — | — | none | — |

Citations that did not resolve: 3. Claims that could not be decided: none.

## H. Evidence index

| Evidence | Symbol | Sections |
|---|---|---|
| `gallery/admin.py:7` | `admin.site.register` | D |
| `gallery/models.py:9` | — | A |
| `gallery/models.py:11` | `email` | A |
| `gallery/models.py:12` | `full_name` | A |
| `gallery/models.py:13` | `joined_at` | A |
| `gallery/models.py:16` | `gallery_account` | A |
| `gallery/models.py:21` | `ImageField`, `image` | A |
| `gallery/models.py:22` | `caption` | A |
| `gallery/models.py:23` | `taken_at` | A |
| `gallery/models.py:24` | `CASCADE` | A, D |
| `gallery/models.py:27` | `gallery_photo` | A |
| `gallery/models.py:32` | `body` | A |
| `gallery/models.py:33` | `posted_at` | A |
| `gallery/models.py:34` | `CASCADE` | A, D |
| `gallery/models.py:37` | `gallery_comment` | A |
| `gallery/signals.py:9` | `Comment` | D |
| `gallery/signals.py:11` | `instance.image.delete` | D |
| `gallery/views.py:9` | `delete_account` | D |
| `gallery/views.py:12` | `account.delete` | D |
| `slatecove/settings.py:10` | `SECURE_SSL_REDIRECT` | E |
