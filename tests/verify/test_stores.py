"""Store detection (03-verifier.md section 3) and the completeness-guard list (3.9).

Every store kind of the contract's closed set, the `FileField` second store of R8,
the keyed attribution of 3.10 (one handle, several namespaces), the subject-root
mark of 3.1 and the guard's positive and negative. The ten synthetic cases are
checked against the stores their manifests list, compared through the scorer's own
`norm` (05-eval-harness.md Decision 5); the verifier never reads a manifest.
"""

from __future__ import annotations

import pytest
import yaml

from art30.verify import build_graph
from evals.harness.score import norm, stems
from tests.verify.conftest import CASES, FIXTURES, edge_between, store_ids

DJANGO_MODELS = """
from django.db import models


class Account(models.Model):
    email = models.EmailField()
    full_name = models.CharField(max_length=255)
    avatar = models.ImageField(upload_to="account/avatars/")
    notes = models.JSONField()

    class Meta:
        db_table = "accounts_account"
"""


def test_django_model_table_name_and_fields(graph_of):
    graph = graph_of({"settings.py": "INSTALLED_APPS = ['app']\n",
                      "app/__init__.py": "", "app/models.py": DJANGO_MODELS})
    store = graph.stores["accounts_account"]
    assert (store.kind, store.subject_root) == ("relational", True)
    assert [f.name for f in store.fields] == ["email", "full_name", "notes"]
    assert store.declared_at.line == 4 and store.subject_link.line == 4
    assert [f.flags for f in store.fields if f.name == "notes"] == [["opaque_container"]]


def test_file_field_is_a_second_store(graph_of):
    """R8 [S1] [S2]: the row and the bytes have different fates."""
    graph = graph_of({"app/__init__.py": "", "app/models.py": DJANGO_MODELS})
    store = graph.stores["account.avatar"]
    assert (store.kind, store.identity) == ("object_storage", "account/avatars/")
    assert (store.declared_at.file, store.declared_at.line) == ("app/models.py", 7)


def test_declarative_base_is_not_a_store(graph_of):
    graph = graph_of({"models.py": """
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()


    class User(Base):
        __tablename__ = "users"
        email = Column(String)


    class Helper:
        pass
    """})
    assert store_ids(graph) == ["users"]


def test_sqlmodel_table_true(graph_of):
    graph = graph_of({"models.py": """
    from sqlmodel import Field, SQLModel


    class User(SQLModel, table=True):
        __tablename__ = "users"
        email: str = Field()
    """})
    assert "users" in graph.stores


def test_core_table_and_association_table(graph_of):
    graph = graph_of({"models.py": """
    from sqlalchemy import Column, Table

    user_tag = Table("user_tag", metadata, Column("user_id"), Column("tag_id"))
    """})
    assert graph.stores["user_tag"].kind == "relational"
    assert [f.name for f in graph.stores["user_tag"].fields] == ["tag_id", "user_id"]


def test_boto3_bucket_store_and_key_field(graph_of):
    graph = graph_of({"storage.py": """
    import boto3

    BUCKET = "uploads"
    s3 = boto3.client("s3")


    def avatar_key(user_id):
        return f"avatars/{user_id}.jpg"


    def upload(user_id, data):
        s3.put_object(Bucket=BUCKET, Key=avatar_key(user_id), Body=data)
    """})
    store = graph.stores["uploads"]
    assert (store.kind, store.identity, store.client_vars) == ("object_storage", "uploads", ["s3"])
    assert store.subject_link.line == 7 and [f.name for f in store.fields] == ["avatar_key"]


def test_two_cache_namespaces_on_one_handle(graph_of):
    """3.10, decision 21: the delete is attributed by its own literal."""
    graph = graph_of({"cache.py": """
    import redis

    r = redis.Redis()


    def cache_profile(u):
        r.setex(f"profile:{u.id}", 86400, u.email)
        r.setex(f"session:{u.id}", 3600, u.email)


    def close_account(u):
        r.delete(f"session:{u.id}")
    """})
    assert store_ids(graph) == ["profile", "session"]
    assert edge_between(graph, "cache.close_account", "store:session", "SE12") is not None
    assert edge_between(graph, "cache.close_account", "store:profile") is None


def test_search_index_store(graph_of):
    graph = graph_of({"search.py": """
    from elasticsearch import Elasticsearch

    INDEX = "doc_search"
    es = Elasticsearch("http://localhost:9200")


    def index_document(user, document):
        es.index(index=INDEX, document={"owner_email": user.email})
    """})
    store = graph.stores["doc_search"]
    # the document key and the attribute that fed it are both recorded
    assert (store.kind, [f.name for f in store.fields]) == ("search_index",
                                                            ["email", "owner_email"])


def test_queue_store_needs_a_personal_payload(graph_of):
    files = {"queue.py": """
    import json

    import pika

    QUEUE = "events"
    channel = pika.BlockingConnection().channel()


    def publish(user):
        channel.basic_publish(exchange="", routing_key=QUEUE,
                              body=json.dumps({"email": user.email}))
    """}
    assert graph_of(files).stores["events"].kind == "queue"
    files["queue.py"] = files["queue.py"].replace('{"email": user.email}', '{"id": user.id}')
    assert store_ids(graph_of(files, "two")) == []


def test_stripe_recipient_is_detected_by_import_plus_call(graph_of):
    graph = graph_of({"billing.py": """
    import stripe


    def create_customer(user):
        return stripe.Customer.create(email=user.email, name=user.full_name)
    """})
    store = graph.stores["stripe"]
    assert (store.kind, store.subject_link.line) == ("third_party", 5)


def test_import_alone_is_not_a_recipient(graph_of):
    graph = graph_of({"billing.py": "import stripe\n\nstripe.api_key = 'x'\n"})
    assert store_ids(graph) == []


def test_sentry_init_alone_carries_the_r23_default_fields(graph_of):
    graph = graph_of({"app.py": "import sentry_sdk\n\nsentry_sdk.init(dsn='x')\n"})
    store = graph.stores["sentry"]
    assert store.kind == "third_party"
    assert [f.name for f in store.fields] == ["query_string", "request_body",
                                              "source_context", "stack_locals", "url"]
    assert store.fields[0].category == "technical"


def test_sentry_pii_flag_adds_the_identity_fields(graph_of):
    graph = graph_of({"app.py": "import sentry_sdk\n\n"
                                "sentry_sdk.init(dsn='x', send_default_pii=True)\n"})
    names = {f.name for f in graph.stores["sentry"].fields}
    assert {"user_identity", "ip_address", "cookies"} <= names


def test_log_sink_named_after_the_logger(graph_of):
    graph = graph_of({"middleware.py": """
    import logging

    logger = logging.getLogger("request_log")


    def log_request(request):
        ip_address = request.client.host
        logger.info("%s %s", ip_address, request.url.path)
    """})
    store = graph.stores["request_log"]
    assert (store.kind, [f.name for f in store.fields]) == ("log", ["ip_address"])


def test_backup_store_from_its_own_name_constant(graph_of):
    graph = graph_of({"jobs/__init__.py": "", "jobs/backup.py": """
    import json

    BACKUP_NAME = "nightly_backup"
    DUMP_COLUMNS = ["email", "full_name"]


    def dump_database(session):
        rows = [{c: getattr(r, c) for c in DUMP_COLUMNS} for r in session.query(User).all()]
        json.dump(rows, open(f"{BACKUP_NAME}.json", "w"))
    """})
    store = graph.stores["nightly_backup"]
    assert (store.kind, store.subject_link.line) == ("backup", 4)
    assert [f.name for f in store.fields] == ["email", "full_name"]


# --------------------------------------------------------------------------
# 3.9 the completeness-guard list
# --------------------------------------------------------------------------
def test_guard_fires_on_a_strong_field(graph_of):
    graph = graph_of({"models.py": "class User:\n    __tablename__ = 'users'\n"
                                   "    email = Column(String)\n"})
    assert graph.stores["users"].guard == "strong"


def test_guard_is_silent_on_a_negative_store(graph_of):
    """`products` is the precision test S07 exists for."""
    graph = graph_of({"catalog.py": "class Product:\n    __tablename__ = 'products'\n"
                                    "    sku = Column(String)\n    title = Column(String)\n"})
    assert graph.stores["products"].guard == ""


def test_name_is_qualified_and_needs_a_subject_link(graph_of):
    graph = graph_of({"models.py": """
    class Group:
        __tablename__ = "groups"
        name = Column(String)


    class Profile:
        __tablename__ = "user_profiles"
        name = Column(String)
    """})
    assert graph.stores["groups"].guard == ""
    assert graph.stores["user_profiles"].guard == "qualified"


# --------------------------------------------------------------------------
# the ten synthetic cases
# --------------------------------------------------------------------------
@pytest.mark.parametrize("case", CASES)
def test_manifest_stores_are_detected(case):
    manifest = yaml.safe_load((FIXTURES / "manifests" / f"{case}.yaml").read_text())
    graph = build_graph(FIXTURES / "synthetic" / case)
    prefixes = tuple((manifest.get("normalisation") or {}).get("prefixes") or ())
    known = stems([s["name"] for s in manifest["stores"]], prefixes)
    found = {norm(store_id, prefixes, known) for store_id in graph.stores}
    wanted = {norm(s["name"], prefixes, known) for s in manifest["stores"]}
    assert wanted <= found, f"{case}: missing {sorted(wanted - found)}"


@pytest.mark.parametrize("case", CASES)
def test_manifest_subject_links_are_cited(case):
    manifest = yaml.safe_load((FIXTURES / "manifests" / f"{case}.yaml").read_text())
    graph = build_graph(FIXTURES / "synthetic" / case)
    prefixes = tuple((manifest.get("normalisation") or {}).get("prefixes") or ())
    known = stems([s["name"] for s in manifest["stores"]], prefixes)
    by_name = {norm(k, prefixes, known): v for k, v in graph.stores.items()}
    for declared in manifest["stores"]:
        link = declared.get("subject_link")
        store = by_name[norm(declared["name"], prefixes, known)]
        if link:
            assert store.subject_link is not None, f"{case}: {declared['name']}"
            assert (store.subject_link.file, store.subject_link.line) == (link["file"], link["line"])


@pytest.mark.parametrize("case", CASES)
def test_negatives_stay_out_of_the_guard(case):
    manifest = yaml.safe_load((FIXTURES / "manifests" / f"{case}.yaml").read_text())
    graph = build_graph(FIXTURES / "synthetic" / case)
    prefixes = tuple((manifest.get("normalisation") or {}).get("prefixes") or ())
    for negative in manifest.get("negatives") or []:
        for store in graph.stores.values():
            if norm(store.id, prefixes) == norm(negative, prefixes):
                assert store.guard == "", f"{case}: guard fires on the negative {negative}"


# --------------------------------------------------------------------------
# 3.10 and 4.2 SE12: which store a primitive touches
# --------------------------------------------------------------------------
def test_object_store_delete_naming_another_bucket_adds_no_edge(graph_of):
    graph = graph_of({"storage.py": """
    import boto3

    UPLOADS = "uploads"
    THUMBS = "thumbs"
    s3 = boto3.client("s3")


    def store(uid, data):
        s3.put_object(Bucket=UPLOADS, Key=f"a/{uid}")
        s3.put_object(Bucket=THUMBS, Key=f"t/{uid}")


    def close_account(uid):
        s3.delete_object(Bucket=THUMBS, Key=f"t/{uid}")
    """})
    assert store_ids(graph) == ["thumbs", "uploads"]
    assert edge_between(graph, "storage.close_account", "store:thumbs", "SE12") is not None
    assert edge_between(graph, "storage.close_account", "store:uploads") is None


def test_raw_sql_names_its_table_and_nothing_else(graph_of):
    """R19 [S11]: the table is read from the literal; there is no cascade behind it."""
    graph = graph_of({
        "models.py": "class User:\n    __tablename__ = 'users'\n    email = Column(String)\n\n\n"
                     "class Post:\n    __tablename__ = 'posts'\n    body = Column(String)\n",
        "api.py": """
        def delete_user(connection, uid):
            cursor = connection.cursor()
            cursor.execute(text("DELETE FROM users WHERE id=%s"), uid)
        """,
    })
    edge = edge_between(graph, "api.delete_user", "store:users", "SE12")
    assert edge is not None and edge.sets_mode == "raw_sql"
    assert edge_between(graph, "api.delete_user", "store:posts") is None


def test_bulk_dml_sets_its_own_mode(graph_of):
    graph = graph_of({
        "models.py": "class User:\n    __tablename__ = 'users'\n    email = Column(String)\n",
        "api.py": "from sqlalchemy import delete\n\nfrom models import User\n\n\n"
                  "def delete_user(session):\n    session.execute(delete(User))\n",
    })
    edge = edge_between(graph, "api.delete_user", "store:users", "SE12")
    assert edge is not None and edge.sets_mode == "bulk_dml"


def test_r13_versioning_declared_in_terraform_is_recorded(graph_of):
    graph = graph_of({
        "storage.py": "import boto3\n\nBUCKET = 'uploads'\ns3 = boto3.client('s3')\n\n\n"
                      "def delete_avatar(uid):\n    s3.delete_object(Bucket=BUCKET, Key=uid)\n",
        "infra/main.tf": 'resource "aws_s3_bucket_versioning" "v" {\n'
                         '  versioning_configuration {\n    status = "Enabled"\n  }\n}\n',
    })
    assert [(v["file"], v["line"]) for v in graph.versioning] == [("infra/main.tf", 1),
                                                                 ("infra/main.tf", 2)]
    assert "versioning_declared" in graph.stores["uploads"].flags


def test_r13_versioning_declared_in_a_python_bootstrap_is_recorded(graph_of):
    """1.1: the research finds the declaration in a bootstrap script, not only in IaC."""
    graph = graph_of({
        "bootstrap.py": 'import boto3\n\ns3 = boto3.client("s3")\n'
                        's3.put_bucket_versioning(Bucket="uploads",\n'
                        '                         VersioningConfiguration={"Status": "Enabled"})\n',
    })
    assert graph.versioning and graph.versioning[0]["how"] == "string search"


def test_r13_no_declaration_leaves_the_store_unflagged(graph_of):
    graph = graph_of({
        "storage.py": "import boto3\n\nBUCKET = 'uploads'\ns3 = boto3.client('s3')\n\n\n"
                      "def delete_avatar(uid):\n    s3.delete_object(Bucket=BUCKET, Key=uid)\n",
    })
    assert graph.versioning == []
    assert graph.stores["uploads"].flags == []


def test_flask_sqlalchemy_db_model_is_a_table(graph_of):
    """[S21]: `db.Model` is a declarative base, and it is not `models.Model`."""
    graph = graph_of({"models.py": """
    from app import db


    class User(db.Model):
        email = db.Column(db.String(120))
    """})
    assert graph.stores["user"].kind == "relational"


def test_sqlmodel_without_table_true_is_not_a_store(graph_of):
    """[S43]: the schema classes of a SQLModel repository are not tables, and the
    completeness guard must not demand four of them in the record."""
    graph = graph_of({"models.py": """
    from sqlmodel import Field, SQLModel


    class UserBase(SQLModel):
        email: str = Field()


    class User(UserBase, table=True):
        id: int = Field(primary_key=True)
    """})
    assert store_ids(graph) == ["user"]


def test_a_store_records_the_primitive_that_reached_it(graph_of):
    graph = graph_of({"cache.py": """
    import redis

    r = redis.Redis()


    def write(u):
        r.setex(f"session:{u.id}", 3600, u.email)


    def close_account(u):
        r.delete(f"session:{u.id}")
    """})
    assert graph.stores["session"].primitives == [
        {"call": "r.delete", "file": "cache.py", "line": 11, "rule": "R20",
         "caller": "cache.close_account", "mode": ""}
    ]


def test_a_file_field_declared_in_a_mixin_is_still_a_second_store(graph_of):
    """R8, 3.1: the row and the bytes have different fates wherever the field is written.

    Reading the class's own body alone lost the `<model>.<field>` store for every
    `FileField` held by a mixin, so django-cleanup (SE3) and a `post_delete` receiver
    (SE2) had nothing to point at and the guard could not ask for the missing store.
    """
    graph = graph_of({
        "app/__init__.py": "",
        "app/mixins.py": """
        from django.db import models


        class AvatarMixin:
            avatar = models.ImageField(upload_to="avatars/")
            bio = models.TextField()
        """,
        "app/models.py": """
        from django.db import models

        from app.mixins import AvatarMixin


        class Profile(AvatarMixin, models.Model):
            email = models.EmailField()
        """,
    })
    assert store_ids(graph) == ["profile", "profile.avatar"]
    bytes_store = graph.stores["profile.avatar"]
    assert bytes_store.kind == "object_storage"
    assert "django_file_field" in bytes_store.flags
    # the citation points at the mixin, where the declaration is
    assert (bytes_store.declared_at.file, bytes_store.declared_at.line) == ("app/mixins.py", 5)
    assert [f.name for f in graph.stores["profile"].fields] == ["bio", "email"]


def test_raw_sql_without_a_text_wrapper_names_its_table(graph_of):
    """R19 [S11]: 4.1's own example is `connection.cursor().execute("DELETE ...")`.

    Gated on `arg0_call: [text]`, the bare-string form matched no primitive at all and
    every psycopg repository lost R19.
    """
    graph = graph_of({
        "models.py": "class User:\n    __tablename__ = 'users'\n    email = Column(String)\n\n\n"
                     "class Post:\n    __tablename__ = 'posts'\n    body = Column(String)\n",
        "api.py": """
        def delete_user(connection, uid):
            cursor = connection.cursor()
            cursor.execute("DELETE FROM users WHERE id=%s", uid)
        """,
    })
    edge = edge_between(graph, "api.delete_user", "store:users", "SE12")
    assert edge is not None and (edge.rule, edge.sets_mode) == ("R19", "raw_sql")
    assert edge_between(graph, "api.delete_user", "store:posts") is None
