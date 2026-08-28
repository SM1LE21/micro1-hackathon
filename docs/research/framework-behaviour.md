# Framework behaviour behind the verifier's rule sets

What the verifier is allowed to assert, and the documented behaviour each assertion rests on. Source excerpts with full quotes live in `docs/research/sources/frameworks/`; source IDs are shared across all five files and repeated in the table at the bottom.

Versions studied, all checked 2026-08-28: Django **6.1** (current stable [S44]), SQLAlchemy **2.0.52** [S45], SQLModel **0.0.39**, Flask-SQLAlchemy **3.1.1**, django-cleanup **9.0.0**, django-storages **1.14.6**, sentry-sdk **2.68.1**, boto3 **1.43.82**, Python **3.12**.

---

## 1. Django: rows cascade, files stay

The row half is simple and the documentation says so plainly: `on_delete=CASCADE` deletes the related object, Django emulating `ON DELETE CASCADE` in Python, and `pre_delete` / `post_delete` fire for every object deleted that way [S1]. That is the basis for treating a cascade edge as a propagation path (AMBIGUITIES row 13).

The file half is the bug this project exists to catch. `FieldFile.delete()` exists and removes the file; nothing calls it when the instance is deleted:

> Note that when a model is deleted, related files are not deleted. If you need to cleanup orphaned files, you'll need to handle it yourself [S1]

This has been true since 2011 and was a deliberate change, not a gap. The 1.3 release notes give the reason: automatic deletion "opened the door to several data-loss scenarios, including rolled-back transactions and fields on different models referencing the same file" [S2]. Fifteen years later it is still the default, and it is still the thing a hand-written record of processing gets wrong.

So a `FileField` on a model whose row is deleted is erased only if something else does the work: a `pre_delete` or `post_delete` receiver registered for that model, django-cleanup in `INSTALLED_APPS`, or an explicit storage delete on the erasure path. Everything else leaves the bytes. Note the condition at the front of that sentence. All three mechanisms hang off the row being deleted, so none of them is evidence for a `FileField` on a model the erasure path never reaches — a point the first draft of rule R8 missed, and section 4.4(a) reproduces.

### Django 6.1 changes the picture

New in 6.1 is a second family of `on_delete` values that push the work into the database: `DB_CASCADE`, `DB_SET_NULL`, `DB_SET_DEFAULT`. The documentation is explicit about the cost:

> The database variants are more efficient because they avoid fetching related objects, but `pre_delete` and `post_delete` signals won't be sent when `DB_CASCADE` is used. [S1]

A repository that adopts `DB_CASCADE` for performance silently disables every signal-based file cleanup on the cascaded models, django-cleanup included. The rows go, the files stay, and the code that used to delete them still looks correct. This is a new false-safe shape and the verifier has to know the option names. Reproduced in section 4.4(b), django-cleanup installed and all: `Avatar rows after DB_CASCADE: 0`, the `Avatar` sender absent from the signal list, `file exists after delete: True`.

### Which delete was called

`Model.delete()` [S7] and `QuerySet.delete()` are not interchangeable. The bulk method

> does a bulk delete and does not call any `delete()` methods on your models. It does, however, emit the `pre_delete` and `post_delete` signals for all deleted objects (including cascaded deletions). [S3]

A model with an overridden `delete()` that removes an S3 object is therefore erased when a view calls `user.delete()` and not erased when anything calls `.delete()` on a queryset, when the object is reached by cascade [S1], or when the admin's "delete selected" action runs, since that action "uses `QuerySet.delete()` for efficiency reasons, which has an important caveat: your model's `delete()` method will not be called" [S8]. The single-object admin path is the other way round: `delete_model` calls `super().delete_model()` "to delete the object using `Model.delete()`" [S9]. Both are real entry points under AMBIGUITIES row 15, and they behave differently.

Below that sits the fast path. Django skips loading objects entirely when related fields use `DB_*` options or when "there are no cascades and no delete signal receivers" [S3]. The second condition is self-fulfilling for our purposes: if there are no delete receivers, there was no signal-based cleanup to lose.

Underneath everything, `connection.cursor()` exists and Django advertises it as "routing around the model layer entirely" [S11]. `QuerySet._raw_delete` is private and undocumented; the verifier treats both as an opaque edge.

### Signals are easy to mis-wire

`post_delete` carries `sender`, `instance`, `using` and `origin`, the last naming "the `Model` or `QuerySet` instance from which the deletion originated" [S5]. Three failure modes around it, all documented, all worth a rule:

1. `sender=` restricts a receiver to one model. `@receiver(pre_save, sender=MyModel)` means "The `my_handler` function will only be called when an instance of `MyModel` is saved" [S6]. A receiver with no `sender` runs for every model; a receiver with the wrong `sender` runs for the wrong one and looks identical in a grep. Eval case S09 plants exactly this.
2. Weak references. "Django stores signal receivers as weak references by default. Thus, if your receiver is a local function, it may be garbage collected." [S6] A receiver defined inside a factory function and connected without `weak=False` can vanish between registration and the first delete.
3. Registration requires import — by something. Receivers are conventionally "connected in the `ready()` method of your application configuration class", and if you use the decorator you "import the `signals` submodule inside `ready()`" [S6]. A `signals.py` that nothing imports is dead code that reads like working code. The converse trap is bigger: Django imports every installed app's `models` module itself, so a receiver at the bottom of `models.py` is connected with no import anywhere in the repository (section 4.4(a)). The same guide advises against that placement [S6], which is a style preference and not a claim that it fails.

Point 2 is not theoretical. It bit this research: see section 4.1.

### django-cleanup

The package "automatically deletes files for `FileField`, `ImageField` and subclasses […] When a model that has a `FileField` is deleted, the file is also deleted" [S13], by connecting `post_init`, `pre_save`, `post_save` and `post_delete` handlers for every `INSTALLED_APPS` model that has a `FileField` [S13]. Detection is cheap but not a single string: `CleanupConfig` sets `default = True`, so the bare label `'django_cleanup'` resolves to it and behaves identically to the dotted `'django_cleanup.apps.CleanupConfig'` [S13], verified in section 4.4(a). Two modifiers change the answer: `CleanupSelectedConfig`, which must be written out in full, inverts the default to opt-in [S13], and `@cleanup.ignore` exempts a model [S13]. Because it hangs off `post_delete`, none of it fires for a row that is never deleted. MIT, 9.0.0, last released 2024-09-18 [S13].

### django-storages

`S3Storage.delete()` calls `self.bucket.Object(name).delete()` [S14], which satisfies Django's `Storage.delete()` contract [S12] and issues an S3 `DeleteObject`. That call is the erasure primitive for an object store, with the caveat in section 3.

---

## 2. SQLAlchemy: the cascade you didn't configure

The default `relationship.cascade` is `save-update, merge` [S15], which contains no `delete`. With the default, deleting a parent does not delete children:

> if our `User.addresses` relationship does *not* have `delete` cascade, SQLAlchemy's default behavior is to instead de-associate `address1` and `address2` from `user1` by setting their foreign key reference to `NULL` [S15]

The rows survive with every personal-data column intact and only the link removed. If the column is `NOT NULL` the flush raises instead [S18]. Either way the store is not erased, and the difference between a leak and an exception is one schema decision.

Many-to-many association rows look like the exception: those "**are** deleted in all cases" [S18]. Read the sentence in its frame. [S18] introduces the list it belongs to with "There are various important behaviors related to the `Session.delete()` operation" and "in general the rules are", so "all cases" means all cases of `Session.delete()`. Push the same parent through `session.execute(delete(User)...)` and the association row survives with whatever it carries; section 4.3 has the transcript. A `secondary` table is where user↔tag, user↔consent and user↔group links live, which are personal data about the subject, so the scope of that sentence is not a detail.

So the verifier cannot read `session.delete(user)` and stop. It has to read the `cascade=` string on each `relationship()` reaching the store in question — and read it as a token list, not as a substring. `delete-orphan` contains the letters of `delete` and is not a delete cascade: SQLAlchemy warns "The 'delete-orphan' cascade option requires 'delete'." and ships anyway, leaving the children in place (section 4.3). The correct decomposition is in the same source: "The `all` symbol is a synonym for `save-update, merge, refresh-expire, expunge, delete`" [S15].

### The invisible path

The other direction is worse for a naive reader. With `passive_deletes=True` on the relationship and `ondelete="CASCADE"` on the `ForeignKey`, unloaded children produce no `DELETE` statements at all [S15]; the database does the work, and "SQLAlchemy only emits DELETE for those rows that are already locally present in the `Session`" [S15]. There is no ORM call to find and no event to observe, and on an engine that enforces foreign keys the children are genuinely gone. A tool that only looks for delete calls reports a false negative here.

The evidence is a string in the schema: the `ondelete` argument, "If set, emit ON DELETE <value> when issuing DDL for this constraint" [S19]. That is the only place the behaviour is written down in the source, so the verifier must parse `ForeignKey(..., ondelete=...)` as a first-class edge.

It must also refuse to treat that string as sufficient. `ondelete` emits DDL and nothing else; the deletion happens only if the engine enforces the constraint, and "To use 'ON DELETE CASCADE', the underlying database engine must support `FOREIGN KEY` constraints and they must be enforcing" [S15]. SQLite does not enforce by default — "SQLite supports FOREIGN KEY syntax when emitting CREATE statements for tables, however by default these constraints have no effect on the operation of the table" [S46] — and SQLAlchemy does not turn it on for you; the documented remedy is a connect-time listener emitting `PRAGMA foreign_keys=ON` [S46]. Section 4.3 has the run: on a default `create_engine("sqlite://")`, `passive_deletes=True` plus `ondelete="CASCADE"` deletes the parent, leaves the child row with its email intact, and reports `PRAGMA foreign_keys = 0`. `passive_deletes=True` is what makes this the worst case rather than a curiosity: it is the instruction that stops the ORM emitting the DELETE, so when the engine also declines nothing at all deletes the row.

### Bulk DML

`session.execute(delete(Model))` is a different machine. ORM delete cascade "applies **only** to the use of the `Session.delete()` method" [S15], and the bulk features "bypass ORM unit of work automation" and "do not offer in-Python cascading of relationships" [S16]. Children survive unless the database-level `ON DELETE` handles them.

Mapper events do not help: `before_delete` and `after_delete` "only" apply to the session flush and do "not apply to the ORM DML operations" [S17]. A `before_delete` listener that deletes an avatar from S3 is silent on the bulk path and silent when the database cascades.

### SQLModel and Flask-SQLAlchemy

"SQLModel is based on Python type annotations, and powered by Pydantic and SQLAlchemy" [S20], and its `Session` is a subclass of `sqlalchemy.orm.Session` [S43]. Flask-SQLAlchemy's `db.session` is "a `sqlalchemy.orm.scoping.scoped_session` that creates instances of `Session`" [S21], that `Session` being a SQLAlchemy `Session` subclass [S21]. Neither needs its own rule set. The verifier needs their import names, nothing more. This covers eval cases R01 (SQLModel) and R02 (Flask-SQLAlchemy) without new logic.

---

## 3. Stores that are not the database

**S3.** A delete on a versioned bucket does not remove anything:

> If bucket versioning is enabled, the operation inserts a delete marker, which becomes the current version of the object. To permanently delete an object in a versioned bucket, you must include the object's `versionId` in the request. [S23]

The user guide is blunter: a GET after that returns 404 "even though it has not been erased" [S22]. Lifecycle rules do not save you either; `Expiration` adds a delete marker and only `NoncurrentVersionExpiration` removes bytes [S22].

Versioning is a deployment setting, but it is declared in the repository often enough to be worth looking for: a boto3 `put_bucket_versioning(..., Status="Enabled")` or `BucketVersioning(bucket).enable()` in a bootstrap script or management command, a Terraform `aws_s3_bucket_versioning` block with `status = "Enabled"`, a CloudFormation or CDK `VersioningConfiguration`, a MinIO or localstack init step in `docker-compose`. Where that sits in the same tree as a delete call that passes no `versionId`, the repository already says the bytes stay, and rendering `erased` would contradict its own evidence. R05 (Django-Styleguide-Example) is a boto3/S3 repo of exactly the shape where such a declaration would live.

**Assumption, narrowed: where no versioning declaration is found in the repository, an object-store delete on the erasure path is scored as reaching erasure.** Where one is found, the verdict is `not_erased`. The rendered artifact carries the standing note in both branches — a versioned bucket retains prior versions unless `versionId` is supplied. Scoring the undeclared case any other way would punish correct code for a fact the tool cannot see.

**Redis.** `DEL` "Removes the specified keys" [S24]. `EXPIRE` sets a timeout after which "the key will automatically be deleted" [S25]. That is a real hard delete performed by the store, which makes a TTL a retention timer for the Art. 30 record and not an erasure path: it fires on a clock, not on account closure, and nothing binds it to the deletion request. Two properties make the distinction load-bearing rather than pedantic. The timeout is cleared by any command that overwrites the value, and a repeated `EXPIRE` updates it [S25], so a session key refreshed on every request never expires. And a `setex` sits at write time, nowhere near the erasure entry point, so treating it as erasure would score a repository with no deletion feature at all as reaching erasure.

**Elasticsearch.** A search index is a separate store. `DELETE /{index}/_doc/{id}` removes "a JSON document from the specified index" [S26] and delete-by-query "Deletes documents that match the specified query" [S27]. Deleting the row does not touch the index. Eval case R04 exists because of this.

**Stripe.** `Customer.delete` "Permanently deletes a customer. It cannot be undone." [S28] and, four paragraphs later, "Unlike other objects, deleted customers can still be retrieved through the API in order to be able to track their history." [S28] Stripe's own deletion guidance points businesses at redaction rather than deletion, says Stripe "might retain data as legally required, after redaction", excludes transactions for 90 days, and excludes invoices entirely because they "can be subject to tax-integrity and record-retention requirements" [S29]. A `stripe.Customer.delete()` call is evidence of intent. It is not evidence of erasure, and the tool must never render it as such.

**Sentry.** One flag decides *which* fields go, not *whether* anything goes. `send_default_pii` — "If this flag is enabled, certain personally identifiable information (PII) is added by active integrations" [S30] — gates five categories on the data-collected page: HTTP headers, cookies, logged-in user identity, the user's IP address, and LLM inputs and responses [S31]. Its default in sentry-sdk 2.68.1 is `send_default_pii: Optional[bool] = None` [S42], falsy.

The same page lists what is not gated. "The full request URL of outgoing and incoming HTTP requests is always sent to Sentry", and the identical sentence for the query string; both add "Depending on your application, this could contain PII data" [S31]. For bodies, "JSON and form bodies are sent", limited by an option that "is set to `medium` by default" [S31]. For stack traces, "the names and values of local variables that were set when the errors occurred are sent at the same time", plus a snapshot of surrounding source [S31] — `include_local_variables` and `include_source_context` both default to `True` in `consts.py` at 2.68.1 [S42].

So `sentry_sdk.init(dsn=...)` with no flag, in a FastAPI app with a `PATCH /users/me` handler, ships the request URL, the JSON body carrying `email`, and the local `user` object's fields on the first unhandled 500. That is a recipient under Art. 30(1)(d) and under AMBIGUITIES row 7 reading B: personal data flows into the call. Leaving Sentry out of the record because a flag is absent is the same class of harm as a false erasure claim — a founder signs a document saying data does not go somewhere it goes. One more supersession to watch: `_experiments={"data_collection": {...}}` "opts into the feature" and, with fields omitted, "most categories are collected", taking precedence over `send_default_pii` [S42], so a repository can be a full PII recipient with the flag nowhere in sight. R01 vendors `sentry_sdk`; this rule decides that case.

**Mixpanel, Segment, SendGrid.** All three publish a user-deletion endpoint [S32] [S33] [S34] [S47]. Their existence is why the verdict for these stores is `external_manual` rather than `no_entry_point`: erasure is possible, it is just not happening in this codebase unless the endpoint is called on the path.

---

## 4. Evidence from execution

Seven scripts, run with uv against pinned versions. Each is reproduced here with the command that produced its transcript, so the evidence travels with the document instead of with a scratch directory a judge cannot open. Every transcript below was re-run on 2026-08-28 and reproduces byte-identically.

The first two confirm quoted behaviour, and one of them produced an accident worth keeping. The remaining five were written to attack the rule set in section 6, and eight rules changed because of what they printed. Four were false safes — R5, R6, R7 and R8(b) each rendered `erased` for a store whose personal data was still in the database or on disk when the script finished. Four were the opposite, R3, R8(a), R10 and R12 refusing a store that really was erased.

### 4.1 Django 6.1: cascade, files, django-cleanup

`demo_app/models.py`:

```python
from django.db import models


class Owner(models.Model):
    email = models.EmailField()


class Avatar(models.Model):
    owner = models.ForeignKey(Owner, on_delete=models.CASCADE)
    image = models.FileField(upload_to="avatars/")
```

`run.py`:

```python
import os, sys, tempfile, django
from django.conf import settings

USE_CLEANUP = "--cleanup" in sys.argv
MEDIA = tempfile.mkdtemp()
apps = ["django.contrib.contenttypes", "django.contrib.auth", "demo_app"]
if USE_CLEANUP:
    apps.append("django_cleanup.apps.CleanupConfig")
settings.configure(
    INSTALLED_APPS=apps, MEDIA_ROOT=MEDIA, USE_TZ=True,
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    DEFAULT_AUTO_FIELD="django.db.models.AutoField",
)
django.setup()
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db.models.signals import post_delete
from demo_app.models import Owner, Avatar

call_command("migrate", run_syncdb=True, verbosity=0)
seen = []


def strong_receiver(sender, instance, **kw):      # module-level: strongly referenced
    seen.append(sender.__name__)


post_delete.connect(strong_receiver)


def register_local():
    def local_receiver(sender, instance, **kw):   # local: only a weak ref is kept
        seen.append("LOCAL-" + sender.__name__)

    post_delete.connect(local_receiver)


register_local()

o = Owner.objects.create(email="a@example.test")
a = Avatar.objects.create(owner=o)
a.image.save("x.png", ContentFile(b"pixels"), save=True)
path = a.image.path
print("django", django.get_version(), "| cleanup:", USE_CLEANUP)
print("file exists before delete:", os.path.exists(path))
o.delete()                                        # cascade: the Avatar row goes too
print("Avatar rows after cascade:", Avatar.objects.count())
print("post_delete senders seen:", sorted(set(seen)))
print("file exists after cascade delete:", os.path.exists(path))
```

```
$ uv run --with django==6.1 --with django-cleanup==9.0.0 python run.py
django 6.1 | cleanup: False
file exists before delete: True
Avatar rows after cascade: 0
post_delete senders seen: ['Avatar', 'Owner']
file exists after cascade delete: True

$ uv run --with django==6.1 --with django-cleanup==9.0.0 python run.py --cleanup
django 6.1 | cleanup: True
file exists before delete: True
Avatar rows after cascade: 0
post_delete senders seen: ['Avatar', 'Owner']
file exists after cascade delete: False
```

Three readings. The cascade deleted the `Avatar` row and `post_delete` fired for both models, matching [S1]. The file survived the cascade, matching [S1] and [S2]. Adding `django_cleanup.apps.CleanupConfig` to `INSTALLED_APPS` deleted it, matching [S13]. Same code, same delete, opposite answer to "is this user's avatar erased".

The first version of this script used a lambda:

```python
post_delete.connect(lambda sender, instance, **kw: seen.append(sender.__name__))
```

It printed `post_delete senders seen: []`. The lambda had no other reference and was garbage collected before the delete, exactly as documented: "Django stores signal receivers as weak references by default. Thus, if your receiver is a local function, it may be garbage collected." [S6] Replacing it with a module-level function produced the output above. The second, function-local receiver in the final script never fired either, for the same reason. This is a silent failure with no warning and no traceback, and it is the shape of a production bug the verifier should refuse to call erased.

### 4.2 SQLAlchemy 2.0.52: default cascade and bulk delete

`sa_run.py`. `User.posts` is a plain `relationship()`, so the cascade is the default `save-update, merge`, and `Post.user_id` is nullable:

```python
import sqlalchemy as sa
from sqlalchemy import ForeignKey, delete, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session


class Base(DeclarativeBase): ...


class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    posts: Mapped[list["Post"]] = relationship()           # default cascade only


class Post(Base):
    __tablename__ = "post"
    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str]
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))


fired = []
event.listen(Post, "before_delete", lambda m, c, t: fired.append(("orm", t.id)))

e = sa.create_engine("sqlite://")
Base.metadata.create_all(e)
print("sqlalchemy", sa.__version__)

with Session(e) as s:                       # A: Session.delete, no delete cascade
    u = User(id=1, posts=[Post(id=1, body="ip 1.2.3.4"), Post(id=2, body="x")])
    s.add(u); s.commit()
    s.delete(u); s.commit()
    print("A rows left in post:", s.scalars(sa.select(Post.id)).all(),
          "| user_id values:", s.scalars(sa.select(Post.user_id)).all(),
          "| before_delete fired:", fired)

with Session(e) as s:                       # B: bulk ORM-enabled DELETE
    s.add(User(id=2, posts=[Post(id=3, body="y")])); s.commit()
    fired.clear()
    s.execute(delete(User).where(User.id == 2)); s.commit()
    print("B post rows:", s.scalars(sa.select(Post.id)).all(),
          "| user_id values:", s.scalars(sa.select(Post.user_id)).all(),
          "| before_delete fired:", fired)
```

```
$ uv run --with sqlalchemy==2.0.52 python sa_run.py
sqlalchemy 2.0.52
A rows left in post: [1, 2] | user_id values: [None, None] | before_delete fired: []
B post rows: [1, 2, 3] | user_id values: [None, None, 2] | before_delete fired: []
```

A: `session.delete(user)` left both `Post` rows in place with `user_id` set to `NULL`, matching [S15]. The rows still hold their body text. B: `session.execute(delete(User).where(...))` removed the parent and left `Post` 3 pointing at a `user_id` that no longer exists, with no ORM event fired, matching [S16] and [S17]. The dangling reference survived rather than raising because SQLite does not enforce foreign keys unless asked [S15]; on PostgreSQL the same code raises instead. Neither outcome erases the row.

### 4.3 SQLAlchemy 2.0.52: three attacks on the rule set

`attack_sa.py` runs the exact patterns rules R5, R6 and R7 were written to bless.

```python
import sqlalchemy as sa
from sqlalchemy import ForeignKey, Table, Column, delete
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

print("sqlalchemy", sa.__version__)

# ---------- ATTACK 2: ondelete="CASCADE" + passive_deletes=True on default SQLite
class B2(DeclarativeBase): ...
class U2(B2):
    __tablename__ = "u"
    id: Mapped[int] = mapped_column(primary_key=True)
    posts: Mapped[list["P2"]] = relationship(cascade="all, delete", passive_deletes=True)
class P2(B2):
    __tablename__ = "p"
    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str]
    user_id: Mapped[int | None] = mapped_column(ForeignKey("u.id", ondelete="CASCADE"))

e2 = sa.create_engine("sqlite://"); B2.metadata.create_all(e2)
with Session(e2) as s:
    s.add(U2(id=1, posts=[P2(id=1, body="email b@example.test")])); s.commit()
with Session(e2) as s:
    u = s.get(U2, 1)                       # children NOT loaded
    s.delete(u); s.commit()
    print("ATTACK2 ondelete=CASCADE + passive_deletes=True, default sqlite -> post rows:",
          s.scalars(sa.select(P2.id)).all(),
          "| bodies:", s.scalars(sa.select(P2.body)).all(),
          "| user rows:", s.scalars(sa.select(U2.id)).all())
    print("        PRAGMA foreign_keys =", s.execute(sa.text("PRAGMA foreign_keys")).scalar())

# ---------- ATTACK 3: many-to-many secondary + bulk ORM DELETE
class B3(DeclarativeBase): ...
assoc = Table("user_tag", B3.metadata,
              Column("user_id", ForeignKey("u.id"), primary_key=True),
              Column("tag_id", ForeignKey("t.id"), primary_key=True),
              Column("note", sa.String))       # the association row carries data
class U3(B3):
    __tablename__ = "u"
    id: Mapped[int] = mapped_column(primary_key=True)
    tags: Mapped[list["T3"]] = relationship(secondary=assoc)
class T3(B3):
    __tablename__ = "t"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]

e3 = sa.create_engine("sqlite://"); B3.metadata.create_all(e3)
with Session(e3) as s:
    t = T3(id=1, name="hiv-positive"); s.add(U3(id=1, tags=[t])); s.commit()
with Session(e3) as s:      # 3a: Session.delete -> the doc's "in all cases"
    s.delete(s.get(U3, 1)); s.commit()
    print("ATTACK3a Session.delete -> user_tag rows:", s.execute(sa.select(assoc)).all())
with Session(e3) as s:
    s.add(U3(id=2, tags=[s.get(T3, 1)])); s.commit()
with Session(e3) as s:      # 3b: bulk ORM DELETE
    s.execute(delete(U3).where(U3.id == 2)); s.commit()
    print("ATTACK3b bulk delete()  -> user_tag rows:", s.execute(sa.select(assoc)).all())

# ---------- ATTACK 4: the cascade-string substring trap
import warnings
class B4(DeclarativeBase): ...
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    class U4(B4):
        __tablename__ = "u"
        id: Mapped[int] = mapped_column(primary_key=True)
        posts: Mapped[list["P4"]] = relationship(cascade="save-update, merge, delete-orphan")
    class P4(B4):
        __tablename__ = "p"
        id: Mapped[int] = mapped_column(primary_key=True)
        body: Mapped[str]
        user_id: Mapped[int | None] = mapped_column(ForeignKey("u.id"))
    e4 = sa.create_engine("sqlite://"); B4.metadata.create_all(e4)
    with Session(e4) as s:
        s.add(U4(id=1, posts=[P4(id=1, body="email c@example.test")])); s.commit()
    with Session(e4) as s:
        s.delete(s.get(U4, 1)); s.commit()
        print("ATTACK4 cascade='save-update, merge, delete-orphan' -> post rows:",
              s.scalars(sa.select(P4.id)).all(), "| bodies:", s.scalars(sa.select(P4.body)).all())
    print("        warnings:", [str(x.message)[:110] for x in w][:3])
```

```
$ uv run --with sqlalchemy==2.0.52 python attack_sa.py
sqlalchemy 2.0.52
ATTACK2 ondelete=CASCADE + passive_deletes=True, default sqlite -> post rows: [1] | bodies: ['email b@example.test'] | user rows: []
        PRAGMA foreign_keys = 0
ATTACK3a Session.delete -> user_tag rows: []
ATTACK3b bulk delete()  -> user_tag rows: [(2, 1, None)]
ATTACK4 cascade='save-update, merge, delete-orphan' -> post rows: [1] | bodies: ['email c@example.test']
        warnings: ["The 'delete-orphan' cascade option requires 'delete'."]
```

Attack 2 is the worst result in this document. The parent row is gone, the child row and the email in it are still there, no ORM `DELETE` was emitted, no event fired, and `PRAGMA foreign_keys` reads `0` on the connection SQLAlchemy handed out. This is the configuration the SQLAlchemy documentation presents as the database-side cascade, run against the database FastAPI and SQLModel tutorials start with, and it erases nothing. The first version of R6 called this shape sufficient evidence of erasure on its own.

Attack 3 puts a boundary on [S18]'s "in all cases": true for `Session.delete()`, false for bulk DML, where the association row survives with its `note` column. Attack 4 is a one-character-class bug: a rule implemented as `"delete" in cascade_string` returns true for `delete-orphan`, SQLAlchemy emits a warning nobody reads, and the child rows keep their bodies.

### 4.4 Django 6.1: four attacks on the rule set

Four short scripts, one model module each. Full sources are inline; each was run against `django==6.1` (and `django-cleanup==9.0.0` where the transcript says so).

**(a) django-cleanup with no delete on the row, the bare app label, and a receiver in `models.py`.** `atk_app/models.py`:

```python
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver


class Owner(models.Model):
    email = models.EmailField()


class Avatar(models.Model):                       # FK is SET_NULL, not CASCADE
    owner = models.ForeignKey(Owner, null=True, on_delete=models.SET_NULL)
    image = models.FileField(upload_to="avatars/")


class Doc(models.Model):                          # unrelated model, receiver in models.py
    f = models.FileField(upload_to="docs/")


FIRED = []


@receiver(post_delete, sender=Doc)                # registered by importing models.py alone
def doc_gone(sender, instance, **kw):
    FIRED.append(sender.__name__)
```

`atk_django.py`:

```python
import os, sys, tempfile, django
from django.conf import settings

MODE = sys.argv[1] if len(sys.argv) > 1 else "none"
MEDIA = tempfile.mkdtemp()
apps = ["django.contrib.contenttypes", "django.contrib.auth", "atk_app"]
if MODE == "dotted":
    apps.append("django_cleanup.apps.CleanupConfig")
elif MODE == "bare":
    apps.append("django_cleanup")                 # bare label: does it still work?
settings.configure(INSTALLED_APPS=apps, MEDIA_ROOT=MEDIA, USE_TZ=True,
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    DEFAULT_AUTO_FIELD="django.db.models.AutoField")
django.setup()
from django.core.files.base import ContentFile
from django.core.management import call_command
from atk_app.models import Owner, Avatar, Doc, FIRED
call_command("migrate", run_syncdb=True, verbosity=0)

from django.apps import apps as app_registry
print("django", django.get_version(), "| INSTALLED_APPS entry:", MODE,
      "| cleanup app loaded:", app_registry.is_installed("django_cleanup"))

o = Owner.objects.create(email="a@example.test")
a = Avatar.objects.create(owner=o)
a.image.save("x.png", ContentFile(b"pixels"), save=True)
p = a.image.path
o.delete()
print("A5 owner deleted | Avatar rows:", Avatar.objects.count(),
      "| avatar.owner_id:", Avatar.objects.values_list("owner_id", flat=True).first(),
      "| file still on disk:", os.path.exists(p))

d = Doc.objects.create()
d.f.save("y.png", ContentFile(b"bytes"), save=True)
p2 = d.f.path
d.delete()
print("A6 doc deleted | receiver in models.py fired:", FIRED,
      "| file still on disk:", os.path.exists(p2))
```

```
$ uv run --with django==6.1 --with django-cleanup==9.0.0 python atk_django.py none
django 6.1 | INSTALLED_APPS entry: none | cleanup app loaded: False
A5 owner deleted | Avatar rows: 1 | avatar.owner_id: None | file still on disk: True
A6 doc deleted | receiver in models.py fired: ['Doc'] | file still on disk: True

$ uv run --with django==6.1 --with django-cleanup==9.0.0 python atk_django.py dotted
django 6.1 | INSTALLED_APPS entry: dotted | cleanup app loaded: True
A5 owner deleted | Avatar rows: 1 | avatar.owner_id: None | file still on disk: True
A6 doc deleted | receiver in models.py fired: ['Doc'] | file still on disk: False

$ uv run --with django==6.1 --with django-cleanup==9.0.0 python atk_django.py bare
django 6.1 | INSTALLED_APPS entry: bare | cleanup app loaded: True
A5 owner deleted | Avatar rows: 1 | avatar.owner_id: None | file still on disk: True
A6 doc deleted | receiver in models.py fired: ['Doc'] | file still on disk: False
```

Three results. django-cleanup was installed and the avatar file survived, because the row carrying it was never deleted — `SET_NULL` orphaned it instead, and `post_delete` cannot fire for a row that still exists. An install string in `INSTALLED_APPS` is a repository-global fact and says nothing about which `FileField` a deletion reaches. Second: the bare label `'django_cleanup'` behaves exactly like the dotted `'django_cleanup.apps.CleanupConfig'`, because `CleanupConfig` sets `default = True` [S13]; a verifier matching only the dotted string would call a repository that does delete its files `not_erased`. Third: `@receiver(post_delete, sender=Doc)` at the bottom of `models.py` fired in all three modes with nothing importing it, because Django imports every installed app's `models` module itself.

The three scripts below share `run.py`'s settings preamble from 4.1 with the app name swapped, so only the model module and the part that differs are reproduced.

**(b) `DB_CASCADE` versus django-cleanup.** `dbc_app/models.py`:

```python
class Owner(models.Model):
    email = models.EmailField()


class Avatar(models.Model):
    owner = models.ForeignKey(Owner, on_delete=models.DB_CASCADE)
    image = models.FileField(upload_to="avatars/")
```

`dbc_run.py` is `run.py` pointed at `dbc_app`, with a module-level `post_delete` receiver appending `sender.__name__` to a list.

```
$ uv run --with django==6.1 --with django-cleanup==9.0.0 python dbc_run.py --cleanup
django 6.1 | DB_CASCADE | cleanup: True
  Avatar rows after DB_CASCADE: 0
  post_delete senders seen: ['Owner']
  file exists after delete: True
```

The `Avatar` row is gone and `Avatar` is missing from the senders list: the database removed the row and Django never knew, so django-cleanup's handler never ran and the file stayed. Section 1 asserted this from the documentation alone; it now has a transcript.

**(c) `PROTECT` and the two-step deletion idiom.** `res_app/models.py`:

```python
class Owner(models.Model):
    email = models.EmailField()


class Invoice(models.Model):
    owner = models.ForeignKey(Owner, on_delete=models.PROTECT)
    billing_name = models.CharField(max_length=80)
```

`res_run.py`, after the same preamble:

```python
o = Owner.objects.create(email="a@example.test")
Invoice.objects.create(owner=o, billing_name="Jenny Rosen")
try:
    o.delete()
    print("naive delete succeeded (unexpected)")
except Exception as ex:
    print("PROTECT: bare parent delete raises ->", type(ex).__name__)

o2 = Owner.objects.get(pk=o.pk)
Invoice.objects.filter(owner=o2).delete()      # the two-step pattern real code uses
o2.delete()
print("two-step delete_account(): Owner rows:", Owner.objects.count(),
      "| Invoice rows:", Invoice.objects.count())
```

```
$ uv run --with django==6.1 python res_run.py
PROTECT: bare parent delete raises -> ProtectedError
two-step delete_account(): Owner rows: 0 | Invoice rows: 0
```

`PROTECT` is not an edge, but a `PROTECT` foreign key does not mean the store is unreachable. Clear the children first and both tables empty. `PROTECT` on billing and audit relations is the standard Django idiom, so a rule that reads it as `not_erased` loses recall on the repositories most likely to have a working erasure path.

**(d) `pre_delete` is the other half of the file-cleanup idiom.** `pre_app/models.py`:

```python
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver


class Owner(models.Model):
    email = models.EmailField()


class Avatar(models.Model):
    owner = models.ForeignKey(Owner, on_delete=models.CASCADE)
    image = models.FileField(upload_to="avatars/")


@receiver(pre_delete, sender=Avatar)          # pre_delete, not post_delete
def drop_file(sender, instance, **kw):
    instance.image.delete(save=False)
```

`pre_run.py` creates an `Owner` and an `Avatar` with a saved file, then calls `owner.delete()` and reports the row count and `os.path.exists` on the file path.

```
$ uv run --with django==6.1 python pre_run.py
pre_delete receiver on cascade | Avatar rows: 0 | file on disk: False
```

`owner.delete()` cascades to `Avatar`, `pre_delete` fires on the cascade path, and the file is gone. It is the form some codebases prefer, because the row and its file path are still readable when the receiver runs. A rule naming only `post_delete` renders it `not_erased`.

---

## 5. Build decision: stdlib `ast`, no dependency

**Decision: the verifier uses `ast` from the standard library. No call-graph package is added.**

Reasons, with the one that decides it at 3:

1. **Licence.** pyan3 is the most actively developed name-based call-graph extractor, and it is GPL-2.0 [S37]. micro1 owns the submission and may train on it (AGENTS.md). A copyleft dependency in the core analyser is not a trade worth making for code we can write in 200 lines. The permissive alternative is code2flow, MIT, name-based, AST-powered — and its last release was 2023-01-08 [S38]. So the licence objection does not clear the field on its own; reason 3 is the one that decides the build either way.
2. **The best-fitting alternative is abandoned.** PyCG is the strongest research implementation and its repository is archived, last pushed 2023-11-26, latest release 0.0.8 [S36]. Reproducibility is 15 points; an archived Apache-2.0 package pinned in a lockfile is defensible, an archived package we depend on for the primary metric is not.
3. **None of them answers our question anyway.** code2flow states its own limits: functions without definitions skipped, identically-named methods in different namespaces skipped, functions passed as parameters skipped [S38]. pyan tracks bindings linearly and folds lambdas into their enclosing function [S37]. Those are the same name-resolution limits a stdlib implementation has. More to the point, no general call-graph tool knows that `on_delete=models.CASCADE` is an edge, that `passive_deletes=True` plus `ondelete="CASCADE"` is an edge, or that `sender=Avatar` in a decorator changes which model a receiver covers. The domain rules are the product. The graph is the cheap part.
4. **jedi and pyright are the wrong shape.** jedi is an editor inference engine [S39]; pyright is a type checker that needs a Node.js runtime and emits diagnostics, not a graph [S40]. Either would add a large surface for a partial answer.
5. **AGENTS.md prefers stdlib** and NON-GOALS already rules out type inference and dynamic-dispatch resolution. `ast` gives us what those rules permit: `Call.func` as `Name` or `Attribute` [S35], `decorator_list` as readable data [S35], and 1-indexed `lineno` / `end_lineno` for the `file:line` citations every claim carries [S35].

What we give up: `storage.delete()` cannot be resolved to a backend class, two same-named functions in different modules are ambiguous, and a callable passed as an argument is invisible. All three are handled by AMBIGUITIES row 14, verdict `unverified`, counted as not-reaching. Guessing in either direction is the failure the tool exists to prevent.

---

## 6. Rule-set consequences

Concrete rules for `advanced/verify.py`. Each is a claim the verifier can decide from the AST plus the rule data, and each cites the behaviour it rests on.

**Path construction**

1. **R1** A Django `ForeignKey(..., on_delete=CASCADE)` from table B to table A is a propagation edge A→B for relational rows [S1] [S4].
2. **R2** `on_delete` in {`SET_NULL`, `SET_DEFAULT`, `SET`, `DO_NOTHING`} is **not** an edge: the row survives with its personal-data columns intact [S1]. Verdict for B is `not_erased` unless another path reaches it.
3. **R3a** `on_delete=PROTECT` is not a propagation edge. If the erasure path calls a delete primitive for the child store *before* deleting the parent, that store is `erased` on that path and the parent delete succeeds. Otherwise verdict `not_erased`, note "deletion of the parent raises `ProtectedError` while children exist" [S1]. Both halves reproduced in section 4.4(c): a bare `owner.delete()` raises, and `Invoice.objects.filter(owner=user).delete()` followed by `user.delete()` empties both tables.
4. **R3b** `RESTRICT` behaves as `PROTECT` with one documented exception — "deletion of the referenced object is allowed if it also references a different object that is being deleted in the same operation, but via a `CASCADE` relationship" [S1]. Where that shape is present the verdict is `unverified`, not `not_erased`.
5. **R4** `on_delete=DB_CASCADE` is a propagation edge for rows, and simultaneously **kills** every signal-based cleanup on the cascaded model: "signals won't be sent when `DB_CASCADE` is used" [S1] [S3]. Any file store whose only erasure evidence is a `pre_delete`/`post_delete` receiver on a `DB_CASCADE` child is `not_erased`, django-cleanup included. Confirmed by execution (section 4.4(b)): the row went, the sender never appeared in the signal list, the file stayed.
6. **R5** Split the `cascade=` string on commas and strip whitespace. A SQLAlchemy `relationship()` is a propagation edge only if the resulting token set contains the exact token `delete` or the exact token `all`; `all` is "a synonym for `save-update, merge, refresh-expire, expunge, delete`" [S15]. A substring test is wrong: `delete-orphan` on its own is not a delete cascade, SQLAlchemy only warns ("The 'delete-orphan' cascade option requires 'delete'."), and the children survive the parent delete with their personal-data columns intact (section 4.3). Absent a `delete` token, children are de-associated with the FK set to `NULL` [S15] [S18], verdict `not_erased`.
7. **R6** `ForeignKey(..., ondelete="CASCADE")` is a propagation edge **only when the connection is shown to enforce foreign keys**. `ondelete` emits DDL and nothing more [S19], and the cascade runs only where "the underlying database engine must support `FOREIGN KEY` constraints and they must be enforcing" [S15]. Evidence required: a non-SQLite engine URL (`postgresql://`, `mysql://`) in the repository's engine construction or settings; or, for SQLite, a `PRAGMA foreign_keys=ON` connect listener, which SQLAlchemy documents as `@event.listens_for(Engine, "connect")` [S46]. Absent either, verdict `unverified`, counted as not-reaching. Where `passive_deletes=True` is set and the engine is not shown to enforce foreign keys, verdict `not_erased`: the ORM has been told not to emit the `DELETE` and nothing else will. Section 4.3 is the transcript — parent gone, child row and its email present, `PRAGMA foreign_keys = 0`.
8. **R7** A many-to-many association table linked by `relationship.secondary` is erased when the parent is deleted through `Session.delete()` [S18], which is the scope [S18] states for that rule ("There are various important behaviors related to the `Session.delete()` operation […] in general the rules are"). On a bulk-DML path (R17), or where the parent row is removed by a database cascade, the ORM performs no in-Python cascade [S16] and the association rows survive unless the association table's own foreign key carries `ondelete="CASCADE"` under R6. Reproduced both ways in section 4.3.

**Files and object storage**

9. **R8** A Django `FileField`/`ImageField` reachable only by cascade is **`not_erased`**. Precondition governing every branch below: the row carrying the field must itself be reached by the erasure path under R1, R3a, R4 or R14. No delete on that row means no delete signal, and none of (a)–(c) fires — section 4.4(a) has django-cleanup installed and the avatar file still on disk, because a `SET_NULL` foreign key orphaned the row instead of deleting it. Given the precondition, the field becomes `erased` if one of:
   (a) a `pre_delete` **or** `post_delete` receiver whose `sender=` is that exact model calls a delete primitive on the field or its storage [S1] [S5]. `pre_delete` counts and works on the cascade path — the signals "are sent for all deleted objects" [S1], and a `pre_delete` receiver calling `instance.image.delete(save=False)` removes the file (section 4.4(d));
   (b) django-cleanup is active for that model under R10 **and** the row is reached;
   (c) a delete primitive for that file is called directly from the erasure path [S2] [S13].
10. **R9** For (a), a receiver with a different `sender=` does not count, and a receiver with no `sender=` counts for every model [S6]. Applies to `pre_delete` and `post_delete` alike. This is the S09 decoy.
11. **R10** django-cleanup is active when `INSTALLED_APPS` contains the app label in any form: the bare `'django_cleanup'`, which resolves to `CleanupConfig` because that class sets `default = True` [S13], or the dotted `'django_cleanup.apps.CleanupConfig'`. Both delete the file, verified in section 4.4(a); a verifier matching only the dotted string reports `not_erased` for a repository whose files are in fact deleted. The single exception is the explicit dotted `'django_cleanup.apps.CleanupSelectedConfig'`, which inverts the default to opt-in: only models decorated `@cleanup.select` are covered [S13]. The bare label can never mean select mode, since `default = True` sits on `CleanupConfig` alone. `@cleanup.ignore` on the model removes coverage in either mode [S13].
12. **R11** A `pre_delete`/`post_delete` receiver defined inside a function body and connected without `weak=False` is `unverified`, never `erased`: it may be garbage collected before it ever fires [S6]. Confirmed by execution (section 4.1).
13. **R12** A receiver is connected if it is defined in — or imported by — a module Django loads on its own, meaning an installed app's `models.py` or `apps.py`, or a module imported by an `AppConfig.ready()`, or a module imported transitively from either. A `signals.py` that nothing on that list imports is not connected and is not evidence [S6]; that is the static analogue of "the function exists but is never called" (eval case S10). The signals guide recommends against putting receivers in `models` ("it's recommended to avoid the application's root module and its `models` module" [S6]), but a recommendation against a pattern is not evidence the pattern fails: a `@receiver(post_delete, sender=Doc)` at the bottom of `models.py`, imported by nothing in the repository, fired in every configuration tested (section 4.4(a)).
14. **R13** An object-store delete (`Storage.delete`, `S3Storage.delete`, boto3 `delete_object`, `Object().delete()`) on the path reaches erasure **only when no versioning declaration for that bucket is found in the repository** [S12] [S14] [S23]. Look for `put_bucket_versioning`, `BucketVersioning`, `aws_s3_bucket_versioning`, `VersioningConfiguration` and the equivalent IaC keys; infrastructure files are outside the Python scan, so this is a string search and is reported as one. Where such a declaration enables versioning and the delete call passes no `VersionId`, verdict `not_erased`, with [S22]'s own words as the reason: Amazon S3 "behaves as though the object has been deleted (even though it has not been erased)". Where none is found, the narrowed **Assumption** in section 3 applies and the delete is scored as reaching erasure. The standing artifact note — a versioned bucket keeps prior versions unless `versionId` is supplied — is rendered in both branches [S22] [S23].

**Which delete was called**

15. **R14** An overridden `Model.delete()` that performs cleanup is evidence **only** on paths that call `Model.delete()`. It is not called for cascaded objects [S1], not called by `QuerySet.delete()` [S3] [S4], and not called by the admin's "delete selected" action [S8].
16. **R15** `QuerySet.delete()` still emits `pre_delete`/`post_delete` for all deleted objects including cascaded ones [S3], so signal-based cleanup survives the bulk path. Only R4 removes it.
17. **R16** Django admin counts as an erasure entry point when the model is registered (AMBIGUITIES row 15), flagged `admin_only`. The single-object path resolves to `Model.delete()` via `delete_model` [S9]; the bulk action resolves to `QuerySet.delete()` via `delete_queryset` [S8] [S9]. The two get different verdicts under R14.
18. **R17** SQLAlchemy bulk DML (`session.execute(delete(Model))`) propagates only through R6 database-level cascades, never through R5 ORM cascades [S15] [S16]. R7 association tables are not an exception to this (section 4.3).
19. **R18** `before_delete` / `after_delete` listeners are evidence only for stores reached by a `Session.delete()` flush. They are not evidence for bulk DML paths or for rows removed by a database cascade [S17].
20. **R19** A call through `connection.cursor()`, `session.execute(text(...))` or `QuerySet._raw_delete` is an opaque edge: no ORM cascade, no signals [S11] [S16]. Rows named directly in the SQL are `erased`; anything downstream is `unverified`.

**Non-relational and third-party stores**

21. **R20** Redis: `delete`/`unlink` **reached from the erasure entry point** is erasure [S24]. A TTL (`expire`/`setex`/`pexpire`) is a retention timer recorded in the Art. 30 record, not an erasure path: verdict `not_erased`, the TTL rendered in the retention column, with a note that an overwrite clears the timeout and a re-`EXPIRE` extends it indefinitely [S25]. `erased_after_timer` requires a scheduled job on the path that reaches a hard delete (AMBIGUITIES row 4); a `setex` at write time is not one and is not bound to account closure at all.
22. **R21** A search index is a distinct store. It is erased only by an index `delete` or `delete_by_query` on the path; a relational delete never reaches it [S26] [S27].
23. **R22** Stripe is `external_manual` even when `Customer.delete` is called on the path, because deleted customers "can still be retrieved through the API", transactions never support deletion and can only be redacted after 90 days, and invoices are excluded from redaction entirely [S28] [S29]. Never render `erased` for a Stripe store.
24. **R23** An `sentry_sdk.init(...)` call makes Sentry a recipient. With no flag set, request URLs and query strings are "always sent to Sentry", JSON and form request bodies are sent under the default `max_request_body_size="medium"`, and stack traces carry source context and the names and values of local variables under `include_source_context=True` and `include_local_variables=True` [S30] [S31] [S42]. The field list in that case is `url` and `query_string`, plus `free_text_may_contain` for bodies and stack-frame locals. `send_default_pii=True`, `set_user()` or `set_context()` add headers, cookies, logged-in user identity and IP [S30] [S31] and upgrade those fields to identifier, contact and technical. `_experiments={"data_collection": {...}}` supersedes the flag and collects most categories by default [S42]. Erasure verdict `external_manual` in every case.
25. **R24** Mixpanel, Segment and SendGrid are `external_manual` when a personal-data field flows into an SDK call, and `erased` only if the vendor's deletion endpoint is called on the path [S32] [S33] [S34] [S47].

**Soft delete and unresolvable code**

26. **R25** `is_active = False`, `deleted_at = now()` and equivalent flag writes are `not_erased`. Django's own auth documentation recommends the pattern ("We recommend that you set this flag to `False` instead of deleting accounts") [S10], which is why it is everywhere and why the verifier must refuse it. It becomes `erased_after_timer` only with a scheduled job whose path reaches a hard delete, timer cited (AMBIGUITIES row 4).
27. **R26** A call whose target cannot be resolved by name, or resolves to more than one definition, is `unverified` and counts as not-reaching for the false-safe row [S35] (AMBIGUITIES row 14, NON-GOALS).
28. **R27** A `@receiver(...)` decorator is read as data from `decorator_list`, including its `sender=` keyword [S35]. What any other decorator does to a function is not modelled; a delete primitive reached only through an unmodelled decorator is `unverified`.
29. **R28** Every verdict carries `file:line` from `lineno`, which is 1-indexed [S35]. If position information is missing, the evidence cell is empty and the verdict drops to `unverified` rather than citing a guessed line [S35].

---

## Sources

| ID | Title | URL | Accessed | Used for |
|---|---|---|---|---|
| S1 | Model field reference (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/models/fields/ | 2026-08-28 | `FieldFile.delete()`, files-not-deleted note, `on_delete` values, `DB_*` signal caveat |
| S2 | Django 1.3 release notes | https://docs.djangoproject.com/en/6.1/releases/1.3/#deleting-a-model-doesn-t-delete-associated-files | 2026-08-28 | Why automatic file deletion was removed |
| S3 | QuerySet API reference — `delete()` (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/models/querysets/#delete | 2026-08-28 | Bulk delete, signals for cascaded objects, fast-delete path |
| S4 | Making queries — Deleting objects (Django 6.1) | https://docs.djangoproject.com/en/6.1/topics/db/queries/#deleting-objects | 2026-08-28 | Cascade emulation, bulk SQL execution |
| S5 | Signals reference (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/signals/#post-delete | 2026-08-28 | `post_delete` / `pre_delete` arguments |
| S6 | Signals topic guide (Django 6.1) | https://docs.djangoproject.com/en/6.1/topics/signals/ | 2026-08-28 | `sender=`, weak references, `dispatch_uid`, `ready()` wiring |
| S7 | Model instance reference (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/models/instances/#deleting-objects | 2026-08-28 | `Model.delete()` |
| S8 | Admin actions (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/contrib/admin/actions/ | 2026-08-28 | "delete selected" uses `QuerySet.delete()` |
| S9 | `ModelAdmin` reference (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#django.contrib.admin.ModelAdmin.delete_queryset | 2026-08-28 | `delete_model` / `delete_queryset` |
| S10 | `django.contrib.auth` reference (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/contrib/auth/#django.contrib.auth.models.User.is_active | 2026-08-28 | The `is_active` soft-delete recommendation |
| S11 | Performing raw SQL queries (Django 6.1) | https://docs.djangoproject.com/en/6.1/topics/db/sql/#executing-custom-sql-directly | 2026-08-28 | `connection.cursor()` bypass |
| S12 | File storage API (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/files/storage/#django.core.files.storage.Storage.delete | 2026-08-28 | `Storage.delete()` contract |
| S13 | django-cleanup 9.0.0 — metadata, README and `src/django_cleanup/apps.py` | https://pypi.org/project/django-cleanup/ · https://github.com/un1t/django-cleanup · https://raw.githubusercontent.com/un1t/django-cleanup/master/src/django_cleanup/apps.py | 2026-08-28 | Behaviour, signals, install string, `CleanupConfig.default = True`, select/ignore modes, version, MIT |
| S14 | django-storages 1.14.6 — `storages/backends/s3.py` | https://github.com/jschneier/django-storages/blob/master/storages/backends/s3.py | 2026-08-28 | `S3Storage.delete()` issues an S3 object delete |
| S15 | Cascades — SQLAlchemy 2.0 ORM | https://docs.sqlalchemy.org/en/20/orm/cascades.html | 2026-08-28 | Default cascade, FK-set-NULL, `passive_deletes`, bulk warning, SQLite FK caveat |
| S16 | ORM-Enabled UPDATE and DELETE — SQLAlchemy 2.0 | https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html#important-notes-and-caveats-for-orm-enabled-update-and-delete | 2026-08-28 | Bulk DML bypasses unit of work and in-Python cascades |
| S17 | `MapperEvents.before_delete` / `after_delete` — SQLAlchemy 2.0 | https://docs.sqlalchemy.org/en/20/orm/events.html#sqlalchemy.orm.MapperEvents.before_delete | 2026-08-28 | Flush-only scope of delete events |
| S18 | Session Basics — Deleting — SQLAlchemy 2.0 | https://docs.sqlalchemy.org/en/20/orm/session_basics.html#deleting | 2026-08-28 | Related rows not deleted by default; many-to-many always deleted |
| S19 | `Session.delete()` and `ForeignKey.ondelete` — SQLAlchemy 2.0 API | https://docs.sqlalchemy.org/en/20/orm/session_api.html#sqlalchemy.orm.Session.delete · https://docs.sqlalchemy.org/en/20/core/constraints.html#sqlalchemy.schema.ForeignKey.params.ondelete | 2026-08-28 | Deferred-to-flush semantics; the `ondelete` DDL string |
| S20 | SQLModel documentation home | https://sqlmodel.tiangolo.com/ | 2026-08-28 | SQLModel is powered by SQLAlchemy |
| S21 | Flask-SQLAlchemy 3.1 API reference | https://flask-sqlalchemy.readthedocs.io/en/stable/api/ | 2026-08-28 | `db.session` is a SQLAlchemy scoped session |
| S22 | Deleting object versions — Amazon S3 User Guide | https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html | 2026-08-28 | Delete markers, "not been erased", lifecycle expiration |
| S23 | `S3.Client.delete_object` — boto3 | https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/delete_object.html | 2026-08-28 | Versioning-dependent delete behaviour |
| S24 | Redis `DEL` | https://redis.io/docs/latest/commands/del/ | 2026-08-28 | What DEL removes |
| S25 | Redis `EXPIRE` | https://redis.io/docs/latest/commands/expire/ | 2026-08-28 | TTL semantics, timeout cleared by overwrite, TTL refresh |
| S26 | Delete a document — Elasticsearch API | https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete | 2026-08-28 | Document delete |
| S27 | Delete by query — Elasticsearch API | https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query | 2026-08-28 | Query-based delete |
| S28 | Delete a customer — Stripe API reference | https://docs.stripe.com/api/customers/delete | 2026-08-28 | What deletion does; deleted customers remain retrievable |
| S29 | Handling customer deletion requests — Stripe | https://docs.stripe.com/privacy/deletion-requests | 2026-08-28 | Redaction vs deletion, legal retention, 90-day rule, invoices |
| S30 | Configuration options — Sentry Python SDK | https://docs.sentry.io/platforms/python/configuration/options/ | 2026-08-28 | `send_default_pii` description |
| S31 | Data collected — Sentry Python SDK | https://docs.sentry.io/platforms/python/data-management/data-collected/ | 2026-08-28 | Which categories the flag gates; which are always sent; body, source-context and stack-local defaults |
| S32 | Create a Deletion — Mixpanel API reference | https://docs.mixpanel.com/reference/create-deletion | 2026-08-28 | User-deletion endpoint exists |
| S33 | Deletion and Suppression — Segment Public API | https://docs.segmentapis.com/tag/Deletion-and-Suppression | 2026-08-28 | User-deletion endpoint exists |
| S34 | Delete Contacts — SendGrid API reference | https://www.twilio.com/docs/sendgrid/api-reference/contacts/delete-contacts | 2026-08-28 | Contact-deletion endpoint exists |
| S35 | `ast` — Abstract Syntax Trees (Python 3.12) | https://docs.python.org/3.12/library/ast.html | 2026-08-28 | Node shapes, `decorator_list`, `lineno`/`end_lineno`, `get_source_segment` |
| S36 | PyCG — PyPI and GitHub | https://pypi.org/pypi/pycg/json · https://github.com/vitsalis/PyCG | 2026-08-28 | 0.0.8, Apache-2.0, archived 2023-11-26 |
| S37 | pyan — PyPI, README, LICENSE.md | https://pypi.org/pypi/pyan3/json · https://github.com/Technologicat/pyan | 2026-08-28 | 2.8.1 (2026-08-22), GPL-2.0, self-described limits |
| S38 | code2flow — PyPI and README | https://pypi.org/pypi/code2flow/json · https://github.com/scottrogowski/code2flow | 2026-08-28 | 2.5.1, MIT, known limitations |
| S39 | jedi — PyPI and GitHub | https://pypi.org/pypi/jedi/json · https://github.com/davidhalter/jedi | 2026-08-28 | 0.20.0, MIT, editor scope |
| S40 | pyright — PyPI wrapper and GitHub | https://pypi.org/pypi/pyright/json · https://github.com/microsoft/pyright | 2026-08-28 | 1.1.411, MIT, type checker |
| S42 | `sentry_sdk/consts.py` (sentry-sdk 2.68.1) | https://github.com/getsentry/sentry-python/blob/master/sentry_sdk/consts.py | 2026-08-28 | Defaults of `send_default_pii`, `max_request_body_size`, `include_local_variables`, `include_source_context`; `_experiments["data_collection"]` supersession |
| S43 | SQLModel source — `sqlmodel/orm/session.py` | https://github.com/fastapi/sqlmodel/blob/main/sqlmodel/orm/session.py | 2026-08-28 | `Session` subclasses `sqlalchemy.orm.Session` |
| S44 | Django release metadata on PyPI | https://pypi.org/pypi/Django/json | 2026-08-28 | Current stable version is 6.1 |
| S45 | SQLAlchemy release metadata on PyPI | https://pypi.org/pypi/SQLAlchemy/json | 2026-08-28 | Current version 2.0.52, MIT |
| S46 | SQLite — Foreign Key Support, SQLAlchemy 2.0 dialect documentation | https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#foreign-key-support | 2026-08-28 | SQLite FK constraints inert by default; the `PRAGMA foreign_keys=ON` connect-listener recipe |
| S47 | User Deletion and Suppression — Segment documentation | https://segment.com/docs/privacy/user-deletion-and-suppression/ → https://www.twilio.com/docs/segment/privacy/user-deletion-and-suppression | 2026-08-28 | Regulation types, what a deletion request removes and from where |

Note on S47: the `segment.com` URL returns HTTP 403 to the documentation fetcher, which is a bot filter rather than a property of the page. `curl -sSL --compressed` with a browser user-agent follows a cross-host redirect to `www.twilio.com/docs/segment/...` and returns HTTP 200; the quotes in `sources/frameworks/storage-and-services.md` come from that response. The earlier FETCH FAILED line is withdrawn.
