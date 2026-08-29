"""Call resolution, the symbol table and the synthetic edges R1 to R7 pin.

03-verifier.md 1.2 to 1.6 (CG-1 to CG-20), 4.1 (delete modes), 4.2 (SE1, SE4-SE7),
4.5 (enforcing foreign keys) and 4.6 (cascade-token parsing). Each test names the
rule it pins.
"""

from __future__ import annotations

from tests.verify.conftest import call, call_named, edge_between, edges

# --------------------------------------------------------------------------
# 1.5 call resolution
# --------------------------------------------------------------------------
def test_cg1_import_bound_name(graph_of):
    graph = graph_of({
        "helpers.py": "def wipe_user(u):\n    return u\n",
        "app.py": "from helpers import wipe_user\n\n\ndef go(u):\n    wipe_user(u)\n",
    })
    site = call(graph, 5)
    assert (site.outcome, site.rule, site.targets) == ("resolved", "CG-1", ["helpers.wipe_user"])
    assert edge_between(graph, "app.go", "helpers.wipe_user", "call") is not None


def test_cg2_module_level_definition(graph_of):
    graph = graph_of({"app.py": "def helper():\n    pass\n\n\ndef go():\n    helper()\n"})
    assert call(graph, 6).rule == "CG-2"


def test_cg3_single_short_name_is_resolved_and_flagged(graph_of):
    graph = graph_of({
        "other.py": "def only_one():\n    pass\n",
        "app.py": "def go():\n    only_one()\n",
    })
    site = call(graph, 2)
    assert (site.outcome, site.rule, site.reason) == ("resolved", "CG-3", "by_short_name")


def test_cg4_two_definitions_are_ambiguous(graph_of):
    graph = graph_of({
        "a.py": "def twice():\n    pass\n",
        "b.py": "def twice():\n    pass\n",
        "app.py": "def go():\n    twice()\n",
    })
    site = call(graph, 2)
    assert site.outcome == "ambiguous" and site.rule == "CG-4"
    assert sorted(site.targets) == ["a.twice", "b.twice"]
    assert all(e.ambiguous for e in graph.edges if e.src == "app.go" and e.kind == "call")


def test_cg5_unknown_name_is_unresolved(graph_of):
    graph = graph_of({"app.py": "def go():\n    print('x')\n"})
    assert call(graph, 2).outcome == "unresolved"


def test_cg6_intra_repo_module_attribute(graph_of):
    graph = graph_of({
        "pkg/__init__.py": "",
        "pkg/jobs.py": "def purge_user():\n    pass\n",
        "app.py": "from pkg import jobs\n\n\ndef go():\n    jobs.purge_user()\n",
    })
    site = call(graph, 5)
    assert (site.outcome, site.rule, site.targets) == ("resolved", "CG-6", ["pkg.jobs.purge_user"])


def test_cg8_self_then_bases(graph_of):
    graph = graph_of({
        "app.py": """
        class Base:
            def scrub(self):
                pass


        class Child(Base):
            def go(self):
                self.scrub()
        """
    })
    site = call_named(graph, "self.scrub")
    assert (site.rule, site.targets) == ("CG-8", ["app.Base.scrub"])


def test_cg9_and_cg10_class_and_super(graph_of):
    graph = graph_of({
        "app.py": """
        class Base:
            def scrub(self):
                pass


        class Child(Base):
            @classmethod
            def one(cls):
                cls.scrub()

            def two(self):
                super().scrub()
        """
    })
    assert call_named(graph, "cls.scrub").rule == "CG-9"
    supercall = call_named(graph, "super().scrub")
    assert supercall.rule == "CG-10" and supercall.targets == ["app.Base.scrub"]


def test_cg11_unknown_receiver_is_ambiguous(graph_of):
    graph = graph_of({
        "a.py": "def flush():\n    pass\n",
        "b.py": "def flush():\n    pass\n",
        "app.py": "def go(obj):\n    obj.flush()\n",
    })
    site = call(graph, 2)
    assert site.outcome == "ambiguous" and site.rule == "CG-11"


def test_cg12_getattr_sets_dynamic(graph_of):
    graph = graph_of({"app.py": "def go(o, name):\n    getattr(o, name)()\n"})
    assert call_named(graph, "getattr").rule == "CG-12"
    assert graph.symbols["app.go"].dynamic is True


def test_cg13_and_cg14_lambdas(graph_of):
    graph = graph_of({
        "app.py": """
        def helper():
            pass


        cleaner = lambda: helper()


        def go():
            sorted([], key=lambda x: helper())
            cleaner()
        """
    })
    assert graph.symbols["app.cleaner"].kind == "lambda"
    # 1.2: an inline lambda folds into its enclosing scope, so the module-level
    # lambda's own call is attributed to `<module>` and the callback's to `go`.
    inline = [s for s in graph.calls if s.name == "helper" and s.in_lambda]
    assert [s.caller for s in inline] == ["app.<module>", "app.go"]     # CG-13
    assert call_named(graph, "cleaner").targets == ["app.cleaner"]     # CG-14


def test_cg15_reference_is_not_an_edge(graph_of):
    graph = graph_of({
        "storage.py": "def cleanup_user_files(uid):\n    pass\n",
        "app.py": """
        from storage import cleanup_user_files


        def schedule(fn):
            pass


        def go():
            schedule(cleanup_user_files)
        """,
    })
    assert edge_between(graph, "app.go", "storage.cleanup_user_files") is None
    assert [(r.caller, r.target) for r in graph.references
            if r.target == "storage.cleanup_user_files"] == [("app.go", "storage.cleanup_user_files")]


def test_cg20_wildcard_import_falls_through(graph_of):
    graph = graph_of({
        "helpers.py": "def erase_user():\n    pass\n",
        "app.py": "from helpers import *\n\n\ndef go():\n    erase_user()\n",
    })
    site = call(graph, 5)
    assert site.rule == "CG-20" and site.targets == ["helpers.erase_user"]


# --------------------------------------------------------------------------
# 1.1 to 1.4 discovery, symbols, imports, decorators
# --------------------------------------------------------------------------
def test_skip_list_and_always_scan(graph_of):
    graph = graph_of({
        "app/models.py": "X = 1\n",
        "tests/test_thing.py": "X = 1\n",
        "app/migrations/0001_initial.py": "X = 1\n",
        "conftest.py": "X = 1\n",
        "settings.py": "INSTALLED_APPS = ['django_cleanup']\n",
        "app/management/commands/purge_users.py": "X = 1\n",
    })
    assert "app.models" in graph.modules and "settings" in graph.modules
    assert "app.management.commands.purge_users" in graph.modules
    assert "tests.test_thing" not in graph.modules
    assert not any(m.startswith("app.migrations") for m in graph.modules)
    assert graph.skipped["dir:migrations"] == 1


def test_unparsed_file_is_recorded_not_raised(graph_of):
    graph = graph_of({"app.py": "def go(:\n", "ok.py": "X = 1\n"})
    assert graph.unparsed == [{"file": "app.py", "error": "SyntaxError"}]
    assert "ok" in graph.modules


def test_symbol_table_qualnames(graph_of):
    graph = graph_of({
        "pkg/__init__.py": "",
        "pkg/mod.py": """
        class C:
            def m(self):
                def inner():
                    pass
                return inner
        """,
    })
    assert "pkg.mod.C.m" in graph.symbols and "pkg.mod.C.m.inner" in graph.symbols
    assert graph.symbols["pkg.mod.C.m"].kind == "method"
    assert graph.symbols["pkg.mod.C.m.inner"].is_nested is True


def test_relative_and_aliased_imports(graph_of):
    graph = graph_of({
        "pkg/__init__.py": "",
        "pkg/models.py": "class User:\n    pass\n",
        "pkg/sub/__init__.py": "",
        "pkg/sub/view.py": "from ..models import User as U\n\n\ndef go():\n    U()\n",
    })
    assert graph.modules["pkg.sub.view"].imports["U"] == ("symbol", "pkg.models.User")


def test_function_local_import_shadows_module_level(graph_of):
    graph = graph_of({
        "a.py": "def run():\n    pass\n",
        "b.py": "def run():\n    pass\n",
        "app.py": """
        from a import run


        def go():
            from b import run
            run()
        """,
    })
    assert call(graph, 6).targets == ["b.run"]


def test_decorators_are_data_including_receiver_sender(graph_of):
    graph = graph_of({
        "app.py": """
        from django.db.models.signals import post_delete
        from django.dispatch import receiver


        @receiver(post_delete, sender=Comment)
        def handler(sender, instance, **kwargs):
            pass
        """
    })
    decorator = graph.symbols["app.handler"].decorators[0]
    assert decorator.name == "receiver" and decorator.args == ["post_delete"]
    assert decorator.keywords == {"sender": "Comment"} and decorator.line == 5


def test_r27_unmodelled_decorator_is_flagged(graph_of):
    graph = graph_of({"app.py": "@my_retry\ndef go():\n    pass\n"})
    assert graph.symbols["app.go"].wrapped_by_unmodelled_decorator is True


def test_variable_to_model_table(graph_of):
    graph = graph_of({
        "models.py": "class User:\n    __tablename__ = 'users'\n",
        "app.py": """
        from models import User


        def go(session, uid):
            user = session.get(User, uid)
            user.delete()
        """,
    })
    assert graph.symbols["app.go"].var_models == {"user": "models.User"}


def test_to_dict_is_sorted_and_stable(graph_of, mkrepo):
    files = {
        "models.py": "class User:\n    __tablename__ = 'users'\n    email = Column(String)\n",
        "app.py": "from models import User\n\n\ndef delete_user(s, i):\n    s.delete(s.get(User, i))\n",
    }
    first, second = graph_of(files, "one").to_dict(), graph_of(files, "one").to_dict()
    assert first == second
    assert [e["src"] for e in first["edges"]] == sorted(e["src"] for e in first["edges"])


# --------------------------------------------------------------------------
# 4.2 synthetic edges: R1 to R7, and the two decoys
# --------------------------------------------------------------------------
DJ_SETTINGS = "INSTALLED_APPS = ['app']\n"


def django_repo(models_body: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    files = {
        "settings.py": DJ_SETTINGS,
        "app/__init__.py": "",
        "app/models.py": "from django.db import models\n\n\n" + models_body,
        "app/views.py": """
        from .models import Account


        def delete_account(request, pk):
            account = Account.objects.get(pk=pk)
            account.delete()
        """,
    }
    files.update(extra or {})
    return files


PARENT = """
class Account(models.Model):
    email = models.EmailField()

    class Meta:
        db_table = "account"
"""


def test_r1_cascade_is_an_edge(graph_of):
    graph = graph_of(django_repo(PARENT + """

class Post(models.Model):
    body = models.TextField()
    account = models.ForeignKey(Account, on_delete=models.CASCADE)

    class Meta:
        db_table = "post"
"""))
    edge = edge_between(graph, "store:account", "store:post")
    assert edge is not None and (edge.kind, edge.rule) == ("SE1", "R1")
    assert edge.modes == ("model_delete", "queryset_delete")
    assert (edge.file, edge.note) == ("app/models.py", "on_delete=CASCADE")


def test_r2_set_null_is_not_an_edge(graph_of):
    graph = graph_of(django_repo(PARENT + """

class Post(models.Model):
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True)

    class Meta:
        db_table = "post"
"""))
    assert edge_between(graph, "store:account", "store:post") is None


def test_r4_db_cascade_switches_the_mode(graph_of):
    graph = graph_of(django_repo(PARENT + """

class Comment(models.Model):
    account = models.ForeignKey(Account, on_delete=models.DB_CASCADE)

    class Meta:
        db_table = "comment"
"""))
    edge = edge_between(graph, "store:account", "store:comment")
    assert (edge.kind, edge.rule, edge.sets_mode) == ("SE4", "R4", "db_cascade")
    # R4 [S1] [S3]: the rows go, the signals do not fire, so no cleanup edge is
    # admissible once the walk is in `db_cascade`.
    assert all("db_cascade" not in e.modes for e in graph.edges if e.kind in {"SE2", "SE3"})


def test_r5_delete_orphan_alone_is_not_a_delete_cascade(graph_of):
    files = {
        "models.py": """
        from sqlalchemy.orm import declarative_base, relationship

        Base = declarative_base()


        class User(Base):
            __tablename__ = "users"
            email = Column(String)
            posts = relationship("Post", cascade="save-update, merge, delete-orphan")


        class Post(Base):
            __tablename__ = "posts"
            body = Column(String)
        """
    }
    graph = graph_of(files)
    assert edge_between(graph, "store:users", "store:posts") is None


def test_r5_all_token_is_a_delete_cascade(graph_of):
    graph = graph_of({
        "models.py": """
        from sqlalchemy.orm import declarative_base, relationship

        Base = declarative_base()


        class User(Base):
            __tablename__ = "users"
            posts = relationship("Post", cascade="all, delete-orphan")


        class Post(Base):
            __tablename__ = "posts"
        """
    })
    edge = edge_between(graph, "store:users", "store:posts")
    assert (edge.kind, edge.rule, edge.modes) == ("SE5", "R5", ("session_delete",))


def sa_repo(engine: str, fk_extra: str = "", relationship_extra: str = "") -> dict[str, str]:
    return {
        "db.py": f"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import declarative_base, sessionmaker

        engine = create_engine("{engine}")
        SessionLocal = sessionmaker(bind=engine)
        Base = declarative_base()
        """,
        "models.py": f"""
        from sqlalchemy import Column, ForeignKey, Integer, String
        from sqlalchemy.orm import relationship

        from db import Base


        class User(Base):
            __tablename__ = "users"
            email = Column(String)
            posts = relationship("Post"{relationship_extra})


        class Post(Base):
            __tablename__ = "posts"
            body = Column(String)
            user_id = Column(Integer, ForeignKey("users.id"{fk_extra}))
        """,
    }


def test_r6_ondelete_without_enforcing_evidence_is_unverified(graph_of):
    graph = graph_of(sa_repo("sqlite:///app.db", ', ondelete="CASCADE"'))
    assert edge_between(graph, "store:users", "store:posts", "SE7") is None
    assert "r6_unverified" in graph.stores["posts"].flags


def test_r6_ondelete_with_postgres_is_an_edge(graph_of):
    graph = graph_of(sa_repo("postgresql://host/db", ', ondelete="CASCADE"'))
    edge = edge_between(graph, "store:users", "store:posts", "SE7")
    assert edge is not None and edge.rule == "R6" and len(edge.modes) == 7


def test_r6_passive_deletes_on_sqlite_is_not_erased(graph_of):
    graph = graph_of(sa_repo("sqlite:///app.db", ', ondelete="CASCADE"',
                             ", passive_deletes=True"))
    assert edge_between(graph, "store:users", "store:posts", "SE7") is None
    assert "r6_not_erased" in graph.stores["posts"].flags


PRAGMA_LISTENER = """
from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, "connect")
def set_pragma(dbapi_connection, record):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")
"""


def test_r6_sqlite_with_pragma_listener_is_an_edge(graph_of):
    """4.5 [S46]: the listener is evidence on the engine whose module loads it.

    The fixture imports `listeners` from the module that builds the engine, which is
    what registers the listener at runtime; without that import nothing calls it and
    the next test is the case.
    """
    files = sa_repo("sqlite:///app.db", ', ondelete="CASCADE"')
    files["db.py"] += "import listeners" + chr(10)      # what registers it
    files["listeners.py"] = PRAGMA_LISTENER
    graph = graph_of(files)
    assert edge_between(graph, "store:users", "store:posts", "SE7") is not None


def test_r6_pragma_in_a_module_the_engine_never_loads_is_not_evidence(graph_of):
    """4.5, R6 [S46]: enforcement is a property of the connection, not of the tree.

    A repository-wide string scan blessed SE7 for any `PRAGMA foreign_keys=ON` in any
    file -- a listener nothing imports never runs, SQLite keeps foreign keys inert,
    and the child row and its email survive the parent delete. Verdict `unverified`.
    """
    files = sa_repo("sqlite:///app.db", ', ondelete="CASCADE"')
    files["listeners.py"] = PRAGMA_LISTENER
    graph = graph_of(files)
    assert edge_between(graph, "store:users", "store:posts", "SE7") is None
    assert "r6_unverified" in graph.stores["posts"].flags


def test_r6_a_bare_pragma_string_is_not_a_connect_listener(graph_of):
    """4.5: the evidence is a `connect` listener, not the string on its own."""
    files = sa_repo("sqlite:///app.db", ', ondelete="CASCADE"')
    files["db.py"] += '\nNOTE = "PRAGMA foreign_keys=ON"\n'
    graph = graph_of(files)
    assert edge_between(graph, "store:users", "store:posts", "SE7") is None
    assert "r6_unverified" in graph.stores["posts"].flags


def test_r12_receiver_under_a_src_layout_is_connected(graph_of):
    """R12 [S6]: the app label is resolved through the module tree, not concatenated.

    `INSTALLED_APPS = ["blog"]` with the package at `src/blog/` gives the modules
    `src.blog.models` and `src.blog.apps`; seeding the literal strings `blog.models`
    and `blog.apps` matched neither, so every receiver in the repository read
    "imported by nothing" and its file store lost the SE2 edge it has.
    """
    graph = graph_of({
        "settings.py": "INSTALLED_APPS = ['blog']\n",
        "src/__init__.py": "",
        "src/blog/__init__.py": "",
        "src/blog/models.py": """
        from django.db import models
        from django.db.models.signals import post_delete
        from django.dispatch import receiver


        class Photo(models.Model):
            image = models.ImageField(upload_to="p/")

            class Meta:
                db_table = "photo"


        @receiver(post_delete, sender=Photo)
        def drop_image(sender, instance, **kwargs):
            instance.image.delete(save=False)
        """,
    })
    receivers = [r for r in graph.receivers if r.symbol.endswith("drop_image")]
    assert receivers and receivers[0].connected is True and receivers[0].reason == ""
    assert edge_between(graph, "store:photo", "src.blog.models.drop_image", "SE2") is not None


def test_r12_an_app_config_label_names_its_package(graph_of):
    """R12 [S6]: `"blog.apps.BlogConfig"` is the same app as `"blog"`."""
    graph = graph_of({
        "settings.py": "INSTALLED_APPS = ['blog.apps.BlogConfig']\n",
        "blog/__init__.py": "",
        "blog/models.py": """
        from django.db import models
        from django.db.models.signals import post_delete
        from django.dispatch import receiver


        class Photo(models.Model):
            image = models.ImageField(upload_to="p/")

            class Meta:
                db_table = "photo"


        @receiver(post_delete, sender=Photo)
        def drop_image(sender, instance, **kwargs):
            instance.image.delete(save=False)
        """,
    })
    assert edge_between(graph, "store:photo", "blog.models.drop_image", "SE2") is not None


def test_r6_second_unrelated_engine_leaves_it_unverified(graph_of):
    files = sa_repo("sqlite:///app.db", ', ondelete="CASCADE"')
    files["metrics.py"] = """
    from sqlalchemy import create_engine

    analytics_engine = create_engine("postgresql://host/metrics")
    """
    graph = graph_of(files)
    assert edge_between(graph, "store:users", "store:posts", "SE7") is None
    assert "r6_unverified" in graph.stores["posts"].flags


def test_r7_secondary_is_a_session_delete_edge(graph_of):
    graph = graph_of({
        "models.py": """
        from sqlalchemy import Column, Table
        from sqlalchemy.orm import declarative_base, relationship

        Base = declarative_base()
        user_tag = Table("user_tag", Base.metadata, Column("user_id"), Column("tag_id"))


        class User(Base):
            __tablename__ = "users"
            email = Column(String)
            tags = relationship("Tag", secondary=user_tag)


        class Tag(Base):
            __tablename__ = "tags"
        """
    })
    edge = edge_between(graph, "store:users", "store:user_tag", "SE6")
    assert edge is not None and edge.modes == ("session_delete",)


def test_r9_wrong_sender_is_the_decoy(graph_of):
    graph = graph_of(django_repo(PARENT + """

class Photo(models.Model):
    image = models.ImageField(upload_to="p/")
    account = models.ForeignKey(Account, on_delete=models.CASCADE)

    class Meta:
        db_table = "photo"


class Comment(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE)

    class Meta:
        db_table = "comment"
""", {"app/signals.py": """
    from django.db.models.signals import post_delete
    from django.dispatch import receiver

    from .models import Comment


    @receiver(post_delete, sender=Comment)
    def delete_attached_image(sender, instance, **kwargs):
        instance.image.delete(save=False)
    """}))
    assert "photo.image" in graph.stores
    assert edge_between(graph, "store:photo", "app.signals.delete_attached_image") is None
    assert not [e for e in graph.edges if e.dst == "store:photo.image"]


def test_r11_weak_receiver_inside_a_function_is_not_an_edge(graph_of):
    graph = graph_of(django_repo(PARENT + """

class Photo(models.Model):
    image = models.ImageField(upload_to="p/")
    account = models.ForeignKey(Account, on_delete=models.CASCADE)

    class Meta:
        db_table = "photo"
""", {"app/signals.py": """
    from django.db.models.signals import post_delete

    from .models import Photo


    def wire():
        def handler(sender, instance, **kwargs):
            instance.image.delete(save=False)

        post_delete.connect(handler, sender=Photo)
    """}))
    receiver = graph.receivers[0]
    assert receiver.nested is True and receiver.weak is True
    assert not edges(graph, "SE2")


def test_r10_bare_django_cleanup_label_activates(graph_of):
    files = django_repo(PARENT + """

class Photo(models.Model):
    image = models.ImageField(upload_to="p/")
    account = models.ForeignKey(Account, on_delete=models.CASCADE)

    class Meta:
        db_table = "photo"
""")
    files["settings.py"] = "INSTALLED_APPS = ['app', 'django_cleanup']\n"
    graph = graph_of(files)
    edge = edge_between(graph, "store:photo", "store:photo.image", "SE3")
    assert edge is not None and edge.rule == "R10"


def test_r10_selected_config_is_opt_in(graph_of):
    files = django_repo(PARENT + """

class Photo(models.Model):
    image = models.ImageField(upload_to="p/")

    class Meta:
        db_table = "photo"
""")
    files["settings.py"] = "INSTALLED_APPS = ['app', 'django_cleanup.apps.CleanupSelectedConfig']\n"
    graph = graph_of(files)
    assert edge_between(graph, "store:photo", "store:photo.image", "SE3") is None


# --------------------------------------------------------------------------
# 1.2 and 1.5: what must NOT resolve
# --------------------------------------------------------------------------
def test_cg6_queryset_chain_off_a_class_is_not_the_override(graph_of):
    """R14, 4.2: `Avatar.objects.filter(...).delete()` never runs `Avatar.delete` [S3].

    Resolving a receiver that merely *starts* with an imported class gave the model's
    own override a non-ambiguous call edge admissible in every mode, so the bytes read
    `erased` on a queryset path -- 4.2's own worked example and test 27.
    """
    graph = graph_of({
        "app/__init__.py": "",
        "app/models.py": """
        from django.db import models
        import boto3

        s3 = boto3.client("s3")


        class Avatar(models.Model):
            image = models.ImageField(upload_to="a/")

            def delete(self, *a, **k):
                s3.delete_object(Bucket="avatars", Key=str(self.pk))
                return super().delete(*a, **k)
        """,
        "app/views.py": """
        from app.models import Avatar


        def close_account(request):
            Avatar.objects.filter(user=request.user).delete()
        """,
    })
    site = call_named(graph, "Avatar.objects.filter().delete")
    assert site.outcome == "ambiguous" and site.rule == "CG-11"
    edge = edge_between(graph, "app.views.close_account", "app.models.Avatar.delete")
    assert edge is not None and edge.ambiguous is True


def test_cg6_direct_class_receiver_still_resolves(graph_of):
    graph = graph_of({
        "app/__init__.py": "",
        "app/models.py": "class Avatar:\n    def delete(self):\n        pass\n",
        "app/views.py": "from app.models import Avatar\n\n\ndef go(obj):\n    Avatar.delete(obj)\n",
    })
    site = call_named(graph, "Avatar.delete")
    assert (site.outcome, site.rule, site.targets) == (
        "resolved", "CG-6", ["app.models.Avatar.delete"])


def test_a_conditional_redefinition_makes_every_call_ambiguous(graph_of):
    """1.2: both definitions are kept and every call to the name is ambiguous.

    The last body wins the symbol table, so a resolved edge credits the surviving
    symbol with the dead body's primitive: `delete_account -> impl.scrub_user ->
    store:uploads` for a bucket the surviving definition never touches.
    """
    graph = graph_of({
        "impl.py": """
        import boto3

        FAST = True
        s3 = boto3.client("s3")

        if FAST:
            def scrub_user(uid):
                s3.delete_object(Bucket="uploads", Key=uid)
        else:
            def scrub_user(uid):
                pass
        """,
        "api.py": "from impl import scrub_user\n\n\ndef delete_account(uid):\n"
                  "    scrub_user(uid)\n",
    })
    site = call(graph, 5, "api.py")
    assert site.outcome == "ambiguous" and site.rule == "CG-1"
    assert site.reason == "conditional redefinition of impl.scrub_user (1.2)"
    assert edge_between(graph, "api.delete_account", "impl.scrub_user").ambiguous is True


def test_an_ambiguous_call_with_no_target_is_still_recorded(graph_of):
    """CG-8 against an external base: no edge, so 6.1 row 8 needs it listed."""
    graph = graph_of({"views.py": """
    from rest_framework.views import APIView


    class AccountView(APIView):
        def delete_account(self, request):
            self.drop(request.user)
    """})
    site = call_named(graph, "self.drop")
    assert (site.outcome, site.rule, site.targets) == ("ambiguous", "CG-8", [])
    assert [c.dotted for c in graph.unresolved] == ["self.drop"]


# --------------------------------------------------------------------------
# 4.5 and R12: the two facts that must stay scoped to what names them
# --------------------------------------------------------------------------
def test_r6_engine_url_is_read_in_the_engines_own_module(graph_of):
    """4.5, R6 [S15]: `create_engine(DATABASE_URL)` reads *this* module's name.

    The name was resolved by a repository-wide scan, first module in alphabetical
    order winning, so an unrelated analytics `config.DATABASE_URL` overrode `db.py`'s
    own `sqlite:///app.db`, SE7 was added in every mode and the child rows read
    `erased` on a database with foreign keys off -- 4.5's own worked example, and the
    transcript the research calls the worst result in the document.
    """
    files = sa_repo("sqlite:///app.db", ', ondelete="CASCADE"')
    files["db.py"] = """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import declarative_base, sessionmaker

    DATABASE_URL = "sqlite:///app.db"
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    Base = declarative_base()
    """
    files["config.py"] = 'DATABASE_URL = "postgresql://host/metrics"' + chr(10)
    graph = graph_of(files)
    assert [e["url"] for e in graph.settings["engines"]] == ["sqlite:///app.db"]
    assert edge_between(graph, "store:users", "store:posts", "SE7") is None
    assert "r6_unverified" in graph.stores["posts"].flags


def _vendored_receiver(models_path: str) -> dict[str, str]:
    files = {
        "settings.py": "INSTALLED_APPS = ['blog']\n",
        "blog/__init__.py": "",
        "blog/models.py": """
        from django.db import models


        class Photo(models.Model):
            image = models.ImageField(upload_to="p/")

            class Meta:
                db_table = "photo"
        """,
        models_path: """
        from django.db.models.signals import post_delete
        from django.dispatch import receiver

        from blog.models import Photo


        @receiver(post_delete, sender=Photo)
        def drop_image(sender, instance, **kwargs):
            instance.image.delete(save=False)
        """,
    }
    package = models_path.rsplit("/", 1)[0].split("/")
    for depth in range(1, len(package) + 1):
        files["/".join(package[:depth]) + "/__init__.py"] = ""
    return files


def test_r12_a_vendored_models_module_is_not_an_installed_app(graph_of):
    """R12 [S6]: Django loads `<package>.models`, not every module named `models`.

    Matching the app label by suffix beside an exact match seeded an uninstalled
    `vendor/blog/models.py`, so a receiver Django never connects read `connected` and
    its file store read `erased` on a signal that never fires.
    """
    graph = graph_of(_vendored_receiver("vendor/blog/models.py"))
    found = [r for r in graph.receivers if r.symbol.endswith("drop_image")]
    assert found and found[0].connected is False
    assert edge_between(graph, "store:photo", "vendor.blog.models.drop_image", "SE2") is None


def test_r12_a_models_module_nested_under_the_app_is_not_loaded(graph_of):
    """R12 [S6]: one level. `blog/vendor/plugin/models.py` is not `blog.models`."""
    graph = graph_of(_vendored_receiver("blog/vendor/plugin/models.py"))
    found = [r for r in graph.receivers if r.symbol.endswith("drop_image")]
    assert found and found[0].connected is False
    assert edge_between(graph, "store:photo",
                        "blog.vendor.plugin.models.drop_image", "SE2") is None


def test_r14_a_name_bound_to_a_queryset_is_not_an_instance(graph_of):
    """R14 [S3], 4.2: `qs = M.objects.filter(...)` then `qs.delete()` is a bulk delete.

    `binding.var_models` binds a name to a model from any assignment that mentions the
    class, with no record of whether the binding is an instance or a queryset, and the
    delete receiver carries no dot -- so the rule entry's `model_delete` stood, SE8
    became admissible, and 4.2's own worked example written over two lines credited
    the `Model.delete()` override for bytes still on disk.
    """
    graph = graph_of({
        "settings.py": DJ_SETTINGS,
        "app/__init__.py": "",
        "app/models.py": """
        from django.db import models


        class Avatar(models.Model):
            image = models.ImageField(upload_to="a/")

            class Meta:
                db_table = "avatar"

            def delete(self, *a, **k):
                self.image.delete(save=False)
                return super().delete(*a, **k)
        """,
        "app/views.py": """
        from app.models import Avatar


        def close_account(request):
            qs = Avatar.objects.filter(user=request.user)
            qs.delete()
        """,
    })
    edge = edge_between(graph, "app.views.close_account", "store:avatar", "SE12")
    assert edge is not None and (edge.rule, edge.sets_mode) == ("R15", "queryset_delete")
    verdicts = _verdicts(graph)
    assert verdicts["avatar.image"] != "erased"


def _verdicts(graph) -> dict[str, str]:
    from art30.verify.reach import verdicts as _decide

    return {k: v.verdict for k, v in _decide(graph).items()}
