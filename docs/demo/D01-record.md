# Record of processing — harbourlight

|  |  |
|---|---|
| Case | D01 (synthetic) |
| Arm | advanced |
| Model | Claude (your login) — claude-opus-5, effort high |
| Run | `adv-D01-s1-3dbfe02` |
| Code read | `evals/fixtures/synthetic/D01`, sha256 `274ffa62d227` |
| Instructions | sha256 `43c86cec9e8c` |
| Generated | 2026-08-31 15:01:25 UTC |
| Trace | `results/web/advanced-D01-s1-19858b/traces/advanced/D01-s1.jsonl` |
| Verification | 1 submission, accepted on attempt 1, rule set `e9a260adc28b` |
| Approved | 2026-08-31 15:01:25 UTC at the terminal, 262 s at the checkpoint, risk HIGH |
| Cost | USD 0.332818 (estimate at list prices), 13 tool calls |

This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

## A. Data inventory

Data subjects:

- members (account holders) — inferred from model name (`members/models.py:9`).
- members using the login route — inferred from route name (`harbourlight/urls.py:12`).

### members_member — relational — `members/models.py:18`

The member table; the class the rest of the app links to.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `members/models.py:11` |  |
| `display_name` | identifier | `members/models.py:12` |  |
| `phone` | contact | `members/models.py:13` |  |
| `last_login` | behavioural | `members/models.py:15` | Set by auto_now_add on the member row, so it records when the row was created for this person. |

Linked to the data subject at `members/models.py:9`.

### members_note — relational — `members/models.py:28`

Support notes written about a member.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `body` | free_text_may_contain | `members/models.py:23` | The comment on the column says these are support notes that may include phone numbers and addresses. |
| `written_at` | behavioural | `members/models.py:24` |  |

Linked to the data subject at `members/models.py:25`.

### members_order — relational — `members/models.py:38`

Orders placed by a member.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `total` | financial | `members/models.py:33` |  |
| `placed_at` | behavioural | `members/models.py:34` |  |

Linked to the data subject at `members/models.py:35`.

### member.avatar — object_storage — `members/models.py:14`

Uploaded avatar files written under the member/avatars/ prefix.

| Field | Category | Evidence | Note |
|---|---|---|---|
| `avatar` | identifier | `members/models.py:14` | An ImageField whose stored file sits under the member/avatars/ prefix and belongs to one member. |

Linked to the data subject at `members/models.py:14`.

Not scanned:

- `README.md` (not Python).
- `requirements.txt` (not Python).

## B. Recipients

No store of kind third_party was found in the code.

## C. Retention

| Store | Category | Envisaged limit | Evidence | Justification |
|---|---|---|---|---|
| members_member | — | NO TIMER EVIDENCED | — | requires human completion |
| members_note | — | NO TIMER EVIDENCED | — | requires human completion |
| members_order | — | NO TIMER EVIDENCED | — | requires human completion |
| member.avatar | — | NO TIMER EVIDENCED | — | requires human completion |

A period found in code is evidence for a retention schedule. The schedule itself is a policy the controller sets, and the reason for each period belongs in the justification column.

## D. Erasure

Erasure entry points:

- `delete_account` — view — `members/views.py:9` (Routed at members/<int:pk>/delete/ in harbourlight/urls.py line 10 and calls member.delete().).
- `Member` — admin — `members/admin.py:7`, admin only (Member is registered with the default admin site, which gives operators a delete action.).

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| member.avatar | NOT ERASED | `members/models.py:14`<br>`members/views.py:12` | Deleting the member row leaves the uploaded file: the repository registers no pre_delete or post_delete receiver, no storage delete call, and INSTALLED_APPS in harbourlight/settings.py lines 12 to 18 does not list django_cleanup. |
| members_member | ERASED | `members/views.py:9`<br>`members/views.py:12` | The delete_account view loads the member and calls member.delete(), which removes the row. |
| members_note | ERASED | `members/models.py:25`<br>`members/views.py:12` | The foreign key to Member uses on_delete=models.CASCADE, so member.delete() in the view removes the note rows with it. |
| members_order | ERASED | `members/models.py:35`<br>`members/views.py:12` | The foreign key uses on_delete=models.DB_CASCADE, which removes the order rows in the database when the member is deleted and emits no Django signal. |

Object storage: where bucket versioning is enabled, a delete that passes no `versionId` leaves the previous version of the object in place.

## E. Observations from the code (not findings)

Module names. A module name says what the code was called, not what it is for. Article 30(1)(b) purposes are in section F.

| Name | File |
|---|---|
| members | `members/apps.py` |
| harbourlight | `harbourlight/settings.py` |
| shop | `shop/models.py` |

Region hints. A region string says where a service was configured to run. It is not a finding about a transfer under Article 30(1)(e); that cell is in section F.

None.

Security measures. Technical measures under Article 32(1)(a) only, one line each. The organisational half is in section F.

| Measure | Evidence | Symbol |
|---|---|---|
| encryption in transit | `harbourlight/settings.py:10` | `SECURE_SSL_REDIRECT` |

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
| `harbourlight/settings.py:10` | `SECURE_SSL_REDIRECT` | E |
| `harbourlight/urls.py:12` | — | A |
| `members/admin.py:7` | `Member` | D |
| `members/models.py:9` | — | A |
| `members/models.py:11` | `email` | A |
| `members/models.py:12` | `display_name` | A |
| `members/models.py:13` | `phone` | A |
| `members/models.py:14` | `avatar`, `ImageField` | A, D |
| `members/models.py:15` | `last_login` | A |
| `members/models.py:18` | `members_member` | A |
| `members/models.py:23` | `body` | A |
| `members/models.py:24` | `written_at` | A |
| `members/models.py:25` | `CASCADE` | A, D |
| `members/models.py:28` | `members_note` | A |
| `members/models.py:33` | `total` | A |
| `members/models.py:34` | `placed_at` | A |
| `members/models.py:35` | `DB_CASCADE` | A, D |
| `members/models.py:38` | `members_order` | A |
| `members/views.py:9` | `delete_account` | D |
| `members/views.py:12` | `delete` | D |
