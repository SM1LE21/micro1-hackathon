# Fixture generator — `evals/fixtures/gen.py`

One YAML spec per case produces both the synthetic repository the agent reads and the manifest the scorer grades against, from the same file, in one pass. That is the only property that matters here: if the truth were written by hand next to a hand-written repo, the two would drift by Saturday afternoon and every number after that would be measuring the drift. This document fixes the spec format, the two repository templates, what each knob emits, how the manifest is derived, and what "deterministic" means precisely enough that `make fixtures` can assert it with `git diff --exit-code`.

**Reads with** `docs/spec/00-contract.md` (record vocabulary, store kinds, verdict enum, name normalisation — it wins), `evals/CASES.md` (the case table and the manifest shape), `docs/research/framework-behaviour.md` §6 (rules R1–R28: what each planted trap is supposed to exercise), `docs/research/gdpr-sources.md` §3 and §6 (backups, pseudonymisation, per-category retention), `.vault/AMBIGUITIES.md` (rows 1–16), `docs/spec/05-eval-harness.md` (the scorer that consumes the manifests), `docs/spec/03-verifier.md` (the rules the fixtures are built to exercise).

---

## 1. What the generator is and is not

`gen.py` is a template renderer with a consistency check bolted on. It is not a code synthesiser: every line it emits comes from a fixed template with slots. There is no randomness, no LLM, no formatting library, and no import of anything outside the standard library plus `pyyaml`.

Two outputs per case:

| Output | Path | Committed |
|---|---|---|
| The repository the agent reads | `evals/fixtures/synthetic/<case>/` | yes |
| The manifest the scorer reads | `evals/fixtures/manifests/<case>.yaml` | yes |
| Generation index (spec hash, gen version) | `evals/fixtures/synthetic/.gen-index.json` | yes |

The agent never sees the manifest and never sees the spec (`00-contract.md` §Verifier contract: "No access to manifests, ever" — the same holds for the model). Nothing under `evals/fixtures/specs/` or `evals/fixtures/manifests/` is inside any repository path the tools can reach, because `art30 scan` is pointed at `evals/fixtures/synthetic/<case>/`.

### Double entry, not derivation, for verdicts

The inventory half of the manifest (stores, fields, categories, `file:line`) is **derived**: the generator wrote those lines, so it knows where they are. The verdict half is **declared** in the spec's `expect:` block and then **cross-checked** against an implication table that maps knob combinations to the verdict they must produce (§6). A mismatch is a hard failure with a diff, not a warning.

The reason for the asymmetry: a derived verdict would make the manifest a second copy of the generator's opinion, so a generator bug that emits a `SET_NULL` where the spec asked for `CASCADE` would silently move the ground truth to match the bug, and every arm would be graded against the wrong answer without anything failing. Declaring the verdict by hand and checking it means the bug shows up as a failed generation instead.

---

## 2. Spec format

One file per case: `evals/fixtures/specs/S01.yaml` … `S10.yaml`. All keys below; anything absent takes the default.

### 2.1 Top level

| Key | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `case` | str | yes | — | `S01`–`S10`. Must equal the filename stem. |
| `split` | `dev`\|`test`\|`reserve` | yes | — | Cross-checked against `evals/split.yaml`. |
| `flavour` | `sqlalchemy`\|`django` | yes | — | Which template family renders. |
| `package` | str | yes | — | Short application name. Used in the README line and as the normalisation prefix list. SQLAlchemy fixtures put their modules **at the repository root** (`models.py`, `api/account.py`, `jobs/purge.py`), matching CASES.md's example manifest and `docs/demo-script.md`; Django fixtures use it as the project package directory because Django requires one. |
| `apps` | list[str] | django only | `[]` | Django app labels; first is the account app. |
| `intent` | str | yes | — | One line. Copied verbatim into the manifest header as `intent`. Never into the repo. |
| `engine` | str | no | `sqlite:///./app.db` | Literal `DATABASE_URL` in config/settings. Decides R6. |
| `enforce_sqlite_fk` | bool | no | `false` | Emits the `@event.listens_for(Engine, "connect")` `PRAGMA foreign_keys=ON` listener (research §6 R6, [S46]). |
| `models` | list | yes | — | Relational models (§2.2). |
| `stores` | list | no | `[]` | Non-relational stores (§2.3). |
| `entry_points` | list | no | `[]` | Erasure entry points (§2.4). Empty list is legal and is what S08 tests. |
| `jobs` | list | no | `[]` | Scheduled jobs (§2.5). |
| `routes` | list | no | `[]` | Non-deletion routes/views, pure noise (§2.6). |
| `extra_files` | list | no | `[]` | Files with no personal data at all (§2.6). |
| `receivers` | list | django only | `[]` | Signal receivers (§2.7). |
| `admin` | list[str] | django only | `[]` | Model names registered in `admin.py`. |
| `retention` | list | no | `[]` | Declared retention rows (§2.8). |
| `expect` | map | yes | — | Declared verdicts (§2.9). |

### 2.2 `models[]`

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | — | Class name. |
| `table` | str | lowered plural of `name` | Emitted **literally**: `__tablename__ = "<table>"` for SQLAlchemy, `class Meta: db_table = "<table>"` for Django. Not left implicit — see §7 rule 1: a manifest store name that appears in no line of the repository is an alias, and the Django default table name (`accounts_address`) is exactly the alias an implicit `db_table` would create. |
| `store` | str | `table` | Manifest store name. Must equal `table`, or the store identity `03-verifier.md` §3.1 derives for that model, or generation fails (§7). |
| `negative` | bool | `false` | Table with no personal data. Goes in the manifest's `negatives:` list, not `stores:`. |
| `parent` | str\|null | `null` | Model name this one has a foreign key to. |
| `on_delete` | str | `CASCADE` | Django only: `CASCADE`, `SET_NULL`, `PROTECT`, `RESTRICT`, `DO_NOTHING`, `DB_CASCADE`. |
| `cascade` | str | `save-update, merge` | SQLAlchemy only: the `cascade=` string on the parent's `relationship()`. |
| `ondelete` | str\|null | `null` | SQLAlchemy only: `ForeignKey(..., ondelete=...)`. |
| `passive_deletes` | bool | `false` | SQLAlchemy only. |
| `fields` | list | — | See below. |

`fields[]` items:

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | — | Column name. |
| `type` | `str`\|`int`\|`bool`\|`datetime`\|`json`\|`text`\|`image`\|`decimal` | `str` | Rendered column type per flavour. `image` is Django `ImageField` only. |
| `category` | one of the six, or `null` | `null` | `null` means not personal data: the column is emitted, no manifest tuple is produced. |
| `pk` | bool | `false` | Primary key. Implies `category: null`. |
| `comment` | str\|null | `null` | Rendered as a trailing `# ...` comment on the column line. This is the only channel for the "may contain phone numbers" style hint. |
| `nullable` | bool | `true` | |
| `store` | str\|null | `null` | Routes this field's manifest tuple to a non-relational store instead of the model's own. Used for Django `ImageField`: the column is the pointer, the bytes are the store, and §7 rule 4 forbids counting both. The store name is then the `<model>.<field>` identity `03-verifier.md` §3.1 derives (§7 rule 1). |

The foreign-key column is **not** listed in `fields[]`. The generator emits it from `parent`: SQLAlchemy `user_id = Column(Integer, ForeignKey("users.id"))`, Django `account = models.ForeignKey(Account, on_delete=…)`. It carries no category and produces no tuple.

### 2.3 `stores[]` (non-relational)

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | — | Manifest store name **and** the identifier the template emits: the value of `BUCKET`, the Elasticsearch index, the cache key prefix, the queue name, the logger name, the backup target constant, or the SDK module. The templates take the identifier *from* this field rather than carrying their own literal, so the two cannot drift — see §7 rule 1. |
| `kind` | one of `object_storage`, `cache`, `search_index`, `queue`, `third_party`, `log`, `backup` | — | Contract §Record vocabulary. |
| `client` | `boto3`, `redis`, `elasticsearch`, `pika`, `stripe`, `sendgrid`, `mixpanel`, `sentry`, `logging`, `file` | — | Selects the template and the import. |
| `module` | str | derived from `client` | Path inside the package that holds the client (`storage.py`, `cache.py`, …). |
| `fields` | list[{name, category}] | — | What is written or sent. For third-party stores these are the argument names, not columns. |
| `writes_from` | str\|null | — | Name of the function in `module` that writes/sends. `null` where the store has no writer function of its own — a Django `ImageField`, whose write is the model column. |
| `write_called_by` | str \| `module` \| null | `module` | Who calls `writes_from`. A **symbol** (a route, usually) emits the call in that function's body. **`module`** emits the call at import time or from a schedule the module carries — `sentry_sdk.init` inside `init_observability()` called at the bottom of `app.py`, a middleware registered when the module loads, a dump script whose `SCHEDULE` constant is the evidence, a `if __name__ == "__main__":` entry on a job. **`null`** means the writer is defined and called by nothing: a dead-writer trap, used by no spec in S01–S10. |
| `delete_call` | str\|null | `null` | Name of the deletion function in `module`, e.g. `delete_avatar`. `null` means no deletion primitive exists at all. |
| `delete_called_by` | str\|null | `null` | Symbol that calls `delete_call`. **`null` while `delete_call` is set is the dead-helper shape**: the S10 trap on test, rehearsed on dev by S05's session cache so the rule is not first met on a case that costs a sweep. |
| `key_template` | str | `null` | e.g. `avatars/{user_id}.jpg`. Rendered as an f-string. |
| `versioning_declared` | bool | `false` | Emits `put_bucket_versioning(..., Status="Enabled")` in a bootstrap module. Flips R13. |
| `ttl_seconds` | int\|null | `null` | Cache only: `setex` TTL. Becomes a retention row, never an erasure path (R20). |
| `sdk_options` | map | `{}` | Sentry only: `send_default_pii`, `_experiments` (R23). |

### 2.4 `entry_points[]`

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | — | Function name. |
| `kind` | `route`\|`view`\|`cli`\|`admin`\|`task`\|`signal` | `route` | Contract §Entry-point kinds. |
| `module` | str | `api/account.py` (sqlalchemy) / `<app>/views.py` (django) | Repository-root relative, like every path in a manifest (contract: `file` is "relative to the repo root"). |
| `action` | `hard_delete`\|`soft_delete`\|`anonymise`\|`none` | — | What the body does to the primary model. |
| `deletes_via` | `session_delete`\|`bulk_dml`\|`model_delete`\|`queryset_delete` | flavour default | Which delete was called (R14–R17). |
| `calls` | list[str] | `[]` | Extra symbols called in the body, in order. |
| `docstring` | str\|null | `null` | Verbatim. **The S10 trap is a docstring that contradicts `calls`.** |

### 2.5 `jobs[]`

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | — | Function name. |
| `module` | str | `jobs/<name>.py` | |
| `kind` | `purge`\|`backup` | — | |
| `target` | str\|null | — | Model name for `purge`. |
| `method` | `orm_loop`\|`bulk_dml` | `orm_loop` | Purge only (R17). |
| `retention_days` | int\|null | `null` | Emitted as a module constant `RETENTION_DAYS = N` and used in the cutoff arithmetic. `null` on a backup job is the `no_schedule_evidenced` trap. |
| `schedule` | str\|null | `null` | Cron string emitted as `SCHEDULE = "0 3 * * *"`. |
| `filter_field` | str | `deleted_at` | The column the cutoff compares against. |

### 2.6 `routes[]` and `extra_files[]`

`routes[]`: `{name, module, reads: [Model.field, …]}` — a GET handler that touches personal data and deletes nothing. Noise, and the reason a repo has more than one thing in it.

`extra_files[]`: `{path, kind}` where `kind` is `helpers` (three pure string/date functions), `constants` (feature flags, page sizes), or `readme` (a two-line `README.md`). No personal data, ever. Each case carries at least one, per CASES.md ("plus one or two files with no personal data at all").

### 2.7 `receivers[]` (django only)

`{name, signal: pre_delete|post_delete, sender: <Model>|null, module, weak: true|false, registered_in: apps_ready|models|orphan, body: delete_file|noop}`.

- `registered_in: apps_ready` — `signals.py` imported from `AppConfig.ready()`. Connected (R12).
- `registered_in: models` — receiver at the bottom of `models.py`. Connected, because Django imports every installed app's `models` (R12, research §4.4(a)).
- `registered_in: orphan` — `signals.py` imported by nothing. Not connected, not evidence (R12).
- `sender: null` — receiver covers every model (R9).

### 2.8 `retention[]`

`{store, category, days|criteria, anchor|null}`. AMBIGUITIES row 16 wants retention split per `(store, category)` where the code distinguishes them; the synthetic set exercises the split across stores (S03 has three categories under three different timers) and not within one, because every within-store construction we tried needed a purge job that contradicts its own comment. Within one store the same idea is exercised on the erasure axis instead, by S07's field-level overrides. The real-repo manifests are where a within-store retention split will appear if the code has one. `days` and `criteria` are mutually exclusive (contract §Record vocabulary: "a `criteria` string is allowed where no number exists"). **`anchor` is required and may not be null.** A criteria string with no line behind it renders a manifest row with `file: null, line: null`, and invariant I6 of `04-output-schema.md` §4 rejects exactly that row in a submitted record, in both arms — so `retention_check.missing` would be permanently non-zero on a dev case for a row no arm is allowed to produce, and the number would mean nothing. CASES.md's illustrative manifest shows the null form; `04-output-schema.md` proposal 4 asks the lead for the errata line calling it a shape example rather than a submittable one. Where the criteria comes from a comment, the anchor is the line the comment sits on: comments are rendered inline on the column they annotate (§3.1, `models.py`), so `models.py::Invoice.reference` resolves to a line that carries the wording. A criteria with nothing to cite anywhere is `human.retention_justification`, not a retention row.

### 2.9 `expect`

```yaml
expect:
  entry_points: [close_account]          # names; must equal the entry_points[] names
  stores:
    users:   {verdict: erased_after_timer, timer_days: 30,
              evidence: "jobs/purge.py::purge_closed_accounts!delete"}
    uploads: {verdict: not_erased, evidence: null,
              note: "cleanup_user_files defined at {storage.py::cleanup_user_files}, never called"}
  fields:                                 # optional; overrides the store verdict for one field
    users.full_name: {verdict: anonymised, evidence: "privacy.py::anonymize_user!full_name"}
```

`note` strings may embed `{<anchor>}`; the generator resolves each to `path:line` after rendering. That is how the manifest carries "defined at `storage.py:41`, never called" without a human ever typing `41`.

---

## 3. The two flavours as file templates

Both templates are concrete: the same modules in the same order every time, contents decided by the knobs. File counts land in CASES.md's 8–15 band.

### 3.1 SQLAlchemy flavour

| File | Always | What it contains |
|---|---|---|
| `README.md` | yes | Two lines: the app's name and one sentence of purpose. No claim about deletion. |
| `requirements.txt` | yes | Pinned versions from research §Versions studied: `SQLAlchemy==2.0.52`, plus one line per SDK knob (`boto3==1.43.82`, `redis`, `stripe`, `sentry-sdk==2.68.1`, …). |
| `app.py` | yes | Two-line application object. When a Sentry store is declared: the `SENTRY_DEFAULT_FIELDS` list (one field name per line, §6.1), then `def init_observability()` holding `sentry_sdk.init(dsn=SENTRY_DSN)`, then a module-level `init_observability()` call — the init therefore runs at import time (R23) *and* the writer has a name the manifest can anchor to, which is what `write_called_by: module` means. |
| `config.py` | yes | `DATABASE_URL`, feature constants, region strings (`AWS_REGION = "eu-central-1"` — an `observed_region_hints` decoy that is not a transfer finding). |
| `db.py` | yes | `create_engine`, `SessionLocal`, `Base`; the `PRAGMA foreign_keys=ON` listener when `enforce_sqlite_fk`. |
| `models.py` | yes | Every model, in spec order. Columns in spec order, with `comment` rendered inline. `relationship(...)` on the parent side carrying `cascade` / `passive_deletes`. |
| `api/__init__.py` | yes | Empty. |
| `api/account.py` | yes | Entry points whose `module` defaults here. Absent entry points still leave the file, holding only the noise routes — S08 needs an `account.py` that has no delete in it. |
| `api/profile.py` | when `routes[]` non-empty | Noise routes. |
| `storage.py` | object_storage store | `BUCKET = "<store name>"`, boto3 client, a key builder named after the key field (`def avatar_key(user_id)`), `upload_*` carrying any metadata field as a literal dict key, `delete_*` if `delete_call`. |
| `billing.py` | stripe store | `stripe.Customer.create(email=user.email, name=user.full_name)` — one keyword per declared field, on its own line. |
| `cache.py` | cache store | `redis.Redis(...)`, `setex(f"<store name>:{…}", TTL, …)`, optional `delete`. The key prefix is the store name, which is the identity `03-verifier.md` §3.3 derives. |
| `analytics.py` | mixpanel store | `mp.track(user.email, ...)`. |
| `mail.py` | sendgrid store | `body = f"Welcome, {user.full_name}."` then `sg.send(to=user.email, …)` — every declared field named on one emitted line. |
| `search.py` | search_index store | `INDEX = "<store name>"`, `es.index(index=INDEX, document={…})` with one document key per line. |
| `queue.py` | queue store | `QUEUE = "<store name>"`, `channel.basic_publish(routing_key=QUEUE, body=json.dumps({…}))` with one payload key per line. |
| `middleware.py` | log store | `logger = logging.getLogger("<store name>")`, then one named local per declared field (`ip_address = request.client.host`, `path = request.url.path`) and `logger.info("%s %s", ip_address, path)`. The logger name is the store identity (`03-verifier.md` §3.7) and every field is a token the code writes. |
| `privacy.py` | `action: anonymise` | `anonymize_user(user)`. |
| `jobs/__init__.py` | `jobs[]` non-empty | Empty. |
| `jobs/<name>.py` | per job | Purge, or backup: `BACKUP_NAME = "<store name>"`, `DUMP_COLUMNS = ["email", "full_name"]` (every declared field of the backup store, one list, one line), the `SCHEDULE` and `BACKUP_RETENTION_DAYS` constants where the knobs ask for them, and the dump writer. `BACKUP_NAME` is the store identity; `DUMP_COLUMNS` is the line every backup field cites (§6.1). |
| `catalog.py` | a `negative` model exists | The negative model, alone, so a precision error has a file to come from. |
| `utils/text.py` | yes | `extra_files` `helpers`: slugify, truncate, humanise_bytes. No personal data. |

### 3.2 Django flavour

| File | Always | What it contains |
|---|---|---|
| `README.md`, `requirements.txt` | yes | As above; `Django==6.1`. |
| `manage.py` | yes | Stock four-line shim. |
| `<project>/__init__.py`, `<project>/urls.py` | yes | `urlpatterns` wiring the views. |
| `<project>/settings.py` | yes | `INSTALLED_APPS` (apps + `django_cleanup` when a knob asks), `DATABASES` from `engine`, `SECURE_SSL_REDIRECT = True` (an Art. 32(1)(a) `security_evidence` item, research §5(g)). |
| `<app>/__init__.py` | yes | Empty. |
| `<app>/apps.py` | yes | `AppConfig`; `ready()` importing `signals` when any receiver is `registered_in: apps_ready`. |
| `<app>/models.py` | yes | Models with an inner `class Meta: db_table = "<table>"`, `on_delete=models.<VALUE>`, `ImageField(upload_to=...)`; receivers when `registered_in: models`. |
| `<app>/views.py` | yes | Entry points and noise views. |
| `<app>/signals.py` | any receiver in `apps_ready`/`orphan` | The receivers. |
| `<app>/admin.py` | `admin[]` non-empty | `admin.site.register(...)` — AMBIGUITIES 15. |
| `<app>/storage.py` | object_storage store with a boto3 client | As the SQLAlchemy one. |
| `<second app>/models.py` | a `negative` model exists | The negative app. |
| `<app>/utils.py` | yes | Helpers, no personal data. |

### 3.3 File counts

| Case | Flavour | Files | Case | Flavour | Files |
|---|---|---|---|---|---|
| S01 | sqlalchemy | 11 | S06 | django | 15 |
| S02 | sqlalchemy | 10 | S07 | sqlalchemy | 13 |
| S03 | sqlalchemy | 13 | S08 | sqlalchemy | 15 |
| S04 | sqlalchemy | 12 | S09 | django | 15 |
| S05 | sqlalchemy | 15 | S10 | sqlalchemy | 15 |

---

## 4. Anchors: how a symbol becomes a line

The spec never contains a line number. Line numbers exist only after rendering, and are resolved by re-parsing the file the generator just wrote with `ast` — `lineno` is 1-indexed [research §6 R28, S35].

Four anchor forms, all `<relpath>::<symbol>`, all repository-root relative:

| Form | Resolves to | Example |
|---|---|---|
| `file::Class.attr` | The line of the assignment or annotated assignment for `attr` inside `class Class` | `models.py::User.email` |
| `file::name` | The `def` (or module-level assignment) line for `name`. For a decorated function this is the `def` line, not the decorator [S35] | `jobs/purge.py::purge_closed_accounts` |
| `file::name!callee` | The first `Call` inside `name` whose callee's last attribute equals `callee` | `api/account.py::delete_account!delete` |
| `file::name@attr` | The first assignment inside `name` whose target's last attribute equals `attr` | `privacy.py::anonymize_user@full_name` |

Resolution algorithm:

```
def resolve(anchor, rendered_files):
    path, symbol = anchor.split("::")
    tree = ast.parse(rendered_files[path])
    if "@" in symbol:
        holder, attr = symbol.split("@")
        node = find_def(tree, holder)
        for stmt in sorted(assignments_in(node), key=lambda n: (n.lineno, n.col_offset)):
            if last_name(stmt.targets[0]) == attr:
                return path, stmt.lineno
        raise SpecError(f"{anchor}: no assignment to {attr} inside {holder}")
    if "!" in symbol:
        holder, callee = symbol.split("!")
        node = find_def(tree, holder)
        calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
        for call in sorted(calls, key=lambda n: (n.lineno, n.col_offset)):
            if last_name(call.func) == callee:
                return path, call.lineno          # first in source order
        raise SpecError(f"{anchor}: no call to {callee} inside {holder}")
    if "." in symbol:
        cls, attr = symbol.split(".")
        node = find_class(tree, cls)
        for stmt in node.body:
            if assigns_to(stmt, attr):
                return path, stmt.lineno
        raise SpecError(...)
    node = find_def_or_assign(tree, symbol)
    return path, node.lineno
```

`ast.walk` does not preserve source order, which is why both search forms sort by `(lineno, col_offset)` before taking the first match. Every field anchor is generated, not written: the generator records the `lineno` of each column as it renders and does not need to search. Anchors are only written by hand in `expect:` (evidence and notes) and in `retention[].anchor`, and every one of them is resolved through this function so a typo fails the build.

`SpecError` aborts generation for the whole case. A half-written fixture is never left on disk: files are rendered into memory, checked, then written.

---

## 5. What each knob emits

The table is the contract between a spec and a template. Rule IDs are `docs/research/framework-behaviour.md` §6.

| Knob | Emitted code (abridged) | Exercises |
|---|---|---|
| `entry_points[].action: soft_delete` | `user.deleted_at = datetime.now(timezone.utc)` `user.is_active = False` | R25, AMBIGUITIES 4 |
| `entry_points[].action: hard_delete`, `deletes_via: session_delete` | `session.delete(user)` `session.commit()` | R5, R7 |
| `deletes_via: bulk_dml` | `session.execute(delete(User).where(...))` | R17 — no in-Python cascade |
| `deletes_via: model_delete` | `account.delete()` | R14 |
| `deletes_via: queryset_delete` | `Account.objects.filter(pk=pk).delete()` | R15 |
| `entry_points[].action: anonymise` | `privacy.py::anonymize_user` writing `sha256(...).hexdigest()` to the email and a constant to the name | gdpr §3.2 split: `pseudonymised` vs `anonymised` |
| `models[].cascade: "all, delete"` | `relationship("Order", cascade="all, delete")` | R5 positive |
| `models[].cascade` default | `relationship("Invoice")` — no delete token | R5 negative |
| `models[].ondelete: CASCADE` + `passive_deletes: true` | `ForeignKey("users.id", ondelete="CASCADE")`, `relationship(..., passive_deletes=True)` | R6 — `unverified` on SQLite unless `enforce_sqlite_fk` |
| `enforce_sqlite_fk: true` | `@event.listens_for(Engine, "connect")` emitting `PRAGMA foreign_keys=ON` | R6 positive [S46] |
| `models[].on_delete: CASCADE` | `ForeignKey(Account, on_delete=models.CASCADE)` | R1 |
| `models[].on_delete: SET_NULL` | `ForeignKey(..., on_delete=models.SET_NULL, null=True)` | R2 |
| `models[].on_delete: DB_CASCADE` | `ForeignKey(..., on_delete=models.DB_CASCADE)` | R4 — rows cascade, delete signals do not fire |
| `fields[].type: image` | `models.ImageField(upload_to="avatars/")` | R8 |
| `receivers[]` with matching `sender` | `@receiver(post_delete, sender=Account)` calling `instance.avatar.delete(save=False)` | R8(a) |
| `receivers[]` with a different `sender` | Same body, `sender=Comment` | **R9 — the S09 decoy** |
| `receivers[].registered_in: orphan` | `signals.py` imported by nothing | R12 |
| `receivers[].weak: false` | `post_delete.connect(handler, weak=False)` inside a function | R11 |
| `stores[].client: boto3` + `delete_call` + `delete_called_by` | `s3.delete_object(Bucket=BUCKET, Key=key)` reachable from the entry point | R13 positive |
| `delete_call` set, `delete_called_by: null` | The same function, defined, called by nothing | **R26 — S10's dead helper on test, S05's `purge_session` on dev** |
| `versioning_declared: true` | `bootstrap.py` with `put_bucket_versioning(Status="Enabled")` | R13 negative [S22][S23] |
| `stores[].client: redis` + `ttl_seconds` | `r.setex(f"{name}:{email}", SESSION_TTL_SECONDS, ...)` where `{name}` is the store name | R20 — a TTL is retention, not erasure |
| `stores[].client: stripe` | `stripe.Customer.create(` then one `field=user.<field>` line per declared field | R22 — never `erased` |
| `stores[].client: sentry`, `sdk_options: {}` | `SENTRY_DEFAULT_FIELDS = [...]`, one declared field name per line, then `sentry_sdk.init(dsn=SENTRY_DSN)` inside `init_observability()` | R23 — recipient with the flag absent, with the SDK's defaults written down where they can be cited |
| `stores[].client: mixpanel` / `sendgrid` | `mp.track(user.email, "account_closed")` / `body = f"Welcome, {user.full_name}."` + `sg.send(to=user.email, ...)` | R24 |
| `stores[].client: elasticsearch` | `INDEX = "<store name>"`; `es.index(index=INDEX, document={` one declared field per line `})` | R21 |
| `stores[].client: pika` | `QUEUE = "<store name>"`; `channel.basic_publish(routing_key=QUEUE, body=json.dumps({` one declared field per line `}))` | store kind `queue` |
| `stores[].client: logging` | `logger = logging.getLogger("<store name>")`; one `<field> = <source>` line per declared field; `logger.info("%s %s", ip_address, path)` | store kind `log` |
| `jobs[].kind: purge` + `retention_days` | `RETENTION_DAYS = 30`; `cutoff = now - timedelta(days=RETENTION_DAYS)` | `erased_after_timer`, Art. 30(1)(f) |
| `jobs[].kind: backup` + `schedule` + `retention_days` | `BACKUP_NAME = "<store name>"`, `DUMP_COLUMNS = [...]`, `SCHEDULE = "0 3 * * *"`, `BACKUP_RETENTION_DAYS = 35` | `governed_by_retention`, gdpr §3.1 |
| `jobs[].kind: backup`, `schedule: null`, `retention_days: null` | `BACKUP_NAME`, `DUMP_COLUMNS` and a dump writer, with no timer or cron string anywhere | `no_schedule_evidenced` — the EDPB finding, gdpr §3.1 |
| `entry_points[].docstring` | Rendered as the function docstring | **The S10 contradiction** |
| `fields[].comment` | Trailing `# free text; may contain phone numbers` | S07 semantic classification |
| `models[].negative: true` | The model in its own module, no personal columns | Precision: the `negatives` list |
| `admin[]` | `admin.site.register(Account)` | AMBIGUITIES 15, R16 |

---

## 6. Manifest derivation and the implication check

### 6.1 Derived

```
manifest.case            = spec.case
manifest.split           = spec.split
manifest.source          = "synthetic"
manifest.intent          = spec.intent
manifest.spec_sha256     = sha256(spec file bytes)
manifest.gen_version     = GEN_VERSION constant in gen.py
manifest.normalisation.prefixes = spec.apps          # [] for the sqlalchemy flavour, which has no package dir
manifest.entry_points[]  = one per spec.entry_points[], with file+line from the rendered def
manifest.stores[]        = one per non-negative model (kind relational) + one per spec.stores[]
  .fields[]              = every field with a non-null category, in spec order,
                           file+line captured while rendering the token that names it
  .recipient_kind        = "unknown" for kind third_party (contract: the agent may never set it)
manifest.negatives[]     = store/table names of models with negative: true
manifest.retention[]     = spec.retention[] with anchors resolved
```

**Which line names a field.** Only a relational field has a column, and `00-contract.md` requires `file` and `line` on every field of every store — so the templates are written so that each declared field's name appears verbatim on exactly one emitted line, and the generator records that line as it writes it. No search, no anchor, no hand-written number.

| Store kind | The line the field cites |
|---|---|
| `relational` | the column assignment |
| `object_storage`, key field | the `def <field>(...)` key builder in the storage module |
| `object_storage`, metadata field | the `Metadata={...}` dict entry inside the upload call |
| `third_party` | the keyword line of the transmitting call (`email=user.email`), or the line that interpolates the attribute (`body = f"Welcome, {user.full_name}."`) |
| `cache` | the `setex` / `set` line |
| `queue` | the payload key inside `basic_publish` |
| `search_index` | the document key inside `es.index` |
| `log` | the `<field> = <source>` line in the writer |
| `backup` | the `DUMP_COLUMNS` line, which is what makes an inherited column citable at all |

Two consequences the first draft of this document left as a hole. A declared field whose name the templates never write is a **build failure**, not a recall problem for the arm to absorb: the Sentry defaults are emitted as `SENTRY_DEFAULT_FIELDS` and the log's client address is emitted as `ip_address = request.client.host`, because a manifest field the verifier's citation check (`03-verifier.md` §7.2) rejects on every spelling leaves the advanced arm choosing between a rejected submit and lost recall, while the baseline — which runs schema validation only — books the same field as a true positive. That is an eval unfair between arms in the baseline's favour, and it rewards fabricating a citation.

### 6.2 Declared and checked

`expect.stores[<name>].verdict` is written into the manifest as-is. Before writing, `gen.py` computes the verdict the knobs imply and compares:

| Condition on the rendered case | Implied verdict |
|---|---|
| No entry point at all, store kind ≠ `backup` | `no_entry_point` |
| Store kind `backup`, a `schedule` or `retention_days` on its job | `governed_by_retention` |
| Store kind `backup`, neither | `no_schedule_evidenced` |
| Store kind `third_party`, no vendor deletion call on the path | `external_manual` |
| Relational, entry point `action: hard_delete`, store is the target or reachable by a delete-cascade edge (R1/R4/R5/R6+listener/R7) | `erased` |
| Relational, entry point `action: soft_delete`, a `purge` job with `retention_days` whose target is reachable | `erased_after_timer` |
| Relational, entry point `action: soft_delete`, no such job | `not_erased` |
| Entry point `action: anonymise`, every personal field on the store overwritten with a constant | `anonymised` |
| Entry point `action: anonymise`, any field hashed/tokenised, or the row and its foreign key survive | `pseudonymised` |
| `object_storage` with `delete_call` and a `delete_called_by` chain reaching an entry point, `versioning_declared: false` | `erased` |
| `object_storage` with `delete_call` but `delete_called_by: null` | `not_erased` |
| `cache`/`search_index`/`queue`/`log` with no delete on the path | `not_erased` |
| `ondelete` edge without `enforce_sqlite_fk` on a SQLite engine | `unverified` |

The rows are evaluated in `03-verifier.md` §6.1's precedence order, not in the order they are written here, and the first that fires decides. That ordering is what makes S03's invoices `unverified` rather than `not_erased`: both rows fire — no delete cascade token, and an `ondelete` edge with nothing enforcing it — and the verifier's row 8 sits above its row 9 precisely so the tool says "I could not tell" wherever the reason is its own blindness (AMBIGUITIES 14). Both are on the false side of `reaches_erasure`, so no scored tuple depends on the ordering; the rendered verdict does.

Mismatch → `SpecError: S07 store users: expect says 'anonymised', knobs imply 'pseudonymised' (email is hashed at privacy.py::anonymize_user)`. This table is deliberately a second, independent statement of the same rules the verifier implements; when it and `docs/spec/03-verifier.md` disagree, one of the two is wrong and the fixture build is where that surfaces.

Field-level `expect.fields[]` entries are written into the manifest as an `erasure` block on that field and override the store's for that field only (contract §Record vocabulary). The implication check runs per field with the same table.

### 6.3 Manifest header

```yaml
case: S10
split: test
source: synthetic
intent: "existence versus reachability: a dead cleanup helper and a docstring that contradicts the call graph"
spec_sha256: "…"
gen_version: 1
normalisation:
  prefixes: []
labelling_minutes: null      # synthetic default; see §8
```

Real-repo manifests (`R01`–`R05`) are hand-written in exactly this shape with `source: real`, `spec_sha256: null`, `gen_version: null`, `labelling_minutes: <int>` from the CASES.md protocol, plus `repo_sha` and `licence`. The scorer does not care which kind it is reading.

---

## 7. Naming rules that keep scoring unambiguous

The metric matches on `(store, field, reaches_erasure)` after normalisation. Four generator conventions remove the ways a correct answer could fail to match, without softening the metric. The first three are asserted mechanically, because the first draft of this document asserted the first one in prose and nine store names across five specs broke it.

1. **No aliases in the manifest, and the assertion is a build failure.** Two conditions, both checked after rendering and before writing:

   | Check | What it means |
   |---|---|
   | *Literal* | the store name occurs verbatim in at least one rendered file of that case |
   | *Same identity* | the store name equals the identity `03-verifier.md` §3.1–§3.8 derives for that store — the `__tablename__` or `db_table` string, the `BUCKET` value, the index name, the cache key prefix up to the first placeholder, the queue name, the logger name, the backup target constant, and for a third-party recipient the vendor key in `verify/rules/recipients.yaml` (`stripe`, `sentry`, `mixpanel`, `sendgrid` — the SDK module without its `_sdk` suffix) |

   The one store whose identity is not a single literal is a Django `FileField`/`ImageField`, which `03-verifier.md` §3.1 gives the id `<model>.<field>`; there the assertion is that both halves appear on the rendered column line and that the manifest name is `<model>.<field>` lowercased. That case matters more than it looks: the advanced arm's completeness guard names a missing store the way the verifier derives it, so a manifest calling it `avatar_files` would have the arm's own feedback steering it to a name that scores zero.

   The shared instruction text (`docs/spec/10-instructions.md`) must tell the agent the same convention in the same terms; that is a change for the lead, listed at the end of this document. An alias list would let the manifest absorb wrong answers and make the number unfalsifiable.
2. **No name collides across stores after normalisation, and the assertion runs over the rendered identifiers too.** The generator asserts that `norm(name)` is unique across all stores in a case, across all fields within a store, and across the identity strings the templates emitted, using the scorer's own normalisation function imported from `evals/harness/score.py`. Singularisation makes `uploads`/`upload` the same string, so a case may not contain both — and it also made S08's `documents` table collide with an index the knob table rendered as `index="documents"`, which the old manifest-only assertion could not see because the two names differed on the manifest side and agreed in the code. `extract()` drops the loser under `duplicates` (first occurrence wins), so the collision silently deletes tuples from a test case.
3. **No irregular plural.** The generator refuses a store or field name in `{statuses, analyses, indices, matrices, criteria, media, people, children}` and any name for which `norm(norm(x)) != norm(x)`. `norm` handles `-s`, `-ies` and `-es` (`05-eval-harness.md` §2) and nothing else; an irregular does not collide, it simply never matches, which is the silent failure the injectivity assertion cannot see.
4. **A relational column never mirrors an object key.** Object-store keys are derived from `user.id` inside the storage module (`f"avatars/{user_id}.jpg"`), never stored in a column. Without this rule a repo has `users.avatar_key` and `uploads.avatar_key`, one tuple is arguably a duplicate of the other, and the manifest has to take a side.

---

## 8. Determinism

Every one of these is asserted by `make fixtures`, not assumed.

- **No randomness.** No `random`, no `uuid`, no `hash()` (PYTHONHASHSEED-dependent). `sha256` over spec bytes is the only hash, and it is stable.
- **No timestamps.** Nothing generated carries a build date. `datetime` appears in generated code only as `datetime.now(timezone.utc)` inside function bodies, which is source text, not a value.
- **Fixed ordering.** Files are rendered in a fixed template order and written sorted by path. Models, fields, stores and jobs keep spec order. YAML is dumped with `sort_keys=False` and explicit key order, `default_flow_style=False`, `allow_unicode=True`, `width=100`.
- **LF only.** Every file is written with `newline="\n"` and ends in exactly one newline. No trailing whitespace on any line.
- **No generated-by banner inside the repos.** The fixtures are what the agent reads; a "do not edit, generated" header is a tell that changes what the model is looking at. Provenance lives in `evals/fixtures/synthetic/.gen-index.json`, outside every repo, one entry per case: `{"case", "spec_sha256", "gen_version", "files": {path: sha256}}`.
- **Idempotent.** `gen.py` removes `evals/fixtures/synthetic/<case>/` and rewrites it, so a file deleted from a spec disappears instead of lingering.

### The consistency assertions, in the order they run

All of them run after rendering into memory and before anything is written, so a violation leaves no fixture on disk. Each is a `SpecError` naming the case, the store and what was expected.

| # | Assertion |
|---|---|
| 1 | Every anchor in `expect:` and `retention[].anchor` resolves through §4 |
| 2 | Every store name is literal in a rendered file and equals the identity `03-verifier.md` derives (§7 rule 1) |
| 3 | `norm` is injective over store names, over each store's field names, and over the rendered identity strings (§7 rule 2) |
| 4 | No name is an irregular plural, and `norm` is idempotent on every name (§7 rule 3) |
| 5 | Every declared field's recorded `file:line` exists and the line contains the field name under `norm` — the same test `03-verifier.md` §7.2 runs on a submitted record. A ground-truth field the arms cannot cite is a build failure, not a recall tax (§6.1) |
| 6 | For a `third_party` store, every declared field appears on the transmitting call's rendered lines — as a keyword name or an interpolated attribute |
| 7 | `write_called_by: null` is refused on any store that declares fields and has a non-null `writes_from`; the dead-writer trap is not something a spec falls into by leaving a key at its default (§2.3) |
| 8 | The declared `expect` verdict equals the verdict the knobs imply (§6.2) |
| 9 | `spec.split` equals the case's membership in `evals/split.yaml` |

CLI: `uv run python evals/fixtures/gen.py [--case S03] [--all] [--check]`. `--check` renders into memory and diffs against disk without writing, exit 1 on any difference.

The Makefile target (`00-contract.md` §CLI contract lists `fixtures`):

```make
fixtures:
	uv run python evals/fixtures/gen.py --all
	git diff --exit-code -- evals/fixtures/synthetic evals/fixtures/manifests
	@echo "fixtures clean"
```

A judge who runs `make fixtures` on a clean clone gets `fixtures clean` and a zero exit. A non-empty diff means either a spec changed without its outputs being regenerated, or the generator is not deterministic; both are build failures.

### The freeze rule

**A spec is frozen the moment any agent run exists for its case.** Enforced, not promised: `gen.py` writes `spec_sha256` into the manifest, and `evals/harness/run.py` refuses to start a case whose manifest `spec_sha256` differs from `sha256` of the spec file on disk, exiting 4 with both digests. Changing a frozen spec therefore invalidates the case until the change is recorded: a dated line in `evals/CASES.md` §Errata, regeneration, and the deletion of that case's rows from `results/` so no number survives that was produced against a different repository. Manifest corrections after a run follow the same path (CASES.md §Rules: "Corrections after that go into the errata section with a date and apply to both arms").

### Blind labelling sidecar

G-01 has the author hand-label two synthetic dev cases (S03, S05) under the CASES.md protocol, timed, before seeing their manifests. That number cannot live in a generated manifest — `gen.py` would overwrite it and `make fixtures` would then never be clean. It lives in `evals/fixtures/manifests/<case>.labelling.yaml`, hand-written, never generated:

```yaml
case: S03
labelling_minutes: 34
labelled_at: 2026-08-29
labeller: author
protocol: evals/CASES.md#labelling-protocol
blind: true          # the manifest was not read before the timer stopped
```

`evals/harness/report.py` reads `labelling_minutes` from the manifest header for real repos and from the sidecar for synthetic ones, and reports which is which.

---

## 9. Extensions to the CASES.md case table

CASES.md is frozen except for a dated errata section, and these specs extend four of its rows. The lead applies the errata; the specs are written as if it is already applied, and each extension is listed here so the two can be reconciled in one read.

| Case | Extension | Why |
|---|---|---|
| S03 | Adds `jobs/backup.py` with `SCHEDULE` and `BACKUP_RETENTION_DAYS = 35`, giving a `nightly_backup` store with verdict `governed_by_retention` | gdpr-sources §3.1 added two backup verdicts after CASES.md was written; the rule must be built and tuned on dev, not first met on test |
| S03 | `Invoice` gains `ondelete: CASCADE` on its foreign key, with no `PRAGMA foreign_keys` listener and a SQLite engine; the verdict becomes `unverified` | AMBIGUITIES 14 makes `unverified` the project's safety valve, and no spec produced it — `unverified_mean` could only ever have been populated by the real repos, so nothing measured whether an arm over- or under-uses the one verdict that exists to stop a guess. Two lines, and it exercises R6 on dev. The tuple count and every `reaches_erasure` value are unchanged: `unverified` is on the false side exactly as `not_erased` was |
| S05 | Adds `sentry_sdk.init(dsn=…)` with no flags, a `sentry` third-party store with fields `url`, `query_string`, `request_body`, `local_variables`, and a `SENTRY_DEFAULT_FIELDS` list in `app.py` naming those four | research §6 R23 [S30][S31][S42]; R01 vendors `sentry_sdk`, so the rule needs a dev case. The list literal is what makes the four names citable — without it they are the research's answer and no line of code's, and §6.1 explains why that is a build failure rather than a recall tax |
| S05 | `sessions` gains `delete_call: purge_session` with `delete_called_by: null` | The dead-deletion-helper shape existed on S10 alone, which is test: a bug in the rule would be found by spending one of the two test sweeps. One knob on a store whose verdict does not move (`not_erased` either way, and no tuple changes) puts the rehearsal on dev, on a different store kind from S10's, so the two are not the same fixture twice |
| S05 | `analytics` becomes kind `third_party` with verdict `external_manual`, not `not_erased` | `00-contract.md`: "Recipients are stores of kind `third_party`; there is no separate recipients list." Same for the mail SDK, which CASES.md called "a recipient, not a store". **`reaches_erasure` is `false` either way, so no scored tuple changes** — the errata is a label correction |
| S07 | Gains the hashed-email trap: `close_account` calls `anonymize_user`, which hashes the email and writes a constant name. Store verdict `pseudonymised`; field `full_name` overrides to `anonymised` | gdpr-sources §3.2 asks for a planted case. Placed on S07 rather than S09 for three reasons: the `pseudonymised` false-safe rule must be developed on **dev**, because a trap first met on test cannot be fixed without spending one of the two test sweeps; S09's value is that it isolates a single variable (`sender=` mismatch) and a second trap would confound the attribution; and S07 already carries the "read what the code means, not what it is called" theme, which is exactly what `anonymize_user` writing a hash is |
| S08 | Gains three stores — `doc_search` (`search_index`), `events` (`queue`), `nightly_dump` (`backup`, no schedule, verdict `no_schedule_evidenced`) — reaching six stores of five kinds | Completes synthetic coverage of the contract's store kinds, and `no_schedule_evidenced` is the EDPB's own finding (controllers claiming schedules they do not have). The index is named `doc_search` and not `documents`: the case already has a `documents` table, and an index the code called `documents` normalises to the same string, which `extract()` resolves by dropping one of the two |
| S06 | One child model uses `on_delete=models.DB_CASCADE` | R4's row half is a real Django 6.1 propagation edge and belongs in the clean case. R4's other half — `DB_CASCADE` silently killing signal-based file cleanup — is a false-safe shape that stays in the verifier's unit tests (`docs/spec/03-verifier.md`), not in a scored case, so S09 keeps one variable |
| S10 | Drops the `(users, financial, criteria)` retention row that appears in CASES.md's illustrative manifest | That row says a financial field on `users` is kept for the statutory accounting period while the same table is hard-deleted at 30 days. The example is a shape illustration; the four stores and both evidence notes are reproduced exactly |
| S10 | Gains `users.signup_ip`, `users.last_seen_at`, `uploads.original_filename` and a second Stripe argument, reaching eleven tuples | `docs/spec/example-record-S10.md` is the hand-written target artefact — the document on screen at 1:15 of the video and the one the author holds the real output against — and it renders all four. Scored against the old seven-tuple manifest, the project's own model answer was precision 0.64 and `pass` false. The exemplar wins; `05-eval-harness.md` §1's counts are recomputed (11 tuples, 5 reaching, 6 not; 90 / 38 / 52 across the ten cases) |
| S05, S10 | The Stripe customer's second argument is `name`, in the template and in both specs | The two specs disagreed (`full_name` on S05, `name` in the exemplar) about the keyword the rendered `Customer.create(...)` actually passes. One spelling, asserted by §8 check 6: the declared fields of a third-party store are the names its call writes |
| S06, S09 | Store names become the identifiers the code carries: `accounts_account`, `accounts_address`, `accounts_comment`, `account.avatar`; `gallery_account`, `gallery_photo`, `gallery_comment`, `photo.image`. Django models emit an explicit `db_table` | §7 rule 1. The old names (`accounts`, `addresses`, `photo_files`, …) appeared in no line of either repository, and S09's `photo_files` is the single non-reaching tuple the whole case exists to measure — under an alias the case measured naming luck rather than the sender check |
| S07 | The log store's writer emits `ip_address = request.client.host` and `path = request.url.path` as named locals, and the logger is `logging.getLogger("request_log")` | The manifest declared `ip_address` on a store called `request_log`; the code wrote `request.client.host` through a module-named logger, so neither the field nor the store had a line that named it (§6.1, §7 rule 1) |

### Errata the lead applies to `evals/CASES.md`

CASES.md is frozen except for its dated errata section. Beyond the extensions above, three lines belong there and are stated plainly rather than left to a reader to reconstruct:

1. **Three rules have no dev rehearsal.** `no_entry_point` appears in one spec, S08 (test), where it decides 10 of 13 tuples; `no_schedule_evidenced` appears in one spec, S08, deciding 3; and the admin-only entry point of AMBIGUITIES 15 is first met on R03 (test). Their first *scored* appearance is therefore on the test split, and a bug in any of them is discovered by spending one of the two live test sweeps. Each is covered by a unit test written before the first advanced run — `test_no_entry_point_repo` (41), `test_backup_no_schedule` (49), `test_r16_admin_two_paths` (29) in `03-verifier.md` §10 — and that is the whole of their pre-test coverage. The dead-deletion-helper shape, which had the same problem, now has a dev rehearsal on S05.
2. **The synthetic set carries 90 tuples**, 38 reaching and 52 not, after the S10 reconciliation above.
3. **Pass requires `stop_condition == accepted`** (`05-eval-harness.md` §4.2), which is a change to the frozen Primary-metric definition.

### Knobs with no fixture behind them

These are specified for the real repos and for `03-verifier.md` §10's unit tests, and are **not** eval coverage — recorded here so nobody reads §5's table as a coverage claim: `enforce_sqlite_fk`, `passive_deletes`, `versioning_declared: true`, non-empty `sdk_options`, `weak: false`, `registered_in: models` and `orphan`, `deletes_via: bulk_dml` and `queryset_delete`, `method: bulk_dml`, and the `on_delete` values `SET_NULL`, `PROTECT`, `RESTRICT` and `DO_NOTHING`. The verdict `unverified` was on that list until S03 took `ondelete: CASCADE`; the others stay on it deliberately, because each new knob in a scored case is a second variable in a case built to isolate one.

---

## Decisions taken here

1. Verdicts are **declared** in the spec and cross-checked against a knob→verdict implication table; only the inventory is derived. A generator bug then fails the build instead of moving the ground truth.
2. Anchors are symbol references (`file::Class.attr`, `file::name`, `file::name!callee`) resolved to 1-indexed lines by re-parsing the rendered file with `ast`. No line number is ever written by hand, including inside manifest note strings, which support `{anchor}` interpolation.
3. Two templates, fixed file lists, 10–15 files per case; every case carries at least one file with no personal data in it.
4. Object-store keys are derived from `user.id` in the storage module and never mirrored in a relational column, so no two stores can claim the same field.
5. No aliases in manifests, asserted rather than asserted-in-prose: a store name must occur verbatim in a rendered file **and** equal the identity the verifier derives for that store, with `<model>.<field>` as the one derived-identity case. Django models emit an explicit `db_table` so the manifest's table name is a literal.
6. Normalised store names are asserted unique per case — over manifest names, over field names within a store, and over the identity strings the templates rendered — using the scorer's own normalisation function. Irregular plurals are refused outright, because they fail silently rather than colliding.
7. Determinism is defined as: no randomness, no timestamps, fixed order, LF, single trailing newline, no generated-by banner inside the repos, provenance in a single out-of-repo index file. `make fixtures` asserts it with `git diff --exit-code`.
8. A spec freezes when the first run against its case exists, enforced by `spec_sha256` in the manifest and a runner that exits 4 on a mismatch.
9. `labelling_minutes` for the blind-labelled synthetic cases lives in a hand-written sidecar, never in the generated manifest, so the clean-diff check survives the G-01 measurement.
10. The hashed-email pseudonymisation trap goes to **S07** (dev), not S09.
11. The scheduled backup goes to **S03** (dev) and to **S10** (test, matching CASES.md's own example manifest); the unscheduled one goes to **S08**, which is where `no_schedule_evidenced` belongs.
12. `DB_CASCADE` appears in S06 as a row-propagation edge only; its signal-killing half is a verifier unit test, so S09 keeps a single planted variable.
13. Every declared field's citation line is recorded while the template writes the token that names it, per store kind (§6.1), and the generator asserts the line contains the name. A ground-truth field no line of code names is a build failure: it costs the advanced arm either a rejected submit or its recall, and gives the baseline the same tuple for free.
14. `write_called_by` has three values, and `null` — the dead-writer trap — is refused on any store that declares fields. Five specs had reached it by leaving a key at its default, which asserted personal data in a store no execution path writes.
15. `unverified` gets a dev fixture (S03's invoices), the dead-helper shape gets a dev rehearsal (S05's session cache), and the two rules that still have none are named in the CASES.md errata rather than left for a test sweep to discover.

## Open risks

- **The implication table is a second implementation of the verifier's rules.** If both are wrong the same way, the fixture build passes and the eval measures nothing. Mitigated only by the fact that the two are written from the research document independently, and by the real repos, whose manifests are hand-labelled and owe nothing to either.
- **Synthetic repos are recognisably synthetic.** Short files, no dead history, no framework version drift. The real cases (R01–R04) exist because of this; the split puts the harder half of them in test, and dev F1 will read high partly for that reason. README must say so before a judge notices.
- **Sentry's four field names are now written down in `app.py`, which is a fixture that teaches.** `SENTRY_DEFAULT_FIELDS` makes them citable and stops the eval being unfair between the arms, and it also puts the answer in the repository the model reads. A model that lists all four has read a list, not reasoned about an SDK's defaults, so S05 measures less than it looks like it measures — the rule it exercises end to end is "a recipient with no `send_default_pii` flag is `external_manual`", not "you know what Sentry sends". R01 vendors `sentry_sdk` with no such list and is where the harder half is measured. If S05's Sentry recall reads suspiciously perfect in the first dev run, that is the reason, and the errata line reducing the store to `url` and `request_body` is still the fallback.
- **`make fixtures` is only as strong as the machine it runs on.** LF enforcement protects Windows; nothing protects against a future PyYAML dumping differently. The lockfile pins it, and a version bump that changes the dump is caught by the same clean-diff check that catches everything else.
- **Ten specs are ~700 lines of YAML that no test exercises until `gen.py` exists.** If the generator slips past Saturday morning, the fallback is to hand-write S01, S02 and S10 as literal repositories with hand-written manifests and drop the rest, which costs the synthetic coverage of six store kinds and the clean-diff guarantee. That trade is worse than it looks and should be the last thing cut.

- **Two rules are still first met on test.** `no_entry_point` decides 10 of S08's 13 tuples and `no_schedule_evidenced` decides 3, and no dev case rehearses either — a case with no entry point anywhere cannot be built from S01–S07 without destroying the case it is built from, and adding an eleventh synthetic case is more than the weekend has room for. Unit tests 41 and 49 stand in, the CASES.md errata says so plainly, and if the first test sweep shows either rule misfiring, that sweep is the one that pays for it.
- **`db_table` on every Django model is slightly unusual code.** Most Django projects leave it implicit, so the fixtures now differ from the median repository in a way the model can see. The alternative was a manifest name that appears nowhere in the repository, which is worse: it makes a correct answer unscoreable. The real Django cases (R03, R05) carry whatever the upstream authors wrote, which is where that difference gets measured.

## Proposed changes

### To `00-contract.md`

`00-contract.md` §Repository layout lists `evals/fixtures/manifests/<case>.yaml` and nothing beside it. Two files need adding to the layout, both created by this document:

- `evals/fixtures/manifests/<case>.labelling.yaml` — hand-written blind-labelling sidecar for synthetic cases (§8). Reason: `labelling_minutes` cannot live in a generated file without breaking the clean-diff check that ADR 0003 §9 requires.
- `evals/fixtures/synthetic/.gen-index.json` — one provenance entry per case (§8). Reason: provenance has to live somewhere, and inside the fixture repos it would be visible to the model.

### To `docs/spec/10-instructions.md`

**State the store-identity convention once, in the text both arms read.** §7 rule 1 makes the manifest side mechanical: a store name is the identifier the code carries, in the terms `03-verifier.md` §3.1–§3.8 derives it — the `__tablename__` or `db_table` string, the bucket constant, the index name, the cache key prefix, the queue name, the logger name, the SDK module, and `<model>.<field>` for a Django file field. The instructions currently say nothing about it, so the convention binds the ground truth and not the arms. Reason: the metric matches on the store name, the completeness guard names a missing store the verifier's way, and an arm that never learns the convention loses tuples to spelling.
