# Source excerpts — Django ecosystem packages that change the erasure answer

Two packages decide whether a Django `FileField` is actually erased: `django-cleanup` (wires the missing signal handler) and `django-storages` (sends the delete to S3 instead of the local disk).

---

## django-cleanup 9.0.0

Version and licence: **9.0.0**, uploaded **2024-09-18**, classifier `License :: OSI Approved :: MIT License`. [S13]

Context: what it does, from the package's own README (the PyPI long description).

> The django-cleanup app automatically deletes files for `FileField`, `ImageField` and subclasses. When a `FileField`'s value is changed and the model is saved, the old file is deleted. When a model that has a `FileField` is deleted, the file is also deleted. A file that is set as the `FileField`'s default value will not be deleted.

[S13]

Context: the mechanism. Four signals, connected per model at app-registry time, with the actual unlink deferred to transaction commit.

> In order to track changes of a `FileField` and facilitate file deletions, django-cleanup connects `post_init`, `pre_save`, `post_save` and `post_delete` signals to signal handlers for each `INSTALLED_APPS` model that has a `FileField`. In order to tell whether or not a `FileField`'s value has changed a local cache of original values is kept on the model instance. If a condition is detected that should result in a file deletion, a function to delete the file is setup and inserted into the commit phase of the current transaction.

[S13]

Context: installation. The README shows the dotted form.

> Add `django_cleanup` to the bottom of `INSTALLED_APPS` in `settings.py`
>
> ```
> INSTALLED_APPS = (
>     ...,
>     'django_cleanup.apps.CleanupConfig',
> )
> ```
>
> That is all, no other configuration is necessary.

[S13]

Context: the dotted string is not the only spelling that works, and the source says why. `src/django_cleanup/apps.py`, read 2026-08-28:

> ```python
> class CleanupConfig(AppConfig):
>     name = 'django_cleanup'
>     verbose_name = 'Django Cleanup'
>     default = True
>
>     def ready(self):
>         cache.prepare(False)
>         handlers.connect()
>
> class CleanupSelectedConfig(AppConfig):
>     name = 'django_cleanup'
>     verbose_name = 'Django Cleanup'
>
>     def ready(self):
>         cache.prepare(True)
>         handlers.connect()
> ```

[S13]

`default = True` on `CleanupConfig` means the bare app label `'django_cleanup'` in `INSTALLED_APPS` resolves to that config, so it wires the same handlers as the dotted path. Verified by execution in both spellings — `framework-behaviour.md` section 4.4(a) — with the same result: the file is deleted. A verifier matching only `'django_cleanup.apps.CleanupConfig'` under-detects and reports `not_erased` for repositories that do delete their files. The asymmetry is useful in the other direction too: `default = True` sits on `CleanupConfig` alone, so the bare label can never mean select mode. Only the explicit dotted `'django_cleanup.apps.CleanupSelectedConfig'` does.

Context: the select-mode variant, which changes the default from opt-out to opt-in. A repo using it erases files only for decorated models.

> If you have many models to ignore, or if you prefer to be explicit about what models are selected, you can change the mode of django-cleanup to "select mode" by using the select mode app config. In your `INSTALLED_APPS` setting you will replace '`django_cleanup.apps.CleanupConfig`' with '`django_cleanup.apps.CleanupSelectedConfig`'.

[S13]

Context: the per-model opt-out.

> To ignore a model and not have cleanup performed when the model is deleted or its files change, use the `ignore` decorator to mark that model

[S13]

Context: a limitation that matters for discovery — models the app registry never sees are never wired.

> If you notice that `django-cleanup` is not removing files when expected, check that your models are being properly loaded […] If your models are not loaded, `django-cleanup` will not be able to discover their `FileField`'s.

[S13]

**Cascaded deletes.** The README says nothing about cascade. It does not have to: django-cleanup hangs off `post_delete`, and Django sends `post_delete` "for all deleted objects" under a Python `CASCADE` [S1]. Confirmed by execution — see the experiment in `docs/research/framework-behaviour.md` section 4.1. Under `on_delete=DB_CASCADE` (Django 6.1) no signal is sent [S1], so django-cleanup does not run and the file survives; also confirmed by execution, section 4.4(b).

**And no delete, no cleanup.** The same dependence on `post_delete` sets the limit of what an `INSTALLED_APPS` string can tell you. Where the erasure path never deletes the row holding the `FileField` — a `SET_NULL` foreign key, a soft delete, a model nothing reaches — no signal fires and the file stays, with django-cleanup installed and working. Reproduced in section 4.4(a): `Avatar rows: 1 | avatar.owner_id: None | file still on disk: True`. Detection of the package is therefore a precondition for the `erased` verdict, never the whole of it; the row has to be reached as well.

---

## django-storages 1.14.6 — S3 backend

Version and licence: **1.14.6**, uploaded **2025-04-02**, `BSD-3-Clause`. [S14]

Context: the backend implements Django's `Storage.delete(name)` contract [S12] by issuing an S3 object delete. Source, `storages/backends/s3.py`:

> ```python
> def delete(self, name):
>     try:
>         name = self._normalize_name(clean_name(name))
>         self.bucket.Object(name).delete()
>     except ClientError as err:
>         if err.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
>             # Not an error to delete something that does not exist
>             return
> ```

[S14]

`Object.delete()` is the boto3 resource form of `DeleteObject`; on a versioned bucket that inserts a delete marker rather than removing versions — see `storage-and-services.md`. So a Django app can call `storage.delete()`, get no error, and still hold every version of the file.

---

## Sources

| ID | Title | URL | Accessed | Used for |
|---|---|---|---|---|
| S1 | Model field reference (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/models/fields/ | 2026-08-28 | `post_delete` sent for all cascaded objects; not sent for `DB_CASCADE` |
| S12 | File storage API (Django 6.1) | https://docs.djangoproject.com/en/6.1/ref/files/storage/#django.core.files.storage.Storage.delete | 2026-08-28 | The `Storage.delete()` contract the S3 backend implements |
| S13 | django-cleanup 9.0.0 — package metadata, README and `src/django_cleanup/apps.py` | https://pypi.org/project/django-cleanup/ · https://github.com/un1t/django-cleanup · https://raw.githubusercontent.com/un1t/django-cleanup/master/src/django_cleanup/apps.py | 2026-08-28 | Behaviour, signals used, install string, `CleanupConfig.default = True`, select/ignore modes, version, MIT licence |
| S14 | django-storages 1.14.6 — `storages/backends/s3.py` | https://github.com/jschneier/django-storages/blob/master/storages/backends/s3.py · https://pypi.org/project/django-storages/ | 2026-08-28 | `S3Storage.delete()` issues an S3 object delete; version and BSD-3 licence |
