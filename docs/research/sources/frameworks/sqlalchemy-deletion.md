# Source excerpts — SQLAlchemy 2.0 deletion semantics

Version under study: **SQLAlchemy 2.0.52** (latest on PyPI, uploaded 2026-08-11; MIT). Quotes taken from the documentation source at branch `rel_2_0` and from the docstrings that generate the API reference; the `cascades` and `dml` pages are byte-identical between `rel_2_0` and `main`. [S45]

---

## 1. The default cascade does not delete children

Context: the top of the cascade chapter. The default is the setting most models never override.

> The default value of `relationship.cascade` is `save-update, merge`. The typical alternative setting for this parameter is either `all` or more commonly `all, delete-orphan`. The `all` symbol is a synonym for `save-update, merge, refresh-expire, expunge, delete`, and using it in conjunction with `delete-orphan` indicates that the child object should follow along with its parent in all cases, and be deleted once it is no longer associated with that parent.

[S15]

Context: what `delete` cascade does, and what happens without it. The second half is the failure the erasure table has to catch.

> The `delete` cascade indicates that when a "parent" object is marked for deletion, its related "child" objects should also be marked for deletion.

> Alternatively, if our `User.addresses` relationship does *not* have `delete` cascade, SQLAlchemy's default behavior is to instead de-associate `address1` and `address2` from `user1` by setting their foreign key reference to `NULL`.

[S15]

The `cascade=` string is a comma-separated token list and has to be read as one. `delete-orphan` contains the letters of `delete` and is not a delete cascade: the quote above names `delete` and `all` as the symbols that matter, and `all` is spelled out as `save-update, merge, refresh-expire, expunge, delete`. Setting `cascade="save-update, merge, delete-orphan"` and calling `Session.delete()` on the parent leaves the children in place; SQLAlchemy emits the warning `The 'delete-orphan' cascade option requires 'delete'.` and continues. Transcript in `framework-behaviour.md` section 4.3. A substring implementation of the rule renders that store `erased` while the rows and their emails survive.

Context: the session guide states the same rule as a bullet, and adds the non-nullable case. The scope of the whole list matters and is set by the two sentences that introduce it — this is a list about `Session.delete()`, not about deletion in general.

> There are various important behaviors related to the `Session.delete()` operation, particularly in how relationships to other objects and collections are handled.

> There's more information on how this works in the section Cascades, but in general the rules are:

> Rows that correspond to mapped objects that are related to a deleted object via the `relationship()` directive are **not deleted by default**. If those objects have a foreign key constraint back to the row being deleted, those columns are set to NULL. This will cause a constraint violation if the columns are non-nullable.

> Rows that are in tables linked as "many-to-many" tables, via the `relationship.secondary` parameter, **are** deleted in all cases when the object they refer to is deleted.

[S18]

So "in all cases" is bounded by the introduction: all cases of `Session.delete()`. On a bulk `session.execute(delete(Model))` the ORM does no in-Python cascade at all [S16], and the association rows stay. Confirmed by execution — see `docs/research/framework-behaviour.md` section 4.3, where the same `secondary` table is emptied by `Session.delete()` and left intact by the bulk statement.

Context: `Session.delete()` itself. Deletion is deferred to flush, which is why events are flush events.

> Mark an instance as deleted.
>
> The object is assumed to be either persistent or detached when passed; after the method is called, the object will remain in the persistent state until the next flush proceeds. […] When the next flush proceeds, the object will move to the deleted state, indicating a `DELETE` statement was emitted for its row within the current transaction.

[S19]

---

## 2. `passive_deletes=True` plus `ondelete="CASCADE"`

Context: the ORM defers to the database's foreign-key cascade. The children are deleted by the database, and the ORM never loads them.

> There is then an additional option on `relationship()` which indicates the degree to which the ORM should try to run DELETE/UPDATE operations on related rows itself, vs. how much it should rely upon expecting the database-side FOREIGN KEY constraint cascade to handle the task; this is the `relationship.passive_deletes` parameter and it accepts options `False` (the default), `True` and `"all"`.

[S15]

Context: the step-by-step for `cascade="all, delete", passive_deletes=True` with `ForeignKey(..., ondelete="CASCADE")`.

> 2. When the `Session` next flushes changes to the database, all of the **currently loaded** items within the `my_parent.children` collection are deleted by the ORM, meaning a `DELETE` statement is emitted for each record.
>
> 3. If the `my_parent.children` collection is **unloaded**, then no `DELETE` statements are emitted. If the `relationship.passive_deletes` flag were **not** set on this `relationship()`, then a `SELECT` statement for unloaded `Child` objects would have been emitted.
>
> 4. A `DELETE` statement is then emitted for the `my_parent` row itself.
>
> 5. The database-level `ON DELETE CASCADE` setting ensures that all rows in `child` which refer to the affected row in `parent` are also deleted.

[S15]

> Under this behavior, SQLAlchemy only emits DELETE for those rows that are already locally present in the `Session`; for any collections that are unloaded, it leaves them to the database to handle, rather than emitting a SELECT for them.

[S15]

Context: the schema-side argument that carries the actual `ON DELETE` clause. This string is the only place the cascade is written down.

> `ondelete`: Optional string. If set, emit ON DELETE <value> when issuing DDL for this constraint. Typical values include CASCADE, SET NULL and RESTRICT. Some dialects may allow for additional syntaxes.

[S19]

Context: the prerequisite. On SQLite, foreign keys are off unless the application turns them on, so the same code erases on Postgres and leaks on SQLite.

> To use "ON DELETE CASCADE", the underlying database engine must support `FOREIGN KEY` constraints and they must be enforcing […] When using SQLite, foreign key support must be enabled explicitly.

[S15]

Context: the SQLite dialect page states the default and gives the only supported way to change it. This is the string a verifier has to look for before it can treat `ondelete="CASCADE"` as an edge.

> SQLite supports FOREIGN KEY syntax when emitting CREATE statements for tables, however by default these constraints have no effect on the operation of the table.
>
> Constraint checking on SQLite has three prerequisites:
>
> * At least version 3.6.19 of SQLite must be in use
> * The SQLite library must be compiled without the SQLITE_OMIT_FOREIGN_KEY or SQLITE_OMIT_TRIGGER symbols enabled.
> * The `PRAGMA foreign_keys = ON` statement must be emitted on all connections before use – including the initial call to `MetaData.create_all()`.
>
> SQLAlchemy allows for the PRAGMA statement to be emitted automatically for new connections through the usage of events:
>
> ```python
> from sqlalchemy.engine import Engine
> from sqlalchemy import event
>
> @event.listens_for(Engine, "connect")
> def set_sqlite_pragma(dbapi_connection, connection_record):
>     # the sqlite3 driver will not set PRAGMA foreign_keys
>     # if autocommit=False; set to True temporarily
>     ac = dbapi_connection.autocommit
>     dbapi_connection.autocommit = True
>     cursor = dbapi_connection.cursor()
>     cursor.execute("PRAGMA foreign_keys=ON")
>     cursor.close()
>     # restore previous autocommit setting
>     dbapi_connection.autocommit = ac
> ```

[S46]

Measured, not just documented: on a default `create_engine("sqlite://")` the connection reports `PRAGMA foreign_keys = 0`, and a `cascade="all, delete", passive_deletes=True` relationship over `ForeignKey(..., ondelete="CASCADE")` deletes the parent while the child row keeps its email. Transcript in `framework-behaviour.md` section 4.3. `passive_deletes=True` makes this the worst configuration rather than a curiosity: it is the setting that stops the ORM emitting the child `DELETE`, so when the engine also declines, nothing deletes the row.

Context: `passive_deletes="all"` — the ORM stops nulling the FK entirely.

> The other, more special case way is to set the `relationship.passive_deletes` flag to the string `"all"`. This has the effect of entirely disabling SQLAlchemy's behavior of setting the foreign key column to NULL, and a DELETE will be emitted for the parent row without any affect on the child row, even if the child row is present in memory.

[S15]

---

## 3. Bulk delete bypasses ORM cascades and unit-of-work events

Context: the warning at the end of the `delete` cascade section.

> Note that the ORM's "delete" and "delete-orphan" behavior applies **only** to the use of the `Session.delete()` method to mark individual ORM instances for deletion within the unit of work process. It does **not** apply to "bulk" deletes, which would be emitted using the `delete()` construct

[S15]

Context: the caveat list for ORM-enabled UPDATE and DELETE.

> The ORM-enabled UPDATE and DELETE features bypass ORM unit of work automation in favor of being able to emit a single UPDATE or DELETE statement that matches multiple rows at once without complexity.
>
> * The operations do not offer in-Python cascading of relationships - it is assumed that ON UPDATE CASCADE and/or ON DELETE CASCADE is configured for any foreign key references which require it, otherwise the database may emit an integrity violation if foreign key references are being enforced.

> * In order to intercept ORM-enabled UPDATE and DELETE operations with event handlers, use the `SessionEvents.do_orm_execute()` event.

[S16]

---

## 4. `before_delete` / `after_delete` and when they do not fire

Context: the mapper-level flush events. The note is the operative sentence.

> Receive an object instance before a DELETE statement is emitted corresponding to that instance.
>
> **Note:** this event **only** applies to the session flush operation and does **not** apply to the ORM DML operations described at [ORM-Enabled INSERT, UPDATE and DELETE statements]. To intercept ORM DML events, use `SessionEvents.do_orm_execute()`.

[S17]

The same note heads `after_delete`. [S17]

Both events therefore miss: bulk `session.execute(delete(Model))`, any `connection.execute(text("DELETE ..."))`, and children removed by a database-level `ON DELETE CASCADE` under `passive_deletes=True` (those rows are deleted by the database, and the ORM never sees them).

---

## 5. SQLModel and Flask-SQLAlchemy are the same machinery

Context: SQLModel's own one-line description.

> SQLModel is based on Python type annotations, and powered by Pydantic and SQLAlchemy.

[S20]

Its session class is a direct subclass, `sqlmodel/orm/session.py`:

> ```python
> from sqlalchemy.orm import Session as _Session
> ...
> class Session(_Session):
> ```

[S43]

Context: Flask-SQLAlchemy's `db.session`.

> A `sqlalchemy.orm.scoping.scoped_session` that creates instances of `Session` scoped to the current Flask application context. The session will be removed, returning the engine connection to the pool, when the application context exits.

[S21]

and the `Session` class it creates:

> A SQLAlchemy `Session` class that chooses what engine to use based on the bind key associated with the metadata associated with the thing being queried.

[S21]

So every rule in sections 1–4 applies unchanged to a SQLModel or Flask-SQLAlchemy repository. The verifier needs no separate rule set for either, only to recognise the import names.

---

## Sources

| ID | Title | URL | Accessed | Used for |
|---|---|---|---|---|
| S15 | Cascades — SQLAlchemy 2.0 ORM documentation | https://docs.sqlalchemy.org/en/20/orm/cascades.html | 2026-08-28 | Default cascade, `delete` cascade, FK-set-NULL default, `passive_deletes`, bulk-delete warning |
| S16 | ORM-Enabled INSERT, UPDATE and DELETE statements — SQLAlchemy 2.0 | https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html#important-notes-and-caveats-for-orm-enabled-update-and-delete | 2026-08-28 | Bulk DML bypasses unit of work and in-Python cascades |
| S17 | `MapperEvents.before_delete` / `after_delete` — SQLAlchemy 2.0 ORM events | https://docs.sqlalchemy.org/en/20/orm/events.html#sqlalchemy.orm.MapperEvents.before_delete | 2026-08-28 | Flush-only scope of the delete events |
| S18 | Session Basics — Deleting — SQLAlchemy 2.0 | https://docs.sqlalchemy.org/en/20/orm/session_basics.html#deleting | 2026-08-28 | Related rows not deleted by default; many-to-many rows always deleted |
| S19 | `Session.delete()` and `ForeignKey.ondelete` — SQLAlchemy 2.0 API reference | https://docs.sqlalchemy.org/en/20/orm/session_api.html#sqlalchemy.orm.Session.delete · https://docs.sqlalchemy.org/en/20/core/constraints.html#sqlalchemy.schema.ForeignKey.params.ondelete | 2026-08-28 | Deferred-to-flush semantics; the `ondelete` DDL string |
| S20 | SQLModel documentation home | https://sqlmodel.tiangolo.com/ | 2026-08-28 | SQLModel is powered by SQLAlchemy |
| S21 | Flask-SQLAlchemy 3.1 API reference — `SQLAlchemy.session` | https://flask-sqlalchemy.readthedocs.io/en/stable/api/ | 2026-08-28 | `db.session` is a SQLAlchemy scoped session |
| S43 | SQLModel source — `sqlmodel/orm/session.py` | https://github.com/fastapi/sqlmodel/blob/main/sqlmodel/orm/session.py | 2026-08-28 | `Session` subclasses `sqlalchemy.orm.Session` |
| S45 | SQLAlchemy release metadata on PyPI | https://pypi.org/pypi/SQLAlchemy/json | 2026-08-28 | Current version 2.0.52, MIT |
| S46 | SQLite — Foreign Key Support, SQLAlchemy 2.0 dialect documentation | https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#foreign-key-support | 2026-08-28 | FK constraints inert by default on SQLite; the three prerequisites; the `PRAGMA foreign_keys=ON` connect-listener recipe |
