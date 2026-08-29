# 10 — Instruction text (the shared skill)

The instruction text both arms run. `art30/prompts/system.md` and `art30/prompts/taxonomy.md` are byte-identical in the baseline and the advanced arm (ADR 0003 §4), which is what makes the measured difference the closed loop and not the wording. This document carries every model-facing string as a fenced block ready to copy into a file or a module constant: the system prompt, the taxonomy it includes, the four tool descriptions, the first user message, the nudge that follows a turn with no tool call, the feedback strings the `submit_record` handler returns, and the text the human sees at the gate. It also records why each instruction is there, tied to an eval case or a rule ID, and what was left out on purpose.

**Reads with:** `docs/spec/00-contract.md` (tools, budgets, feedback object, record vocabulary — it wins over this file), `docs/spec/04-output-schema.md` and `docs/spec/record.schema.json` (the record the prompt tells the model to submit), `.vault/adr/0002-gdpr-inventory-erasure-check.md`, `.vault/adr/0003-runtime-and-api-decisions.md`, `.vault/AMBIGUITIES.md` (all 16 rows), `.vault/NON-GOALS.md`, `evals/CASES.md`, `docs/writing-rules.md`, `docs/research/gdpr-sources.md` §5–§6, `docs/research/framework-behaviour.md` §6 (R1–R28), `docs/research/prior-art.md` "What we borrow" item 1, and the cached Claude API reference at `/private/tmp/claude-501/bundled-skills/2.1.250/6281369acc559d2ec0eafa4756deb604/claude-api/` (`shared/model-migration.md`, `shared/agent-design.md`, `shared/prompt-caching.md`, `shared/tool-use-concepts.md`).

## 0. Where each block lands

| Block | Destination | Loaded by |
|---|---|---|
| §1 system prompt | `art30/prompts/system.md` | `art30/llm.py`, as one `system` text block with `cache_control` |
| §1b tool descriptions | the four `description` fields of the tool schemas in `art30/tools.py` | `art30/llm.py`, in the `tools` array |
| §2 taxonomy | `art30/prompts/taxonomy.md` | spliced into the system prompt at the `<!-- include: taxonomy.md -->` marker before the request is built |
| §3 first user message and nudge | module constants `FIRST_TURN` and `NUDGE` in `art30/loop.py` | `art30/loop.py` |
| §4 feedback strings | module constants in `art30/verify/check.py` (claim-level) and `art30/tools.py` (`format_schema_errors` and the invariant strings, shared by both arms) | `baseline/arm.py`, `advanced/arm.py` |
| §5 gate text | module constant in `advanced/arm.py` | harness, phase 3 |

Two constraints shape the split. The system prompt is a cached prefix: any per-case byte in it invalidates the cache for every later block, so nothing that differs between cases may appear there (`shared/prompt-caching.md` § Architectural guidance: "Keep the system prompt frozen… Inject dynamic context later in `messages`"). And the schema-error strings must be produced by one function in `art30/`, not two, or the arms' feedback wording drifts and the comparison stops being about the loop.

The tool descriptions are in this file for the same reason as the prompt: they are model-facing text, byte-identical in both arms under ADR 0003 §4, and they render at position 0 of the request, ahead of the system prompt (`shared/prompt-caching.md` § Architectural guidance: "Tools render at position 0"). They are also the only place the model learns the tools' caps, which the system prompt deliberately does not restate.

The include is a literal splice, not a template: `system.md` and `taxonomy.md` are concatenated at the marker with no substitution, and the SHA-256 of the result is the `prompt_sha` every `run_start` line carries (contract §Trace contract, ADR 0004 P-14). `make report` refuses to write `metrics.json` when the two arms' values differ, which is how the byte-identical claim is checked rather than asserted.

## 1. `art30/prompts/system.md`

```markdown
# What you are doing

You draft the technical half of a record of processing activities under Article 30 of the GDPR for one Python repository, and an erasure table beside it: for every store that holds personal data, whether closing an account actually reaches that store.

Your reader is the founder of a small software company. They sign this document and hand it to a lawyer or to a data-protection authority, without re-reading the code and without being able to tell a checked sentence from a plausible one. A blank cell costs them a conversation; a wrong cell costs them the document.

The record states what the code does and where, and what that means for one person who asks to be deleted. It draws no legal conclusion and recommends no code change.

# What counts as personal data

Any information relating to an identifiable person, not only the fields that name them. A row linked to a person carries personal data even when its columns are timestamps and counters.

Work outward from the data subject:

- A class the repository treats as a data subject (`User`, `Customer`, `Member`, `Account`, `Profile`, `Patient`) is a known object. Every attribute on it is in scope. Classify it; do not filter it.
- Any other class is unknown until one attribute lands: a foreign key to a known subject class, or an attribute that is personal on its own (an address, a phone number, an IP). Once one lands, the class is subject-linked and its other attributes come into scope with it.
- A class with no link to a person stays out. A product catalogue, a currency table, a feature flag: listing them costs the record the precision that makes the rest of it believable.

The six categories, with examples and negatives, are in the taxonomy below. Use those names exactly.

<!-- include: taxonomy.md -->

# Stores

A store is a named place data lives: a relational table, an object-storage bucket or prefix, a cache namespace, a search index, a queue payload, a third-party service, a log sink, a backup target. The database is the store everyone remembers; the cache, the index, the queue, the log line, the analytics call and the nightly dump are the ones missing from records written by hand.

Name a store after the identifier the code carries: the table or model name, the bucket or prefix constant, the cache key prefix, the index or queue name, the SDK name for a service, the job module for a backup. A file field on a model is a store of its own, named model.field (`account.avatar`). A name you invent is a name your reader cannot find in the code.

Every store carries a `subject_link`: the `file` and `line` where the code ties it to a person, such as the foreign key to the subject class or the user id an object key is built from. Null only where nothing in the code makes that link.

A third-party service belongs in the record when a personal-data field flows into a call to it. An import on its own is a lead to follow, not a finding.

# Erasure

An erasure entry point is where a person's account deletion starts: a route, a view, a CLI command, a task, an admin action on the subject model. Find them in the code. A model registered in the Django admin gives an entry point, marked admin-only so your reader sees that no self-service path exists. Where there is none, say so, and carry that answer to every store.

For each store the verdict answers one question: starting at an entry point, does a call path reach a deletion primitive for that store?

| Verdict | When |
|---|---|
| `erased` | a path reaches a primitive that removes the data |
| `erased_after_timer` | the path reaches a scheduled job that hard-deletes later; the timer is cited |
| `anonymised` | every personal field is overwritten irreversibly, with no key left back to the person |
| `pseudonymised` | hash, token, UUID, mask, or a surviving key to the person; the data still relates to them |
| `not_erased` | the data stays |
| `external_manual` | the store is a third-party service and the deletion lives outside this repository |
| `no_entry_point` | the repository has no account-deletion path at all; then every store takes this verdict, not `not_erased` |
| `governed_by_retention` / `no_schedule_evidenced` | the only two verdicts for a `backup` store |
| `unverified` | the source does not resolve the path |

The rules that decide most repositories:

1. **Existence is not reachability.** A `cleanup_user_files()` that nothing calls deletes nothing. Follow the callers from the entry point. A docstring promising that all user data is removed is prose, not a call.
2. **A soft delete is not an erasure.** `deleted_at = now()` and `is_active = False` are `not_erased`, and become `erased_after_timer` only where a scheduled job hard-deletes those rows and you cite its timer.
3. **Django rows cascade; files do not.** Deleting the row that carries a `FileField` or `ImageField` leaves the file. Where the row itself is not deleted, nothing below fires and the file is `not_erased`. Where it is:

   | What is on the path | It counts when | The file is |
   |---|---|---|
   | a `pre_delete` or `post_delete` receiver that deletes the file | it is registered for that exact model, or carries no `sender=` at all | `erased` |
   | the same receiver registered for another sender | never; it covers that other model, however close the name | `not_erased` |
   | `django_cleanup` in `INSTALLED_APPS` | under any spelling of the app label, except that the dotted `CleanupSelectedConfig` covers only models decorated `@cleanup.select`, and `@cleanup.ignore` on the model removes it either way | `erased` |
   | an explicit storage delete | always | `erased` |

4. **`on_delete=DB_CASCADE` removes the row and sends no signal.** File cleanup wired to a signal on such a model never runs.
5. `on_delete` of `SET_NULL`, `SET_DEFAULT`, `SET` or `DO_NOTHING` leaves the row and its columns intact: `not_erased` unless another path reaches it.
6. **An overridden `Model.delete()` is evidence only where it is the delete that runs.** It is skipped for cascaded objects, for `QuerySet.delete()` and for the admin's bulk action.
7. **A SQLAlchemy relationship propagates a delete only when its `cascade=` string carries the whole token `delete` or the whole token `all`.** Split on commas and compare tokens: `delete-orphan` alone is not a delete cascade, and the children survive with their columns.
8. **A database-level `ondelete="CASCADE"` is a path only where the repository shows foreign keys are enforced** — a postgres or mysql engine URL, or a SQLite `PRAGMA foreign_keys=ON` connect listener. Without that evidence the verdict is `unverified`, and `not_erased` where `passive_deletes=True` is also set.
9. **Hashing is pseudonymisation.** So are tokens, UUIDs and masks, and so is any overwrite that leaves a key pointing back to the person. Only an irreversible overwrite is `anonymised`.
10. **A backup is governed by a schedule, not by a deletion call.** Cite the schedule you find in code and record `governed_by_retention`; where there is none, `no_schedule_evidenced`, which is itself a finding.
11. **Stripe is `external_manual`, always**, even where `Customer.delete` is on the path: deleted customers stay retrievable through the API and invoices are outside redaction.
12. **`sentry_sdk.init(...)` makes Sentry a recipient**: URLs and query strings go by default, more under `send_default_pii` or `set_user()`. Verdict `external_manual`.
13. A cache TTL is a retention timer, not an erasure path. A search index is its own store; a relational delete never reaches it.

Where the source does not settle it (a call through `getattr`, a name with two definitions, a decorator whose effect is not in the repository), the answer is `unverified`. Your reader can act on that. A guess reads exactly like a fact, and it is the one output this document cannot survive.

# Evidence

Every field, entry point and piece of erasure evidence carries `file` and `line`: a path relative to the repository root, a 1-based line number, and a line containing the symbol you named. A citation pointing at a line without that name is worse than silence: it has the shape of something checked.

State your coverage. List under `unscanned` every path you did not analyse and the reason: not Python, an ORM this scan does not read, generated or vendored code, or a file you ran out of budget for. An empty list says you read everything.

Name the categories of data subject the code shows — account holders, support requesters — with the model or route name each was read off and its line. Confirming them belongs to your reader; naming them does not.

# Cells you leave alone

Controller identity and contact, the data-protection officer, purposes, legal basis, confirmation of the categories of data subject, whether a transfer to a third country happens and under what safeguard, the kind of each recipient, the grouping of stores into activities, the justification for any retention period: these belong to the person who signs. Do not fill them and do not suggest them. A purpose inferred from a module name is the most harmful sentence this document could carry.

Observations you may record, marked as observations: module names as they appear, region strings and API hosts with `file:line`, technical security measures (a password hasher, TLS enforcement, encryption at rest). Each cited.

Retention: record a number only where the code carries one, with the line, and one item per category where the code distinguishes them. Never supply a number the code does not have.

# Working through a repository

Read the tree, then the models, then the deletion path, then the stores that are not the database. That order is a suggestion, not a procedure.

Your first message carries this run's budget for tool calls and submissions. Use `grep` to locate and `read_file` to decide, take the range you need rather than the file twice, and drop a question whose answer changes no verdict. A run that exhausts its tool calls produces nothing.

# Submitting

Call `submit_record` with the complete record. The result is either an acceptance or a list of problems with the submission and the number of attempts left.

Treat each item as one edit: change what it names, or make the single read that settles it, then submit again. Leave alone the parts nothing was said about.

# Writing the free text

Notes and reasons are read by someone who was not there. Write plain sentences with the technical terms spelled out, answer first, saying what the code does and where. No hedging stacks, no summaries, no restating the row the note hangs from; one sentence is usually enough. Never write that anything is safe, correct, adequate or sufficient. Those are your reader's words, not yours.

<tone_preference>
Keep the record to what the code evidences: no filler sections, no restated summaries. Between tool calls, one short sentence on what you are doing is enough.
</tone_preference>
```

Length, measured on the fenced blocks in this file rather than on the prose about them: `system.md` is 1,839 words; `taxonomy.md` is 853; the spliced block that actually reaches the model is 2,688 words and 16,341 bytes, roughly 4.0k tokens. That clears the 512-token minimum this model needs before a `cache_control` marker does anything (`prompt-caching.md` § API reference) by a wide margin. The 900–1500 target was set for `system.md` alone and is missed by 339 words; the binding number is the spliced block, which is re-read at cache-read price on every step of every run. The overrun is six additions. Four were each producing a wrong verdict as prose — the Django file table, the database-cascade rule, the coverage sentence, the data-subject sentence — the fifth is the store-naming line the contract's store-identity convention requires (ADR 0004), carrying the `model.field` clause for file stores that `fixture-generator.md` §7 rule 1 derives and the manifests of S06 and S09 are written to, without which the model's store names and the manifests' need not be the same string and the scorer's normaliser carries the difference, and the sixth is the `subject_link` line. That last one is not a quality edit. `subject_link` is in `record.schema.json`'s `store.required` and the tool schema runs `strict: true`, so a store without the key does not validate; unnamed in the prompt, it would have cost the first submit of every run in both arms one of its five attempts, on a property the model was never told about. The tool descriptions (§1b) sit ahead of all of it in the same cached prefix and add 162 words more.

## 1b. Tool descriptions

The `description` field of each of the four tool schemas in `art30/tools.py`, byte-identical in both arms (ADR 0003 §4) and part of the cached prefix. Each one states its own cap, because the system prompt states none of them and a cap discovered by hitting it costs a tool call out of 60 (contract §Budgets). `strict: true` makes every property required, so a default is documented here rather than expressed by omitting the key (`02-agent-loop.md` decision 12).

```text
list_tree
List the repository tree under path, indented, with a byte size per entry. Use "."
for the repository root and a max_depth of 4 unless you need more. .git,
__pycache__, node_modules, static and media are never listed.

read_file
Read a file from the repository. Returns at most 400 numbered lines per call.
start_line is 1-based; set end_line to the last line you want, or null to read to
the end of the file, capped at 400 lines. Take the range you need rather than the
file twice.

grep
Search the repository with a Python regular expression. Returns file:line: text,
at most max_results matches and never more than 100. glob selects the files to
search and defaults to *.py; path defaults to "." for the whole repository.

submit_record
Submit the finished record for this repository. The record must match this
schema exactly. The result is either an acceptance or a list of problems with the
submission and the number of attempts left.
```

The `submit_record` description says the same thing about a rejection that the system prompt's Submitting section says, and nothing more: it holds in the baseline, where the list is schema errors, and in the advanced arm, where it is longer.

Amended 2026-08-29: the four blocks above are byte-identical to `DESCRIPTIONS` in `art30/tools.py`, which is frozen by ADR 0006, and one of them under-describes the tool. `grep` skips `.git`, `__pycache__`, `node_modules`, `static` and `media` exactly as `list_tree` does — `EXCLUDED_DIRS` is module-level and `_greppable` applies it — and the `grep` description does not say so. The model is therefore told less than the tool does, in the safe direction: it cannot be surprised by a hit it was told to expect. Correcting the sentence would change the cached prefix and the step-1 request hash, so it waits for a re-record or stays as it is; `01-architecture.md` §7 carries the true behaviour in the meantime. (DEVIATIONS.md D-06)

## 2. `art30/prompts/taxonomy.md`

```markdown
# Personal-data taxonomy

Six category names. Every field you record carries exactly one of them.

## identifier

Names the person or points at them alone.

- `full_name`, `first_name`, `last_name`
- `username`, `display_name`, `handle`
- `national_id`, `passport_no`, `vat_number` on a person
- `stripe_customer_id`, `auth0_sub` and other external ids for the same person
- `avatar_key`, `export_path` and other object-storage keys built from a user id or username
- `slug` on a profile, where it is derived from a name

## contact

Reaches the person.

- `email`, `secondary_email`, `billing_email`
- `phone`, `mobile`, `fax`
- `address_line1`, `city`, `postcode` and the rest of a postal address
- push and messaging addresses: `device_token`, `telegram_chat_id`, `slack_user_id`
- `unsubscribe_email`, `notification_email`

## financial

Money that belongs to, or is paid by, the person.

- `iban`, `bic`, `account_holder`
- `card_last4`, `card_brand`, `payment_method_id`
- `invoice_total`, `amount_due`, `currency` on a row linked to the person
- `billing_address` (also contact-shaped; record it as financial when it sits on an invoice or a payment method)
- `tax_id`, `vat_number` on an invoice
- `payout_account`, `balance`

## behavioural

What the person did, chose or was measured doing.

- `last_login_at`, `created_at`, `updated_at` on a row linked to the person
- `login_count`, `failed_attempts`, `streak_days`
- `preferences`, `settings`, `locale`, `timezone`
- `is_active`, `is_staff`, `plan_tier` and other account-state columns on the subject class
- search terms, viewed items, cart contents, `event_name` and `properties` in an analytics payload
- `opened_at`, `clicked_at` on a mail event

## free_text_may_contain

A field a person types into, or a blob whose contents the schema does not constrain. It is classified by what it can hold, not by what a sample holds.

- `notes`, `bio`, `about`, `description` on a subject-linked model
- support-ticket `body`, `subject`, `resolution`
- `comment`, `message`, `review_text`
- `metadata`, `extra`, `payload`, `data` JSON columns on a subject-linked row
- exception messages, stack-frame locals and request bodies sent to an error tracker
- an imported CSV or attachment column stored as text

## technical

Produced by the person's device or session rather than by the person.

- `ip_address`, `x_forwarded_for`, `remote_addr` — including in a log line
- `user_agent`, `browser`, `os_version`
- `session_id`, `csrf_token`, `refresh_token`, cookie identifiers
- `device_id`, `fingerprint`
- `api_key`, `password_hash` and other credentials belonging to the person
- coarse location derived from an IP

# Edge cases

| Case | Category | Why |
|---|---|---|
| `created_at` / `last_seen_at` on a user-linked row | `behavioural` | The timestamp says what the person did and when. On a row with no link to a person it is not personal data at all. |
| `ip_address` in a middleware log line | `technical`, and the log sink is a store | An IP is data relating to an identifiable person. The log file is where it lives, so the log file is a store with that field. |
| `notes` with a comment saying it may contain phone numbers | `free_text_may_contain` | The comment is evidence about what the column holds. Cite the column's definition line; name the comment in the note. |
| A foreign key to the subject (`user_id`, `owner_id`) | Usually not a field of its own. It is the reason the store is in the record, recorded as the store's subject link with its `file:line`. Where it is the **only** personal data in that store, list it as a field with category `identifier`. | The link makes the row's other columns personal data; listing it twice inflates the field list without telling the reader anything new. Where nothing else is there, the fact that this person has a row in this store is itself information about them. |
| A hashed or tokenised value (`email_hash`, `pseudonym`) | The category the underlying value has (`email_hash` is `contact`) | The hash still points at the person. The hashing matters for the erasure verdict, not for the category. |
| `password_hash` | `technical` | A credential belonging to the person. The hasher is also worth recording as a technical security measure. |
| A soft-delete marker (`deleted_at`, `is_deleted`, `archived_at`) on a subject-linked row | `technical` | The column is the application's own state for the row, not something the person did. It is the line the erasure verdict turns on, so cite it there as well. |
| A foreign key to a lookup table (`plan_id` → `Plan`) | Not personal data; the lookup table stays out | The plan is a product, not a person. Which plan this person is on is `behavioural`, and it is already recorded as the column on the subject row. |
| An email in a queue payload or an analytics call | `contact`, in that store | The store is the queue or the third-party service, not the table the value came from. |

# Not personal data

Predicting these costs precision and nothing else.

- Product, plan, price and catalogue tables
- Currency, country, language and other lookup tables
- Configuration, settings modules, environment names, feature flags
- Migrations, schema metadata, admin registrations
- Static content, templates, translation strings
- Counters and aggregates with no link to a person (`total_orders_today`)
- Log lines that carry no user-linked value
```

## 3. First user message

Built once per run by `art30/loop.py`, as the module constant `FIRST_TURN`. Everything that varies by case lives here rather than in the system prompt, because the system prompt is the cached prefix (`shared/prompt-caching.md` § Architectural guidance).

```text
Scan target: {repo_name}

Every path you cite is relative to the repository root, and every line number is 1-based. `repository` in the record is the name the code gives itself, not this label.

Draft the Art. 30 record and the erasure table for this repository, then submit it with submit_record.

Budget for this run: {tool_call_budget} tool calls and {submit_budget} submit_record attempts. Exceeding either ends the run with no record.

Nobody is watching this run and no one can answer a question before it ends. Before you end a turn, read your last paragraph: if it is a plan, a question or a promise about work you have not done, do that work now with a tool call instead.
```

`{tool_call_budget}` is 60 for a synthetic case and 120 for a real one, `{submit_budget}` is 5 (contract §Budgets). `{repo_name}` is the fixture directory name, which for a synthetic case is the case ID (`evals/fixtures/synthetic/<case>/`), so the case ID does reach the prompt on the ten synthetic cases of fourteen (for a real case it is the vendored directory name, `flaskbb`, not `R02`). Nothing else about the eval does: no split, no expected truth, no manifest path, and no seed. There is no absolute path in the message — the fixture root reaches the tools through `ToolCtx` (`02-agent-loop.md` §2), which is what keeps the step-1 request hash identical on the author's laptop and a judge's, and the replay cache usable.

The label is `Scan target:` and not `Repository:` because `record.schema.json` has a `repository` property described as the name the application gives itself (`tidewharf` in `example-record-S10.md`, the package name `evals/fixtures/specs/S10.yaml` declares); a first line reading `Repository: S10` is copied into that cell.

### `NUDGE`

Appended as a user message after an assistant turn that ends with no tool call. Two are sent; a third quiet turn ends the run as `budget_exhausted` (`02-agent-loop.md` §1, stop table, open risk 1).

```text
You ended your turn without calling a tool. If your last message was a plan, carry it out now; if the record is ready, call submit_record.
```

## 4. Feedback strings

Field names and the object shape come from contract §Feedback object. These are the strings that fill them. Each one names the store or field, the fact that decided it with a citation, and the single edit that resolves it, so that an item can be acted on without a re-read.

Every item on every list carries `expected` — contract §Feedback object requires it (ADR 0004) — so no feedback round asks the model to infer the edit from the problem. `art30/verify/check.py` fills it from the templates below.

### 4.1 Rejected claim (`rejected_claims[]`)

```text
reason:   "no path from entry point {entry_name} ({entry_file}:{entry_line}) to {primitive}; {detail}"
path:     [{"file": ..., "line": ..., "symbol": ...}, …]   the walk the verifier found; [] when none
expected: "verdict {suggested}, or cite the path"
```

`{primitive}` names the store kind's deletion primitive in the words the contract's own example uses: `any relational row-deletion primitive`, `any object-storage deletion primitive`, `any cache deletion primitive`, `any search-index deletion primitive`, `any queue purge`, `any vendor deletion call`. The store is already the entry's `store` key, so the reason does not repeat it. `{suggested}` is the verdict the check would have accepted on the evidence it found. `path` carries the same walk as the prose, structured, so the renderer and the video can show it without a reader parsing a sentence; on this rejection it is empty, which is the finding.

The template renders the contract's §Feedback object example verbatim for the R26 dead-helper case, which is what `03-verifier.md` §7.3 means by calling that example the template, and it is the sentence `06-traces.md` §2, `07-ui.md` §3, `04-output-schema.md` §5 and `example-record-S10.md` §G all quote. An earlier draft here rendered a different sentence for the same rejection, which would have put a string in the video's 0:40 beat that the code never emits.

`{detail}` is one of a closed set, one per rule the check failed:

| Rule | `{detail}` |
|---|---|
| R26 unreached definition | `"{symbol} ({file}:{line}) is defined but has no callers"` |
| R25 soft delete | `"the only write on the path is {symbol} ({file}:{line}), which sets a flag"` |
| R9 wrong sender | `"the receiver at {file}:{line} has sender={sender}, not {model}"` |
| R8 file behind cascade | `"{model}.{field} ({file}:{line}) is a file field; a row cascade does not delete the file"` |
| R4 DB_CASCADE | `"{model}.{fk} ({file}:{line}) is DB_CASCADE, so no delete signal is sent"` |
| R5 cascade token | `"cascade at {file}:{line} is \"{cascade}\": no delete token"` |
| R2 non-cascading on_delete | `"{model}.{fk} ({file}:{line}) is {on_delete}; the row survives"` |
| R22 Stripe | `"a Stripe customer delete does not erase the customer at Stripe"` |

Rendered:

```json
{"store": "uploads", "field": null, "claim": "erasure.verdict=erased",
 "reason": "no path from entry point close_account (api/account.py:12) to any object-storage deletion primitive; cleanup_user_files (storage.py:41) is defined but has no callers",
 "path": [],
 "expected": "verdict not_erased, or cite the path"}
```

### 4.2 Missing store (`missing_stores[]`)

```text
evidence: "{file}:{line} {verb} {what}"
expected: "add store {store} (kind {kind}) with its personal-data fields and an erasure verdict"
```

`{verb}` is one of `writes`, `sends`, `indexes`, `enqueues`, `logs`, `uploads`, `backs up`.

```json
{"store": "sessions", "kind": "cache",
 "evidence": "app/cache.py:18 writes user email under key session:<id>",
 "expected": "add store sessions (kind cache) with its personal-data fields and an erasure verdict"}
```

### 4.2a Missing entry point (`missing_entry_points[]`)

Non-blocking (`03-verifier.md` §7.1): an erasure entry point the verifier discovered and the record does not declare. It costs no attempt and it tells the model what it walked past.

```text
expected: "declare {name} as an entry point, or say in its note why it is not one"
```

```json
{"name": "delete_user", "file": "cli.py", "line": 40, "kind": "cli",
 "expected": "declare delete_user as an entry point, or say in its note why it is not one"}
```

`{kind}` is one of the contract's entry-point kinds. The verifier walks from its own discovered set whatever the record declares (`03-verifier.md` §2.5), so this list changes no verdict; it changes what the record says about how a person is deleted.

### 4.3 Bad citation (`bad_citations[]`)

The four `problem` strings are `03-verifier.md` §7.2's own set, which is the check that produces them; the fourth is the case that file leaves implicit.

```text
problem:  "line {line} does not contain '{symbol}'"
          "line {line} is beyond end of file ({n} lines)"
          "file {file} is not in the scanned set"
          "file {file} does not exist under the repository root"
expected: "cite the line where {symbol} appears, or drop the claim"
          "cite a line in a file this scan read, or drop the claim"   (scanned set)
```

A file the scan skipped exists on disk: `03-verifier.md` §1.1 leaves files over 1 MB, files that raise `SyntaxError` and files that fail strict UTF-8 decoding outside the scanned set. Telling the model that a file it just read does not exist would buy a correct citation being dropped, at the cost of an attempt.

```json
{"file": "models.py", "line": 14, "symbol": "email",
 "problem": "line 14 does not contain 'email'",
 "expected": "cite the line where email appears, or drop the claim"}
```

### 4.4 Unverified (`unverified[]`)

```text
reason:   "{symbol} at {file}:{line} resolves through {mechanism}; the path cannot be decided from the source"
expected: "verdict unverified for {store}, or cite a path that does not pass through {mechanism}"
```

`{mechanism}` is one of `getattr`, `a string import`, `two definitions of the same name`, `an unmodelled decorator`, `raw SQL`, `a callable passed as an argument`.

```json
{"store": "stripe", "claim": "erasure.verdict=external_manual",
 "reason": "delete_customer at billing.py:52 resolves through getattr; the path cannot be decided from the source",
 "expected": "verdict unverified for stripe, or cite a path that does not pass through getattr"}
```

### 4.4a Conservative divergence (`conservative_divergences[]`)

Non-blocking, and never a reason to reject: the record is safer than the evidence, which is the direction this tool asks for (`03-verifier.md` §7.3, Decision 10). It is recorded so the trace shows where the model and the verifier disagreed in the harmless direction.

```text
verifier: "{verdict} via {mechanism} {file}:{line}"
note:     "accepted; the record is more conservative than the evidence"
```

```json
{"store": "orders", "claim": "erasure.verdict=not_erased",
 "verifier": "erased via on_delete=CASCADE models.py:40",
 "note": "accepted; the record is more conservative than the evidence"}
```

The `note` string is the contract's own and is fixed: a per-case sentence here would invite the model to argue with it.

### 4.5 Schema errors (both arms, one function)

`art30/tools.py::format_schema_errors` renders every `jsonschema` validation error the same way in both arms:

```text
"{json_pointer}: {message}"
"{json_pointer}: {message}; allowed: {sorted_allowed_values}"     (enum errors)
```

```json
["/stores/2/erasure/verdict: 'deleted' is not one of the allowed values; allowed: anonymised, erased, erased_after_timer, external_manual, governed_by_retention, no_entry_point, no_schedule_evidenced, not_erased, pseudonymised, unverified",
 "/stores/0/fields/1: 'line' is a required property"]
```

A baseline rejection is this list, the two counters and nothing else — `{"accepted": false, "attempt": 2, "attempts_left": 3, "schema_errors": [...]}` — with the six advanced-only keys **absent**, not present and empty (contract §Feedback object, `01-architecture.md` §1.3, `02-agent-loop.md` §5). The unit tests assert that no baseline tool result in `traces/baseline/**` contains any of the six names, so a `"rejected_claims": []` in that payload fails them. A baseline run whose record is schema-valid and passes §4.6 is accepted on the first attempt, which is the point of the arm.

### 4.6 Handler invariants (both arms)

`04-output-schema.md` §4 defines **ten** checks that JSON Schema cannot carry inside the strict-tool-use subset, and that document is the rule; this section is only the strings. They run in the `submit_record` handler immediately after validation, in both arms, and their messages sort into `schema_errors` by JSON pointer alongside the `jsonschema` ones. They fail closed: the record is rejected and the attempt counts against the five. They are rendered by the same `format_schema_errors` path as the validation errors so the two arms' wording cannot diverge.

I3, I4, I5, I9 and I10 are evaluated over **every** `erasure` block — `stores[].erasure` and every non-null `stores[].fields[].erasure` — and the pointer names the block that failed, so the field-level form of I3 reads `/stores/2/fields/0/erasure/evidence`. The scorer reads the field-level block first (`05-eval-harness.md` §3), so an invariant that looked only at the store block would leave the scored tuple unguarded.

```text
I1   "/stores/{i}: a store with no personal-data field does not belong in the record"
I2   "/stores/{i}/erasure/verdict: entry_points is empty, so every store that is not a
      backup or a third_party recipient takes verdict no_entry_point"
I3   "{block}/evidence: verdict {verdict} needs at least one cited line"
I3b  "{block}/timer_days: {verdict} needs the timer you cited"
I4   "{block}/timer_days: only erased_after_timer and governed_by_retention carry a timer"
I5   "{block}/verdict: a backup store takes governed_by_retention or no_schedule_evidenced"
I5b  "{block}/verdict: {verdict} is only for a store of kind backup"
I6a  "/retention/{i}: needs days or criteria"
I6b  "/retention/{i}: needs a file and a line"
I6c  "/retention/{i}/store: names no store in this record"
I6d  "/retention/{i}/days: a retention period is a whole number of days, not negative"
I7   "{path_pointer}: paths are repository-relative, with no leading / and no .."
I8   "/stores/{i}/name: duplicate store name after normalisation"
I9   "{block}/verdict: a field-level erasure block records a fate that differs from its
      store's; this one repeats it"
I10  "{pointer}: this record states no legal conclusion; remove \"{matched}\""
```

`{block}` is `/stores/{i}/erasure` or `/stores/{i}/fields/{j}/erasure`. I7's pointer names whichever citation failed — a field's, an entry point's, an erasure evidence item's — and the tail of the string is the same in each case. I10's pointer names the string it matched in (`/stores/{i}/erasure/note`, `/retention/{i}/criteria`, `/data_subjects/{i}/label`, …) and quotes the matched substring, so the model can see what to remove rather than guess which sentence offended.

Three of these were wrong here before this pass, and each was wrong in the direction that costs attempts:

- **I2 without its exception** — "every store verdict must be no_entry_point" — rejects S08's `nightly_dump` (a `backup` store, verdict `no_schedule_evidenced`) and R04's third-party stores (`external_manual`) in **both** arms. `03-verifier.md` §6.1 decides kind before reachability, so the advanced arm's own verifier would compute a verdict its handler then refused, and both arms would burn all five attempts on the two cases built to test "there is no way to delete a user".
- **I5 admitting `unverified`** — contract line 101 gives a backup store two verdicts, `03-verifier.md` §6.1 row 1 has no third branch, and `05-eval-harness.md` §3 books any third value as `invalid_verdict_for_kind`. Offering the model a third value here would have had the instructions bless what the metric punishes.
- **I6 without the citation clause** — `07-ui.md` §5b prints `/retention/1: needs a file and a line` in its baseline mock, and nothing in this section produced that string.

## 5. Gate text

Shown on the terminal by `advanced/arm.py` after the record is accepted and before it renders (contract §Run phases 3). `--approve auto` prints the same block, records `by: "simulated"` and approves. Plain ASCII, no emoji, no colour.

```text
RECORD READY FOR REVIEW - {repo_name}
Risk: {HIGH|MEDIUM|LOW}. {risk_reason}

Stores: {n_stores}   reaching erasure: {n_reach}   not reaching: {n_not}   unverified: {n_unverified}
Entry points: {entry_points_or_none}

Does not reach erasure:
  {store} ({kind})  {VERDICT}  {evidence_or_note}

Third-party recipients. Set a kind for each, or press enter to leave it unknown
(unknown | internal | processor | external_controller):
  {store} ({evidence}): _

Left for you, and rendered as requires human completion:
  controller identity and contact, DPO, purposes, legal basis, categories of
  data subject, transfers and safeguards, activity grouping, retention justification.

You are approving a document you will sign. Render it? [y/N]:
```

`{risk_reason}` is the rating's own trigger, quoted from contract §Trace contract, in four shapes:

| Rating | `{risk_reason}` |
|---|---|
| `high` | names the first store that is `not_erased`, `pseudonymised`, `external_manual`, `no_entry_point`, `no_schedule_evidenced` or `unverified` with an identifier or contact field |
| `high`, no entry point anywhere | `no deletion entry point was found; no store in this record reaches erasure` |
| `medium` | every store reaches erasure, at least one only after a timer |
| `low` | every store reaches erasure directly and an entry point was found |

`no_entry_point` is in the contract's `high` list (ADR 0004 P-09), so the second shape is a `high` reason and not the `low` exception it was drafted as. S08 and R04 are the two cases built to test whether the tool can say there is no way to delete a user; under the contract as first written their records matched neither the `high` list nor the `medium` clause and fell to `low`, and the screen would have told the approver that every store reaches erasure, at the lowest urgency, directly above "You are approving a document you will sign".

The gate fires at every rating, so a `low` run still stops here.

The gate reads one line per `third_party` store and then one keystroke, in the printed order: the recipient block sits above `You are approving a document you will sign`, because a person should not be asked to complete cells in a document they have already approved. In `--approve auto`, and wherever there is no TTY, it reads nothing: every `recipient_kind` stays `unknown` and the decision is recorded `by: "simulated"` (`07-ui.md` §3). `01-architecture.md` §2 row 7 and `02-agent-loop.md` §7 now quote this order rather than putting the questions after the keystroke.

What the human typed is recorded on the checkpoint line as `human_completions` — `{"recipient_kind": {"stripe": "processor"}}` (contract §Trace contract, ADR 0004 P-10) — so a cell that came from a person can be traced back to the moment they typed it, which is the one thing this project refuses to leave unevidenced. The trailing `summary` clause an earlier draft used for the same job is dropped: one machine-readable field beats a sentence a reader has to parse.

Rejecting is a run outcome, not a correction channel: the decision is written to the trace as `checkpoint` with `decision: "rejected"` and the run ends `gate_rejected`. The human is not asked to edit the record.

## 6. Why these choices

| Instruction | Why it is there | Traceable to |
|---|---|---|
| Reader is a founder who signs and hands it on; a wrong cell costs more than a blank one | Sets the asymmetry the whole record depends on: silence beats a plausible sentence | ADR 0002 Context; CASES.md §Definition of a good result |
| Known-object / unknown-object split | Aggressive classification on `User`-shaped classes, conservative elsewhere, so hidden fields are found without dragging in `products` | prior-art.md "What we borrow" 1 [S5]; AMBIGUITIES 1; S07 |
| Every attribute of a subject class is in scope, timestamps included | Art. 4(1) "any information relating to" | AMBIGUITIES 1; gdpr-sources.md §5(c); S07 |
| The list of store kinds, with the cache, index, queue, log and backup named | Those are the stores a hand-written record misses; naming them is most of the recall | CASES.md S05, R04; gdpr-sources.md §6.1 |
| Every store carries a `subject_link` with its `file:line` | `store.required` lists the key and the tool schema is `strict: true`, so a store submitted without it does not validate. The link is also the thing that puts the store in the record | contract §Record vocabulary (ADR 0004); record.schema.json `store.required`; Decision 6 |
| A third-party import is a lead, not a finding | Art. 4(9): a recipient receives data | AMBIGUITIES 7; gdpr-sources.md §5(d) |
| Entry points are discovered, and the admin counts as one, flagged admin-only | Real repos do not label the erasure path, and operators do delete through the admin | AMBIGUITIES 3, 15; R16; R03 |
| "Where there is none, say so, and carry that answer to every store" | S08 and R04 have no deletion feature at all; the failure mode is inventing one. The second half is invariant I2, which rejects the record in both arms when `entry_points` is empty and any store reads `not_erased` | S08, R04; 04-output-schema.md §4 I2 |
| Coverage stated under `unscanned`, with the reason | The array is required and `[]` validates, so a record that says nothing says it read everything; on a real repository that is false | record.schema.json `unscanned`; NON-GOALS ("reported as 'unscanned', not analysed"); R03, R05 |
| Categories of data subject named, with the line they were read off | Art. 30(1)(c) is a rendered section of the deliverable; only the *confirmation* is human-only, and the do-not-fill list alone reads as "leave it empty" | record.schema.json `data_subjects`; example-record-S10.md §A; gdpr-sources.md §5(c) |
| Existence is not reachability; a docstring is not a call | The whole thesis, and the planted trap in the hard case | AMBIGUITIES 2; R26; S10 |
| Soft delete is `not_erased` until a purge job is cited | Django's own auth docs recommend the pattern, and a regulator fined a controller for it | R25; AMBIGUITIES 4; gdpr-sources.md §6.9 [S11][S18]; S02, S03 |
| Django rows cascade, files do not, as a four-row table | Django deletes rows and leaves `FileField` uploads; the S09 decoy is a receiver on the wrong sender. The table carries R8's precondition (the row must be reached), R9's bare-receiver case (no `sender=` covers every model, so a bare receiver that deletes the file is `erased`) and R10's two exceptions (`CleanupSelectedConfig` inverts to opt-in, `@cleanup.ignore` removes a model), each of which the one-sentence version got wrong in one direction or the other | R8, R9, R10; framework-behaviour.md §6 R8–R10; AMBIGUITIES 13; S06, S09, R03 |
| `DB_CASCADE` sends no signal | A file store whose only evidence is a signal on a `DB_CASCADE` child is not erased | R4 |
| `SET_NULL` / `SET_DEFAULT` / `SET` / `DO_NOTHING` leave the row | The orphaned row keeps its columns | R2 |
| An overridden `Model.delete()` is evidence only where that delete runs | Not called for cascades, `QuerySet.delete()`, or the admin's bulk action | R14, R16 |
| SQLAlchemy needs the whole token `delete` or `all` | `delete-orphan` alone is not a delete cascade; a substring test gets it wrong | R5; framework-behaviour.md §4.3 attack 4; S01, R02 |
| A database-level `ondelete="CASCADE"` needs evidence that foreign keys are enforced | `ondelete` emits DDL and nothing more; six of fourteen cases are SQLAlchemy or SQLModel, and the research's worst transcript is parent gone, child email still there, `PRAGMA foreign_keys = 0`. Rule 7 covers the ORM-level `cascade=` string, which is a different mechanism | R6; framework-behaviour.md §6 R6 and §4.3; S01–S05, S07, R01, R02, R04 |
| Hashing is pseudonymisation | WP216 requires irreversibility; the EDPB found masking substituted for deletion | AMBIGUITIES 5; gdpr-sources.md §3.2, §6.8 |
| Backups get `governed_by_retention` / `no_schedule_evidenced` | ICO "beyond use" and the EDPB report govern backups by schedule; a missing schedule is itself a finding | AMBIGUITIES 6; gdpr-sources.md §3.1, §6.7 |
| Stripe is `external_manual` even with `Customer.delete` on the path | Deleted customers stay retrievable; invoices are outside redaction | R22 |
| `sentry_sdk.init` makes Sentry a recipient | URLs and query strings are always sent; more under `send_default_pii` | R23; R01 |
| A cache TTL is retention, not erasure; a search index is its own store | An `expire` at write time is not bound to account closure, and a relational delete never reaches an index | R20, R21; S05, R04 |
| `unverified` is an answer; a guess is not | Unresolvable calls are the verifier's own answer too, and guessing in either direction is the failure mode the tool exists to prevent | AMBIGUITIES 14; R26; NON-GOALS |
| Citations are `file:line` and the line must contain the symbol | The check that runs against every claim; a citation that does not resolve is worse than none | contract §Verifier contract; R28 |
| Human-only cells listed by name, with "do not suggest them" | A wrong legal basis is the most harmful sentence the tool could write | AMBIGUITIES 8; gdpr-sources.md §5(a),(b),(e); PDF ground rule 05 |
| Observations (module names, region hints, security measures) marked as not findings | Art. 30(1)(e) needs a human; Art. 32(1)(a) technical measures are chargeable and findable | contract §Record vocabulary; gdpr-sources.md §5(e),(g), §6.5 |
| Retention numbers only where the code has one, one item per category | Art. 30(1)(f) is "where possible"; CNIL requires the per-category split | AMBIGUITIES 16; gdpr-sources.md §6.2, §6.3 |
| Scan → classify → draft named as a suggestion, not a procedure | The harness enforces no stages, and over-prescriptive scaffolding lowers output quality. **Assumption:** "De-prescribe migrated prompts and skills" is recorded for Claude Fable 5 and no equivalent note exists for Claude Opus 5. The neighbouring bullet in that same list, "Make self-verification explicit", is deliberately not taken: the Opus 5 section says the opposite in terms (§7, third bullet) | contract §Run phases 1; model-migration.md § Migrating to Claude Fable 5 → Long-running agent recommendations |
| The caps stated in the tool descriptions, not the system prompt | The system prompt is one cached block that must not restate what the tool schemas carry; a cap the model learns by hitting it costs a call out of 60 | contract §Budgets; prompt-caching.md § Architectural guidance ("Tools render at position 0") |
| Budget named in the first user message, not the system prompt | A per-case byte in the system prompt invalidates the cached prefix for every step | prompt-caching.md § Architectural guidance; contract §API configuration |
| Tool economy: grep to locate, read to decide, drop questions that change no verdict | Tool calls are the run's hard budget and a reported metric | contract §Budgets; AGENTS.md §Trace rules |
| Feedback read as one edit per item | The retry channel is the arm's only feedback loop; five attempts is the cap | contract §Budgets, §Feedback object |
| "Nobody is watching this run", and the instruction to read the last paragraph before ending a turn | An autonomous loop has no channel for a question before the gate. The second half is the half the source spends most of its words on, and it is the fix `02-agent-loop.md` open risk 1 is waiting for: a turn that ends on a plan costs a nudge, and three of them end the run as a counted failure | model-migration.md § Rare: early stopping (recorded for Fable 5; assumption below); 02-agent-loop.md §1, open risk 1 |
| Free-text rules: answer first, terms spelled out, one sentence | The record is the 20-point deliverable and it is read by someone who was not there | docs/writing-rules.md; model-migration.md § Migrating to Claude Opus 5, Behavioral shifts (Longer written deliverables) |
| `<tone_preference>` block at the end of the system prompt | This model writes longer visible text and longer files than its predecessors, and `effort` is not the lever; `max_tokens` is 32000 for thinking, narration and the whole record together, and a truncation is a counted failure | model-migration.md § Migrating to Claude Opus 5, Behavioral shifts (Longer user-facing responses, Longer written deliverables) and the checklist's `[TUNE]` verbosity item; contract §API configuration (ADR 0004 P-11, amending ADR 0003 §1); 02-agent-loop.md open risk 5 |
| Never write that something is safe, correct or adequate | Those are conclusions; the tool reports evidence | AMBIGUITIES 8; NON-GOALS |

## 7. What we deliberately left out

- **Any mention of a verifier, present or absent.** Both arms load this file byte for byte. A sentence like "your record will be checked" would tell the advanced arm something the baseline is not told, and the measured difference would stop being the loop (ADR 0003 §4).
- **Any description of what a rejection contains beyond that it is a list of problems and a count of attempts.** The earlier draft promised feedback "naming, per item, the store or field it concerns, what is wrong with the claim, what would settle it", and that only the advanced arm can deliver: baseline feedback is `schema_errors` and nothing else (contract §Feedback object), and a schema-valid baseline record is accepted whatever it claims (`02-agent-loop.md` §5). Byte-identical is not the same as neutral. A promise of review made to a model that will never be reviewed is an invitation to submit a thin first draft and let the channel do the work, which would inflate the baseline-to-advanced delta on the primary metric. The explanation travels in the rejection, not in the instructions, which is what ADR 0003 §Options considered decided.
- **A demand for reasoning before answering.** Thinking is on by default and interleaves between tool calls with adaptive thinking; asking for it in prose buys nothing (agent-design.md § Model Parameters).
- **Self-check and re-verify instructions.** "Double-check your citations before submitting" is the instruction the migration notes tell callers to delete: the model verifies its own work without being asked, and telling it to causes over-verification with no capability gain (model-migration.md § Migrating to Claude Opus 5, Behavioral shifts: "Over-verification - delete your verification scaffolding" and "Self-check instructions are the same trap", and the checklist's "**Delete** verification instructions from prompts"). The citation rule is stated as what a claim is, never as a pass to run at the end.
- **Step counts and stage gates.** No "make at most N reads", no "complete phase 1 before phase 2". The harness enforces the budget; the prompt states the resource and lets the repository set the order (contract §Run phases 1).
- **Role-play.** No "you are a senior data-protection engineer". The reader is named because the reader changes what a wrong cell costs; a costume changes nothing.
- **Threats and stakes language.** No "this is critical", no penalty figures. The one asymmetry that matters is stated once, in the reader paragraph.
- **A worked example record.** The record's shape is enforced by the `submit_record` input schema, which is `strict: true` with `additionalProperties: false` and every `required` listed. A pasted example in the prompt would be a second, drifting copy of the schema, and few-shot output is copied more often than it is adapted.
- **Severity and conservatism filters.** No "only report what you are confident about". That instruction is followed literally and depresses recall (model-migration.md § Migrating to Claude Opus 5, Behavioral shifts: "Severity filters still depress measured recall"). `unverified` is the calibration channel instead.
- **A list of file names to open.** Naming `models.py`, `settings.py` and `tasks.py` would teach the synthetic fixtures' own layout and would not transfer to a real repository.
- **The words "compliant" and "compliance".** Absent from both prompt files, and from the rendered record (contract §Writing contract).
- **Delegation guidance.** There are no subagents in the loop; the four tools are the whole surface (ADR 0003 §3).

## Decisions taken here

1. `taxonomy.md` is spliced into `system.md` at a literal `<!-- include: taxonomy.md -->` marker, with no substitution, so the two files are one cached system block and one hashable string.
2. Length is reported as measured on the blocks themselves: `system.md` 1,824 words, `taxonomy.md` 853, the spliced block the model receives 2,673 words and 16,255 bytes, roughly 4.0k tokens. The 900–1500 target applied to `system.md` alone and is missed by 324 words; the spliced block is the number that binds, because it is what gets cached and re-read every step. Trimming is a later, measured edit, not a reason to drop a rule that decides a verdict.
3. Everything that varies by case — the scan target's name, the tool-call budget, the submission budget — lives in the first user message, never in the system prompt, so the cached prefix is identical across cases and steps. No absolute path appears anywhere in a request: the fixture root reaches the tools through `ToolCtx`, which is what keeps the request hash machine-independent and the committed replay cache usable by a judge.
4. Schema-error strings are produced by one shared function, `art30/tools.py::format_schema_errors`, called by both arms. Claim-level feedback strings live in `art30/verify/check.py`. No prompt text is duplicated between `baseline/` and `advanced/`.
5. Every feedback item carries the store or field and one cited fact; every list but one also carries a resolving edit in `expected` (contract §Feedback object). `{detail}` and `{mechanism}` are closed sets keyed to rule IDs, so the strings a judge reads in a trace map back to R1–R28. `missing_entry_points` is non-blocking and still names the edit. `conservative_divergences` is the exception on both counts: it carries `note` where the others carry `expected`, because a record safer than the evidence asks for nothing.
6. A foreign key to the data subject is recorded in the store's `subject_link` cell with its `file:line` (contract §Record vocabulary, ADR 0004), not as a personal-data field, except where it is the only personal data in that store, in which case it is a field of category `identifier`. The `# Stores` block of §1 says this in the prompt, because a decision recorded here is not a byte the model reads and `store.required` makes the key mandatory. That exception is also what keeps such a store legal against invariant I1 of `docs/spec/04-output-schema.md` §4, which rejects a store with no fields in both arms. `record.schema.json` does not enforce it: `store.fields` carries the rule in its `description` and has no `minItems`, which is outside the strict-tool-use subset by that document's own §4. Manifests must be written to the same rule or the tuple counts will not compare.
7. `password_hash` and other credentials belonging to the person are `technical`, and the hasher is separately recorded as an Art. 32(1)(a) technical measure.
8. Account-state columns on the subject class (`is_active`, `is_staff`, `plan_tier`) are `behavioural`; timestamps on subject-linked rows are `behavioural`, except soft-delete markers (`deleted_at`, `is_deleted`, `archived_at`), which are `technical` because they record what the application did to the row rather than what the person did; an `ip_address` anywhere, including a log line, is `technical`. The exception is the rule `evals/fixtures/specs/S10.yaml` and `example-record-S10.md` already carry (`deleted_at` technical beside `last_seen_at` behavioural), and the taxonomy row above is where the manifests and the prompt read it from. Categories are not in the scored tuple, so nothing fails on a disagreement — which is exactly why it would have gone unnoticed.
9. The gate reads one line per third-party store, for `recipient_kind`, and then one keystroke for the decision. Both reads happen only in `--approve ask` on a TTY. What the human typed is written to the checkpoint's `human_completions` field so the trace carries it; the gate is still not an editing surface, and a rejection ends the run as `gate_rejected`.
10. The prompt names a working order (tree, models, deletion path, other stores) once and calls it a suggestion. No stage is enforced, no step count is given, and no self-verification pass is requested. The first two rest on the Fable 5 de-prescription note, marked as an assumption in §6; the third rests on the Opus 5 section directly (§ Over-verification, and the checklist's "**Delete** verification instructions from prompts").
11. The first user message tells the model nobody is watching, and tells it to convert a last paragraph that is a plan, a question or a promise into a tool call before ending the turn. **Assumption:** both halves come from `model-migration.md` § Rare: early stopping, which is recorded for Claude Fable 5, and no equivalent note exists for Claude Opus 5. They cost two lines; the loop genuinely has no question channel, and the second half is what `02-agent-loop.md` open risk 1 says the nudge path needs.
12. The four tool `description` strings live in §1b of this file, not in `art30/tools.py` as ad-hoc text, and each states its own cap. They are model-facing, byte-identical across arms under ADR 0003 §4, and part of the hashed prefix.
13. `read_file` documents `end_line: null` as "to the end of the file, capped at 400 lines", because `strict: true` makes every property required and the model cannot express "no end line" by omitting the key. `null` is the value the wire schema of `01-architecture.md` §1.3 and `02-agent-loop.md` Decision 12 already carries (`{"anyOf": [{"type": "integer"}, {"type": "null"}]}`), so the description and the schema now name one absent value; an earlier draft here taught `0`, which a schema built from `01` may reject. `art30/tools.py` still clamps `0`, negatives and anything below `start_line` to the same reading, so a model that sends one of them gets the same bytes (`02-agent-loop.md` open risk 4).
14. The ten handler invariants I1–I10 of `04-output-schema.md` §4 have fixed strings, in §4.6, rendered through the same function as the `jsonschema` errors and sorted into `schema_errors` by JSON pointer. They fire in both arms, so a difference in their wording would be a difference between arms on a path both arms use. That document defines the rules and this one only names them; where the two disagree, it wins.
15. The prompt tells the model to state its coverage in `unscanned` and to name the categories of data subject. Both arrays are required by `record.schema.json` and both validate empty, so nothing but the prompt makes the record say what was not read.
16. `no_entry_point` propagates: where there is no deletion path, every store carries that verdict. Invariant I2 enforces it in both arms, and the prompt says it in two places so the enforcement is never the first the model hears of it.
17. The first line of the first user message is `Scan target:`, not `Repository:`, so it cannot be copied into the record's `repository` cell.

## Open risks

- **The taxonomy and the manifests can disagree.** Decisions 6, 7 and 8 change the tuple count for every case. If manifests are hand-written to a different rule, the scorer measures the disagreement, not the agent. The labelling protocol in `evals/CASES.md` should cite this file's §2 by name before R01 is labelled.
- **The output schema landed after this file was drafted.** `docs/spec/04-output-schema.md` and `docs/spec/record.schema.json` now exist and their key names agree with the prompt: `file`, `line`, `category`, `verdict`, `kind`, `note`, `recipient_kind` typed `null`, and the three `hints` fields. The store object gained `subject_link` in the same pass (ADR 0004), so the subject citation has a cell of its own and `store.note` is back to being one sentence about what the store is. The `# Stores` block of §1 now names that key, which is what the risk was actually about: `store.required` lists it, `strict: true` enforces the list, and a prompt that never mentioned it would have failed every first submit in both arms. The thing to re-check on any schema edit is that `store.additionalProperties` stays `false` and that every key `store.required` gains is named in §1 the same day.
- **The prompt is over its own target and the target may be the wrong measure.** `system.md` is 1,824 words against a 900–1500 target; the spliced block plus the four tool schemas is what the cache holds, and it clears the 512-token minimum this model needs (`prompt-caching.md` § API reference) many times over, so nothing is at risk technically. What is at risk is attention: six lines were added, four because each was producing a wrong verdict, one because the contract names the store-identity convention, one because the schema requires `subject_link`, and no rule was removed to pay for them. The first dev runs should be read for whether the middle of the rule list is being applied at all, and the trim comes from that evidence rather than from the word count.
- **The Django file rule is now a table, and a table teaches sufficiency.** The four rows are read independently, which is the failure the single sentence was avoiding; the lead sentence carries R8's precondition, and it is the sentence a hurried reader skips. S06, S09 and R03 are the cases that settle it. The `CleanupSelectedConfig` and `@cleanup.ignore` exceptions are in no fixture, so nothing in the eval will catch them being dropped.
- **`evals/CASES.md` S05 disagrees with the contract, and the manifest is not written yet.** Its expected truth reads "mail is a recipient, not a store", which predates contract §Record vocabulary: "Recipients are stores of kind `third_party`; there is no separate recipients list." A model following this prompt records the transactional mail service as a `third_party` store carrying the address that flows into it, verdict `external_manual` unless a vendor deletion call is on the path (R24) — correct behaviour that an S05 manifest written from that line would score as a false positive, in both arms, on the case CASES.md nominates for third-party recipients. CASES.md needs an errata row before the S05 manifest exists.
- **The request shapes are reconciled; the bytes are still unmeasured.** `02-agent-loop.md` §1 now renders `FIRST_TURN` from `repo_name`, `tool_call_budget` and `submit_budget` and its §2 now describes the system block as the splice at the `<!-- include: taxonomy.md -->` marker, as §0 here does, and its §7 reads the recipient lines before the keystroke as §5 here prints them. The replay cache is keyed on these bytes, so what remains is not a disagreement between documents but the fact that nobody has yet hashed the assembled string: the `config.py` assertion `02` describes has to be computed against the spliced file, and the constant it compares to does not exist until the prompt files do.
- **Nothing here has been run.** Every claim about how the model responds to this text is a design bet until the first baseline runs on the dev set; the changelog row that follows should quote the S07 and S10 outcomes against the taxonomy and rule 1 specifically.

## Proposed contract changes

All accepted by ADR 0004 on 2026-08-28; the contract now carries them.
