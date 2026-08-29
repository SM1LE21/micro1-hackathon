"""Store detection: what the verifier sees before it reads the record.

03-verifier.md 3.1 (relational, Django and SQLAlchemy, and the `FileField` second
store of R8) plus the orchestration of 3.2-3.8, which live in `services.py`, and
the guard list of 3.9. Detection is name and shape matching over the AST plus the
rule data; there is no type inference (NON-GOALS).
"""

from __future__ import annotations

from art30.verify import imports as importmap
from art30.verify import services
from art30.verify.context import Ctx
from art30.verify.entities import ClassInfo
from art30.verify.findings import Cite, Graph, Relation, Store, StoreField
from art30.verify.rules import RuleSet, norm

DJANGO_BASES = ("Model", "models.Model", "django.db.models.Model")
SUBJECT_BASES = ("AbstractUser", "AbstractBaseUser")


def detect_stores(graph: Graph, rules: RuleSet, imap: importmap.ImportMap) -> None:
    ctx = Ctx(graph, rules, imap)
    _relational(ctx)
    services.detect(ctx)
    _subject_links(ctx)
    _guard(ctx)
    graph.stores = dict(sorted(graph.stores.items()))
    graph.relations.sort(key=lambda r: (r.file, r.line, r.child, r.parent))
    for store in graph.stores.values():
        store.fields.sort(key=lambda f: (f.line, f.name))


# ---------------------------------------------------------------------------
# 3.1 relational
# ---------------------------------------------------------------------------
def _is_django_model(ctx: Ctx, cls: ClassInfo, seen: set[str] | None = None) -> bool:
    seen = seen or set()
    if cls.name in seen:
        return False
    seen.add(cls.name)
    for base in cls.bases:
        if base in DJANGO_BASES or base.split(".")[-1] in {"Model"} and "models" in base:
            return True
        if base.split(".")[-1] in SUBJECT_BASES:
            return True
        dotted = ctx.imap.resolve_dotted(cls.module, None, base)
        if dotted in DJANGO_BASES or dotted.endswith("db.models.Model"):
            return True
        parent = ctx.graph.classes.get(dotted)
        if parent is not None and _is_django_model(ctx, parent, seen):
            return True
    return False


def _is_declarative(ctx: Ctx, cls: ClassInfo) -> bool:
    """3.1: `__tablename__` in the body, `table=True`, or a resolvable declarative base."""
    detect = ctx.rules.kind("relational")["detect"]["sqlalchemy_declarative"]
    names = set(detect["base"])
    if any(a.target == "__tablename__" for a in cls.body):
        return True
    if norm(cls.keywords.get("table", "")) == "true":
        return True
    return any(ctx.imap.resolve_dotted(cls.module, None, base) in ctx.declarative
               or base in names or base.split(".")[-1] in names for base in cls.bases)


def _declares_a_table(ctx: Ctx, cls: ClassInfo) -> bool:
    """3.1: a class with neither `__tablename__` nor a resolvable declarative base is
    not a store, and a base that declares no column of its own is not one either --
    the filter that removed `rows:Base` from every SQLAlchemy repository (11, finding 1).
    """
    if any(a.target == "__tablename__" for a in cls.body):
        return True
    if norm(cls.keywords.get("table", "")) == "true":
        return True
    if any(base.split(".")[-1] == "SQLModel" for base in cls.bases):
        return False        # SQLModel: only `table=True` declares a table [S43]
    calls = set(ctx.rules.kind("relational")["detect"]["sqlalchemy_declarative"]["field_calls"])
    return any(decl.short_call in calls for decl in cls.fields)


def _table_name(ctx: Ctx, cls: ClassInfo) -> str:
    meta = ctx.graph.classes.get(f"{cls.name}.Meta")
    if meta is not None:
        for assign in meta.body:
            if assign.target == "db_table" and assign.value_kind == "literal":
                return assign.value_repr
    for assign in cls.body:
        if assign.target == "__tablename__" and assign.value_kind == "literal":
            return assign.value_repr
    return norm(cls.short)


def _core_tables(ctx: Ctx) -> dict[str, str]:
    """3.1 Core: `Table("name", metadata, Column(...))`. The first string is the store;
    an association table reached by `secondary=` is a store in its own right (R7 [S18])."""
    found: dict[str, str] = {}
    calls = set(ctx.rules.kind("relational")["detect"]["sqlalchemy_core_table"]["call"])
    for module in sorted(ctx.graph.modules):
        info = ctx.graph.modules[module]
        for assign in info.assigns:
            if assign.value_kind != "call" or assign.value_repr.split(".")[-1] not in calls:
                continue
            if not assign.keys:
                continue
            name = assign.keys[0]
            store = Store(id=name, kind="relational", name=name, identity=name,
                          declared_at=Cite(info.file, assign.line))
            for column in assign.keys[1:]:
                store.fields.append(StoreField(name=column, file=info.file,
                                               line=assign.line, declared="Column"))
            ctx.add(store)
            found[assign.target] = name
    return found


def _base_classes(ctx: Ctx, cls: ClassInfo, base: str) -> list[ClassInfo]:
    """A base as written, resolved to intra-repo classes (as `_is_django_model` does)."""
    found: list[ClassInfo] = []
    for candidate in (ctx.imap.resolve_dotted(cls.module, None, base),
                      f"{cls.module}.{base}" if cls.module else base):
        parent = ctx.graph.classes.get(candidate)
        if parent is not None and parent not in found:
            found.append(parent)
    return found


def _fields_of(ctx: Ctx, cls: ClassInfo, seen: set[str] | None = None) -> list:
    """3.1: the class's own declarations, then its intra-repo bases', deduplicated.

    A `FileField` declared in a mixin that is not itself a model is still a column of
    the concrete model, and reading `cls.fields` alone left R8's second store uncreated:
    nothing for django-cleanup (SE3) or a receiver (SE2) to point at, so the row and the
    bytes shared one fate. Each declaration keeps its own file:line (the mixin's).
    """
    seen = seen or set()
    if cls.name in seen:
        return []
    seen.add(cls.name)
    found = list(cls.fields)
    taken = {decl.target for decl in found}
    for base in cls.bases:
        for parent in _base_classes(ctx, cls, base):
            for decl in _fields_of(ctx, parent, seen):
                if decl.target not in taken:
                    taken.add(decl.target)
                    found.append(decl)
    return found


def _relational(ctx: Ctx) -> None:
    detect = ctx.rules.kind("relational")["detect"]
    core = _core_tables(ctx)
    django = detect["django_model"]
    auth_model = (ctx.graph.settings.get("AUTH_USER_MODEL") or "").split(".")[-1]
    tables: dict[str, str] = {}                      # class qual -> store id
    for qual, cls in sorted(ctx.graph.classes.items()):
        is_django = _is_django_model(ctx, cls)
        if not is_django and not _is_declarative(ctx, cls):
            continue
        if not is_django and not _declares_a_table(ctx, cls):
            continue                                 # 3.1: a declarative Base is not a store
        table = _table_name(ctx, cls)
        store = Store(id=table, kind="relational", name=table, model=qual,
                      declared_at=Cite(cls.file, cls.line), identity=table)
        tables[qual] = table
        for decl in _fields_of(ctx, cls):
            short = decl.short_call
            if short in set(django["relation_calls"]) or short == "relationship":
                continue
            if short in set(django["file_field_calls"]):
                _file_store(ctx, cls, decl)
                continue
            if short.endswith("Field") or short in set(
                detect["sqlalchemy_declarative"]["field_calls"]
            ):
                flags = ["opaque_container"] if short in set(
                    django["opaque_container_calls"]
                ) or short == "JSON" else []
                store.fields.append(StoreField(name=decl.target, file=decl.file,
                                               line=decl.line, declared=short, flags=flags))
        store.subject_root = _is_subject_root(ctx, cls, store, auth_model)
        ctx.add(store)
    ctx.core_tables = core
    for qual, cls in sorted(ctx.graph.classes.items()):
        if qual in tables:
            _relations(ctx, cls, tables)


def _is_subject_root(ctx: Ctx, cls: ClassInfo, store: Store, auth_model: str) -> bool:
    """3.1 [S5]: `AbstractUser`, `AUTH_USER_MODEL`, or a subject name with a strong field."""
    if any(base.split(".")[-1] in SUBJECT_BASES for base in cls.bases):
        return True
    if auth_model and norm(auth_model) == norm(cls.short):
        return True
    named = ctx.rules.subject_root_name(cls.short) or ctx.rules.subject_root_name(store.name)
    return named and any(ctx.rules.guard_hit(f.name) == "strong" for f in store.fields)


def _relations(ctx: Ctx, cls: ClassInfo, tables: dict[str, str]) -> None:
    """R1-R7: foreign keys and relationships, read as written."""
    child = tables[cls.name]
    for decl in cls.fields:
        short = decl.short_call
        if short in {"ForeignKey", "OneToOneField", "ManyToManyField"} and decl.raw:
            target = _target_table(ctx, cls, decl.raw[0] or decl.kwraw.get("to", ""), tables)
            token = (decl.keywords.get("on_delete").value if "on_delete" in decl.keywords else "")
            if target:
                ctx.graph.relations.append(Relation(
                    parent=target, child=child, kind="fk", token=token.split(".")[-1],
                    file=decl.file, line=decl.line, field_name=decl.target))
        elif short == "relationship":
            arg = decl.args[0].value if decl.args else decl.kwraw.get("argument", "")
            target = _target_table(ctx, cls, arg, tables)
            cascade = decl.keywords["cascade"].value if "cascade" in decl.keywords else ""
            secondary = decl.kwraw.get("secondary", "")
            passive = norm(decl.keywords["passive_deletes"].value) == "true" if \
                "passive_deletes" in decl.keywords else False
            if target:
                ctx.graph.relations.append(Relation(
                    parent=child, child=target, kind="relationship", token=cascade,
                    passive_deletes=passive, file=decl.file, line=decl.line,
                    field_name=decl.target))
            if secondary:
                assoc = (_target_table(ctx, cls, secondary, tables)
                         or ctx.core_tables.get(secondary.split(".")[-1], "")
                         or _table_id(ctx, secondary.split(".")[-1]))
                ctx.graph.relations.append(Relation(
                    parent=child, child=assoc, kind="secondary", token=secondary,
                    file=decl.file, line=decl.line, field_name=decl.target))
        else:
            fk = decl.find("ForeignKey")
            if fk is not None and fk.args:
                target = _table_id(ctx, str(fk.args[0].value).split(".")[0])
                ondelete = fk.keywords["ondelete"].value if "ondelete" in fk.keywords else ""
                ctx.graph.relations.append(Relation(
                    parent=target, child=child, kind="fk", ondelete=ondelete,
                    file=decl.file, line=decl.line, field_name=decl.target))


def _table_id(ctx: Ctx, table: str) -> str:
    """`ForeignKey("users.id")` names a table; match it to a detected store's id."""
    if table in ctx.graph.stores:
        return table
    for store in sorted(ctx.graph.stores.values(), key=lambda s: s.id):
        if store.kind == "relational" and norm(store.id) == norm(table):
            return store.id
    return table


def _target_table(ctx: Ctx, cls: ClassInfo, written: str, tables: dict[str, str]) -> str:
    if not written:
        return ""
    name = str(written).strip("'\"").split(".")[-1]
    dotted = ctx.imap.resolve_dotted(cls.module, None, name)
    if dotted in tables:
        return tables[dotted]
    local = f"{cls.module}.{name}" if cls.module else name
    if local in tables:
        return tables[local]
    for qual, table in tables.items():
        if qual.split(".")[-1] == name:
            return table
    return ""


def _file_store(ctx: Ctx, cls: ClassInfo, decl) -> None:
    """R8 [S1] [S2]: the row and the bytes have different fates, so two stores."""
    store_id = f"{norm(cls.short)}.{decl.target}"
    upload_to = decl.keywords["upload_to"].value if "upload_to" in decl.keywords else ""
    store = Store(id=store_id, kind="object_storage", name=store_id, model=cls.name,
                  declared_at=Cite(decl.file, decl.line),
                  subject_link=Cite(decl.file, decl.line),
                  identity=upload_to or store_id, flags=["django_file_field"])
    store.fields.append(StoreField(name=decl.target, file=decl.file, line=decl.line,
                                   declared=decl.short_call))
    ctx.add(store)


# ---------------------------------------------------------------------------
# subject links and the 3.9 guard
# ---------------------------------------------------------------------------
def _subject_links(ctx: Ctx) -> None:
    roots = {s.id for s in ctx.graph.stores.values() if s.subject_root}
    for store in ctx.graph.stores.values():
        if store.subject_link is not None:
            continue
        if store.kind != "relational":
            continue
        if store.subject_root:
            store.subject_link = store.declared_at
            continue
        # The foreign key on the child is the citation that ties the row to the
        # subject; a `relationship()` on the parent names the same pair one class up.
        for wanted in ("fk", "secondary", "relationship"):
            for relation in ctx.graph.relations:
                if relation.kind != wanted:
                    continue
                if relation.child == store.id and relation.parent in roots:
                    store.subject_link = Cite(relation.file, relation.line)
                    break
                if relation.parent == store.id and relation.child in roots:
                    store.subject_link = Cite(relation.file, relation.line)
                    break
            if store.subject_link is not None:
                break


def _guard(ctx: Ctx) -> None:
    """3.9, the completeness guard only: never a category, never a verdict."""
    for store in ctx.graph.stores.values():
        hits = {ctx.rules.guard_hit(f.name) for f in store.fields}
        linked = store.subject_link is not None or ctx.rules.subject_word(store.name)
        if "strong" in hits:
            store.guard = "strong"
        elif "qualified" in hits and linked:
            store.guard = "qualified"
