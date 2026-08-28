# Source excerpts — Django deletion semantics

Scope: what Django 6.1 does to rows, files and signals when something is deleted. Analysis lives in `docs/research/framework-behaviour.md`; this file is quotes plus a line of context each.

Version under study: **Django 6.1**. `https://docs.djangoproject.com/en/stable/` returns `302 → /en/6.1/`, and PyPI lists `6.1` as the latest release (checked 2026-08-28) [S44]. Quotes were extracted from the documentation source at tag `stable/6.1.x` in the Django repository so the wording is byte-exact; the rendered pages at the cited URLs carry the same text.

---

## 1. Files are not deleted with the model instance

Context: the `FieldFile.delete()` entry in the model field reference — the method that removes a file, and the note that nothing calls it for you.

> `FieldFile.delete(save=True)`
>
> Deletes the file associated with this instance and clears all attributes on the field. Note: This method will close the file if it happens to be open when `delete()` is called.
>
> The optional `save` argument controls whether or not the model instance is saved after the file associated with this field has been deleted. Defaults to `True`.
>
> Note that when a model is deleted, related files are not deleted. If you need to cleanup orphaned files, you'll need to handle it yourself (for instance, with a custom management command that can be run manually or scheduled to run periodically via e.g. cron).

[S1]

Context: this note appears once on the page, under `FieldFile.delete()`. The `class FileField` entry a developer actually reads when adding an upload field does not repeat it. Its own notes cover the unsupported `primary_key` argument, the fact that the file is saved as part of saving the model, and a warning about validating uploads; none of them mentions what happens on delete. Re-fetched and counted 2026-08-28: exactly one occurrence of "when a model is deleted, related files are not deleted" in the whole document. The behaviour is documented in one place a developer setting up an upload field never reaches, which is a better account of why it keeps biting people than "it is stated twice". [S1]

---

## 2. Why automatic deletion was removed (Django 1.3, 2011)

Context: release-note section heading and body. This is the reason the behaviour exists, and it is not an oversight.

> **Deleting a model doesn't delete associated files**
>
> In earlier Django versions, when a model instance containing a `FileField` was deleted, `FileField` took it upon itself to also delete the file from the backend storage. This opened the door to several data-loss scenarios, including rolled-back transactions and fields on different models referencing the same file. In Django 1.3, when a model is deleted the `FileField`'s `delete()` method won't be called. If you need cleanup of orphaned files, you'll need to handle it yourself (for instance, with a custom management command that can be run manually or scheduled to run periodically via e.g. cron).

[S2]

---

## 3. `on_delete` options

Context: preamble to the option list. Django 6.1 added a second family of options that push the work to the database.

> The possible values for `on_delete` are listed below. Import them from `django.db.models`. The `DB_*` variants use the database to prevent deletions or update referring objects, whilst the other values make Django perform the relevant actions.
>
> The database variants are more efficient because they avoid fetching related objects, but `pre_delete` and `post_delete` signals won't be sent when `DB_CASCADE` is used.
>
> The database variants cannot be mixed with Python variants (other than `DO_NOTHING`) in the same model and in models related to each other.

[S1]

Context: `CASCADE` — the Python-emulated cascade. The second paragraph is the one that makes signal-based file cleanup work at all.

> `CASCADE`
>
> Cascade deletes. Django emulates the behavior of the SQL constraint `ON DELETE CASCADE` and also deletes the object containing the `ForeignKey`.
>
> `Model.delete()` isn't called on related models, but the `pre_delete` and `post_delete` signals are sent for all deleted objects.

[S1]

Context: `DB_CASCADE`, new in 6.1.

> `DB_CASCADE`
>
> *(versionadded 6.1)*
>
> Cascade deletes. Database-level version of `CASCADE`: the database deletes referred-to rows and the one containing the `ForeignKey`.

[S1]

Context: the remaining options, quoted in full because the verifier has to recognise each one by name.

> `PROTECT`
>
> Prevent deletion of the referenced object by raising `ProtectedError`, a subclass of `django.db.IntegrityError`.

> `RESTRICT`
>
> Prevent deletion of the referenced object by raising `RestrictedError` (a subclass of `django.db.IntegrityError`). Unlike `PROTECT`, deletion of the referenced object is allowed if it also references a different object that is being deleted in the same operation, but via a `CASCADE` relationship.

> `SET_NULL`
>
> Set the `ForeignKey` null; this is only possible if `null` is `True`.

> `DB_SET_NULL`
>
> *(versionadded 6.1)*
>
> Set the `ForeignKey` value to `NULL`. This is only possible if `null` is `True`. Database-level version of `SET_NULL`.

> `SET_DEFAULT`
>
> Set the `ForeignKey` to its default value; a default for the `ForeignKey` must be set.

> `DB_SET_DEFAULT`
>
> *(versionadded 6.1)*
>
> Set the `ForeignKey` value to its `Field.db_default` value, which must be set. If a row in the referenced table is deleted, the foreign key values in the referencing table will be updated to their `Field.db_default` values.
>
> `DB_SET_DEFAULT` is not supported on MySQL and MariaDB.

> `SET()`
>
> Set the `ForeignKey` to the value passed to `SET()`, or if a callable is passed in, the result of calling it.

> `DO_NOTHING`
>
> Take no action. If your database backend enforces referential integrity, this will cause an `IntegrityError` unless you manually add an SQL `ON DELETE` constraint to the database field.

[S1]

---

## 4. `Model.delete()` versus `QuerySet.delete()`

Context: the instance method. Note what it does *not* promise.

> `Model.delete(using=DEFAULT_DB_ALIAS, keep_parents=False)`
>
> Issues an SQL `DELETE` for the object. This only deletes the object in the database; the Python instance will still exist and will still have data in its fields, except for the primary key set to `None`. This method returns the number of objects deleted and a dictionary with the number of deletions per object type.

[S7]

Context: the bulk method — the one the admin's "delete selected" action and most management commands go through.

> The `delete()` method does a bulk delete and does not call any `delete()` methods on your models. It does, however, emit the `pre_delete` and `post_delete` signals for all deleted objects (including cascaded deletions). Signals won't be sent when `DB_CASCADE` is used. Also, `delete()` doesn't return information about objects deleted from database variants (`DB_*`) of the `on_delete` argument, e.g. `DB_CASCADE`.

[S3]

Context: the fast-delete path, immediately following. This is the case where Django deletes rows without ever constructing the objects.

> Django won't need to fetch objects into memory when deleting them in the following cases:
>
> 1. If related fields use `DB_*` options.
> 2. If there are no cascades and no delete signal receivers.
>
> In these cases, Django may take a fast path and delete objects without fetching them, which can result in significantly reduced memory usage and fewer executed queries.
>
> ForeignKeys which are set to `on_delete` `DO_NOTHING` do not prevent taking the fast-path in deletion.

[S3]

Context: the topic guide's version of the same warning, which is where most application authors read it.

> Keep in mind that this will, whenever possible, be executed purely in SQL, and so the `delete()` methods of individual object instances will not necessarily be called during the process. If you've provided a custom `delete()` method on a model class and want to ensure that it is called, you will need to "manually" delete instances of that model (e.g., by iterating over a `QuerySet` and calling `delete()` on each object individually) rather than using the bulk `delete()` method of a `QuerySet`.

[S4]

> When Django deletes an object, by default it emulates the behavior of the SQL constraint `ON DELETE CASCADE` -- in other words, any objects which had foreign keys pointing at the object to be deleted will be deleted along with it.

[S4]

---

## 5. Raw SQL as an escape hatch

Context: `_raw_delete` is private API and is not documented; the public route around the ORM is the cursor. Django names exactly what it skips.

> Sometimes even `Manager.raw()` isn't quite enough: you might need to perform queries that don't map cleanly to models, or directly execute `UPDATE`, `INSERT`, or `DELETE` queries.
>
> In these cases, you can always access the database directly, routing around the model layer entirely.
>
> The object `django.db.connection` represents the default database connection. To use the database connection, call `connection.cursor()` to get a cursor object.

[S11]

---

## 6. Delete signals

Context: signal reference. `origin` was added so a receiver can tell which `delete()` call it came from.

> **post_delete**
>
> Like `pre_delete`, but sent at the end of a model's `delete()` method and a queryset's `delete()` method.
>
> Arguments sent with this signal:
>
> `sender` — The model class.
>
> `instance` — The actual instance being deleted. Note that the object will no longer be in the database, so be very careful what you do with this instance.
>
> `using` — The database alias being used.
>
> `origin` — The `Model` or `QuerySet` instance from which the deletion originated, that is, the instance whose `delete()` method was invoked.

[S5]

Context: restricting a receiver to one model. The `sender=` argument is the whole game for the S09 decoy case.

> In these cases, you can register to receive signals sent only by particular senders. In the case of `django.db.models.signals.pre_save`, the sender will be the model class being saved, so you can indicate that you only want signals sent by some model:
>
> ```
> @receiver(pre_save, sender=MyModel)
> def my_handler(sender, **kwargs): ...
> ```
>
> The `my_handler` function will only be called when an instance of `MyModel` is saved.

[S6]

Context: weak references. A receiver defined inside a function can be collected and then silently never fires.

> `Signal.connect(receiver, sender=None, weak=True, dispatch_uid=None)`
>
> `weak`: Django stores signal receivers as weak references by default. Thus, if your receiver is a local function, it may be garbage collected. To prevent this, pass `weak=False` when you call the signal's `connect()` method.
>
> `dispatch_uid`: A unique identifier for a signal receiver in cases where duplicate signals may be sent.

[S6]

Context: duplicate registration, and where `dispatch_uid` earns its keep.

> When `dispatch_uid` is not provided, Django identifies each receiver using its Python object identity and registers it only once. For module-level functions, static methods, and class methods, the identity is stable, so connecting the same receiver more than once has no effect
>
> Bound methods, which take a `self` argument, are different. Their identity is tied to the specific instance, so connecting the same method from a new instance registers it as an additional receiver

[S6]

Context: a receiver that is never imported is never connected. This is the standard wiring pattern and the thing a static reader must look for.

> **Where should this code live?**
>
> Strictly speaking, signal handling and registration code can live anywhere you like, although it's recommended to avoid the application's root module and its `models` module to minimize side-effects of importing code.
>
> In practice, signal receivers are usually defined in a `signals` submodule of the application they relate to. Signal receivers are connected in the `ready()` method of your application configuration class. If you're using the `receiver()` decorator, import the `signals` submodule inside `ready()`, this will implicitly connect signal receivers

[S6]

---

## 7. The admin as an erasure entry point

Context: the "delete selected objects" action. It goes through the bulk path.

> The "delete selected objects" action uses `QuerySet.delete()` for efficiency reasons, which has an important caveat: your model's `delete()` method will not be called.
>
> If you wish to override this behavior, you can override `ModelAdmin.delete_queryset()` or write a custom action which does deletion in your preferred manner -- for example, by calling `Model.delete()` for each of the selected items.

[S8]

Context: the two `ModelAdmin` hooks, which name the underlying call each path makes.

> `ModelAdmin.delete_model(request, obj)`
>
> The `delete_model` method is given the `HttpRequest` and a model instance. Overriding this method allows doing pre- or post-delete operations. Call `super().delete_model()` to delete the object using `Model.delete()`.

> `ModelAdmin.delete_queryset(request, queryset)`
>
> The `delete_queryset()` method is given the `HttpRequest` and a `QuerySet` of objects to be deleted. Override this method to customize the deletion process for the "delete selected objects" action.

[S9]

---

## 8. Django's own advice: do not delete users

Context: the `is_active` field on the built-in `User` model. This is the sentence that produced a generation of soft-deleted accounts.

> `is_active`
>
> Boolean. Marks this user account as active. We recommend that you set this flag to `False` instead of deleting accounts. That way, if your applications have any foreign keys to users, the foreign keys won't break.
>
> This doesn't necessarily control whether or not the user can log in. Authentication backends aren't required to check for the `is_active` flag but the default backend (`ModelBackend`) and the `RemoteUserBackend` do.

[S10]

Under `AMBIGUITIES` row 4 this pattern is **not** erasure. The data stays in the row; only its visibility changes. The product must render `is_active = False` (and every `deleted_at = now()` variant) as `not_erased` unless a purge job with a path to a hard delete exists.

---

## 9. Storage-level delete

Context: the `Storage` API contract that every backend, local or S3, implements.

> `delete(name)`
>
> Deletes the file referenced by `name`. If deletion is not supported on the target storage system this will raise `NotImplementedError` instead.

[S12]

---

## Sources

| ID | Title | URL | Accessed | Used for |
|---|---|---|---|---|
| S1 | Model field reference (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/models/fields/ | 2026-08-28 | `FieldFile.delete()`, FileField note, full `on_delete` list, `DB_*` signal caveat |
| S2 | Django 1.3 release notes | https://docs.djangoproject.com/en/6.1/releases/1.3/#deleting-a-model-doesn-t-delete-associated-files | 2026-08-28 | Why automatic file deletion was removed |
| S3 | QuerySet API reference — `delete()` (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/models/querysets/#delete | 2026-08-28 | Bulk delete, signals for cascaded objects, fast-delete path |
| S4 | Making queries — Deleting objects (Django 6.1) | https://docs.djangoproject.com/en/6.1/topics/db/queries/#deleting-objects | 2026-08-28 | Bulk SQL execution, cascade emulation |
| S5 | Signals reference (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/signals/#post-delete | 2026-08-28 | `post_delete` / `pre_delete` arguments |
| S6 | Signals topic guide (Django 6.1) | https://docs.djangoproject.com/en/6.1/topics/signals/ | 2026-08-28 | `sender=`, weak references, `dispatch_uid`, `ready()` wiring |
| S7 | Model instance reference (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/models/instances/#deleting-objects | 2026-08-28 | `Model.delete()` |
| S8 | Admin actions (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/contrib/admin/actions/ | 2026-08-28 | "delete selected" uses `QuerySet.delete()` |
| S9 | `ModelAdmin` reference (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#django.contrib.admin.ModelAdmin.delete_queryset | 2026-08-28 | `delete_model` / `delete_queryset` |
| S10 | `django.contrib.auth` reference (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/contrib/auth/#django.contrib.auth.models.User.is_active | 2026-08-28 | The soft-delete recommendation |
| S11 | Performing raw SQL queries (Django 6.1) | https://docs.djangoproject.com/en/6.1/topics/db/sql/#executing-custom-sql-directly | 2026-08-28 | `connection.cursor()` bypass |
| S12 | File storage API (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/files/storage/#django.core.files.storage.Storage.delete | 2026-08-28 | `Storage.delete()` contract |
| S44 | Django project download page / PyPI release data | https://pypi.org/pypi/Django/json | 2026-08-28 | Current stable version is 6.1 |
