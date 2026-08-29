# 04 — Output schema: the submitted record, `record.json`, and the render

What the model hands to `submit_record`, what the harness adds to it, and what a person reads. One JSON Schema governs the first; the other two are derived and never hand-edited. The schema is the place the product's central promise is mechanical rather than instructed: a record with a legal cell filled in does not validate, so the model cannot write a legal basis even if it decides to.

**Reads with** `docs/spec/00-contract.md` (vocabulary, tools, feedback object, budgets), `docs/spec/record.schema.json` (the schema itself), `.vault/adr/0002-gdpr-inventory-erasure-check.md`, `.vault/AMBIGUITIES.md` rows 1, 5, 6, 7, 8, 16, `docs/research/gdpr-sources.md` §2, §5, §6, `evals/CASES.md` (manifest shape and scoring tuple), `docs/writing-rules.md`, `docs/spec/example-record-S10.md` (the target artefact), `docs/spec/07-ui.md` (where the render appears on screen).

---

## 1. Three artefacts, one schema

| Artefact | Written by | Validated against | Lives at |
|---|---|---|---|
| the submitted record | the model, through `submit_record` | `record.schema.json`, in both arms | inside the trace as the tool call's `input.record` |
| `record.json` | the harness, after acceptance and the gate | the same schema plus two relaxations (§5) | `results/runs/<arm>/<case>/s<seed>/record.json` |
| `record.md`, `record.html` | `render/markdown.py`, `render/html.py` | not validated; a deterministic function of `record.json` | same directory |

The schema file is 197 lines and carries a `description` on every load-bearing property, because it is sent to the model as the `submit_record` input schema and those descriptions are the only place the field semantics reach the model twice (once in `prompts/system.md`, once here).

**Which file.** `art30/schema/record.schema.json` is the shipped file — the one the contract's §Repository layout names, the one `art30/tools.py` loads and sends. `docs/spec/record.schema.json` is a byte-identical spec copy, kept beside this document because a specification that cites a schema by section is unreadable without it, and it is what every `record.schema.json` reference in this document points at. Two copies of a file that decides the step-1 request hash (`01-architecture.md` §4.5) is a replay failure waiting for a one-line edit to one of them, so `tests/test_schema.py` opens both and asserts their sha256 are equal, in the same test module as the eight cases below. If the assertion is ever inconvenient, the answer is to delete the spec copy and cite the shipped path, never to let the two drift.

## 2. The submitted record, field by field

"Filled by" is the only column that decides anything: it is the difference between a document a founder signs and a document a founder is fined for.

| Path | Meaning | Filled by | Art. 30(1) item | Renders in |
|---|---|---|---|---|
| `schema_version` | `"1"`. Bumped only by an ADR. | agent (constant) | — | title block |
| `repository` | What the code calls the application. CNIL's fiche has a field for it ("nom du logiciel ou de l'application", gdpr-sources §2.2 [S4b]); Art. 30 does not. | agent | — | title block |
| `unscanned[].path` / `.reason` | Paths not analysed: a JS front end, an unsupported ORM, a vendored tree, files the read budget did not reach. | agent | — | A, footer |
| `data_subjects[]` | `label`, `basis` (`model_name` / `route_name` / `comment`), `file`, `line`. Renders as "account holders — inferred from model name". | agent | (c), first half | A, header |
| `entry_points[]` | `name`, `kind` (`route`…`unknown`), `file`, `line`, `admin_only`, `note`. Empty means no deletion feature was found. | agent, verifier checks | — (Art. 17) | D, header |
| `stores[].name` / `.kind` | The named place data lives and which of the eight kinds it is. Recipients are stores of kind `third_party`; there is no second list. | agent, verifier's completeness guard adds misses | (c), (d) | A, B, C, D |
| `stores[].declared_at` | Citation for the store itself. Null where no single line declares it (a cache namespace built from an f-string). | agent | — | A heading, H |
| `stores[].subject_link` | `{file, line}` or null: the line that ties the store to a data subject — a foreign key to the user model, a subject id inside a cache key, an owner column. Kept even where that key is not listed as a field, which is the case the note field used to absorb. | agent | (c), the link half | A, H |
| `stores[].fields[]` | `name`, `category` (six values), `file`, `line`, `note`. The `note` is where a comment such as "may contain phone numbers" is quoted — AMBIGUITIES row 1. | agent | (c), second half | A |
| `stores[].fields[].erasure` | Field-level override, null in the ordinary case. Set only where a field's fate differs from its store's. The scorer reads it when present (contract §Record vocabulary), so §4's invariants are checked over it exactly as over the store block. | agent | — | D, indented sub-row |
| `stores[].erasure.verdict` | One of ten. `erased`, `erased_after_timer`, `anonymised` reach erasure; the other seven do not. | agent, rewritten by the model after the verifier rejects it | — (Art. 17) | D |
| `stores[].erasure.evidence[]` | Citations carrying the path: the entry point's write, each hop, the deletion primitive. Each is `file` + `line` + `symbol`; the verifier reads the line and rejects it if the symbol is not on it. | agent | — | D, H |
| `stores[].erasure.timer_days` | Whole days. Only for `erased_after_timer` and `governed_by_retention`, and only from a number in the code. | agent | (f), as evidence | D |
| `stores[].erasure.note` | Why the verdict is what it is, in the code's terms: the dead helper, the missing hop, the docstring that disagrees with the call graph. | agent | — | D |
| `stores[].recipient_kind` | `unknown` / `internal` / `processor` / `external_controller`, CNIL's vocabulary (§2.2 [S5]). **Typed `null` in the submitted record.** | human, at the gate | (d) | B |
| `retention[]` | Per `(store, category)` where the code distinguishes them, per store otherwise (`category: null`). `days` or `criteria`, `file`, `line`. | agent | (f) | C |
| `retention[].justification` | The legal or business reason for the number. Typed `null`. | human | (f) | C, F |
| `activities` | Art. 30's unit is a processing activity; grouping stores into activities is human work. `const: []`. | human, outside the tool | (b) frame | F |
| `hints.observed_module_names[]` | `name`, `file`. A module called `marketing/` is a hint and a hint is how a wrong legal basis gets written (§5 (b)). | agent | not (b) | E |
| `hints.observed_region_hints[]` | Citations whose `symbol` is a region string or API host. Where a service runs is not a transfer finding (§5 (e)). | agent | not (e) | E |
| `hints.security_evidence[]` | `measure` (hashing / encryption_in_transit / encryption_at_rest / pseudonymisation / backup_configuration), `file`, `line`, `symbol`. Art. 32(1)(a) only. | agent | (g), technical half | E |
| `human.controller` / `.joint_controller` / `.representative` / `.dpo` | `{name: null, contact: null}`. The ICO splits (a) into exactly these four rows (§2.1 [S2]). | human | (a) | F |
| `human.purposes` | Typed `null`. | human | (b) | F |
| `human.legal_basis` | Typed `null`. Not an Art. 30(1) item; present so the render shows the cell empty instead of omitting the question. | human | — | F |
| `human.data_subject_categories_confirmed` | Typed `null`. The agent's inferred labels sit in `data_subjects`. | human | (c) | F |
| `human.data_categories_outside_code` | Typed `null`. Paper files, inboxes, spreadsheets, a CRM nobody committed: the personal data a static reader of this repository cannot see (gdpr-sources §5 (c)). Section A is an inventory of one repository, and this cell is where the page says so. | human | (c) | F |
| `human.special_categories` | Typed `null`. A column name is not evidence of Art. 9 data. | human | — | F |
| `human.transfers.occurs` / `.countries` / `.safeguards` | Typed `null`. | human | (e) | F |
| `human.retention_justification` | Typed `null`. | human | (f) | F |
| `human.security_organisational` | Typed `null`. Art. 32(1)(b)–(d) is process and invisible to a reader of application code. | human | (g), organisational half | F |

Two columns are deliberately absent. There is no `confidence` and no `risk` on any object: a number the model picks for its own claim is not evidence, and the risk rating is computed by the harness from the verdicts (contract §Trace contract). There is no free-text summary field either — a paragraph the model writes about its own work is the part of an AI draft a reader learns to skip.

## 3. Why the human cells are typed `null`

Three mechanisms were available. Omitting the cells from the schema entirely would leave the render inventing a shape the record never had, and would let the model put a purpose in any `note` string with nothing to catch it. Conditional forbidding (`if`/`then` on `kind: third_party` for `recipient_kind`) is not in the strict-tool-use subset and buys nothing: the agent may never set that cell for any store kind. What is left is the one the schema uses.

Every property is listed in `required` and every object carries `additionalProperties: false`, which is what strict tool use demands anyway ([tool-use-concepts.md](file:///private/tmp/claude-501/bundled-skills/2.1.250/6281369acc559d2ec0eafa4756deb604/claude-api/shared/tool-use-concepts.md) §JSON Schema Limitations: "`additionalProperties: false` (required for all objects)"). Optionality is therefore expressed in the type, and a human-only cell is expressed as `{"type": "null"}` — present, named, described, and impossible to fill. The model must write the key. It cannot write a value. `activities` uses `const: []` for the same reason at array level.

The effect is that the CASES.md line "unsignable regardless of score: any legal cell filled by the agent" is not a scoring rule that catches the failure after the fact. It is a validation error that returns the record to the model with `schema_errors` before anything renders, in **both** arms.

Checked against `docs/spec/record.schema.json` with `jsonschema` 4.26.0 (`Draft202012Validator`), 2026-08-28, in a scratch venv:

```
jsonschema 4.26.0 - schema itself is a valid 2020-12 schema
instance errors: 0                                   # the S10 record of docs/spec/example-record-S10.md
legal cell filled (human.purposes):        1 error   human/purposes -> 'to provide the service' is not of type 'null'
recipient_kind set by the agent:           1 error   stores/2/recipient_kind -> 'processor' is not of type 'null'
activity written by the agent:             1 error   activities -> [] was expected
unknown property added:                    1 error   Additional properties are not allowed ('confidence' was unexpected)
verdict outside the enum:                  1 error   stores/1/erasure/verdict -> 'partially_erased' is not one of [...]
evidence line without a symbol:            1 error   stores/0/erasure/evidence/3 -> 'symbol' is a required property
legal basis smuggled onto a store:         1 error   stores/0 -> Additional properties are not allowed ('legal_basis' was unexpected)
field-level override (valid):              0 errors
```

Those eight lines are the first eight cases of the schema's unit test (`tests/test_schema.py`), written before the first advanced run per gap G-05. Re-run 2026-08-28 after `human.data_categories_outside_code` was added to the `human` block (§6 F): the same eight results, and the S10 record validates once the new cell is present. Run a third time the same day, after `subject_link` entered the store object (ADR 0004), against an S10 instance rebuilt with the key on all four stores — the block above **is** that run. `subject_link` is in `store.required` like every other property, so the instance the second run used now fails with four `'subject_link' is a required property` errors; nothing else moved, and the four cases below still validate as they did.

Four more cases sit beside them and test the §4 handler invariants rather than the schema, because that is where the checks live:

| Case | Expected |
|---|---|
| a `retention[]` item with `days: 365` and `file: null`, `line: null` | I6, `/retention/0: needs a file and a line` |
| a field-level `erasure` block with `verdict: erased` and `evidence: []` | I3 on `/stores/0/fields/0/erasure/evidence` |
| a `note` reading "This store is compliant with Article 17 GDPR" | I10, with the matched substring `complian` |
| an `erasure.evidence` citation whose `symbol` is `docstring: removes all user data` | rejected by the verifier's citation check (`03-verifier.md` §7.2), because that string is not on the line |

The first three validate against the schema with zero errors — checked in the same scratch venv on 2026-08-28 — which is the whole reason §4 exists.

## 4. Invariants the wire schema cannot carry

Strict tool use accepts `enum`, `const`, `anyOf`, `allOf`, `$ref`/`$defs` and rejects numerical constraints (`minimum`, `maximum`), string constraints (`minLength`) and "complex array constraints" ([tool-use-concepts.md](file:///private/tmp/claude-501/bundled-skills/2.1.250/6281369acc559d2ec0eafa4756deb604/claude-api/shared/tool-use-concepts.md) §JSON Schema Limitations). The schema file therefore stays inside that subset and can be sent verbatim as the tool's `input_schema`. Everything below is checked in the `submit_record` handler, immediately after JSON Schema validation, and reported in the same `schema_errors` list — **in both arms**, so the arms still differ only in the verifier and the gate.

I3, I4, I5, I9 and I10 are evaluated over **every** `erasure` block in the record — `stores[].erasure` and every non-null `stores[].fields[].erasure` — and the error path names the block it failed on (`stores[2].fields[0].erasure.evidence`). The field-level block is the one the scorer reads first (`05-eval-harness.md` §3: `block = field.get("erasure") or store.get("erasure")`), so an invariant that only looked at the store block would leave the scored tuple unguarded.

| # | Invariant | Why |
|---|---|---|
| I1 | `stores[].fields` is non-empty | A store with no personal-data field does not belong in an Art. 30 record and would score as a false positive. |
| I2 | `entry_points == []` ⇒ every store whose kind is neither `backup` nor `third_party` has verdict `no_entry_point` | S08 and R04 exist for this. "There is no way to delete a user" is the finding. |
| I3 | verdict in {`erased`, `erased_after_timer`, `anonymised`, `pseudonymised`, `governed_by_retention`} ⇒ `evidence` non-empty; `erased_after_timer` and `governed_by_retention` also need `timer_days` | A reaching verdict without a cited line is the claim the whole project refuses, and a claimed retention schedule with nothing to open is the EDPB's own finding turned on this document (gdpr-sources §6 item 7: "controllers claim schedules they do not have"). |
| I4 | verdict not in {`erased_after_timer`, `governed_by_retention`} ⇒ `timer_days` is null | Keeps a stray timer from decorating a `not_erased` row. A backup with no citable schedule, or a schedule that yields no number of days, is `no_schedule_evidenced` — never `governed_by_retention` with an empty cell (`03-verifier.md` §6.3). |
| I5 | `kind: backup` ⇔ verdict in {`governed_by_retention`, `no_schedule_evidenced`} | Contract line 101: those two "are the only verdicts rendered for stores of kind `backup`". `03-verifier.md` §6.1 row 1 has no third branch, and `05-eval-harness.md` §3 scores any third value as `invalid_verdict_for_kind`. |
| I6 | each `retention[]` item has `days` or `criteria` (or both), names an existing store, `days >= 0`, and carries a non-null `file` and `line` | Art. 30(1)(f) allows "the criteria" in place of a period (gdpr-sources §2.2 [S6]); it does not allow an empty row, and neither a number nor a criteria string exists in this tool except as something read off a line (`03-verifier.md` §6.3). A period with no citation is an invented period, which is the one thing `prompts/system.md` tells the model never to write. A store with nothing to cite has no `retention[]` item and renders `NO TIMER EVIDENCED` (§6 C). |
| I7 | every `file` is repository-relative with no leading `/` and no `..`; every `line >= 1` | The evidence index has to resolve on the reader's machine. `ast` line numbers are 1-indexed (framework-behaviour R28). |
| I8 | store names unique after normalisation; field names unique within a store | Same normalisation as the scorer and verifier (contract §Record vocabulary). |
| I9 | a field-level `erasure` block whose verdict equals its store's verdict is rejected | The override exists for a fate that differs (contract §Record vocabulary). A copy of the store's verdict on every field is noise in the render and a second place for the two to drift apart. |
| I10 | every model-written string — `stores[].note`, `stores[].fields[].note`, `stores[].erasure.note`, `stores[].fields[].erasure.note`, `entry_points[].note`, `retention[].criteria`, `data_subjects[].label` — is rejected if it matches, case-insensitively, `complian`, `lawful`, `unlawful`, `legal basis`, `legitimate interest`, `consent of the data subject`, or `Article \d+ (is\|has been) (met\|satisfied)` | §7 rule 3 and CASES.md's "the word 'compliant' anywhere in the record makes it unsignable" had no mechanism behind them: the notes are free text and the renderer prints them as written, so a note is the channel a legal conclusion arrives through. ADR 0002's own thesis is that an instruction is not a control. The error names the path and the substring that matched. |

Two test cases turn on I2's exception. S08 plants `nightly_dump` (`backup`, no schedule, `fixture-generator.md` §9) in a repository with no deletion feature, and R04's mail and Gravatar stores are third-party in a repository with no account deletion. Both keep their kind verdict, because `03-verifier.md` §6.1 decides `backup` (row 1) and `third_party` (row 2) before it reaches "no entry point exists" (row 3). Without the exception the advanced arm's own verifier would compute a verdict its submit handler then refused, and both arms would burn all five attempts on S08 and R04.

I1–I10 fail closed: the record is rejected, the attempt counts against the five, and the message names the path (`stores[2].erasure.timer_days`) rather than restating the rule.

## 5. `record.json`

The submitted record, plus two blocks the model never sees, plus one field the human sets. Validated against `record.schema.json` with exactly two documented relaxations: `verification` and `provenance` are permitted at the root, and `stores[].recipient_kind` accepts the four-value enum instead of `null`.

On write, `record.json` normalises `recipient_kind` from `null` to `"unknown"` for every store of kind `third_party`, in **both** arms. The gate overwrites it for the stores the human answered; `--approve auto` and the baseline leave it. The renderer therefore sees the enum and only the enum, and the relaxation is "the four-value enum instead of `null`" full stop, not "once the gate has run" — the baseline has no gate and would otherwise render an unspecified cell (§6 B).

```json
{
  "schema_version": "1",
  "repository": "tidewharf",
  "stores": [ { "name": "stripe", "kind": "third_party", "recipient_kind": "processor", "...": "..." } ],
  "...": "... the submitted record, unchanged ...",

  "verification": {
    "submits": 2,
    "accepted_on_attempt": 2,
    "rejected_history": [
      {"attempt": 1, "store": "uploads", "field": null, "claim": "erasure.verdict=erased",
       "reason": "no path from entry point close_account (api/account.py:12) to any object-storage deletion primitive; cleanup_user_files (storage.py:41) is defined but has no callers",
       "expected": "verdict not_erased, or cite the path",
       "revised_to": "not_erased"}
    ],
    "missing_stores_resolved": [
      {"attempt": 1, "store": "nightly_backup", "kind": "backup",
       "evidence": "jobs/backup.py:8 writes the users table into the dump",
       "added_on_attempt": 2}
    ],
    "bad_citations_resolved": [],
    "unverified": [],
    "rule_set_sha": "3f9ac1d2"
  },

  "provenance": {
    "arm": "advanced",
    "model": "claude-opus-5",
    "effort": "high",
    "config": {"max_tokens": 32000, "tool_budget": 60, "submit_budget": 5, "overridden": []},
    "run_id": "adv-S10-s1-9f3ac1e",
    "case": "S10",
    "seed": 1,
    "mode": "live",
    "fixture": {"id": "S10", "path": "evals/fixtures/synthetic/S10", "sha256": "9f3c41ab7e02"},
    "instruction_sha256": "c4d81f60a92b",
    "started_at": "2026-08-30T14:02:11Z",
    "finished_at": "2026-08-30T14:05:41Z",
    "trace": "traces/advanced/S10-s1.jsonl",
    "cost_usd": 0.41,
    "tool_calls": 21,
    "gate": {"risk": "high", "decision": "approved", "by": "human", "wait_s": 34.2, "at": "2026-08-30T14:05:40Z"}
  }
}
```

| Block | Field | Source |
|---|---|---|
| `verification` | `submits`, `accepted_on_attempt` | the loop's submit counter. `submits` is the number of `submit_record` calls; the trace's `verify_rounds` counts the rejections among them (`06-traces.md` §1), and the two words are not interchanged anywhere |
| | `rejected_history[]` | every `rejected_claims` entry from every failed attempt, plus `revised_to` — what the next accepted record said about that store. This is the audit trail; it is never pruned. |
| | `missing_stores_resolved[]` | the completeness guard's `missing_stores`, with the attempt the store appeared on. A store the model never added stays here with `added_on_attempt: null` and is listed in the render as an unresolved gap. |
| | `bad_citations_resolved[]` | same shape for the citation check. |
| | `unverified[]` | claims the verifier could not decide (dynamic dispatch, `getattr`, string imports). Counted as not reaching erasure, per AMBIGUITIES row 14. |
| | `rule_set_sha` | sha256 (first 8 hex) of the concatenated `verify/rules/*.yaml`, so a changed rule set is visible in the artefact. |
| `provenance` | `arm`, `model`, `effort`, `run_id`, `case`, `seed`, `mode` | run configuration. `run_id` is `<arm prefix>-<case>-s<seed>-<git sha7>`: it survives a re-run at a different wall-clock time and it is the same column as `results/test-runs.log` and `metrics.json.git_sha` (`05-eval-harness.md` §5.4, §6) |
| | `config` | `max_tokens`, the tool-call budget, the submit budget, and `overridden` — the names of the `ART30_*` environment variables that were actually set for this run (`07-ui.md` §1). The tool budget is 60 for a synthetic case and 120 for a real one (contract §Budgets), so every real-repo run carries a non-default number and the artefact has to be able to say which |
| | `fixture.sha256` | sha256 over the fixture tree, so the record names the exact code it read |
| | `instruction_sha256` | sha256 of `prompts/system.md` + `prompts/taxonomy.md`. Both arms are byte-identical here (ADR 0003 item 4); a differing hash between arms is a bug in the run, and the number is in the artefact so nobody has to take that on trust. |
| | `gate` | mirrors the trace's `checkpoint` line, `wait_s` included: lead decision G-01 reports the gate's approval time next to the human-time row (`05-eval-harness.md` §9), and a number that lives only in the trace is a number the signed document cannot show. The line's other new field, `human_completions` (contract §Trace contract), is not repeated here — what the approver typed is already in the record as the `recipient_kind` cells it set |

The baseline arm writes the same `verification` keys with its own counters — `submits` and `accepted_on_attempt` as the loop counted them, which are `2` and `2` for the schema-rejected run of `07-ui.md` §5b and `1` and `1` for a record accepted first time — with `rejected_history` carrying its `schema_errors`, the three verifier-only lists empty, `rule_set_sha: null`, and `provenance.gate: null`. Same keys, same types, in the same order: `rule_set_sha: null` is what says no verifier ran, and code that reads `verification["accepted_on_attempt"]` — the report's turns column, for one — must not have to branch on the arm. The render then omits section G and prints one line in its place: `Verification: none. This record was accepted on schema validity alone.` The baseline artefact must be readable as the same document, or the comparison in the video is a comparison of two layouts.

## 6. The Markdown render

Order is the order a lawyer reads it: what data, who gets it, how long, what happens on deletion, then the machine's caveats, then the empty cells, then the audit trail. Headings are literal.

**Title block.** `# Record of processing — <repository>`, then a two-column provenance table (case, arm, model, run id, fixture sha, instruction sha, generated at, trace path, cost), then, as its own paragraph:

> This is the technical half of a record of processing activities under Article 30(1) GDPR. It was derived from source code by static reading, on the date above. It is not legal advice, it states no legal basis, and it is incomplete until the cells marked `requires human completion` are filled by a person. It covers Article 30(1) — the controller's own record — for the repository named above; a processor's record under Article 30(2), and any personal data held outside this repository, are not in it.

The second sentence is a boundary, not a disclaimer. §1 of gdpr-sources assumes a controller who also acts as a processor needs a second record (CNIL: "vous recommande de tenir 2 registres") and the tool produces one half of one of them; "Article 30(1)" alone does not tell a founder that Art. 30(2) exists. The other half of the boundary is `human.data_categories_outside_code` in section F, which is where the page admits that section A inventories a repository and not a company.

**A. Data inventory.** One subsection per store, in the order relational, object_storage, cache, search_index, queue, log, backup, third_party — the stores a founder recognises first, and the ones that get forgotten last. Heading `### <store name> — <kind> — <declared_at>`, or `### <store name> — <kind> — declaration not on a single line` where `declared_at` is null, then the store note, then a table:

| Field | Category | Evidence | Note |
|---|---|---|---|
| `email` | contact | `models.py:14` | |

The line under each store's table is `Linked to the data subject at <file:line>`, or `No link to a data subject found in code` where `subject_link` is null. Data-subject labels sit above the first store as one line each: `account holders — inferred from model name (models.py:9)`. The section ends with `Not scanned:` and one line per `unscanned` entry, or `Not scanned: nothing` when the array is empty.

**B. Recipients.** Only `third_party` stores. One row each: name, the fields that flow into it with their citation, `recipient_kind` in capitals, and the Art. 28 question the human owns. `unknown` renders as `UNKNOWN — requires human completion`, and a baseline record renders the same cell: `recipient_kind` is normalised to `unknown` on write in both arms (§5), so this table never meets a `null`. The absence of a gate is stated in the one-line replacement for section G, not here. A note under the table states what the tool did and did not establish: personal data flows into the call at the cited line; whether the recipient is a processor or an independent controller, and whether an Art. 28(3) contract exists, is not visible in code (gdpr-sources §5 (d)).

**C. Retention.** One row per `retention[]` item, in section A's store order (kind first, then store name), then by category in the order the enum declares them: store, category (or `all categories` where `category` is null), the period, evidence, and a `Justification` column reading `requires human completion` in every row. The period cell is `<days> days` where `days` is set, followed by a space and the `criteria` string where that is set too (`30 days after deleted_at`), or the criteria string alone where there is no number. Every item carries a citation (I6). Every store with no retention item gets a row reading `NO TIMER EVIDENCED` with an empty evidence cell. Under the table, one sentence: a period found in code is evidence for a retention schedule; the schedule itself is a policy the controller sets (gdpr-sources §2.1 [S2], §6 item 2). A store with no `retention[]` item gets one synthesised row reading `NO TIMER EVIDENCED` with an empty evidence cell and an empty category cell.

**D. Erasure.** The table the tool exists for. Header line above it: `Erasure entry points:` one line per entry point (`close_account — route — api/account.py:12`), or `Erasure entry points: none found.` Then:

| Store | Verdict | Evidence | Note |
|---|---|---|---|
| uploads | NOT ERASED | — | cleanup_user_files is defined at storage.py:29 and has no caller |

Rules for this table:
- Verdicts in capitals with underscores as spaces: `ERASED AFTER TIMER`, `NO SCHEDULE EVIDENCED`.
- `ERASED AFTER TIMER` renders the timer inline: `ERASED AFTER TIMER (30 days)`.
- A field with its own `erasure` block renders as an indented sub-row under its store, `↳ email — ANONYMISED — jobs/purge.py:19`, and the store row keeps its own verdict. Nothing else in the document repeats a field-level verdict.
- Multiple evidence citations render one per line inside the cell, in path order.
- Backup stores (AMBIGUITIES row 6) never carry an erasure verdict. They render `GOVERNED BY RETENTION (35 days)` or `NO SCHEDULE EVIDENCED`, and a standing note under the table that says what the tool did rather than what the law requires: no erasure verdict is rendered for a store of kind backup; this tool reports the retention schedule it found in code and cites it; whether that schedule and the procedure applied to restored systems are adequate is not visible here. The regulator sources for the rule (gdpr-sources §3.1 [S10] [S11]) are cited in this specification and not in the artefact, which states no legal rule of its own.
- Object-storage rows carry the standing versioning note in both branches: where bucket versioning is enabled, a delete without a `versionId` leaves the previous version in place (framework-behaviour R13).
- `UNVERIFIED` rows carry the reason from `verification.unverified[]` in the note cell.
- The table is sorted by verdict, in the order the schema's enum declares them among the verdicts that do not reach erasure, then by store name; the reaching verdicts follow in the same shape. A reader who stops after four rows has read the ones that matter, and two runs of the renderer over one `record.json` produce the same file, which `05-eval-harness.md` §12's `git diff --exit-code` needs.

**E. Observations.** Heading `## E. Observations from the code (not findings)`, then three short tables — module names, region hints, security evidence — each under its own sentence saying what it is not: a module name is not a purpose, a region string is not a transfer, the security list covers Art. 32(1)(a) technical measures only and the rest is in section F.

**F. Requires human completion.** Every human cell, visibly empty, in Art. 30(1) order: controller, joint controller, representative, DPO (a), purposes (b), confirmation of data-subject categories and the categories of personal data held outside this repository (c), recipient kinds for each third-party store (d), transfers — occurs, countries, safeguards (e), retention justification (f), organisational security measures (g), and last the activity layer. The activity layer renders as a stub fiche with CNIL's section names (activity name, purposes, subject categories, data categories, recipients, transfers, retention, security) and a line: no activity grouping is derived from code; the store map in section A is the input to it (gdpr-sources §6 item 1). Cells read exactly `requires human completion`. This section is the longest in the document and it is meant to be.

**G. Verification appendix.** Advanced arm only. Three tables: what was rejected and what the next round said instead (`rejected_history`), which stores the completeness guard added (`missing_stores_resolved`), and what stayed `unverified` with the reason. The first table is the one the video pauses on; it is the only place in the artefact where the reader sees the model being overruled.

**H. Evidence index.** Every citation in the document, sorted by path then line, with the section that used it. A reader with the repository open can walk it top to bottom. Duplicates collapse into one row listing each section; where several citations resolve to one line, the Symbol column lists each citation's own `symbol`, comma-separated, and every one of them is on that line. A symbol is a name or a literal the verifier can find on the line (`record.schema.json` `$defs.citation`), never a description of what the line says: `docstring: removes all user data` is not a symbol, `including uploaded files` is.

## 7. Writing rules for the render

`docs/writing-rules.md` binds, plus five rules specific to this artefact:

1. No emoji, anywhere, including the verification tables.
2. Verdicts in capitals. Nothing else in the document is capitalised for emphasis.
3. The words `compliant` and `compliance` do not appear. No legal basis, no risk class, no statement about whether anything is lawful. Invariant I10 enforces this over every string the model writes, in both arms, before anything renders; the rule is not left to the instruction text.
4. No adjectives of quality — not `robust`, not `thorough`, not `critical`, not `clean`. A row is `NOT ERASED` at `storage.py:29`; that is the whole sentence.
5. Every cell that came from code carries `file:line`. A cell with no citation is either a human cell or an em dash, never prose.

Renderer behaviour that follows: no sentence in the output is generated from a template with adjectives in it, the only free text is the model's `note` strings and the verifier's `reason` strings, and both are printed as written. The renderer never paraphrases the model, and the model never gets to write a paragraph.

---

## Decisions taken here

1. Human-only cells are `{"type": "null"}` with the key required, and `activities` is `const: []`. Filling one is a validation error in both arms, not a scoring penalty after the fact.
2. Every property is in `required`; optionality is an `anyOf` pair with `{"type": "null"}`, in all twelve places, rather than a `["string", "null"]` type array. The strict-tool-use page lists `anyOf` as supported and never shows a type array ([tool-use-concepts.md](file:///private/tmp/claude-501/bundled-skills/2.1.250/6281369acc559d2ec0eafa4756deb604/claude-api/shared/tool-use-concepts.md) §JSON Schema Limitations), and the file already used the `anyOf` form for `declared_at` and the two `erasure` refs, so one form for one idea.
3. `recipient_kind` is `null` for every store kind in the submitted record, not just `third_party`. Conditional schemas are outside the strict subset and the agent may never set the cell anyway.
4. The schema file stays inside the strict-tool-use keyword subset so it can be sent verbatim as `input_schema`. Ten invariants that need `minimum`, `minItems`, a citation dependency or cross-field logic (I1–I10) live in the `submit_record` handler and report through `schema_errors` in both arms. I3, I4, I5, I9 and I10 run over every `erasure` block, field-level overrides included, because that is the block the scorer reads. *Amended 2026-08-29:* "verbatim" is one edit short of true. `art30/tools.py::_submit_input_schema` sends the schema as `properties.record` with `$schema` and `$id` removed and `$defs` hoisted to the tool `input_schema` root, because `$ref` targets resolve against the document root and the tool's root is its `input_schema`, not the nested record object. No keyword left the strict subset; the file itself is unchanged and `tests/test_schema.py` still asserts the spec copy hash-equal. (DEVIATIONS.md D-05)
5. Erasure evidence items carry `symbol` as well as `file` and `line`, so the verifier's citation check has something to look for on the line. Field and entry-point citations use their own `name` as the symbol.
6. No `confidence`, no `risk`, no model-written summary anywhere in the record.
7. `record.json` = submitted record + `verification` + `provenance`, validated against the same schema with two named relaxations. `verification.rejected_history` keeps every rejected claim with what replaced it; it is never pruned.
8. The baseline arm writes the same two blocks with the same keys — `submits: 1`, `accepted_on_attempt: 1`, empty history, `rule_set_sha: null` — so both arms produce the same document shape and the comparison is about content, and no reader of `record.json` branches on the arm.
9. Render order is A inventory, B recipients, C retention, D erasure, E observations, F human cells, G verification, H evidence index, with the erasure table sorted so the verdicts that do not reach erasure come first.
10. `unscanned` is a required top-level array. Coverage is stated in the artefact, not implied by silence.
11. `backup` and `third_party` stores keep their kind verdict when no entry point exists (I2's exception), because `03-verifier.md` §6.1 decides kind before reachability and the handler may not refuse what the verifier computes. `reaches_erasure` is `false` either way, so no scored tuple moves.
12. A backup store takes `governed_by_retention` or `no_schedule_evidenced` and nothing else (I5), matching contract line 101, the verifier's row 1 and the scorer's `invalid_verdict_for_kind`. A backup whose schedule cannot be read is `no_schedule_evidenced`, not `unverified`.
13. Every retention item carries `file` and `line` (I6), and every claimed retention schedule on a backup carries evidence and a timer (I3). A number with nothing to open is the failure this document exists to make impossible.
14. The forbidden legal vocabulary is a rejection (I10), not an instruction. The renderer prints the model's `note` strings verbatim, so the check has to sit before the render, in both arms.
15. `recipient_kind` is normalised to `"unknown"` on write for every `third_party` store in both arms, so the renderer sees the enum and never a `null`.
16. `human.data_categories_outside_code` is a required human cell. The record says on its own page that it inventories one repository.
17a. **Every store carries `subject_link`**, nullable, its own cell rather than a sentence in `store.note` (contract §Record vocabulary, ADR 0004). The link is what makes a store personal data at all, and a cell the schema names is a cell the completeness guard and the render can both read.
17. `run_id` is `<arm prefix>-<case>-s<seed>-<git sha7>` — the hash form of `06-traces.md` §2, not a wall-clock stamp; the arm prefixes are `adv` and `base` (`01-architecture.md` §2) — and every counter quoted in this document, in `02-agent-loop.md` §9, in `07-ui.md` §3 and in `example-record-S10.md` comes from the one invented run in `06-traces.md` §2. When the first real S10 run lands, all five documents are refreshed from that trace in a single commit.

## Open risks

- **Type unions on the wire — closed.** The nine `["string", "null"]` / `["integer", "null"]` properties were rewritten as `anyOf` pairs on 2026-08-28, deliberately, before the first live call: the type-array form is not shown anywhere on the strict-tool-use page, the `anyOf` form is, and the file already used it in three places. `Draft202012Validator.check_schema` passes and the eight §3 cases produce the same eight messages after the rewrite. What is left of the risk is the compilation itself: the first live call is the first call that compiles this schema, and a 400 there blocks every run rather than one.
- **The two-view schema was not taken.** The stronger version of I1, I3, I6 and I7 is a local copy of the schema carrying `minItems`, `minimum` and the citation dependency through `dependentRequired`, with a wire copy that strips those keywords — the pattern the SDKs use themselves ([tool-use-concepts.md](file:///private/tmp/claude-501/bundled-skills/2.1.250/6281369acc559d2ec0eafa4756deb604/claude-api/shared/tool-use-concepts.md) §Structured Outputs: "The Python and TypeScript SDKs automatically handle unsupported constraints by removing them from the schema sent to the API and validating them client-side"). It would retire four hand-written checks. It also puts two schema files in the repository where the artefact's promise is that one file governs, and it lands after the handler invariants are already specified and unit-tested. If the invariant code in `art30/tools.py` grows past ~80 lines, this is the first thing to reconsider.
- **I10 is a word list, and word lists misfire.** A repository with a module called `lawful_basis.py`, or a column named `consent`, can push a truthful note into a rejection the model then has to write around. The list is deliberately narrow (seven patterns, no single-word `consent`, no `adequate`), the error names the matched substring so the model can see what to remove, and a false positive costs one of five attempts rather than a wrong sentence in a signed document. If a real repository trips it, the pattern comes out and the case goes in the errata, never the other way round.
- **Description budget.** The schema is sent on every request; its descriptions are cached with the tool block (contract §API configuration) but they still count against the cache write. If the record schema grows past ~250 lines, descriptions get trimmed before enums do.
- **`rejected_history` and privacy of the model's errors.** The artefact publishes what the model got wrong. That is the point for a judge and might be uncomfortable for a founder handing the document to a lawyer. No mitigation planned: a redaction switch would be the first step towards a document that hides its own corrections.
- **Two-state `recipient_kind`.** Anything that validates `record.json` with the plain schema (a future harness check, a judge running `jsonschema` by hand) will fail on a gate-set value unless it applies the two relaxations. The renderer is the only code that reads `record.json`, so the exposure is documentation, not runtime.
- **Sibling documents carried the old invariants — closed, in the reconciliation pass of 2026-08-28.** `10-instructions.md` §4.6 now carries ten strings written from §4: I2 with the backup and third-party exception, I5 without `unverified` and with its second direction, I6 with the citation clause, and I9 and I10, which it did not have at all. `03-verifier.md` §6.4 now returns the `no_entry_point` flag and `10-instructions.md` §5 has a fourth `risk_reason` shape for it. The contract's own `high` list names `no_entry_point` as of ADR 0004 P-09, so all three agree.
- **I5 makes backup a closed kind.** A repository whose "backup" is a live replica read by the app would be inventoried as a backup and never get an erasure verdict. Correct under AMBIGUITIES row 6, and wrong for that repository. No case in `evals/CASES.md` has this shape; if a real repo does, it goes to the errata section, not into the schema.

## Proposed contract changes

All accepted by ADR 0004 on 2026-08-28; the contract now carries them.
