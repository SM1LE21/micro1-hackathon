# 03 — The deterministic verifier

The verifier is the part of the system the model cannot talk its way past. It reads the repository itself, builds a name-based call graph, decides for every store whether account deletion reaches it, and then checks the submitted record claim by claim against what it found. This document specifies the four modules under `art30/verify/` in enough detail to write them without a further decision: what is parsed and what is skipped, how a call is resolved and what an unresolved call does to a verdict, which stores the verifier can see on its own, the twenty-eight framework rules from the research turned into operational form, the path search, the verdict table, the claim check, the blind spots, the performance bounds, and a test plan that exists before the first advanced run.

**Reads with** `docs/spec/00-contract.md` (wins over this file), `.vault/adr/0002-gdpr-inventory-erasure-check.md`, `.vault/adr/0003-runtime-and-api-decisions.md`, `.vault/AMBIGUITIES.md` (rows 2, 3, 4, 5, 12, 13, 14, 15), `.vault/NON-GOALS.md`, `evals/CASES.md`, `docs/research/framework-behaviour.md` (§1–§6, rules R1–R28), `docs/research/sources/frameworks/*.md`, `docs/research/prior-art.md` §"What we borrow", `docs/research/gdpr-sources.md` §3, `docs/writing-rules.md`. Ships alongside `docs/spec/verifier-rules-draft.yaml`.

Source IDs (`[S1]`, `[S15]`, …) are the shared IDs of `docs/research/`; rule IDs (`R1`–`R28`) are `framework-behaviour.md` §6. Every rule below names both.

---

## 0. Shape of the thing

Four modules, one responsibility each, all under the 300-line rule.

| Module | Input | Output | Knows about |
|---|---|---|---|
| `verify/callgraph.py` | repo path | `Repo` object: files, symbols, imports, call sites, edges, decorators, class table | Python syntax only. No framework knowledge |
| `verify/rules.py` | `verify/rules/*.yaml` | matcher objects (store detectors, primitives, vocabularies, patterns) | data loading and matching; no graph |
| `verify/reach.py` | `Repo` + rules | stores, entry points, synthetic edges, `path_exists`, per-store verdicts | frameworks; the rules R1–R28 live here |
| `verify/check.py` | submitted record + `reach` results | the feedback object of contract §"Feedback object" | the record schema and the claim policy |

Data flows one way: `callgraph → reach → check`. `rules` is read by `reach` and `check`. Nothing imports the manifest, the harness or a model client; a judge can read `check.py` and see that it is comparison, not judgement (matrix X11).

The whole run is pure: same repo bytes plus same rule bytes give the same feedback object, byte for byte. Every collection that leaves a module is a sorted list.

Amended 2026-08-29: four modules became thirty-three, 6,583 lines, under AGENTS.md's ~300-line rule. The four responsibilities and the one-way flow are unchanged; each of the four outgrew a file and split. `art30/verify/__init__.py` carries the module map, one line per module naming the section of this document it implements, and is the place to start reading. The public surface is unchanged: `build_graph(root)`, `reach.path_exists`, `reach.verdicts`, `check.check`. (DEVIATIONS.md D-09)

---

## 1. Call-graph construction (`verify/callgraph.py`)

### 1.1 Module discovery

Walk the repo root with `os.walk`, directory names sorted, and parse every file matching `*.py`.

Skipped, in this order (first match wins), each skip counted and reported in the `Repo.skipped` tally:

| Skip | Why |
|---|---|
| `.git`, `__pycache__`, `node_modules`, `.venv`, `venv`, `env`, `site-packages`, `.tox`, `build`, `dist`, `.mypy_cache`, `.ruff_cache` | not application code; contract §Budgets excludes the first four from `list_tree` too |
| `static/`, `media/`, `htmlcov/`, `locale/` | assets |
| `migrations/` | generated, and `models.py` is the authority on fields; a migration that adds a column the model no longer has would create a phantom store |
| `tests/`, `test/`, `test_*.py`, `*_test.py`, `conftest.py` | `evals/CASES.md` counts non-test files; vendored real repos are stripped of tests |
| `setup.py`, `noxfile.py`, `docs/` | build and prose |
| files over 1 MB, or that raise `SyntaxError`, or that fail UTF-8 decode with `errors="strict"` | recorded in `Repo.unparsed` with the exception type; every store declared in an unparsed file is `unverified` (R28 [S35]) |

Two exceptions to the skip list, because the answer depends on them: a file named `settings.py` or `settings/*.py` is always parsed (it carries `INSTALLED_APPS`, R10), and a file under a `management/commands/` directory is always parsed (it is an entry point, §2).

Non-Python files are read by exactly one rule: the S3 versioning search of R13 (§4), which globs `*.tf`, `*.tfvars`, `*.yaml`, `*.yml`, `*.json`, `Dockerfile*`, `docker-compose*` at depth ≤ 4. That search never produces an edge, only a verdict downgrade, and the artifact says it was a string search.

The same search also runs over every scanned Python source **as text**, because that is where the research found the declaration living: "boto3 `put_bucket_versioning(..., Status="Enabled")` or `BucketVersioning(bucket).enable()` in a bootstrap script or management command" (`framework-behaviour.md` §3 [S22] [S23]). A declaration in Python was invisible to a search defined as non-Python only, which is the false safe R13 exists to prevent — and test 25's own fixture is a bootstrap script. Reading those files a second time as text costs one pass over bytes already in memory and still produces no edge.

### 1.2 Symbol table

One entry per definition, keyed by a qualified name that is stable across runs.

```
module_path  = relative path, "/" -> ".", ".py" stripped, "__init__" dropped
symbol       = module_path + "." + qualname
qualname     = "f" | "C.m" | "outer.inner" (nested defs; "<locals>" is dropped)
```

Recorded per symbol: `kind` (`function | method | classmethod | staticmethod | property | lambda`), `file`, `line` (`node.lineno`, 1-indexed [S35]), `end_line`, `class` (owner or `None`), `decorators` (§1.4), `args` (names only), `is_nested`, `is_async`, `dynamic` (set when the body contains an unresolvable dispatch, CG-12).

Classes get their own table: `name`, `file`, `line`, `bases` (dotted strings as written), `body_assignments` (the field declarations §3 reads), `decorators`.

Two definitions with the same qualified name in one module (a conditional redefinition) are both kept and every call to the name is `ambiguous`. Same short name in different modules is normal and is resolved by §1.5, not by collapsing.

Lambdas: `f = lambda ...` is a symbol named `f`. An inline lambda (a callback argument, a `default=`) is folded into its enclosing function, which is what the closest name-based tool documents doing [S37] — its calls are attributed to the enclosing function, and the fold is recorded so R11 can find it. A lambda passed to `Signal.connect` is never evidence (R11, §4).

### 1.3 Import map

Per module, a dict from local name to a target that is either an intra-repo symbol, an intra-repo module, or an external dotted path.

| Form | Binding |
|---|---|
| `import a.b` | `a.b` → module `a.b`; also `a` → package `a` |
| `import a.b as c` | `c` → module `a.b` |
| `from a.b import f` | `f` → symbol `a.b.f` if it exists intra-repo, else external `a.b.f` |
| `from a.b import f as g` | as above under `g` |
| `from . import m` (level 1) | resolved against the importing module's package |
| `from ..pkg.mod import f` (level 2) | package walk up `level - 1` from the module's package, then join |
| `from a import *` | module flagged `wildcard`; names fall through to CG-3/CG-4 |
| import inside a function body | recorded with the same binding, scoped to that function; a function-local import shadows the module-level one |
| `importlib.import_module("...")`, `__import__` | unresolved; sets `dynamic` on the enclosing function |

Django `settings.py` values that name modules as strings (`ROOT_URLCONF`, `WSGI_APPLICATION`, `INSTALLED_APPS`) are read as data by §2 and §4, not as imports.

### 1.4 Decorators as data (R27 [S35])

Every entry of `decorator_list` is recorded, never interpreted:

```python
{"name": "receiver",                     # last attribute or the bare Name
 "dotted": "django.dispatch.receiver",   # resolved through the import map where possible
 "args": ["post_delete"],                # dotted strings for Name/Attribute, repr for literals
 "keywords": {"sender": "Comment"},      # same encoding
 "file": "models.py", "line": 21}
```

A decorator whose dotted name matches no rule-set entry sets `wrapped_by_unmodelled_decorator` on the function. A deletion primitive reachable only through such a function is `unverified`, never `erased` (R27).

### 1.5 Call resolution

Every `ast.Call` inside a function body (and at module level, attributed to a synthetic `<module>` symbol) is recorded with `file`, `line`, the callee form, and the resolution outcome. Three outcomes, and each does something different to a path:

- **resolved** — exactly one intra-repo target, or a rule-set primitive. Edge added. A path made only of resolved edges can carry a verdict of `erased`.
- **ambiguous** — more than one candidate target, or a receiver the verifier cannot name. Edges added to every candidate, each flagged. A path that needs an ambiguous edge yields `unverified` for that store and never `erased`.
- **unresolved** — no intra-repo candidate. No edge. Recorded as an external call, which is how SDK primitives (`s3.delete_object`, `redis.delete`) are matched by the rules; if it matches nothing, it is dropped.

| ID | Call form | Resolution order | Outcome |
|---|---|---|---|
| CG-1 | `f()`, `f` bound by an import in this module | import map | resolved |
| CG-2 | `f()`, `f` defined in this module (module level or enclosing class) | module symbols | resolved |
| CG-3 | `f()`, unbound, exactly one repo-wide definition of short name `f` | repo index | resolved, flagged `by_short_name` |
| CG-4 | `f()`, unbound, several definitions of `f` | repo index | ambiguous |
| CG-5 | `f()`, unbound, no definition (builtin, external) | — | unresolved |
| CG-6 | `m.f()`, `m` an intra-repo module or package | import map | resolved |
| CG-7 | `m.f()`, `m` an external module (`boto3`, `redis`, `stripe`) | rule-set primitive match on `m.f` | resolved as primitive, or unresolved |
| CG-8 | `self.f()` inside class `C` | `C.f`, then intra-repo bases depth-first, left to right | resolved; ambiguous if any base is external and `C.f` is absent |
| CG-9 | `cls.f()` | as CG-8 | as CG-8 |
| CG-10 | `super().f()` | nearest intra-repo base defining `f` | resolved, else unresolved |
| CG-11 | `obj.f()`, receiver not a known module or `self` | every repo definition of short name `f` | ambiguous (1 or more candidates); unresolved if none and no primitive matches |
| CG-12 | `getattr(o, name)()`, `globals()[k]()`, `eval`, `exec`, `importlib` | — | unresolved, sets `dynamic` on the enclosing function |
| CG-13 | call inside an inline lambda | attributed to the enclosing function | as the form itself |
| CG-14 | call to a name bound to a lambda | that lambda symbol | resolved |
| CG-15 | a callable passed as an argument (`schedule(cleanup_user_files)`) | no edge | unresolved, recorded as a `reference` (see below) |
| CG-16 | `app.send_task("pkg.tasks.purge")`, `.apply_async` / `.delay` on a task symbol | task-name table (§2.4) | resolved, else unresolved |
| CG-17 | `path("x", views.close_account)`, `url(r"^x$", "app.views.close_account")` | entry-point declaration, not a call edge | see §2 |
| CG-18 | `post_delete.connect(fn, sender=Model)` | receiver record identical to the `@receiver` decorator form | see §4 SE2 |
| CG-19 | a decorated function whose decorator is unmodelled | edges from the body are unchanged | body reachable, but §4 R27 applies to verdicts |
| CG-20 | any call inside a module with a wildcard import, unbound | as CG-3/CG-4 | resolved or ambiguous |

**Reference edges (CG-15).** `Name` nodes in argument position that resolve to an intra-repo function are recorded as `references`, not calls. They do not make a path on their own, and they are the reason S10's diagnosis can say "defined but has no callers": a helper mentioned nowhere is a different finding from a helper handed to a scheduler. Where a reference is passed to a rule-set-known scheduler (`atexit.register`, APScheduler `add_job`, `Signal.connect`, Celery `apply_async(args=...)`), the rules promote it to an edge; anything else leaves it a reference and the store stays `unverified` rather than `not_erased` if that reference is the only thing standing between the store and a primitive.

**Dynamic dispatch (CG-12), narrowed.** An unresolvable call does not poison the whole repository. It downgrades a store's verdict from `not_erased` to `unverified` only when the opaque call is plausibly that store's primitive: the receiver name is a variable the store detector bound to that store's client (`getattr(s3, meth)()` where `s3` is the detected S3 client), or the opaque call sits in a module that holds a detected client for that store. Every other unresolvable call is recorded and changes nothing. Without this narrowing, one `getattr` in a middleware would render an entire repository `unverified` and the tool would say nothing at all (AMBIGUITIES 14 asks for `unverified`, not for silence).

### 1.6 What the graph is

Nodes: symbols, plus store nodes (`store:<id>`, §3), plus entry-point nodes (§2). Edges: resolved and ambiguous call edges, promoted references, and the synthetic edges of §4. Every edge carries `{kind, file, line, rule, ambiguous}` so a path can be printed as evidence with a citation per step — Privado's step-level shape, which is the granularity an erasure table needs (`prior-art.md` §"What we borrow" item 3, [S12a]).

---

## 2. Entry-point discovery

An entry point is where a person's account deletion begins. Fides marks which fields are identities and starts its traversal only there; the erasure walk starts only at an entry point for the same reason (`prior-art.md` §"What we borrow" item 4, [S17]). A deletion primitive that no entry point reaches is not erasure — that is AMBIGUITIES row 2 reading B, and it is the whole eval case S10.

### 2.1 The erasure vocabulary

A function, route, command or task qualifies on its name when the normalised name (contract §Name normalisation) contains one of:

```
delete_user  delete_account  close_account  deactivate_account  remove_account
delete_me    delete_profile  destroy_user   terminate_account   cancel_account
purge        purge_user      erase          forget              forget_me
anonymize    anonymise       gdpr           dsr                 right_to_be_forgotten
scrub        wipe            offboard       account_deletion    data_deletion
```

Three deliberate exclusions. Bare `delete` and bare `destroy` are excluded on their own (they match `delete_comment`, `destroy_session`) except where §2.2 supplies the subject — a DRF `destroy` on a viewset whose queryset is the user model qualifies through the viewset, not through the word. `deactivate` alone qualifies only when the object is the user model or the route path contains `user`/`account`/`me`; on its own it is usually a feature flag. `cleanup` and `remove` never qualify on their own: `cleanup_user_files` in S10 is a helper, not an entry point, and treating it as one would hand the hard case a free pass.

The vocabulary lives in `verify/rules/entrypoints.yaml`, not in code.

### 2.2 Discovery sources

| Kind | Detected from | Recorded as |
|---|---|---|
| `route` | a DELETE-carrying route decorator — Flask `@app.route(..., methods=[... "DELETE" ...])` or `@bp.route(...)` with the same, FastAPI `@app.delete` / `@router.delete`, DRF `@api_view(["DELETE"])` — **and** the subject qualification below | the decorated function, with the HTTP method and path string |
| `route` | DRF: a class with a base named `*ViewSet`/`ModelViewSet` and a `queryset`/`get_queryset` naming the user model — its `destroy`, `perform_destroy`, and any `@action(methods=["delete"])` | the method symbol; the viewset's model is recorded |
| `view` | Django: a function named in `urlpatterns` via `path()`/`re_path()`, or a `DeleteView` subclass, whose name or URL pattern matches the vocabulary | the view function or the class's `delete`/`form_valid` |
| `admin` | `@admin.register(M)` or `admin.site.register(M)` where `M` is a model carrying personal data; unless the `ModelAdmin` sets `has_delete_permission` returning `False` or excludes the `delete_selected` action | two entry points: `admin_delete_model` (mode `model_delete`, [S9]) and `admin_delete_selected` (mode `queryset_delete`, [S8]), both flagged `admin_only` (AMBIGUITIES 15) |
| `cli` | Django `BaseCommand` subclass under `management/commands/` — the file name is the command name; `handle` is the entry symbol | qualifies on the command name or on `handle`'s callees matching the vocabulary |
| `cli` | click (`@click.command`, `@cli.command`), typer (`@app.command`), argparse (`add_parser("name")` plus `set_defaults(func=…)`) | the command name string decides, then the function name |
| `task` | Celery `@app.task` / `@shared_task` / `@task`, RQ `@job`, plus `Queue.enqueue(fn)` targets | the task symbol, with its task name (§2.4) |
| `signal` | never an entry point on its own | receivers are reached *through* a row deletion (§4 SE2), not started at |
| `unknown` | a module-level function matching the vocabulary that none of the above claims | kind `unknown`, still a valid start node |

Kinds are exactly the contract's set: `route | view | cli | admin | task | signal | unknown`.

Amended 2026-08-29: the `unknown` row does most of the work on this eval set. Every route in `S01`–`S10` is an undecorated module-level function — `api/account.py::close_account` has no decorator at all — so no `route` row fires and `_unclaimed` records the function as kind `unknown` (`tests/verify/test_entrypoints.py::test_module_level_function_is_kind_unknown`). The manifests call the same function kind `route`. Both are right about different questions and neither is scored: the metric's tuple is `(store, field, reaches_erasure)`, and this table's own last row already makes `unknown` "still a valid start node". A record and the verifier may therefore disagree about an entry point's kind without either being wrong. (DEVIATIONS.md D-10)

Amended 2026-08-29: the `admin` row yields two entry points **per repository**, not per registration. `registration.admin_entry_points` collects every model whose admin still deletes, then emits `admin_delete_model` and `admin_delete_selected` once, both citing the first qualifying registration line and both carrying the full model list. Two per model would multiply start nodes that set the same two modes and reach the same stores. `tests/verify/test_entrypoints.py::test_admin_gives_exactly_two_entry_points` pins the pair, the shared citation and the two `sets_mode` values. (DEVIATIONS.md D-11)

**The subject qualification, which binds every route form and not only the last one.** The HTTP method is not the question; *whose* deletion it is, is. A DELETE route qualifies as an erasure entry point only when at least one of these holds:

1. the normalised function name matches the §2.1 vocabulary (`delete_user`, `close_account`, `delete_user_me`);
2. the model the handler deletes resolves to a `subject_root` (§3.1) — the DRF `queryset`/`get_queryset` model, or the variable→model binding at the delete call site (§11, finding 2);
3. the route's terminal resource segment names the subject: `/users/{id}`, `/me`, `/account`, `/profile` — the route deletes the user resource itself, not something owned by a user.

Without this, every DELETE endpoint in the repository is an erasure entry point, and

```python
@router.delete("/posts/{post_id}")
def delete_post(post_id: int, s: Session):
    s.delete(s.get(Post, post_id))
```

makes `rows:post` reachable from an "entry point" and scores it as reaching erasure on account closure, in a repository that has no account-closure path at all. That is AMBIGUITIES row 2 reading A, which this project rejected, and it would break the expected `no_entry_point` for S08 and R04 the moment either grew one unrelated DELETE route. Test 51 pins it.

Scheduled jobs are entry points of kind `task` or `cli` and matter twice: as a start node in their own right, and as the second half of `erased_after_timer` (§6). The `task` decorator makes a function an entry-point *candidate*; it is never on its own evidence that anything runs it (§6.2 requirement 4).

### 2.3 No entry point at all

If discovery and the record's declarations together yield nothing, every store's verdict is `no_entry_point` and the completeness guard still runs. This is S08 and R04, and it is the case where the record's most useful sentence is that there is no way for a user to be deleted.

### 2.4 The task-name table

Celery task names default to `module.function` and are overridden by `@app.task(name="…")`. The table maps name string → symbol so that `send_task("billing.tasks.purge_user")` resolves (CG-16). RQ's `enqueue("dotted.path")` uses the same table with dotted-path lookup.

### 2.5 Reconciling declared and discovered entry points (AMBIGUITIES 3, 15)

The record carries the agent's entry points; the verifier has its own set. Let `D` be discovered and `E` declared.

| Case | What the verifier does |
|---|---|
| `e ∈ D ∩ E` | confirmed; used as a start node, no cap |
| `e ∈ E \ D`, citation resolves **and** the verifier can see the symbol registered as externally invocable | accepted as a start node, flagged `declared_only`. The model is allowed to know a route the rules do not cover |
| `e ∈ E \ D`, citation resolves, **no registration visible** | kept in the record and used as a start node, flagged `declared_unregistered`, and **capped**: every verdict derived from it is `unverified`, never `erased`, `erased_after_timer` or `anonymised` |
| `e ∈ E \ D`, citation does not resolve, or the cited line does not contain the symbol | `bad_citations` entry; dropped as a start node |
| `e ∈ D \ E` | used as a start node anyway. It is not itself a rejection |

**Registered as externally invocable** means one of the §2.2 discovery shapes is present on the declared symbol, even where the rules did not qualify it as *erasure*: a route decorator, a reference from `urlpatterns`, a `BaseCommand` subclass under `management/commands/`, a click/typer command decorator, a task decorator plus a §6.2 schedule registration, or an admin registration. The vocabulary is not consulted — this test asks whether anything outside the process can call the function, not whether its name sounds like deletion.

The cap exists because the earlier wording had the safety argument backwards. Adding a start node makes *more* stores read `erased`, which is the unsafe direction, and any intra-repo symbol with a resolving citation was a start node. S10 fell in four lines: the record declares `{name: cleanup_user_files, file: storage.py, line: 41, kind: unknown}`, the citation resolves, and `path_exists` then walks `cleanup_user_files → s3.delete_object` in one hop, so the verifier corroborated `erased` for `uploads` — in the case the whole eval is built around. §2.1 keeps `cleanup` out of the vocabulary precisely so that cannot happen; a declared entry point must not hand it back. Under the cap the model may still tell the verifier about a helper, and the verifier will still say it cannot confirm that anything calls it.

Verdicts are computed over `D ∪ E_valid`, with `declared_unregistered` nodes contributing only capped verdicts. A discovered entry point the record does not declare is one `missing_entry_points` entry — `{name, file, line, kind, expected}`, non-blocking (contract §Feedback object) — so the model is told what it missed without having to read it out of a rejection's prose. The case where the omission also costs a claim is a record that says `no_entry_point` for a store the verifier walks to from a discovered admin registration: the verdicts differ, and that claim is rejected on its own terms.

---

## 3. Store detection

What the verifier can see on its own, before it reads the record. Used for the synthetic edges, for the verdicts, and for the completeness guard. Detection is name and shape matching over the AST plus the rule data — no type inference (NON-GOALS).

A store is `{id, kind, name, declared_at (file:line), client_vars, fields[], evidence[]}`. `kind` is the contract's closed set: `relational | object_storage | cache | search_index | queue | third_party | log | backup`. The name is the identifier the code carries — the table or model name, the bucket or prefix constant, the SDK name, the job module for backups — which is contract §Verifier contract's store-identity convention and binds the manifests and the instruction text alike.

### 3.1 Relational

**Django.** A `ClassDef` whose bases include `Model` (`models.Model`, `django.db.models.Model`, or a base that itself resolves to one intra-repo). Store name = `db_table` from an inner `Meta` if present, else the normalised class name. Fields = every class-body assignment whose value is a call to a name ending in `Field`:

| Field call | Recorded as |
|---|---|
| `CharField`, `TextField`, `EmailField`, `URLField`, `SlugField` | scalar column, type kept verbatim |
| `FileField`, `ImageField` | **a second store** of kind `object_storage`, id `<model>.<field>`, with `upload_to` kept — the row and the bytes have different fates (R8 [S1] [S2]) |
| `JSONField` | scalar column, flagged `opaque_container` (the completeness guard treats a personal-data-looking key inside it as invisible; the taxonomy asks the model for the semantic call) |
| `ForeignKey`, `OneToOneField` | an edge candidate; `to` (first positional or `to=`) and `on_delete` recorded as written (`models.CASCADE` → `CASCADE`) |
| `ManyToManyField` | edge candidate plus, where `through=` names a model, that model as its own store |
| `DateTimeField(auto_now_add=…)`, `BooleanField`, `IntegerField` | scalar column |

`AbstractUser`/`AbstractBaseUser` subclasses, and any model named in `AUTH_USER_MODEL`, are marked `subject_root`: Bearer's known-object idea, which is what makes aggressive classification safe on `User` and conservative elsewhere ([S5], `prior-art.md` item 1).

**SQLAlchemy / SQLModel.** Three shapes:

- declarative: a `ClassDef` with `__tablename__` in its body, or a base that resolves to `DeclarativeBase`/`declarative_base()`; SQLModel's `table=True` class keyword. Fields = `mapped_column(...)`, `Column(...)`, `Field(...)` assignments and bare annotated attributes.
- Core: `Table("name", metadata, Column(...), …)` at module level. The first positional string is the store name; `Column` calls are the fields. Association tables reached by `secondary=` are stores in their own right — they carry the user↔tag, user↔consent links, which are personal data about the subject (§4 R7 [S18]).
- `ForeignKey("user.id", ondelete="CASCADE")` records the target table and the `ondelete` string; `relationship(..., cascade="…", passive_deletes=…, secondary=…)` records the tokens.

A class with neither `__tablename__` nor a resolvable declarative base is not a store. The spike (§11) emitted `rows:Base` for the declarative base class until that filter was added; it is a one-line rule that removes a phantom store from every SQLAlchemy repository.

### 3.2 Object storage

- boto3: `boto3.client("s3")` / `boto3.resource("s3")` assigned to a name; the name becomes a `client_var`. Bucket names from `Bucket=` kwargs and from module constants they resolve to.
- django-storages: `S3Storage`/`S3Boto3Storage` in `DEFAULT_FILE_STORAGE`/`STORAGES`, or instantiated directly [S14].
- Django `FileField`/`ImageField` (§3.1) — local disk or whatever storage is configured; the store's `declared_at` is the field line.
- Any `default_storage.save/delete`, `storage.save/delete` call.

Bucket-or-prefix is the store identity where a bucket name is visible; otherwise the field or the client variable names it. A deletion call is attributed by §3.10, not by the client variable.

Amended 2026-08-29: a Django `FileField`/`ImageField` store is identified as `<normalised model>.<field>` — `avatar.image` — not by the field name alone, and it sits beside the relational store `avatar` rather than inside it (`art30/verify/stores.py::_file_store`: "the row and the bytes have different fates, so two stores"). That id is the key `reach.verdicts()` returns it under and the string every R8 test asserts on. `avatar.image` and a bucket named `uploads` never normalise equal, so the scorer and the acceptance test reconcile a file store by the `FileField` declaration line it cites rather than by its name (`tests/verify/test_fixtures_reproduce.py::_key`). (DEVIATIONS.md D-13)

### 3.3 Cache

`redis.Redis(...)`, `redis.from_url(...)`, `StrictRedis`, `django_redis`, `aioredis`, and Django's `cache` API (`from django.core.cache import cache`). Store identity is the key namespace: the literal prefix of the first argument of `set`/`setex`/`hset`/`get` up to the first format placeholder (`session:{}` → `session`). Where the key is fully dynamic the store is named after the client variable and flagged.

Fields are what is written: for `set(key, value)` the value's attribute names where they are readable (`user.email` → `email`), for `hset` the mapping keys, for `json.dumps(payload)` the keys of a literal dict. One handle normally serves several namespaces, so a `delete` is attributed by §3.10 and never by the handle.

### 3.4 Search index

`elasticsearch.Elasticsearch(...)`, `opensearchpy`, `elasticsearch_dsl`, Django-Haystack, `meilisearch`. Store identity: the `index=` value, and a delete is attributed to the index it names (§3.10). A search index is a distinct store and a relational delete never touches it (R21 [S26] [S27]) — the reason R04 is in the eval at all.

### 3.5 Queue

Celery (`@task`, `.delay(...)`, `.apply_async(args=…)`), RQ (`Queue.enqueue`), Django-Q, Dramatiq, and raw Redis list pushes (`lpush`, `rpush`). A queue is a store only when a personal-data value is in the payload: an argument that is an attribute of a subject-root object (`user.email`), a dict literal with a personal-data-looking key, or a serialised model instance. A task called with `user.id` alone is not a store (an identifier alone is a link, and the record's `identifier` category covers it where the model judges it personal — the verifier does not invent the store).

### 3.6 Third-party recipients

Detected by import plus call, never by import alone (AMBIGUITIES 7 reading B with A as the discovery heuristic). `verify/rules/recipients.yaml` carries, per SDK: import names, the calls that transmit, the fields those calls carry by default, whether a deletion endpoint exists, and the default verdict.

Shipped set: `stripe`, `sentry_sdk`, `mixpanel`, `segment`/`analytics`, `sendgrid`, `mailgun`, `postmark`, `django.core.mail`/`smtplib`, `twilio`, `intercom`, `hubspot`, `amplitude`, `posthog`, `slack_sdk`, `gravatar` (an email hash in a URL, which is R04's quiet recipient).

Sentry is special and R23 says why: `sentry_sdk.init(dsn=…)` alone makes it a recipient, with `url`, `query_string`, request bodies and stack-frame locals going out under the SDK's own defaults [S30] [S31] [S42]. The rule data therefore carries a `fields_by_default` list for Sentry that the other SDKs do not need.

`recipient_kind` is never set by the verifier or the agent — the human sets it at the gate (contract §Record vocabulary).

### 3.7 Log sinks

A `logging` call (`logger.info/warning/error/exception`, `print` in a request path, `structlog` bind/log calls) whose message or arguments interpolate a personal-data-looking attribute: an f-string containing `user.email`, `%s` with `request.META["REMOTE_ADDR"]`, a `extra={...}` dict with such a key. Store identity is the logger name (`__name__` → the module) or `stdout`. Django middleware writing `ip_address` is the S07 case.

### 3.8 Backups

A function or task whose name matches `backup|snapshot|dump|pg_dump|mysqldump|export_all`, a `create_db_snapshot`/`create_snapshot` boto3 call, a cron entry or Celery beat schedule pointing at one, or a documented lifecycle rule. Fields are inherited from the tables the dump covers where they are readable, otherwise the store carries the note that the dump is opaque. Backups never get an erasure verdict: `governed_by_retention` with a cited schedule, or `no_schedule_evidenced` (AMBIGUITIES 6, `gdpr-sources.md` §3.1 [S10] [S11]).

### 3.9 Personal-data-looking field names — completeness guard only

This list is used for one job: deciding that a store the verifier found is missing from the record. It never assigns a category, never appears in the record, and never decides a verdict. It is deliberately short, because a long list turns the guard into a source of false rejections that cost the model attempts:

**Strong** — an identifier or contact name specific enough to carry the guard on its own:

```
email  e_mail  mail  first_name  last_name  full_name  username  phone
phone_number  mobile  address  street  city  postcode  zip  country  dob
date_of_birth  birth_date  ssn  national_id  passport  iban  vat  tax_id
ip  ip_address  user_agent  latitude  longitude  avatar  photo  picture
```

**Qualified** — counts only on a store that also has a link to a subject root (a foreign key to the user model, or a store name containing `user`/`customer`/`member`/`patient`/`account`/`owner`/`profile`/`subscriber`):

```
name  notes  comment  bio  message  content  body
```

The guard fires on a strong match, or on a qualified match plus a subject link. A store with no subject link and no strong match is a negative: it stays out, which is what protects precision on `products` in S07 (Bearer's known/unknown split, [S5]).

`name` moved from strong to qualified after measurement, not on taste. `guard.py` (§11) emulates §3.9 and §7.4 over the four vendored eval repositories and, with `name` strong, fires twice on FlaskBB with no subject link in sight — `Group` (`flaskbb/user/models.py`, columns `name, description, admin, super_mod, mod, guest, banned`) and `PluginRegistry` (`flaskbb/plugins/models.py`, `name, enabled`). Neither holds personal data, so neither is in the R02 manifest, and since `missing_stores` blocks acceptance (§7.1) R02 would either never reach `accepted` in five attempts or reach it by adding two non-personal stores and paying for them in precision on the primary metric — the advanced arm losing the case on the verifier's opinion either way. It also fires on S07's `products`, the case whose whole purpose is the precision test, and `record.schema.json` says of `stores[].fields`: "A store with no personal-data field does not belong in the record". With `name` qualified the same script fires zero times on all four (§7.4 carries the numbers).

### 3.10 Which store a keyed primitive touches

For stores of kind `cache`, `object_storage`, `search_index` and `queue`, the store's identity is a namespace and the client handle is not: one `redis.Redis()`, one boto3 client or one Elasticsearch client normally serves several. Attributing a deletion to the handle marks the siblings erased.

```python
r = redis.Redis()
def cache_profile(u):
    r.setex(f"profile:{u.id}", 86400, json.dumps({"email": u.email}))
    r.setex(f"session:{u.id}", 3600, u.email)
def close_account(u):
    r.delete(f"session:{u.id}")      # only the session key
    u.delete()
```

Two cache stores, `session` and `profile`, both bound to `r`. Attributed by handle, `profile` reads `erased` and the email survives. The same shape is `delete_object(Bucket="thumbs")` against an `uploads` bucket and `es.delete(index="posts")` against a `users` index — R04's store.

So SE12 (§4.2) adds an edge from a primitive to one of these stores only when the primitive's **own literal** matches that store's identity after normalisation:

| Kind | Literal read at the delete call | Compared with |
|---|---|---|
| `cache` | the key argument's literal prefix up to the first placeholder | the store's key namespace (§3.3) |
| `object_storage` | `Bucket=`, or the `upload_to`/prefix of the field the receiver binds to | the bucket-or-prefix identity (§3.2) |
| `search_index` | `index=` | the index name (§3.4) |
| `queue` | the queue or task name | the queue identity (§3.5) |

Where the argument is fully dynamic the store is `unverified` under the §1.5 narrowing (the opaque call plausibly touches a store the module holds a client for). Where the literal names a *different* namespace, no edge is added and the store keeps whatever verdict its own evidence gives it — `not_erased` where nothing else reaches it. Neither branch produces `erased`. Test 52 pins the two-namespace case.

Amended 2026-08-29: the same rule binds one level up, in the store table itself. `context.Ctx.add` keys the detectors' table on `(kind, id)`, never on the id alone. Keyed on the id, a `sessions` table and a `session:`-prefixed cache namespace merged into one store and the relational SE12 edge marked the cache erased while the emails in it survived — this section's own false safe, arrived at through the store table instead of through a client handle. A second kind arriving under a taken id keeps its own entry as `<id>#<kind>`; both stores are flagged `store_id_conflict`, the flag is on the record the feedback carries, and neither is merged. (DEVIATIONS.md D-15)

---

## 4. Synthetic edges and the rules R1–R28

### 4.1 Delete modes: why one graph is not enough

Django and SQLAlchemy both behave differently depending on *which* delete was called, and the difference decides four rules (R14, R15, R17, R18). A single undirected notion of "reaches" would bless a `Model.delete()` override on a path that never calls `Model.delete()`. So a path carries a mode, set at the delete call site and checked at every synthetic edge:

| Mode | Set by | Cascades | Signals / events |
|---|---|---|---|
| `model_delete` | `instance.delete()`, admin `delete_model` [S9] | Python `CASCADE` | `pre_delete`/`post_delete` fire; the overridden `Model.delete()` runs |
| `queryset_delete` | `Model.objects.filter(...).delete()`, admin "delete selected" [S8] | Python `CASCADE` | signals fire [S3]; the override does **not** run [S3] [S4] |
| `db_cascade` | reaching a child through a `DB_CASCADE` foreign key [S1] | database-side | **no signals** — this is what R4 turns into a verdict |
| `session_delete` | `session.delete(obj)` | ORM `cascade` tokens, `secondary` rows [S18] | `before_delete`/`after_delete` fire [S17] |
| `bulk_dml` | `session.execute(delete(Model))` | only database-side `ON DELETE` [S15] [S16] | no ORM events [S17] |
| `raw_sql` | `connection.cursor().execute("DELETE …")`, `session.execute(text(...))`, `_raw_delete` | none visible | none [S11] |

Every synthetic edge below declares the modes it is admissible in. A path is a sequence of edges each admissible in the mode current at that point.

### 4.2 Synthetic edges

| ID | Edge | Condition | Modes | Rule |
|---|---|---|---|---|
| SE1 | `rows:Parent → rows:Child` | Django FK on Child with `on_delete=CASCADE` | `model_delete`, `queryset_delete` | R1 |
| SE2 | `rows:M → receiver_fn` | `pre_delete`/`post_delete` receiver whose `sender` is `M`, or no sender at all | `model_delete`, `queryset_delete` | R8a, R9, R15 |
| SE3 | `rows:M → files:M.<field>` | django-cleanup active for `M` (§4.4) | `model_delete`, `queryset_delete` | R8b, R10 |
| SE4 | `rows:Parent → rows:Child` | Django FK with `on_delete=DB_CASCADE`; the mode switches to `db_cascade` on traversal | `model_delete`, `queryset_delete` | R4 |
| SE5 | `rows:Parent → rows:Child` | SQLAlchemy `relationship(cascade=…)` whose token set contains `delete` or `all` | `session_delete` | R5 |
| SE6 | `rows:Parent → rows:Assoc` | `relationship(secondary=assoc)` | `session_delete` only | R7 |
| SE7 | `rows:Parent → rows:Child` | `ForeignKey(..., ondelete="CASCADE")` **and** enforcing-engine evidence (§4.5) | all modes incl. `bulk_dml` | R6, R17 |
| SE8 | `rows:M → M.delete` | the model overrides `delete()` | `model_delete` only | R14 |
| SE9 | `rows:M → listener_fn` | `before_delete`/`after_delete` mapper listener for `M` | `session_delete` only | R18 |
| SE10 | `entry:admin_delete_model → M.delete`, `entry:admin_delete_selected → rows:M` | model registered in the admin | admissible in `none`; `sets_mode: model_delete` / `queryset_delete` [S9] [S8] | R16 |
| SE11 | `caller → task_fn` | `.delay`/`.apply_async`/`send_task` resolving through the task table | admissible in every mode incl. `none`; sets none | CG-16 |
| SE12 | `fn → store:<id>` | a rule-set deletion primitive for that store called in `fn`, attributed by §3.10 for keyed stores | admissible in every mode incl. `none`; `sets_mode:` the primitive's own mode from `primitives.yaml` (`model_delete`, `queryset_delete`, `session_delete`, `bulk_dml`, `raw_sql`), or none for a non-relational primitive | R13, R20, R21, R24 |

**The mode a walk starts in.** `mode_of(entry) = none` for every entry point except the two admin ones, which SE10 sets. In mode `none` only four things are admissible: ordinary call edges (resolved and ambiguous), SE10, SE11 and SE12 — SE12 sets the mode from the primitive it names, which is how a walk that starts at an ordinary route ever acquires one. (The SE12 row above and `verifier-rules-draft.yaml` `path_modes.admissible_in_none` already say four; the sentence said three, and the sentence is what an implementer codes from: with SE12 inadmissible no store edge is reachable from a non-admin entry point, `path_exists` returns None for every store, and S01, S04 and S06 all read `not_erased`.) SE1–SE9 all name a mode and stay inadmissible until a primitive edge has set one — which is exactly §4.1's sentence ("a path carries a mode, set at the delete call site") given an encoding in the search.

The alternative readings both break. A null mode that admits nothing makes every cascade in every repository read `not_erased`; a start mode of `model_delete` makes SE8 admissible on a queryset path, and R14's false safe returns:

```python
class Avatar(models.Model):
    user  = models.ForeignKey(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="a/")
    def delete(self, *a, **k):
        self.image.delete(save=False); return super().delete(*a, **k)

def close_account(request):
    Avatar.objects.filter(user=request.user).delete()   # the override is not called [S3]
```

`files:avatar.image` would read `erased` and the bytes would stay. Test 27 already expects `not_erased` there; `mode_of(entry) = none` plus `sets_mode` on SE12 is what makes the table agree with its own test.

Amended 2026-08-29: the table needs a thirteenth row, **SE0**, and the search does not work without it. `entry:<name> → the symbol the entry point names`, admissible in every mode, setting none. Without it only the two admin entry points had an out-edge (SE10), so a walk from `entry:close_account` sat on a start node with nowhere to go, `path_exists` returned `None` for every store in every non-admin repository, and S01, S04 and S06 all read `not_erased` however plainly the body deletes. The edge carries the search into the body; the mode is still set by the primitive it finds there. Implemented in `art30/verify/synthetic.py::_entry_edges`. (DEVIATIONS.md D-12)

### 4.3 The rules, operationalised

Each row: what it reads, what it decides, the verdict it produces, the evidence the artifact cites, and the false-safe (or false-alarm) shape it guards.

| Rule | Inputs | Decision | Verdict effect | Evidence cited | Guards against |
|---|---|---|---|---|---|
| **R1** [S1] [S4] | Django FK, `on_delete` token | `CASCADE` → SE1 | child rows `erased` when parent is | `models.py:<fk line>` `on_delete=CASCADE` | claiming a child table is orphaned when Django deletes it |
| **R2** [S1] | `on_delete` ∈ {`SET_NULL`, `DB_SET_NULL`, `SET_DEFAULT`, `DB_SET_DEFAULT`, `SET`, `DO_NOTHING`} | no edge | child `not_erased` unless another path reaches it | the FK line, with the token | "it cascades" — the row survives with every column intact |
| **R3a** [S1] | `on_delete=PROTECT`; the child delete's filter predicate | no edge; then look for a delete primitive for the child *earlier on the same path* than the parent delete, **and read its predicate** (§4.8) | subject-scoped predicate → child `erased`; any additional predicate → child `unverified` **and** every store downstream of the parent delete `unverified`, note "the parent delete may raise `ProtectedError`"; no child delete at all → `not_erased`, note "deleting the parent raises `ProtectedError` while children exist" | both call lines, in order, plus the predicate | reading `PROTECT` as unreachable and losing recall on the repositories that do delete properly (§4.4(c) of the research) — and its mirror, crediting a filtered child delete that leaves rows behind and makes the parent delete raise |
| **R3b** [S1] | `on_delete=RESTRICT` | as R3a, except when the child also has a `CASCADE` relation to another object deleted in the same operation | that shape → `unverified` | the FK line | asserting either way on a documented exception the AST cannot settle |
| **R4** [S1] [S3] | `on_delete=DB_CASCADE` | SE4, mode switches to `db_cascade`; SE2 and SE3 are inadmissible in that mode | rows `erased`; any file store whose only evidence is a signal receiver or django-cleanup → `not_erased` | the FK line plus the receiver line that will not fire | the new Django 6.1 false safe: rows go, signals never fire, files stay (research §4.4(b)) |
| **R5** [S15] [S18] | `relationship(cascade="…")` | split on `,`, strip, exact token match for `delete` or `all` | token present → SE5; absent → child `not_erased` (FK set to NULL) | the `relationship(...)` line with the token list | `"delete" in cascade` returning true for `delete-orphan`, which deletes nothing and only warns (research §4.3) |
| **R6** [S15] [S19] [S46] | `ForeignKey(ondelete=…)`, `passive_deletes`, engine URL, connect listeners | `ondelete="CASCADE"` + enforcing evidence → SE7; no evidence → `unverified`; no evidence **and** `passive_deletes=True` → `not_erased` | as decided | the FK line, plus the engine URL or the `PRAGMA foreign_keys=ON` listener line | the worst transcript in the research: parent gone, child email still there, `PRAGMA foreign_keys = 0` |
| **R7** [S18] [S16] | `relationship(secondary=…)` | SE6, `session_delete` only | assoc rows `erased` on a `Session.delete()` path; on `bulk_dml` or a database cascade → `not_erased` unless the assoc FK carries `ondelete` under R6 | the `secondary=` line and the delete call | "many-to-many are deleted in all cases" read outside its scope; the association row is where consent and tag links live |
| **R8** [S1] [S2] [S5] | `FileField`/`ImageField` store, the row's reachability, receivers, django-cleanup | precondition for (a) and (b): the row carrying the field is reached by the erasure path **under any rule** — a cascade, a queryset delete, an ordinary `instance.delete()`, `session.delete`, a raw delete naming the table. Then `erased` if (a) a `pre_delete` or `post_delete` receiver with `sender` = that model deletes the file, or (b) django-cleanup active (R10). Branch (c), an explicit storage delete for that file on the path, is **independent of the row's fate**: the bytes are gone whether or not the row goes | as decided; otherwise `not_erased` | the receiver line, the `INSTALLED_APPS` line, or the storage-delete line | the bug the project exists to catch, and its subtler half: cleanup installed, row never deleted, file still on disk (research §4.4(a)). The earlier enumeration named only R1/R3a/R4/R14, which left `Avatar.objects.filter(user=u).delete()` failing the precondition while test 28 expects `erased` for that exact fixture |
| **R9** [S6] | receiver `sender=` keyword, and the receiver body when there is no `sender` | sender must equal the model owning the field; no `sender` → covers every model, **unless the body branches on `sender`, `type(instance)` or `isinstance`**, in which case the AST cannot say which models it covers | mismatch → no edge → file store `not_erased`; no-sender-with-a-guard → `unverified` for every model, no edge | the `@receiver(...)` line with the sender as written; the guarding `if` line where present | the S09 decoy, a file-deleting receiver wired to `Comment` — and the no-sender variant of it, where the decorator asserts coverage the body then takes back |
| **R10** [S13] | `INSTALLED_APPS` entries, `@cleanup.ignore`, `@cleanup.select` | active if `'django_cleanup'` **or** `'django_cleanup.apps.CleanupConfig'` is present; `'django_cleanup.apps.CleanupSelectedConfig'` inverts to opt-in (only `@cleanup.select` models); `@cleanup.ignore` removes a model in either mode | SE3 or nothing | the `settings.py` line | matching only the dotted string and calling a repository that does delete its files `not_erased` (the bare label works — `default = True`) |
| **R11** [S6] | receiver defined inside a function body, `weak=` keyword on `connect` | nested def or lambda + no `weak=False` → the receiver may be collected | `unverified`, never `erased` | the `connect` line and the enclosing function | a receiver that silently never fires, with no warning and no traceback (research §4.1) |
| **R12** [S6] | module of the receiver, `INSTALLED_APPS`, `AppConfig.ready()` imports | connected if it lives in an installed app's `models.py`/`apps.py`, or in a module imported (transitively) from either, or from `ready()` | not connected → no edge, store `not_erased`, note "receiver defined at X, module imported by nothing" | the receiver line and the absence | the static analogue of S10: a `signals.py` nothing imports reads exactly like working code. The converse is respected: a receiver at the bottom of `models.py` **is** connected (Django imports it), and calling that dead would be a false alarm |
| **R13** [S12] [S14] [S22] [S23] | object-store delete call, `VersionId` kwarg, the versioning search of §1.1 over the non-Python globs **and** the scanned Python sources as text | a declaration is one of the five literals with `status["']?\s*[:=]\s*["']?enabled` (case-insensitive) within five lines of it — which matches Terraform's `status = "Enabled"`, boto3's and CloudFormation's `"Status": "Enabled"` and YAML's `Status: Enabled` alike. No declaration found → `erased`; declaration found and no `VersionId` passed → `not_erased` | as decided; the standing note renders in both branches | the delete call line; the versioning declaration file:line where found | "we call `delete_object`, so it's gone" on a versioned bucket, where S3's own words are "even though it has not been erased". A fixed `"Status: Enabled"` in YAML spelling matched none of the three real spellings, so the qualifier never fired and the declaration was never counted |
| **R14** [S1] [S3] [S8] | an overridden `Model.delete()` doing cleanup | SE8, `model_delete` only | evidence on `model_delete` paths; ignored on `queryset_delete`, `db_cascade`, cascaded children | the override's line and the calling delete's line | a custom `delete()` that removes an S3 object, credited on a path that never calls it |
| **R15** [S3] | `QuerySet.delete()` | signals still fire | SE2 and SE3 stay admissible | the queryset delete line | losing the file cleanup that does happen on the bulk path |
| **R16** [S8] [S9] | admin registration | SE10, two entry points with different modes | verdicts may differ between them; both flagged `admin_only` | the `admin.py` registration line | pretending a repository has no deletion path when operators delete through the admin every week (AMBIGUITIES 15) |
| **R17** [S15] [S16] | `session.execute(delete(M))` | ORM cascades and events are inadmissible; only SE7 survives | children `not_erased` unless R6 evidence | the bulk statement line | crediting a configured ORM cascade on a path that bypasses the unit of work |
| **R18** [S17] | `before_delete`/`after_delete` listener | SE9, `session_delete` only | not evidence on `bulk_dml`, `raw_sql`, or database-cascaded rows | the `event.listen` / decorator line | an S3 cleanup listener credited on a bulk path where it is silent |
| **R19** [S11] [S16] | `connection.cursor()`, `text("DELETE …")`, `_raw_delete` | parse the statement for a table name only when it is a string literal | that table `erased`; everything downstream `unverified` | the SQL line | both directions: ignoring a real raw delete, and inventing cascades behind one |
| **R20** [S24] [S25] | redis `delete`/`unlink` vs `expire`/`setex`/`pexpire`/`ttl` | a delete reached from an entry point is erasure; a TTL is a retention timer | delete → `erased`; TTL only → `not_erased`, TTL rendered in the retention column with the note that an overwrite clears it and a re-`EXPIRE` extends it | the redis call line | scoring a repository with no deletion feature as erasing, because a `setex` at write time looked like a timer |
| **R21** [S26] [S27] | index `delete`, `delete_by_query` | must be on the path | on path → `erased`; else `not_erased` | the index call line | "the row is gone" while the search index still answers a query with the user's post |
| **R22** [S28] [S29] | any `stripe.*` call carrying personal data | never `erased`, even when `Customer.delete` is on the path | `external_manual` | the SDK call line, plus the standing note that deleted customers stay retrievable and invoices are excluded from redaction | a founder signing a record that says Stripe was erased |
| **R23** [S30] [S31] [S42] | `sentry_sdk.init(...)`, `set_user`, `set_context`, `send_default_pii`, `_experiments={"data_collection": …}` | `init` alone makes Sentry a recipient with `url`, `query_string`, request body and stack-frame locals; the flag or `set_user` adds headers, cookies, identity, IP; `_experiments` supersedes the flag | `external_manual` in every case | the `init` line and any `set_user` line | leaving the error tracker out of the record because a flag is absent — the same class of harm as a false erasure claim |
| **R24** [S32] [S33] [S34] [S47] | Mixpanel, Segment, SendGrid and the rest of `recipients.yaml`; for Segment, the `regulation_type` **string literal at the call site** | `external_manual` by default. The only upgrade to `erased` is a Segment `create_regulation` whose type literal is `SUPPRESS_WITH_DELETE` or `DELETE_ONLY` — the two the documentation calls "Segment & Destination" regulations, the ones that forward downstream [S47]. `DELETE_INTERNAL`, a variable, or an absent type → `external_manual`, note "clears Segment and leaves connected destinations untouched" [S47]. Mixpanel's `create_deletion` stays `external_manual`: the endpoint "Creates a task that specifies a list of users in a project to delete" [S32], which is a queued request and not a confirmation. SendGrid's `contacts.delete` likewise [S34] | as decided | the SDK call line; the deletion call and its type literal where present | "analytics is handled" — and the narrower version the old rule allowed, where matching `create_regulation` by call name alone rendered `erased` for the one call the YAML's own note says does not erase downstream. This is the only route by which a `third_party` store can read `erased`, so it is the one row where R22's and R23's protection does not apply |
| **R25** [S10] | assignment of a falsy/timestamp value to `is_active`, `deleted_at`, `is_deleted`, `deactivated_at`, `status` | soft delete is not erasure | `not_erased`; `erased_after_timer` only with a scheduled job whose path reaches a hard delete, timer parsed (§6.2) | the assignment line, and the purge job line where present | Django's own recommendation, which is why this pattern is everywhere (AMBIGUITIES 4) |
| **R26** [S35] | unresolved or multi-candidate call on the only path | never guess | `unverified`, counted as not reaching | the call line and the reason (`ambiguous receiver`, `getattr`) | guessing in either direction — the failure the tool exists to prevent (AMBIGUITIES 14) |
| **R27** [S35] | `decorator_list` | read as data; `@receiver`'s `sender=` is honoured; other decorators are not modelled | a primitive reachable only through an unmodelled decorator → `unverified` | the decorator line | inventing decorator semantics |
| **R28** [S35] | `lineno`, `end_lineno` | every verdict carries `file:line`; missing position information means no citation | no citation → `unverified` rather than a guessed line | — | a plausible-looking line number nobody can check |

### 4.4 django-cleanup detection, spelled out (R10)

```
active_mode(entries) =
  if "django_cleanup.apps.CleanupSelectedConfig" in entries: return SELECT
  if "django_cleanup" in entries or "django_cleanup.apps.CleanupConfig" in entries: return ALL
  return OFF

covers(model) =
  mode == ALL     and not decorated_with("cleanup.ignore", model)
  mode == SELECT  and     decorated_with("cleanup.select", model)
```

`ALL` from the bare label is not a convenience: `CleanupConfig` sets `default = True`, so the bare label resolves to it, and both spellings deleted the file in the transcripts [S13]. The asymmetry is what makes the rule safe in both directions — the bare label can never mean select mode.

**Which `INSTALLED_APPS`.** Split settings (`settings/base.py`, `settings/dev.py`, `settings/prod.py`) are the norm in the repositories this targets, and §1.1 always scans `settings/*.py`, so several modules declare the list. Reading their union would let a `django_cleanup` present only in the development module make SE3 admissible for the whole repository, and every `FileField` store on a reached row would read `erased` while production keeps the bytes. §8 names "which settings module runs in production" as a blind spot; this is its routing.

| Modules declaring `INSTALLED_APPS` | Entry set used |
|---|---|
| one | that one |
| several, agreeing about `django_cleanup` | the agreed value |
| several, disagreeing | **intersection** for anything that produces a reaching verdict, **union** for anything conservative. Where they disagree about `django_cleanup` specifically, the file store is `unverified`, with both settings lines cited |

The same split applies to any other `INSTALLED_APPS` fact a reaching verdict rests on.

### 4.5 Enforcing-foreign-key evidence (R6)

The `ondelete` string is DDL and nothing more [S19]. Enforcement is a property of the connection the delete runs on, not of the repository, so the evidence is bound to **the engine the session performing the delete is built from**: follow the variable from `create_engine(...)` through `sessionmaker(bind=…)` / `Session(engine)` / Flask-SQLAlchemy's `db` to the delete call site, by name (§11, finding 2's assignment table — no type inference). SE7 is added only when that engine has one of:

- a non-SQLite URL: `create_engine("postgresql…"/"mysql…"/"mariadb…"/"oracle…"/"mssql…")`, a `DATABASE_URL` default it reads, or, for Django, an `ENGINE` of `postgresql`/`mysql`/`oracle` in the settings module §4.4 selects;
- for SQLite, a connect listener registered **on that engine** emitting `PRAGMA foreign_keys=ON` — `@event.listens_for(Engine, "connect")` with that string in the body [S46], or `PRAGMA foreign_keys` in a migration or startup module that names it.

A repository-global string search would repeat the defect §4.4(a) of the research diagnosed for django-cleanup, one level down:

```python
analytics_engine = create_engine("postgresql://host/metrics")   # a second, unrelated engine
engine  = create_engine("sqlite:///app.db")                     # what the app actually uses
Session = sessionmaker(bind=engine)
```

Any `postgresql://` anywhere would bless SE7 for every `ondelete="CASCADE"` in the tree, and the runtime is the configuration the research calls the worst result in the document: parent gone, child row and its email present, `PRAGMA foreign_keys = 0`.

Where several engines exist and the binding cannot be resolved by name: `unverified`. Absent evidence on the bound engine: `unverified`, and `not_erased` when `passive_deletes=True` is also set, because the ORM has then been told not to emit the child `DELETE` and nothing else will.

Amended 2026-08-29: "a migration or startup module that names it" is narrowed to the engine's own import closure, and the PRAGMA must be a call argument rather than a string in the file. `engines.pragma_listener` accepts the evidence only when (1) the listener's module is the module that builds the engine or one it transitively imports (`_engine_modules`), (2) the listener is registered on `Engine` or on that engine's own variable, and (3) the literal appears at a call site inside the body. A `PRAGMA foreign_keys=ON` in a module nobody loads is a string in a file and SQLite's foreign keys stay off; a text scan over the source span accepted `# TODO: emit PRAGMA foreign_keys=ON here one day` above a body of `pass`. Both readings produced the exact false safe this section exists to stop. (DEVIATIONS.md D-14)

### 4.6 Cascade-token parsing (R5)

```
tokens = {t.strip() for t in cascade_string.split(",")}
is_delete_cascade = ("delete" in tokens) or ("all" in tokens)
```

Exact tokens. `delete-orphan` alone is not a delete cascade — SQLAlchemy warns and carries on, and the children keep their email addresses (research §4.3, [S15]).

### 4.7 Anonymised versus pseudonymised

Read the assignments performed on the store's personal-data fields on the erasure path.

| Right-hand side | Verdict contribution |
|---|---|
| a string/number literal, `None`, `""`, `"REDACTED"`, `"deleted"`, a constant from the module | `anonymised` candidate |
| `hashlib.*`, `hmac`, `sha256`, `md5`, `uuid4()`, `secrets.token_*`, `base64`, a mask (`"x" * n`, `email[:2] + "***"`), an f-string or `%`/`format` that interpolates `id`, `pk`, `email` or another surviving key | `pseudonymised` — reversible or still linked [S12] |
| a call the verifier cannot resolve (`anonymize_user(user)` whose body is dynamic) | `unverified` (R26) |

**Over which columns.** `anonymised` requires **every** column the verifier itself detected for that store — §3.1 class-body field declarations for relational stores, §3.3 written keys for a cache, the equivalent per kind — *union* every field the record claims for the store, minus the primary key, to be overwritten on the path, and no foreign key to a `subject_root` to survive. One untouched column, or a surviving `user_id`, makes it `pseudonymised`.

The column list is the verifier's own, never the record's, and it never consults §3.9. Reading "personal-data field" as the record's `stores[].fields[]` would let the model shrink the list until "every field" is satisfied: the code sets `user.email = ""` and leaves `full_name` and `phone` untouched, the record lists `email` alone, the verdict is `anonymised`, `reaches_erasure = true`, accepted — while the name and the phone number survive. That is the model's claim deciding the verifier's evidence in the safe direction, and it is the "basic pseudonymisation or partial masking" substitution AMBIGUITIES row 5 exists to catch. Taking the union with the record's fields closes the mirror hole, where the model names a column the detectors missed.

The cost is recall: a store with a `created_at` the erasure path does not touch reads `pseudonymised` rather than `anonymised`. Both are on the false side of `reaches_erasure`, so the tuple is wrong in the conservative direction, and that is the direction this project pays for (open risk 8). The EDPB found controllers substituting pseudonymisation for deletion; this is the row that catches it (`gdpr-sources.md` §3.2 [S11] [S12]).

### 4.8 Predicate reading at a child delete (R3a)

A child delete only stands in for a cascade when it deletes *the subject's* children and no fewer. The qualifying shapes, and nothing else:

```
Child.objects.filter(<fk to subject> = <subject var>).delete()
Child.objects.filter(<fk to subject>__in = <subject collection>).delete()
<subject var>.<related manager>.all().delete()
session.query(Child).filter(Child.<fk> == <subject var>.id).delete()
```

Any additional predicate disqualifies it:

```python
def close_account(u):
    Invoice.objects.filter(owner=u, status="draft").delete()   # drafts only
    u.delete()                                                 # raises ProtectedError
```

Paid invoices survive with their billing names, and because `PROTECT` still has children the parent delete raises, so the user row is not deleted either — nothing at all is erased, and the old rule rendered `erased` for the invoice store and, through the parent delete, for everything downstream of it. The research reproduced the raise (§4.4(c)); only the happy half became a rule.

So: qualifying predicate → the child is `erased` on that path and the parent delete stands. Any other predicate → the child is `unverified`, and every store whose only path runs through that parent delete is `unverified` too, with the note that the parent delete may raise `ProtectedError`.

---

## 5. `path_exists(graph, entry, target, must_pass_through=None)`

### 5.1 Signature and semantics

```python
def path_exists(graph, entry, target, must_pass_through=None) -> Path | None:
    """entry:  an entry-point node (or any symbol, for tests)
       target: a store node, a symbol, or a primitive id
       must_pass_through: a set of node ids; the path must contain at least one
       returns: the first shortest path under a fixed edge ordering, or None.
                Identical across runs for identical inputs.
    """
```

Not "the lexicographically smallest shortest path": the search carries one `seen` set over states, so it never enumerates the competing shortest paths a lexicographic minimum would be selected from — a node first reached from a later-expanded predecessor keeps that predecessor's path. Sorting the out-edges gives determinism, which is the property §5.2 actually needs.

Contract §Verifier contract carries this signature by pointing at this section (ADR 0004 P-15): the search needs the graph, and the target is a store node as often as it is a primitive. There is no `mode` parameter. The delete mode is carried in the search state (§5.2), set by `mode_of(entry)` at the start and by the mode-setting edges along the way, so no caller can hand the walk a mode the code did not establish. `01-architecture.md` §1.1 carries the same signature and the same sentence.

A `Path` is a list of steps, each `{from, to, kind, file, line, rule, ambiguous}`. `Path.ambiguous` is true when any step is; `Path.mode` is the delete mode at the target.

### 5.2 Search

Breadth-first over the state `(node, mode, passed)`, where `mode` is the current delete mode (§4.1) and `passed` is a boolean for `must_pass_through`. BFS rather than DFS so the first hit is a shortest path, which is the one the record cites.

```
targets  = must_pass_through or frozenset()      # None is the only value the GDPR rule set passes
start    = (entry, mode_of(entry), entry in targets)
frontier = deque([start + ([],)])
seen     = {start}
while frontier:
    node, mode, passed, path = frontier.popleft()
    if node == target and (not targets or passed):
        return path
    for edge in sorted(graph.out(node), key=(to, kind, file, line)):
        if mode not in edge.admissible_modes: continue
        nmode   = edge.sets_mode or mode
        npassed = passed or edge.to in targets
        state   = (edge.to, nmode, npassed)
        if state in seen: continue
        seen.add(state); frontier.append((edge.to, nmode, npassed, path + [edge]))
return None
```

`mode_of(entry)` is `none` for every entry point except the two admin ones (§4.2). `none` is a real mode in the state tuple and in `admissible_modes`, so the state space is `|V| × 7 × 2`. The mode table itself (`path_modes` in `verifier-rules-draft.yaml`) is not a rule file: it ships as a constant in `art30/verify/reach.py` beside this search, because it is the search's own state space and not data a rule set may vary.

**Cycles** are handled by the `seen` set over states, not nodes: recursion and mutual calls terminate, and a cycle can still be traversed once per mode. The state space is `|V| × |modes| × 2`, so at most fourteen times the node count.

**Determinism**: the out-edge iteration is sorted; ties among equal-length paths break on the sorted order, so the same repository always produces the same cited path.

**Ambiguity**: an ambiguous edge is traversable and marks the path. `reach.py` runs the search twice where it matters — once over resolved edges only, once over all edges. A target reached in the first run is evidence; a target reached only in the second is `unverified` (R26). This is the single mechanic that keeps a guessed edge from ever producing `erased`.

**`must_pass_through`** is a set of node ids. It is unused by the GDPR rule set and exists for the gated AI Act extension (NON-GOALS), where the question is whether a decision path passes a human-approval node: `path_exists(g, entry, deploy_action, must_pass_through={"approval:request_approval"})`. Specifying it now costs one boolean in the state tuple; retrofitting it later would mean rewriting the search.

### 5.3 Query budget

Per repository: one BFS per `(entry point, edge set)` pair, with the reachable set memoised, rather than one per `(entry, store)` pair. With ≤ 20 entry points and two edge sets that is ≤ 40 traversals, each O(V + E).

---

## 6. Verdict decision procedure per store

### 6.1 Precedence

Applied in order; the first row that fires decides. Ordering is itself the safety property: the conservative labels sit above the reaching ones wherever the evidence is weaker. Like `path_modes`, this table (`verdict_precedence` and `reaches_erasure_true` in `verifier-rules-draft.yaml`) ships as a constant in `art30/verify/reach.py` rather than under `verify/rules/`: a rule file that could reorder the precedence could put a reaching verdict above a conservative one.

| # | Condition | Verdict |
|---|---|---|
| 1 | store kind is `backup` | `governed_by_retention` if a schedule parses (§6.3), else `no_schedule_evidenced` |
| 2 | store kind is `third_party` | `erased` only for the one shape R24 admits — a Segment `create_regulation` with a `SUPPRESS_WITH_DELETE` or `DELETE_ONLY` type literal on a resolved path; otherwise `external_manual` (R22, R23, R24) |
| 3 | no entry point exists (discovered or declared) | `no_entry_point` |
| 4 | a hard-delete primitive for the store is on a resolved path, and no rule downgrades it (R4 file case, R6 without enforcement, R13 versioning) | `erased` |
| 5 | every personal-data field on the store is overwritten on a resolved path with constants or `None`, no surviving subject key (§4.7) | `anonymised` |
| 6 | a soft-delete marker is written on the path **and** a scheduled job reaches a hard delete for that store **and** a timer parses (§6.2) | `erased_after_timer` (with `timer_days`) |
| 7 | fields overwritten with hash, token, UUID, mask, or an id-bearing template (§4.7) | `pseudonymised` |
| 8 | the store is reachable only through an ambiguous edge, an unmodelled decorator, an opaque raw-SQL downstream, a weakly referenced receiver, or a `RESTRICT` exception shape (R3b, R11, R19, R26, R27), or its declaration sits in an unparsed file (R28) | `unverified` |
| 9 | anything else, including a primitive that exists but no path reaches | `not_erased` |

Row 4 before row 5 means a row that is both blanked and deleted reads `erased`. Row 6 before row 7 means a soft delete followed by a real purge is not demoted by an incidental hash. Row 8 before row 9 is the one that matters for the false-safe row: the tool says "I could not tell" rather than "not erased" whenever the reason is the tool's own blindness, and both count as not reaching (AMBIGUITIES 14).

Two caps sit above the table and are applied after it. A store whose only path starts at a `declared_unregistered` entry point (§2.5) is `unverified` whatever row fired. A store reached only through the parent delete of a disqualified two-step `PROTECT` idiom (§4.8) is `unverified` likewise. Both replace a reaching verdict with a conservative one and never the other way round.

Per-field overrides use the same table over the field's own assignments (contract §Record vocabulary: a field whose fate differs carries its own `erasure` block).

### 6.2 `erased_after_timer`

All five required, or the verdict falls back to row 9:

1. the erasure entry point writes a soft-delete marker on the store (R25);
2. a job entry point (kind `task` or `cli`) has a resolved path to a hard-delete primitive for that store;
3. **a registration citation for that job's schedule** — an entry in `beat_schedule` / `CELERYBEAT_SCHEDULE` naming it, a `crontab(...)` or `run_every=` argument on its own decorator, an `add_periodic_task` call, an RQ-scheduler `cron`/`schedule` call, or a cron file, systemd timer or Kubernetes `CronJob` naming the management command;
4. the schedule or the job's age filter yields an integer number of days (§6.3);
5. evidence for all four is citable as `file:line`.

Requirement 3 is the one the decorator does not supply. `@shared_task` makes a function kind `task` (§2.2) and an age filter is a filter, so without it nothing in the list asked whether anything ever runs the job:

```python
# jobs/purge.py
from celery import shared_task
@shared_task                      # not in beat_schedule, never .delay()ed, never imported
def purge_deleted_users():
    cutoff = timezone.now() - timedelta(days=30)
    User.objects.filter(deleted_at__lt=cutoff).delete()
```

That rendered `erased_after_timer`, `reaches_erasure = true`, and the rows survive for ever. It is the S10 shape — a deletion function that exists and nothing calls — moved one level up, and the verifier's own headline argument does not reach it unless the schedule is evidence in its own right. §6.3's `schedule_patterns` already lists the strings; §6.2 requires one of them and cites it.

Without a registration: `not_erased`, note "purge job defined at `jobs/purge.py:4`, nothing in the repository schedules it". Test 37 and its negative twin 37a pin both directions. This is the verdict most likely to be wrong on R02 and R05, so the negative is the one to watch.

A selection predicate on the marker field (`filter(deleted_at__lt=cutoff)`) is recorded as a further citation where present and strengthens the note; its absence does not block the verdict, because a job that deletes rows older than N days does delete them.

### 6.3 Timer parsing

| Pattern | Yields |
|---|---|
| `timedelta(days=N)`, `days=N`, `timedelta(hours=N)` | `N` days (hours rounded down, minimum 1, and the note keeps the original unit) |
| a module constant (`RETENTION_DAYS = 30`) referenced in the filter | `30`, cited at the constant's line |
| `settings.X` resolving to a module-level integer literal in the repository | that integer |
| Celery beat `crontab(...)`, `schedule(run_every=…)`, a cron string in a config file | the cadence, rendered as a criteria string where it is not a number of days |
| S3 lifecycle `Days`, `NoncurrentVersionExpiration.NoncurrentDays` | that integer |
| anything else (an env var, a computed value) | no number; a `criteria` string quoting the source line |

The tool never invents a number; absence renders `no_timer_evidenced` in the retention column (contract §Record vocabulary), and for a backup store, `no_schedule_evidenced` as the verdict.

### 6.4 Risk input for the gate

The rating is computed from **the accepted record's** verdicts — the document the human is about to approve — which is what the contract's checkpoint line describes. §7.3 accepts a conservative divergence by design, so a rating computed from the verifier's own set could read `low` while the record in front of the human says NOT ERASED for a contact field, and the gate would under-warn on exactly the divergence the spec is proud of allowing.

`reach.py` returns the same flags over its own verdicts, carried alongside as a cross-check: whether any store is `not_erased` / `pseudonymised` / `external_manual` / `no_entry_point` / `no_schedule_evidenced` / `unverified` with an `identifier` or `contact` field, and whether every reaching store reaches only after a timer. Where the two ratings differ, both are shown at the gate with the stores that differ named. The verifier computes the inputs; the harness decides the rating and writes the checkpoint line.

`no_entry_point` is in the contract's `high` list (ADR 0004 P-09), so a record whose every store is `no_entry_point` — S08 and R04, the two cases built to test whether the tool can say there is no way to delete a user — rates `high` and the gate says why. Before the amendment those two records matched neither the `high` list nor the `medium` clause and fell to `low`, which is the rating the screen would have shown above "You are approving a document you will sign".

---

## 7. Claim checking (`verify/check.py`)

Input: the submitted record (already schema-valid), the repo path, the rule sets, and `reach.py`'s output. Output: the feedback object of contract §"Feedback object", exactly those seven list keys — `schema_errors`, `rejected_claims`, `missing_stores`, `missing_entry_points`, `bad_citations`, `unverified`, `conservative_divergences` — plus `accepted`, `attempt`, `attempts_left`.

### 7.1 Acceptance

```
accepted = schema_errors == [] and rejected_claims == [] and missing_stores == [] and bad_citations == []
```

`unverified`, `missing_entry_points` and `conservative_divergences` are informational and never block. A repository with one `getattr` in it would otherwise be unable to produce an accepted record at all, and the arm would measure the verifier's blind spots rather than the model's work. `conservative_divergences` could not block by construction: the record being safer than the evidence is the direction this project asks for.

### 7.2 Citation re-read

`bad_citations` blocks acceptance (§7.1), so which objects are checked cannot be left to the implementer. `record.schema.json` puts positions on eight object types; here is what happens to each.

| Record object | Has `symbol` | Path must be | Symbol checked |
|---|---|---|---|
| `stores[].declared_at` | yes | a scanned file | yes |
| `stores[].subject_link` (nullable) | no | a scanned file | no |
| `stores[].fields[].file/line` | — (name is the symbol) | a scanned file | yes, against `name` |
| `stores[].erasure.evidence[]` | yes | a scanned file | yes |
| `stores[].fields[].erasure.evidence[]` | yes | a scanned file | yes |
| `entry_points[].file/line` | — (name is the symbol) | a scanned file | yes, against `name` |
| `retention[].file/line` | no | any path under the repo root | no |
| `data_subjects[].file/line` | no | any path under the repo root | no |
| `hints.observed_region_hints[]`, `hints.security_evidence[]` | yes | any path under the repo root | no |

Then, in order:

1. the path must exist under the repo root and resolve inside it (no `..` escape). For the first five rows it must also be one of the scanned files;
2. the line must exist (1-indexed);
3. where the row says the symbol is checked, the cited **logical** line must contain it after normalisation (contract §Record vocabulary and §Verifier contract): the cited physical line, or the statement whose span contains it, so a field declaration split across three lines or a call broken by a formatter is cited by its first line and still passes. Normalisation is both sides lowercased, non-alphanumerics collapsed to `_`, compared on token boundaries, singular and plural equal. `email` matches `email = models.EmailField()` and does not match `user_email_verified_at` on its own.

Two of the position-carrying objects have no `symbol` property at all, so rule 3 has nothing to compare and is skipped rather than guessed at. And the `hints` rows are let out of the scanned set on purpose: Art. 32(1)(a) evidence for TLS or encryption at rest normally cites a `docker-compose.yml`, an nginx config or a Dockerfile, none of which is Python, and turning honest evidence into a blocking citation error would cost the model an attempt for doing the right thing.

A failure is one `bad_citations` entry: `{file, line, symbol, problem, expected}` with the problem stated in the terms of the check ("line 14 does not contain 'email'", "file storage.py is not in the scanned set", "line 402 is beyond end of file (311 lines)") and `expected` saying what to do about it ("cite the line that carries the symbol"). Every item on the three blocking lists carries `expected`, and so do `missing_entry_points` and `unverified`; contract §Feedback object requires it. `conservative_divergences` is the one exception and carries `note` in its place, because a record safer than the evidence asks nothing of the model (§7.3; `10-instructions.md` §4.4a).

Citations are re-read from disk rather than trusted from the graph, because the check has to catch a plausible line number the model produced without looking. Reading the logical line means parsing the file once per citation batch and mapping physical lines to statement spans, which the call graph already builds.

### 7.3 Verdict consistency

Let `M` be the record's verdict for a store (or field) and `V` the verifier's. `reach()` is the CASES.md mapping to true/false.

| Case | Result | Why |
|---|---|---|
| `reach(M) = true`, `reach(V) = false` | `rejected_claims` | the false-safe direction, and the only one that gets a founder fined |
| `reach(M) = true`, `V = unverified` | `rejected_claims`, expected "verdict `unverified`, or cite the path" | an unverifiable safe claim is a safe claim without evidence |
| `M = erased`, `V = erased_after_timer` | `rejected_claims` | the record's retention column would say the data is gone today when it survives N days |
| `M = erased_after_timer`, `V = erased` | accepted; one `conservative_divergences` entry | conservative, and the timer is cited |
| `reach(M) = false`, `reach(V) = true` | accepted; one `conservative_divergences` entry naming the verifier's verdict and its evidence | the model may have seen what the rules do not model. **The verifier never upgrades a claim to safer than the model wrote**, and the divergence is recorded rather than dropped, so the trace shows where the record was safer than the code |
| `M` and `V` both false-side but different labels (`not_erased` vs `external_manual`) | accepted | the scored tuple is `reaches_erasure`; the fine-grained label is rendered, not scored (CASES.md) |
| `M` uses a verdict reserved for another kind — `governed_by_retention` or `no_schedule_evidenced` on a non-`backup` store, or any other verdict on a `backup` store | `rejected_claims`, expected the kind's allowed set | the contract says those two "are the only verdicts rendered for stores of kind `backup`". The kind also decides the render section and whether `recipient_kind` applies, so a wrong one is a defect in the signed document |
| the record's `kind` for a store differs from the verifier's detected kind | non-blocking `unverified` note naming both | the detectors can be wrong about kind; the document should still say the two disagreed |
| the store is in the record but not in the verifier's store set, `reach(M) = true` | `rejected_claims`, expected "verdict `unverified`, or cite the path" | same direction as row 2 and the same reason: a safe claim with no corroboration is a safe claim without evidence (Decision 11). Since `unverified` never blocks, the old row let `erased` through on any store the detectors miss — or whose name simply does not normalise to the verifier's id — with no evidence at all |
| the store is in the record but not in the verifier's store set, `reach(M) = false` | `unverified` entry; accepted | the model may see a store the detectors do not; a conservative verdict on it costs nothing |
| `M` claims a path and the cited evidence line is not on any path the verifier found | `rejected_claims` with the reason naming what was found instead | a citation that points at the right file and the wrong reason |

**File-store reconciliation.** §3.1 gives a Django file store the id `<model>.<field>` (`avatar.image`) and a record will naturally call it `uploads` or `avatars`; the two never normalise equal, so before the split above the S10, S04 and R03 file store landed in the uncorroborated row every time. The rule: a record store whose `declared_at` is the `FileField`/`ImageField` declaration line matches the verifier's `<model>.<field>` store for that line, whatever it is named. Name normalisation is tried first; this is the fallback, and it is keyed on a citation the model already has to get right.

Each `rejected_claims` entry is `{store, field, claim, reason, path, expected}` exactly as the contract shows, with the reason written as a sentence a person can act on: what was looked for, where the search started, what was found. The contract's own example is the template ("no path from entry point `close_account` (api/account.py:12) to any object-storage deletion primitive; `cleanup_user_files` (storage.py:41) is defined but has no callers"). `path` is the structured walk the verifier found, each element `{file, line, symbol}`, and it is `[]` when there is none — the S10 rejection above has none, which is the whole finding. The renderer and the video read `path`; the prose stays for the model.

### 7.4 Completeness guard

The guard fires for a store the verifier detected that is absent from the record after name normalisation **and** has either a strong §3.9 match, or a qualified §3.9 match together with a subject link. One `missing_stores` entry `{store, kind, evidence, expected}`, where the evidence is the `file:line` and a phrase naming what was seen there and `expected` says to add the store with its fields and an erasure verdict. Matching is on the normalised store name, with the contract's plural/singular equality and app-prefix stripping, so `app_users` in the record matches `users` in the scan; file stores also match by declaration line (§7.3).

It does not fire for a store the verifier found with no qualifying match: predicting `products` costs the model precision, and demanding it would cost the tool credibility.

**Measured fire rate, before the first advanced run** (open risk 4 asked for this number; the script is `guard.py`, §11):

```
$ python3 guard.py repos/full-stack-fastapi-template repos/flaskbb repos/pinry repos/microblog
== full-stack-fastapi-template    models:  0  guard fires WITHOUT any subject link: 0  (with link: 0, silent: 0)
== flaskbb                        models: 12  guard fires WITHOUT any subject link: 0  (with link: 3, silent: 9)
== pinry                          models:  4  guard fires WITHOUT any subject link: 0  (with link: 1, silent: 3)
== microblog                      models:  5  guard fires WITHOUT any subject link: 0  (with link: 5, silent: 0)
```

Zero unlinked fires across the four vendored repositories with the §3.9 list as it now stands, against two on FlaskBB with `name` strong. Two caveats the number carries: the script emulates the guard over Django models and `__tablename__` declaratives only, so R01's SQLModel `table=True` classes are outside it (0 models detected there is the emulation's limit, not a finding about the repository), and "with link" counts stores that fire *and* have a subject link, which is the guard working as intended.

### 7.5 Determinism

Every list in the feedback object is sorted: `rejected_claims` by `(store, field or "", claim)`, `unverified` by `(store, claim)` — the contract's `unverified` entry is `{store, claim, reason, expected}` and carries no `field` — `missing_stores` by `(store)`, `missing_entry_points` by `(file, line, name)`, `bad_citations` by `(file, line, symbol)`, `conservative_divergences` by `(store, claim)`, `schema_errors` by JSON pointer. A `rejected_claims` entry's `path` is the search's own output and is never re-sorted: its order is the walk. Sets are never iterated. Dict ordering is never relied on. File walking is sorted at every level. The same record and repository produce the same bytes, which is what makes the replay layer exact (ADR 0003 §6).

---

## 8. What the verifier cannot see

Listed so the artifact can say it, and so a judge reads the limits from us rather than finding them. Each maps to `unverified` or to a written assumption; none is silently guessed.

| Blind spot | Handling |
|---|---|
| Type inference. `storage.delete(name)` — which storage? | the primitive matches by name against the rule set. For `cache`, `object_storage`, `search_index` and `queue` the store is the one the primitive's **own literal** names (§3.10) — the key prefix, `Bucket=`, `index=` — never the client variable, because one handle serves several namespaces. Fully dynamic argument → `unverified` (R26); a literal naming another namespace → no edge |
| Dynamic dispatch, `getattr`, string imports, registries | `unverified` for the store the opaque call plausibly touches (§1.5), no effect elsewhere |
| Decorator semantics beyond `@receiver` and the rule-set framework decorators | `unverified` for primitives reachable only through them (R27) |
| Calls into installed packages: what a dependency does with the object you hand it | out of scope; only the rule-set SDK primitives are modelled |
| Non-Python code — a Node worker, a stored procedure, a Terraform-driven lifecycle rule | reported "unscanned" (NON-GOALS); the one exception is the R13 versioning string search, which the artifact labels as a string search |
| Runtime configuration: whether the bucket really has versioning | **Assumption**: where the repository declares nothing, the delete is scored as reaching (§3 of the research, narrowed); where it declares versioning, `not_erased` |
| Which settings module runs in production | §4.4: intersection of the declared `INSTALLED_APPS` for anything that reaches, union for anything conservative; disagreement about `django_cleanup` → the file store is `unverified` with both lines cited |
| Which engine a session is bound to, when the binding cannot be followed by name | §4.5: `unverified`, never the repository-wide engine string |
| Database-side triggers, rules and views | invisible; a row deleted by a trigger reads `not_erased` |
| Whether a scheduled job is actually scheduled in production (a crontab outside the repo, a paused beat schedule) | the schedule is evidence from code only; `erased_after_timer` cites the code, not the deployment |
| Data inside a `JSONField`, a pickle, a blob | flagged `opaque_container`; the semantic call belongs to the model, and the completeness guard does not fire on its keys |
| Multi-tenant or sharded topologies, replicas, read-only mirrors | one logical store per detection; replicas are not modelled |
| Whether a personal-data field really relates to a person | that is the model's job. The verifier's field-name list exists only for the completeness guard (§3.9) |
| Deleted-but-recoverable states (soft delete in a vendor, S3 delete markers, Stripe's retrievable customers) | R13, R22, R23 turn each into a verdict rather than an omission |

---

## 9. Complexity and performance

Bounds for the target size: ≤ 200 Python files, ≤ 150 non-test files for the real cases (`evals/CASES.md`).

| Stage | Cost | Note |
|---|---|---|
| Parse + walk | O(total AST nodes) | measured, §11's environment, two corpora — see below |
| Symbol table, imports, decorators | O(definitions + import statements) | single pass, folded into the walk |
| Call-site records | O(call sites) | ~1 record per `ast.Call`; the AST is dropped after extraction, so peak memory is the largest single file's tree |
| Edge construction | O(call sites × candidates) | candidates are usually 1; the pathological case is a short method name defined in many classes, bounded by an index lookup |
| Store detection | O(class bodies + call sites) | |
| Versioning string search | O(bytes of ≤ 200 matched non-Python files) | fixed-string, depth ≤ 4 |
| `path_exists` | O(V + E) per traversal, ≤ 40 traversals | state space `|V| × 7 modes × 2` (`none` is a mode) |
| Claim check | O(claims) re-reads, each one file read cached per file | |

The parse-and-walk figure is two measurements, both re-runnable today from the scripts §11 names. The eval corpus first — the four vendored repositories, the spec's skip list applied, first 200 files:

```
$ python3 perf_repos.py repos/flaskbb repos/pinry repos/microblog repos/full-stack-fastapi-template
python 3.9.6 | files 200 | lines 25,368 | nodes 92,987 | unparsed 5 | 0.13 s      (three runs, identical)
```

Then a stress corpus of the same size but four times the depth, because the eval repositories are smaller than the 200-file bound the budget is written for — the 200 largest files of the interpreter's own stdlib:

```
$ python3 perf2.py /Applications/Xcode.app/.../lib/python3.9
python 3.9.6 | 200 largest files | lines 336,950 | nodes 1,233,343 | 1.84 s       (1.84 / 1.92 / 1.89 s)
```

About 650k nodes per second on this machine, and 1.2M nodes is well past anything the eval will hand it. The five unparsed files in the first run are 3.12 syntax under a 3.9 interpreter (`type X = …`), which is R28's path and not a timing artifact; on the project's 3.12 they parse.

Budget: **under 5 s wall clock for a 200-file repository, under 1 s for a synthetic case**, single-threaded, no I/O beyond reading the files. The verifier runs inside the `submit_record` handler, and up to five attempts per run; anything slower would show up in the arm's wall-clock row for the wrong reason.

Memory: bounded by the call-site records, roughly one small dict per `ast.Call`. At the stress corpus's 1.2M nodes and the ~10% of them that are calls, that is tens of megabytes.

---

## 10. Test plan (`tests/verify/`)

Written before the first advanced run (matrix G-05). Fixtures are inline strings written to a `tmp_path` repo by a `mkrepo(files: dict)` helper, so each test is readable in one screen; the shared helpers live in `tests/verify/conftest.py`. Every test names the rule it pins.

Amended 2026-08-29: the plan's sixty-five tests became 339 under `tests/verify/`, plus a twelve-case acceptance test (`test_fixtures_reproduce.py`) that reproduces every store verdict and every field-level override in the manifests of S01–S10, D01 and D02 without the verifier reading a manifest at run time. **Two of the sixty-five do not pass and ship as `xfail(strict=True)`:** test 19 (`test_r09_receiver_without_sender`) and test 62 (`test_r09_no_sender_receiver_with_guard`). Both are R9 receivers with no `sender=`: `synthetic.add_edges` leaves `instance` unbound, so the body's `instance.image.delete()` is attributed to no store, no SE12 edge exists, and the verdict falls to `not_erased` where `erased` and `unverified` were asked for. Both failures land on the conservative side, which is the direction this project pays for; the strict marker means they turn red the day the graph layer learns to bind `instance`. The fix belongs in `art30/verify/synthetic.py`. The code spells both tests `test_r09_...`; row 62 of the table below spells its one `test_r9_no_sender_receiver_with_guard`, and the name in `tests/verify/test_verdicts.py` is the one that runs. (DEVIATIONS.md D-16)

| # | Test | Rule | Minimal fixture | Expected |
|---|---|---|---|---|
| 1 | `test_r01_cascade_is_an_edge` | R1 | `class Post(Model): user = FK(User, on_delete=models.CASCADE)` + a view calling `user.delete()` | `rows:post` → `erased`, evidence cites the FK line |
| 2 | `test_r02_set_null_is_not_an_edge` | R2 | same with `on_delete=models.SET_NULL` | `rows:post` → `not_erased` |
| 3 | `test_r03a_protect_two_step` | R3a | `Invoice.user = FK(..., PROTECT)`; view does `Invoice.objects.filter(user=u).delete()` then `u.delete()` | both `erased`, two citations in order |
| 4 | `test_r03a_protect_bare_parent_delete` | R3a | same without the first line | `rows:invoice` → `not_erased`, note names `ProtectedError` |
| 5 | `test_r03b_restrict_is_unverified` | R3b | `on_delete=models.RESTRICT` with a second `CASCADE` relation in the same delete | `unverified` |
| 6 | `test_r04_db_cascade_kills_cleanup` | R4, R8 | `on_delete=models.DB_CASCADE` on an `Avatar` with `ImageField`, django-cleanup installed | `rows:avatar` `erased`, `files:avatar.image` `not_erased` |
| 7 | `test_r05_delete_orphan_without_delete` | R5 | `relationship(cascade="save-update, merge, delete-orphan")` + `session.delete(user)` | children `not_erased` (the substring trap) |
| 8 | `test_r05_all_token` | R5 | `relationship(cascade="all, delete-orphan")` | children `erased` |
| 9 | `test_r06_passive_deletes_sqlite` | R6 | `ondelete="CASCADE"`, `passive_deletes=True`, `create_engine("sqlite://")` | children `not_erased` |
| 10 | `test_r06_ondelete_without_evidence` | R6 | `ondelete="CASCADE"`, no engine URL anywhere | `unverified` |
| 11 | `test_r06_ondelete_with_postgres` | R6 | same plus `create_engine("postgresql://…")` | children `erased` |
| 12 | `test_r06_sqlite_with_pragma_listener` | R6 | `sqlite://` plus `@event.listens_for(Engine,"connect")` emitting `PRAGMA foreign_keys=ON` | children `erased` |
| 13 | `test_r07_secondary_session_delete` | R7 | `relationship(secondary=user_tag)` + `session.delete(user)` | assoc `erased` |
| 14 | `test_r07_secondary_bulk_dml` | R7, R17 | same with `session.execute(delete(User)…)` | assoc `not_erased` |
| 15 | `test_r08_filefield_cascade_only` | R8 | `Avatar.image = ImageField`, FK `CASCADE`, no receiver, no cleanup | `files:avatar.image` `not_erased` |
| 16 | `test_r08_precondition_row_not_reached` | R8, R10 | cleanup installed, FK is `SET_NULL` | file store `not_erased` — the installed package is not the whole of the answer |
| 17 | `test_r08_pre_delete_receiver_counts` | R8a | `@receiver(pre_delete, sender=Avatar)` calling `instance.image.delete(save=False)` | `erased` |
| 18 | `test_r09_wrong_sender_decoy` | R9 | S09's shape: receiver's `sender=Comment`, file field on `Avatar` | file store `not_erased`; the reason names the sender |
| 19 | `test_r09_receiver_without_sender` | R9 | `@receiver(post_delete)` with no sender, deleting `instance.image` | covers every model with that field |
| 20 | `test_r10_bare_label_activates` | R10 | `INSTALLED_APPS = ["django_cleanup"]` | active; file store `erased` when the row is reached |
| 21 | `test_r10_selected_config_opt_in` | R10 | `CleanupSelectedConfig` and an undecorated model | inactive for that model → `not_erased` |
| 22 | `test_r11_receiver_inside_function` | R11 | receiver defined in a factory function, `connect()` without `weak=False` | `unverified` |
| 23 | `test_r12_signals_module_unimported` | R12 | `signals.py` with a valid receiver, imported by nothing, app not in `INSTALLED_APPS` | not connected → `not_erased` |
| 24 | `test_r12_receiver_in_models_is_connected` | R12 | receiver at the bottom of an installed app's `models.py` | connected → the file store can be `erased` |
| 25 | `test_r13_versioned_bucket` | R13 | `s3.delete_object(Bucket=…, Key=…)` plus `put_bucket_versioning(Status="Enabled")` in a bootstrap script | `not_erased`, both lines cited |
| 26 | `test_r13_no_versioning_declaration` | R13 | the delete alone | `erased`, standing note present |
| 27 | `test_r14_override_not_on_queryset_path` | R14 | `Model.delete()` override doing a storage delete; the view calls `.objects.filter(...).delete()` | file store `not_erased` |
| 28 | `test_r15_queryset_delete_fires_signals` | R15 | same view, but the cleanup is a `post_delete` receiver | file store `erased` |
| 29 | `test_r16_admin_two_paths` | R16 | model registered in the admin, override present, no other entry point | `admin_delete_model` reaches the override, `admin_delete_selected` does not; both flagged `admin_only` |
| 30 | `test_r19_raw_sql_downstream` | R19 | `cursor.execute("DELETE FROM users WHERE id=%s")` | `rows:users` `erased`; the child table `unverified` |
| 31 | `test_r20_setex_ttl_is_not_erasure` | R20 | `r.setex(f"session:{u.id}", 3600, u.email)` and no delete | cache store `not_erased`, TTL in the retention column |
| 32 | `test_r20_redis_delete_on_path` | R20 | `r.delete(f"session:{u.id}")` inside `close_account` | `erased` |
| 33 | `test_r21_search_index_distinct` | R21 | Elasticsearch index write, relational delete only | index `not_erased` |
| 34 | `test_r22_stripe_never_erased` | R22 | `stripe.Customer.delete(u.stripe_id)` on the path | `external_manual`, not `erased` |
| 35 | `test_r23_sentry_init_alone` | R23 | `sentry_sdk.init(dsn=…)` and nothing else | Sentry is a store of kind `third_party` with `url`, `query_string`, body and locals; verdict `external_manual` |
| 36 | `test_r25_is_active_false` | R25 | `user.is_active = False; user.save()` | `not_erased` |
| 37 | `test_r25_soft_delete_plus_purge` | R25, §6.2 | `deleted_at = now()` in the route, `jobs/purge.py` deleting rows older than `timedelta(days=30)`, named in `beat_schedule` | `erased_after_timer`, `timer_days = 30`, four citations incl. the schedule entry |
| 37a | `test_r25_purge_job_never_scheduled` | §6.2 req. 3 | same, with the `beat_schedule` entry removed — `@shared_task`, never `.delay()`ed, never imported | `not_erased`, note "nothing in the repository schedules it" |
| 38 | `test_s10_dead_helper` | R26, §2 | S10's shape: `cleanup_user_files()` defined in `storage.py`, called nowhere, docstring on `close_account` claiming files are removed | uploads `not_erased`; the reason says the helper has no callers |
| 39 | `test_pseudonymised_hashed_email` | §4.7 | `user.email = hashlib.sha256(user.email.encode()).hexdigest()` | `pseudonymised`, `reaches_erasure=false` |
| 40 | `test_anonymised_constant_overwrite` | §4.7 | every personal field set to `""`/`None`, no surviving FK | `anonymised` |
| 41 | `test_no_entry_point_repo` | §2.3 | five stores, no route, no command, no admin | every store `no_entry_point` |
| 42 | `test_completeness_guard_missing_cache` | §7.4 | record omits the Redis store that holds `email` | one `missing_stores` entry with `file:line` |
| 43 | `test_completeness_guard_ignores_negative` | §3.9 | a `Product` table with no subject link | no `missing_stores` entry |
| 44 | `test_citation_line_mismatch` | §7.2 | record cites `models.py:14` for `email`; line 14 holds `full_name` | one `bad_citations` entry |
| 45 | `test_conservative_claim_accepted` | §7.3 | verifier says `erased`, record says `not_erased` | accepted, no feedback entry |
| 46 | `test_false_safe_rejected` | §7.3 | verifier says `not_erased`, record says `erased` | one `rejected_claims` entry with the expected value |
| 47 | `test_cycle_terminates` | §5.2 | mutually recursive helpers between the entry point and the primitive | returns a path, no recursion error |
| 48 | `test_must_pass_through` | §5.2 | a path with and without the required node | `None` when the node is absent |
| 49 | `test_backup_no_schedule` | §6.1 | `pg_dump` task, no retention value anywhere | `no_schedule_evidenced` |
| 50 | `test_feedback_is_sorted_and_stable` | §7.5 | two runs over the same repo and record | byte-identical feedback objects, every list sorted |
| 51 | `test_unrelated_delete_route_is_not_an_entry_point` | §2.2 | the repository's only DELETE route is `@router.delete("/posts/{post_id}") def delete_post` | `no_entry_point` for every store; `rows:post` is not `erased` |
| 52 | `test_two_namespaces_one_client` | §3.10 | `r.setex("profile:…")` and `r.setex("session:…")` on one handle; `close_account` deletes the session key only | `cache:session` `erased`, `cache:profile` `not_erased` |
| 53 | `test_declared_entry_point_without_registration` | §2.5 | the S10 repository, record declares `cleanup_user_files` (`storage.py:29`, kind `unknown`) as an entry point | `uploads` is `unverified`, never `erased`; the entry point is flagged `declared_unregistered` |
| 54 | `test_r18_listener_not_evidence_on_bulk_dml` | R18 | `before_delete` mapper listener deleting an S3 object; the path is `session.execute(delete(User))` | file store `not_erased`; the same fixture with `session.delete(user)` gives `erased` |
| 55 | `test_r24_deletion_endpoint_upgrade` | R24 | `create_regulation(regulation_type="SUPPRESS_WITH_DELETE", …)` on the path | Segment store `erased` |
| 56 | `test_r24_delete_internal_is_not_erasure` | R24 | same with `regulation_type="DELETE_INTERNAL"`, and a third variant passing a variable | `external_manual` in both, note names the untouched destinations |
| 57 | `test_r27_unmodelled_decorator_unverified` | R27 | the storage delete sits behind `@my_retry` | file store `unverified` |
| 58 | `test_r28_missing_position_unverified` | R28 | a store declared in a file that raises `SyntaxError` | `unverified`, no citation invented |
| 59 | `test_getattr_narrowing_does_not_poison_other_stores` | §1.5, Decision 3 | `getattr(s3, meth)()` in the module holding the S3 client, plus an unrelated relational store | the object store is `unverified`, the relational store keeps its own verdict |
| 60 | `test_r13_versioning_declared_in_terraform` | R13 | `status = "Enabled"` in an `aws_s3_bucket_versioning` block, delete passes no `VersionId` | `not_erased`, the `.tf` line cited |
| 61 | `test_r3a_filtered_child_delete` | R3a, §4.8 | `Invoice.objects.filter(owner=u, status="draft").delete()` then `u.delete()` under `PROTECT` | invoices `unverified`, everything downstream of the parent delete `unverified`, note names `ProtectedError` |
| 62 | `test_r9_no_sender_receiver_with_guard` | R9 | `@receiver(post_delete)` whose body branches on `sender.__name__ == "Comment"` | `unverified` for every model, no edge |
| 63 | `test_anonymised_over_detected_columns` | §4.7 | the path sets `email = ""` and leaves `full_name` and `phone`; the record lists `email` alone | `pseudonymised`, and the record's `anonymised` claim is rejected |
| 64 | `test_split_settings_disagree_on_cleanup` | §4.4 | `settings/dev.py` installs `django_cleanup`, `settings/prod.py` does not | file store `unverified`, both settings lines cited |
| 65 | `test_engine_binding_not_repository_wide` | §4.5 | a second `create_engine("postgresql://…")` for metrics; the session is bound to `sqlite:///app.db` | children `unverified`, never `erased` |

Sixty-five tests is more than the fifteen the module count suggests, and the reason is in the eval design: a verifier bug that fabricates a path is a false safe the eval cannot tell apart from a model error (matrix G-05). Tests 6, 9, 18, 25, 27, 38, 39, 51, 53, 54 and 65 are the ones that would catch the specific false safes the research or the adversarial read reproduced. Every rule in §4.3 is now pinned by at least one test, and the two mechanisms that carry the safety argument outside the rule table — §2.5's declared-versus-discovered reconciliation and §1.5's narrowed dynamic dispatch — have tests 53 and 59.

---

## 11. Feasibility spike

**Throwaway.** The script below lives under the session scratchpad, not in the repository, and no line of it ships. It exists to answer one question before the four modules are written: can stdlib `ast`, a name-based call graph and two synthetic edges answer `path_exists` on the two idioms the eval is built from?

Two tiny repositories, written for the spike:

- `repo_dj/` — Django-shaped. `User`, `Avatar` with an `ImageField` and a `CASCADE` foreign key, `Comment` with a `CASCADE` foreign key, a `@receiver(post_delete, sender=Comment)` that deletes `instance.image` (the S09 decoy: right code, wrong sender), and `views.close_account` calling `user.delete()` under a docstring promising files are removed.
- `repo_sa/` — SQLAlchemy-shaped. `User` with `__tablename__`, `account.close_account` calling `session.delete(user)`, and `storage.cleanup_user_files` calling `s3.delete_object`, defined and called by nobody (the S10 shape).

149 lines of Python: module walk, class and function scan, a variable→model table built from `User.objects.get(...)` and `session.get(User, …)`, call records, name-based edges, R1 cascade edges, R9 receiver-by-sender edges, and a depth-first `path_exists` with a visited set.

```
$ python3 spike.py repo_dj repo_sa
== repo_dj ==  entry points: ['close_account']
   files:Avatar.image         object_storage  NOT_ERASED  declared models.py:12; no deletion primitive on any path
   rows:Avatar                relational      ERASED    views.py:close_account -> rows:User -> rows:Avatar  [views.py:7; on_delete=CASCADE models.py:11]
   rows:Comment               relational      ERASED    views.py:close_account -> rows:User -> rows:Comment  [views.py:7; on_delete=CASCADE models.py:16]
   rows:User                  relational      ERASED    views.py:close_account -> rows:User  [views.py:7]
== repo_sa ==  entry points: ['close_account']
   object_store:uploads       object_storage  NOT_ERASED  declared storage.py:7; primitive at ['storage.py:cleanup_user_files'] has no caller from an entry point
   rows:User                  relational      ERASED    account.py:close_account -> rows:User  [account.py:8]
```

Both hard cases come out right. The Django decoy renders `NOT_ERASED` for the image because the receiver's sender is `Comment` and the field belongs to `Avatar`; the SQLAlchemy repository renders `NOT_ERASED` for the bucket with the diagnosis the contract's feedback example asks for — the primitive exists, nothing calls it.

What the spike does not show: its `path_exists` is depth-first over a global visited set, not the BFS over `(node, mode, passed)` states §5.2 ships, and it has no delete modes, no resolved/ambiguous split and no entry-point qualification beyond a substring match on six vocabulary words. So its green result is evidence about `ast` and name-based edges, and evidence about nothing in §2.2, §2.5 or §4.1.

What it took: about forty minutes including the two fixtures, and three findings that changed this document.

1. The first version reported a store called `rows:Base` — the SQLAlchemy declarative base class, which is not a table. One line (`__tablename__` or a resolvable declarative base) removes it, and §3.1 now carries that filter as a rule rather than as an implementation detail.
2. Attributing a delete to a store needs a variable→model table (`user = User.objects.get(...)` then `user.delete()`), which is three lines of assignment tracking and no type inference. Without it, `.delete()` is just a method name and the graph says nothing. §1.5 CG-11 and §3 assume that table exists.
3. Printing the evidence as a path with a citation per step, rather than one line per finding, fell out of the graph for free and is what makes a rejection message actionable. That is the Privado borrow ([S12a]) landing in the design rather than in a footnote.

Environment note: the spike ran under the system interpreter (`Python 3.9.6`) rather than the project's 3.12, so it exercises no 3.12-only AST shape. The shipped modules target 3.12 (ADR 0003 §7).

**The three other throwaway scripts**, beside `spike.py` in the session scratchpad, each quoted where their output is used:

| Script | What it answers | Quoted in |
|---|---|---|
| `guard.py` | how often §3.9 + §7.4 fire on a store with no subject link, over the four vendored eval repositories | §3.9 and §7.4 |
| `perf_repos.py` | parse-and-walk time over the eval corpus, spec skip list applied | §9 |
| `perf2.py` | the same over a four-times-deeper stress corpus of the same file count | §9 |

The earlier §9 figure (299,074 nodes in 0.48 s on `_pytest` plus `pygments`) is withdrawn: no script produced it, and neither package imports under the interpreter the note named, so nobody could re-run it. A load-bearing "measured" without an artifact is what AGENTS.md's evidence discipline rules out. The replacement numbers came from the two scripts above and reproduce on this machine today.

---

## Decisions taken here

1. **Four modules, one direction of flow.** `callgraph.py` knows Python and no frameworks; `reach.py` holds every framework rule; `rules.py` is data loading; `check.py` holds the claim policy and imports no model client.
2. **Resolution outcomes are three-valued and asymmetric.** Resolved edges can produce `erased`; ambiguous edges can only produce `unverified`; unresolved calls produce no edge. `reach.py` runs the search twice (resolved edges only, then all edges) and the difference is exactly the `unverified` set.
3. **Dynamic dispatch is narrowed rather than global.** An opaque call downgrades only the store whose client or module it plausibly touches. Without this, one `getattr` would make a repository unverifiable and the tool would say nothing.
4. **Paths carry a delete mode.** `model_delete`, `queryset_delete`, `db_cascade`, `session_delete`, `bulk_dml`, `raw_sql`. Every synthetic edge declares the modes it is admissible in, which is how R14, R15, R17, R18 and R4 become mechanical instead of prose.
5. **Entry points are the union of discovered and validly cited declared ones**, admin registrations included and flagged `admin_only`. A declared entry point with a citation that does not resolve is a `bad_citations` entry and is dropped.
5a. **A declared entry point the verifier cannot see registered as externally invocable caps every verdict derived from it at `unverified`.** Adding a start node makes more stores read `erased`, which is the unsafe direction; the record may not supply the entry point §2.1 refuses.
6. **`cleanup`, `remove`, bare `delete` and bare `destroy` are not erasure vocabulary.** S10's `cleanup_user_files` must not be promoted to an entry point by its name.
6a. **The HTTP method is not the qualification.** A DELETE route is an erasure entry point only when its function name matches the vocabulary, the model it deletes is the `subject_root`, or its terminal path segment names the subject. Otherwise `delete_post` makes `rows:post` reach erasure in a repository with no account-closure path at all.
7. **A Django `FileField` is a second store**, id `<model>.<field>`, kind `object_storage`. The row and the bytes have different fates, and the record has to be able to say so.
8. **Test files, migrations and vendored virtualenvs are not scanned**; `settings.py` and `management/commands/` always are, because the answer depends on them.
9. **Acceptance is `schema_errors + rejected_claims + missing_stores + bad_citations` all empty.** `unverified` is informational and never blocks a submission.
10. **The verifier never upgrades a claim.** A model more conservative than the verifier is accepted and the difference is recorded in `conservative_divergences`; a model less conservative is rejected. The asymmetry is the whole safety argument, and it is why "the tool agreed" can never mean "the tool made it look better".
11. **An unverifiable reaching claim is a rejection, not an `unverified` note.** `reach(M)=true` with no corroborated path lands in `rejected_claims` with "verdict `unverified`, or cite the path".
12. **`erased` claimed where the verifier has `erased_after_timer` is rejected**; the reverse is accepted. The retention column is part of what the founder signs.
13. **The completeness guard uses a deliberately short field-name list**, and only fires on stores that the detectors already found, with the free-text names counting only on a store linked to a subject root.
14. **Citations are re-read from disk**, checked against the logical line — the statement whose span contains the cited physical line (contract §Record vocabulary) — with path traversal outside the repo treated as a bad citation.
15. **`must_pass_through` is specified now and unused now.** One boolean in the search state buys the AI Act extension later; retrofitting would mean rewriting the search.
16. **S3 versioning is a bounded regex search over the non-Python globs and over the scanned Python sources as text**, reported as a string search, with the narrowed assumption from the research: no declaration found means the delete is scored as reaching. The qualifier is `status["']?\s*[:=]\s*["']?enabled`, case-insensitive, because Terraform, boto3 and YAML each spell it differently.
17. **Verdict precedence is fixed and ordered conservative-first** (§6.1), so two rules never race for the same store non-deterministically.
18. **Every output is sorted**; the feedback object is byte-stable across runs, which the replay layer depends on.
19. **A walk starts in mode `none`**, in which only ordinary call edges, SE10 and SE11 are admissible. SE12 and the admin edges set the mode from the primitive they name; every mode-bearing synthetic edge stays inadmissible until one does. This is what stops SE8 crediting a `Model.delete()` override on a queryset path.
20. **`erased_after_timer` requires a schedule registration, cited.** A `@shared_task` decorator says a function can be a job, not that anything runs it. Without a `beat_schedule` entry, a `crontab`/`run_every` argument, `add_periodic_task`, an RQ-scheduler call or a cron file naming the command: `not_erased`.
21. **A keyed primitive is attributed by its own literal, not by its client handle** (§3.10). One Redis handle, one boto3 client or one Elasticsearch client serves several namespaces; deleting one must not mark its siblings erased.
22. **`anonymised` is decided over the verifier's detected columns union the record's claimed fields, minus the primary key** — never over the record alone. Otherwise the model shrinks the field list until "every field is overwritten" is true while the name and the phone number survive.
23. **A reaching claim on a store the verifier does not hold is a rejection**, matching Decision 11, not an `unverified` note. File stores reconcile by declaration line, because `avatar.image` and `uploads` never normalise equal.
24. **`name` is a qualified field name, not a strong one** (§3.9), on measurement: with it strong the guard fires twice on FlaskBB with no subject link, on `Group` and `PluginRegistry`, and blocks acceptance for R02.
25. **The gate's risk rating is computed from the accepted record**, with the verifier's own rating carried alongside and both shown when they differ. Rating the verifier's set would under-warn on exactly the conservative divergence §7.3 accepts.
26a. **A conservative divergence and a discovered-but-undeclared entry point are recorded, not swallowed.** `conservative_divergences` and `missing_entry_points` are non-blocking lists on the feedback object (contract §Feedback object), so both reach the trace instead of living only inside `reach.py`.
26b. **Every feedback item carries `expected` except a conservative divergence**, which carries `note` instead: the entry records something, it does not ask for anything. A rejected claim carries the structured `path` beside its prose reason, `[]` where the search found none.
26. **R24 upgrades a third-party store to `erased` in one shape only** — a Segment regulation whose type literal forwards downstream. `DELETE_INTERNAL`, a variable, Mixpanel's queued task and SendGrid's contact delete all stay `external_manual`.

## Open risks

1. **Rule surface versus twelve hours.** Twenty-eight rules, twelve synthetic edge types and six delete modes is a lot of behaviour for one Saturday. Mitigation: R1, R5, R8, R9, R13, R25, R26 and the `path_exists` core carry S01–S10; the rest degrade to `unverified`, which is the safe direction. Kill switch 1 in ADR 0002 (narrow to "primitive reachable within the erasure module") stays available and would cost recall on R02 and R03, not correctness.
2. **`unverified` inflation on real repositories.** FlaskBB and the Django styleguide example use idioms the rules do not model. If the advanced arm renders most stores `unverified`, it cannot separate from the baseline on F1 — ADR 0002 names this as the condition that reopens the decision. First measurement is R01 and R02 on Saturday.
3. **The delete-mode model can be wrong in the recall direction.** A repository that calls `Model.delete()` through a helper the graph resolves by short name (CG-3) inherits that mode correctly; one that dispatches through a manager method the graph cannot resolve loses the mode and lands on `unverified`.
4. **The completeness guard is a precision risk for the model.** Every `missing_stores` entry costs a submit attempt. Measured before any run (§7.4): zero unlinked fires across the four vendored repositories with `name` qualified, against two on FlaskBB with it strong. The measurement covers Django models and `__tablename__` declaratives only, so R01's SQLModel classes are untested and the first dev run still reports the fire rate per case. Tests 42 and 43 pin both directions.
5. **Citation strictness versus real formatting.** A field defined across three lines, or a call chain broken by a formatter, produces citations that name the statement's first line while the symbol sits on the third. The logical-line rule (contract §Record vocabulary, ADR 0004) covers that shape; what it does not cover is a symbol that appears nowhere in its own statement — a field built by a loop, a column named by a variable — and those still land in `bad_citations` on the real repos.
6. **Timer parsing is shallow.** An env-var retention period, a value computed from a plan tier, or a schedule living in Kubernetes will yield no number, so a repository that does erase on a timer can read `not_erased`. The `criteria` string keeps it honest but costs a tuple.
7. **The spike is not the verifier.** 149 lines answered the two shapes it was written for, with a DFS path search, no delete modes and no entry-point qualification — so it is evidence about `ast` and name-based edges and about nothing in §2.2, §2.5 or §4.1. The modules have to hold twenty-eight rules, seven modes and a claim checker, and nothing in the spike proves that stays inside the 300-line-per-file rule.
8. **The conservative fixes cost recall, and the cost lands on the primary metric.** `anonymised` over every detected column (§4.7), a schedule registration for `erased_after_timer` (§6.2), a bound engine for SE7 (§4.5), a subject qualification on DELETE routes (§2.2): each turns a case of "probably reaching" into `pseudonymised`, `not_erased` or `unverified`. Every one of those is a wrong tuple when the manifest says the store does reach erasure, and F1 pays. The trade is deliberate — false safes are the must-be-zero row (CASES.md) and each fix closed a reproducible one — but if the advanced arm's recall on R01 and R02 collapses, §6.2 requirement 3 and §4.7's column rule are the first two to re-examine, with a changelog row each.
9. **Six of the fixes are unexercised by any fixture yet.** Tests 51–65 are written against shapes the eval repositories may not contain, so they pin the rules without proving the rules matter. The first real-repo run says which of them ever fires.

## Proposed contract changes

All accepted by ADR 0004 on 2026-08-28; the contract now carries them.
