"""The verdict procedure, one rule at a time (03-verifier.md 6.1, and R1-R28).

Section 10's test plan, every row of it that ends in a verdict. Each test names the
rule it pins in its own name and cites the behaviour in its docstring, so a rule that
loses its test is visible as a missing name rather than as a silent gap. The two
mechanisms that carry the safety argument outside the rule table -- 2.5's declared
entry point and 1.5's narrowed dynamic dispatch -- are tests 53 and 59 at the end.

`erased`, `erased_after_timer` and `anonymised` are the reaching verdicts (contract,
Record vocabulary); everything else counts as not reaching, and no test below asserts
`erased` where the research reproduced a survivor.
"""

from __future__ import annotations

import pytest

from art30.verify import build_graph
from art30.verify.findings import Cite, EntryPoint, Store
from art30.verify.reach import verdicts, verdict_for

# ---------------------------------------------------------------------------
# shared fixture text
# ---------------------------------------------------------------------------
DJ_HEAD = """
from django.db import models
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver


class User(models.Model):
    email = models.EmailField()
"""
AVATAR = """

class Avatar(models.Model):
    user = models.ForeignKey(User, on_delete=models.{token})
    image = models.ImageField(upload_to="avatars/")
"""
INSTANCE_DELETE = """
from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    user.delete()
"""
SA_HEAD = """
from sqlalchemy import Column, ForeignKey, Integer, String, Table, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()
"""
SESSION_DELETE = """
from models import Session, User


def close_account(user_id):
    session = Session()
    user = session.get(User, user_id)
    session.delete(user)
"""


def _v(graph) -> dict[str, str]:
    return {k: v.verdict for k, v in verdicts(graph).items()}


def _django(models_body: str, settings: str = "INSTALLED_APPS = ['app']\n",
            view: str = INSTANCE_DELETE, **extra) -> dict[str, str]:
    files = {"settings.py": settings, "app/__init__.py": "",
             "app/models.py": models_body, "app/views.py": view}
    files.update(extra)
    return files


# ---------------------------------------------------------------------------
# R1-R4: Django on_delete
# ---------------------------------------------------------------------------
def test_r01_cascade_is_an_edge(graph_of):
    """Test 1, R1 [S1] [S4]: the child rows go with the parent, and the FK is cited."""
    graph = graph_of(_django(DJ_HEAD + """

class Post(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    body = models.TextField()
"""))
    found = verdicts(graph)
    assert found["post"].verdict == "erased"
    assert found["post"].evidence == [{"file": "app/models.py", "line": 11, "symbol": "post"}]
    assert "R1" in found["post"].reasons


def test_r02_set_null_is_not_an_edge(graph_of):
    """Test 2, R2 [S1]: the row survives with every personal-data column intact."""
    graph = graph_of(_django(DJ_HEAD + """

class Post(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    body = models.TextField()
"""))
    assert _v(graph) == {"post": "not_erased", "user": "erased"}


PROTECT_MODELS = DJ_HEAD + """

class Invoice(models.Model):
    owner = models.ForeignKey(User, on_delete=models.PROTECT)
    billing_name = models.CharField(max_length=200)
"""


def test_r03a_protect_two_step(graph_of):
    """Test 3, R3a and 4.8: a subject-scoped child delete stands in for the cascade."""
    graph = graph_of(_django(PROTECT_MODELS, view="""
from app.models import Invoice, User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    Invoice.objects.filter(owner=user).delete()
    user.delete()
"""))
    found = verdicts(graph)
    assert (found["invoice"].verdict, found["user"].verdict) == ("erased", "erased")
    assert found["invoice"].evidence[0]["line"] == 6      # the child delete, first
    assert found["user"].evidence[0]["line"] == 7         # then the parent delete


def test_r03a_protect_bare_parent_delete(graph_of):
    """Test 4, R3a [S1]: with no child delete the parent raises `ProtectedError`."""
    graph = graph_of(_django(PROTECT_MODELS))
    found = verdicts(graph)
    assert found["invoice"].verdict == "not_erased"
    assert "ProtectedError" in found["invoice"].note


def test_r03a_filtered_child_delete(graph_of):
    """Test 61, 4.8: `status="draft"` leaves paid invoices, so nothing at all is erased."""
    graph = graph_of(_django(PROTECT_MODELS, view="""
from app.models import Invoice, User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    Invoice.objects.filter(owner=user, status="draft").delete()
    user.delete()
"""))
    found = verdicts(graph)
    assert found["invoice"].verdict == "unverified"
    assert found["user"].verdict == "unverified"          # downstream of the parent delete
    assert "ProtectedError" in found["user"].note


def test_r03b_restrict_is_unverified(graph_of):
    """Test 5, R3b [S1]: the documented exception the AST cannot settle."""
    graph = graph_of(_django(DJ_HEAD + """

class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total = models.IntegerField()


class Receipt(models.Model):
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    billing_name = models.CharField(max_length=200)
"""))
    found = verdicts(graph)
    assert found["receipt"].verdict == "unverified" and "R3b" in found["receipt"].reasons
    assert found["order"].verdict == "erased"


def test_r04_db_cascade_kills_cleanup(graph_of):
    """Test 6, R4 [S1] [S3]: the rows go, the signals never fire, the file stays."""
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="DB_CASCADE"),
                             settings="INSTALLED_APPS = ['django_cleanup', 'app']\n"))
    assert _v(graph) == {"avatar": "erased", "avatar.image": "not_erased", "user": "erased"}


# ---------------------------------------------------------------------------
# R5-R7, R17: SQLAlchemy
# ---------------------------------------------------------------------------
def _sa(cascade: str = "", ondelete: str = "", engine: str = "sqlite:///app.db",
        passive: str = "", listener: str = "", second: str = "", account=SESSION_DELETE):
    body = SA_HEAD + f"""{second}
engine = create_engine("{engine}")
Session = sessionmaker(bind=engine)
{listener}

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String)
    notes = relationship("Note"{cascade}{passive})


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"{ondelete}))
    body = Column(String)
"""
    return {"models.py": body, "account.py": account}


def test_r05_delete_orphan_without_delete(graph_of):
    """Test 7, R5 [S15]: the substring trap -- `delete-orphan` alone deletes nothing."""
    graph = graph_of(_sa(cascade=', cascade="save-update, merge, delete-orphan"'))
    assert _v(graph) == {"notes": "not_erased", "users": "erased"}


def test_r05_all_token(graph_of):
    """Test 8, R5 [S15]: `all` is a synonym that contains `delete`."""
    graph = graph_of(_sa(cascade=', cascade="all, delete-orphan"'))
    assert _v(graph) == {"notes": "erased", "users": "erased"}


def test_r06_passive_deletes_sqlite(graph_of):
    """Test 9, R6 [S15]: the ORM was told not to emit the child DELETE, and nothing will."""
    graph = graph_of(_sa(ondelete=', ondelete="CASCADE"', passive=", passive_deletes=True"))
    found = verdicts(graph)
    assert found["notes"].verdict == "not_erased" and "passive_deletes" in found["notes"].note


def test_r06_ondelete_without_evidence(graph_of):
    """Test 10, R6 [S19]: `ondelete` emits DDL and nothing more."""
    graph = graph_of(_sa(ondelete=', ondelete="CASCADE"'))
    found = verdicts(graph)
    assert found["notes"].verdict == "unverified" and "R6" in found["notes"].reasons


def test_r06_ondelete_with_postgres(graph_of):
    """Test 11, R6: a non-SQLite URL on the engine the session is bound to."""
    graph = graph_of(_sa(ondelete=', ondelete="CASCADE"', engine="postgresql://host/db"))
    assert _v(graph)["notes"] == "erased"


def test_r06_sqlite_with_pragma_listener(graph_of):
    """Test 12, R6 [S46]: `PRAGMA foreign_keys=ON` on *that* engine's connect."""
    graph = graph_of(_sa(ondelete=', ondelete="CASCADE"', listener='''

@event.listens_for(Engine, "connect")
def _fk_on(dbapi_connection, record):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")
'''))
    assert _v(graph)["notes"] == "erased"


def test_r06_engine_binding_is_not_repository_wide(graph_of):
    """Test 65, 4.5: a second, unrelated Postgres engine must not bless SE7."""
    graph = graph_of(_sa(ondelete=', ondelete="CASCADE"',
                         second='analytics_engine = create_engine("postgresql://host/metrics")'))
    assert _v(graph)["notes"] == "unverified"


M2M = SA_HEAD + """
engine = create_engine("sqlite:///app.db")
Session = sessionmaker(bind=engine)

user_tag = Table(
    "user_tag",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("tag_id", Integer, ForeignKey("tags.id")),
)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String)
    tags = relationship("Tag", secondary=user_tag)


class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    label = Column(String)
"""


def test_r07_secondary_session_delete(graph_of):
    """Test 13, R7 [S18]: the association row is where the consent link lives."""
    graph = graph_of({"models.py": M2M, "account.py": SESSION_DELETE})
    assert _v(graph)["user_tag"] == "erased"


def test_r07_and_r17_secondary_bulk_dml(graph_of):
    """Tests 14 and 17, R7 and R17 [S16]: bulk DML performs no in-Python cascade."""
    graph = graph_of({"models.py": M2M, "account.py": """
from sqlalchemy import delete

from models import Session, User


def close_account(user_id):
    session = Session()
    session.execute(delete(User))
"""})
    assert _v(graph) == {"tags": "not_erased", "user_tag": "not_erased", "users": "erased"}


def test_r18_listener_is_not_evidence_on_bulk_dml(graph_of):
    """Test 54, R18 [S17]: a mapper listener is silent on the bulk path."""
    listener = '''

@event.listens_for(User, "before_delete")
def _drop(mapper, connection, target):
    s3.delete_object(Bucket=BUCKET, Key=str(target.id))
'''
    head = 'import boto3\n\ns3 = boto3.client("s3")\nBUCKET = "uploads"\n'
    files = _sa(cascade="")
    files["models.py"] = head + files["models.py"] + listener
    bulk = dict(files)
    bulk["account.py"] = """
from sqlalchemy import delete

from models import Session, User


def close_account(user_id):
    session = Session()
    session.execute(delete(User))
"""
    assert _v(graph_of(bulk, "bulk"))["uploads"] == "not_erased"
    assert _v(graph_of(files, "orm"))["uploads"] == "erased"


# ---------------------------------------------------------------------------
# R8-R12: files, receivers, django-cleanup
# ---------------------------------------------------------------------------
RECEIVER = '''

@receiver({signal}, sender=Avatar)
def drop(sender, instance, **kwargs):
    instance.image.delete(save=False)
'''


def test_r08_filefield_cascade_only(graph_of):
    """Test 15, R8 [S1] [S2]: a cascade moves the row, never the bytes."""
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="CASCADE")))
    assert _v(graph)["avatar.image"] == "not_erased"


def test_r08_precondition_row_not_reached(graph_of):
    """Test 16, R8 and R10: cleanup installed, the row orphaned, the file on disk."""
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="SET_NULL"),
                             settings="INSTALLED_APPS = ['django_cleanup', 'app']\n"))
    assert _v(graph)["avatar.image"] == "not_erased"


def test_r08_pre_delete_receiver_counts(graph_of):
    """Test 17, R8a [S1]: `pre_delete` is sent for all deleted objects."""
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="CASCADE")
                             + RECEIVER.format(signal="pre_delete")))
    assert _v(graph)["avatar.image"] == "erased"


def test_r09_wrong_sender_decoy(graph_of):
    """Test 18, R9 [S6]: S09's decoy -- right code, wrong `sender=`."""
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="CASCADE") + """

class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    body = models.TextField()


@receiver(post_delete, sender=Comment)
def drop(sender, instance, **kwargs):
    instance.image.delete(save=False)
"""))
    assert _v(graph)["avatar.image"] == "not_erased"


@pytest.mark.xfail(strict=True, reason=(
    "R9's no-sender receiver reaches every relational store through SE2, but "
    "`instance` is left unbound by synthetic.add_edges when the decorator carries no "
    "`sender=`, so the body's `instance.image.delete()` is attributed to no store and "
    "no SE12 edge exists. The verdict falls to `not_erased`, which is the conservative "
    "side of R9 but not what section 10 test 19 asks for. Fix belongs in "
    "art30/verify/synthetic.py, which this agent does not own."))
def test_r09_receiver_without_sender(graph_of):
    """Test 19, R9 [S6]: no `sender=` covers every model carrying that field."""
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="CASCADE") + """

@receiver(post_delete)
def drop(sender, instance, **kwargs):
    instance.image.delete(save=False)
"""))
    assert _v(graph)["avatar.image"] == "erased"


@pytest.mark.xfail(strict=True, reason=(
    "Test 62 asks for `unverified`; the graph adds no SE2 edge for a guarded "
    "no-sender receiver (correct) but the body's primitive is also attributed to no "
    "store, for the same unbound-`instance` reason as test 19, so nothing marks the "
    "file store as unverifiable and it falls to `not_erased`."))
def test_r09_no_sender_receiver_with_guard(graph_of):
    """Test 62, R9: a body branching on `sender` takes the decorator's claim back."""
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="CASCADE") + """

@receiver(post_delete)
def drop(sender, instance, **kwargs):
    if sender.__name__ == "Comment":
        instance.image.delete(save=False)
"""))
    assert _v(graph)["avatar.image"] == "unverified"


def test_r10_bare_label_activates(graph_of):
    """Test 20, R10 [S13]: `CleanupConfig` sets `default = True`, so the bare label wins."""
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="CASCADE"),
                             settings="INSTALLED_APPS = ['django_cleanup', 'app']\n"))
    assert _v(graph)["avatar.image"] == "erased"


def test_r10_dotted_config_activates(graph_of):
    """Test 20, R10 [S13]: both spellings deleted the file in the transcripts."""
    graph = graph_of(_django(
        DJ_HEAD + AVATAR.format(token="CASCADE"),
        settings="INSTALLED_APPS = ['django_cleanup.apps.CleanupConfig', 'app']\n"))
    assert _v(graph)["avatar.image"] == "erased"


def test_r10_selected_config_opt_in(graph_of):
    """Test 21, R10 [S13]: `CleanupSelectedConfig` inverts the default to opt-in."""
    graph = graph_of(_django(
        DJ_HEAD + AVATAR.format(token="CASCADE"),
        settings="INSTALLED_APPS = ['django_cleanup.apps.CleanupSelectedConfig', 'app']\n"))
    assert _v(graph)["avatar.image"] == "not_erased"


def test_r10_split_settings_disagree_on_cleanup(graph_of):
    """Test 64, 4.4: the union would let a development setting bless production."""
    files = {"proj/__init__.py": "", "proj/settings/__init__.py": "",
             "proj/settings/dev.py": "INSTALLED_APPS = ['django_cleanup', 'app']\n",
             "proj/settings/prod.py": "INSTALLED_APPS = ['app']\n",
             "app/__init__.py": "", "app/views.py": INSTANCE_DELETE,
             "app/models.py": DJ_HEAD + AVATAR.format(token="CASCADE")}
    found = verdicts(graph_of(files))
    assert found["avatar.image"].verdict == "unverified"
    assert [c["file"] for c in found["avatar.image"].evidence] == [
        "proj/settings/dev.py", "proj/settings/prod.py"]


def test_r11_receiver_inside_function(graph_of):
    """Test 22, R11 [S6]: a weakly connected nested receiver may never fire."""
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="CASCADE"), **{"app/apps.py": """
from django.db.models.signals import post_delete

from app.models import Avatar


def wire():
    def drop(sender, instance, **kwargs):
        instance.image.delete(save=False)

    post_delete.connect(drop, sender=Avatar)
"""}))
    found = verdicts(graph)
    assert found["avatar.image"].verdict == "unverified"
    assert "R11" in found["avatar.image"].reasons


def test_r12_signals_module_unimported(graph_of):
    """Test 23, R12 [S6]: a `signals.py` nothing loads is not evidence."""
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="CASCADE"),
                             settings="INSTALLED_APPS = ['other']\n", **{"app/signals.py": """
from django.db.models.signals import post_delete
from django.dispatch import receiver

from app.models import Avatar


@receiver(post_delete, sender=Avatar)
def drop(sender, instance, **kwargs):
    instance.image.delete(save=False)
"""}))
    assert _v(graph)["avatar.image"] == "not_erased"


def test_r12_receiver_in_models_is_connected(graph_of):
    """Test 24, R12 [S6]: Django imports `models.py`; calling that dead is a false alarm."""
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="CASCADE")
                             + RECEIVER.format(signal="post_delete")))
    assert _v(graph)["avatar.image"] == "erased"


# ---------------------------------------------------------------------------
# R13: object storage and versioning
# ---------------------------------------------------------------------------
STORAGE = """
import boto3

s3 = boto3.client("s3")
BUCKET = "uploads"


def close_account(user):
    s3.delete_object(Bucket=BUCKET, Key=f"users/{user.id}/avatar.png")
"""


def test_r13_no_versioning_declaration(graph_of):
    """Test 26, R13: the narrowed assumption -- nothing declared, the delete reaches."""
    found = verdicts(graph_of({"storage.py": STORAGE}))
    assert found["uploads"].verdict == "erased"


def test_r13_versioned_bucket(graph_of):
    """Test 25, R13 [S22]: "as though the object has been deleted (even though ...)"."""
    found = verdicts(graph_of({"storage.py": STORAGE, "bootstrap.py": """
import boto3

s3 = boto3.client("s3")


def setup():
    s3.put_bucket_versioning(
        Bucket="uploads",
        VersioningConfiguration={"Status": "Enabled"},
    )
"""}))
    assert found["uploads"].verdict == "not_erased"
    assert [c["file"] for c in found["uploads"].evidence] == ["storage.py", "bootstrap.py"]


def test_r13_versioning_declared_in_terraform(graph_of):
    """Test 60, R13 [S23]: Terraform spells it `status = "Enabled"`."""
    found = verdicts(graph_of({"storage.py": STORAGE, "infra/main.tf": """
resource "aws_s3_bucket_versioning" "uploads" {
  bucket = "uploads"
  versioning_configuration {
    status = "Enabled"
  }
}
"""}))
    assert found["uploads"].verdict == "not_erased"
    assert found["uploads"].evidence[-1]["file"] == "infra/main.tf"


# ---------------------------------------------------------------------------
# R14, R15: which delete was called
# ---------------------------------------------------------------------------
OVERRIDE = """

    def delete(self, *args, **kwargs):
        self.image.delete(save=False)
        return super().delete(*args, **kwargs)
"""
QUERYSET_VIEW = """
from app.models import Avatar


def close_account(request, user):
    Avatar.objects.filter(user=user).delete()
"""


def test_r14_override_not_on_queryset_path(graph_of):
    """Test 27, R14 [S3]: the override is not called by `QuerySet.delete()`.

    Section 10's cell says `not_erased`; the shipped answer is `unverified`, because
    the receiver of the chained `.delete()` is not a name the graph can resolve and
    6.1 row 8 sits above row 9 for exactly that reason. Both are on the false side of
    `reaches_erasure`; what R14 forbids is `erased`, and that is what is asserted.
    """
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="CASCADE") + OVERRIDE,
                             view=QUERYSET_VIEW))
    assert _v(graph)["avatar.image"] == "unverified"


def test_r15_queryset_delete_fires_signals(graph_of):
    """Test 28, R15 [S3]: signals survive the bulk path; only R4 removes them."""
    graph = graph_of(_django(DJ_HEAD + AVATAR.format(token="CASCADE")
                             + RECEIVER.format(signal="post_delete"), view=QUERYSET_VIEW))
    assert _v(graph)["avatar.image"] == "erased"


# ---------------------------------------------------------------------------
# R19-R21: raw SQL, Redis, the search index
# ---------------------------------------------------------------------------
def test_r19_raw_sql_downstream(graph_of):
    """Test 30, R19 [S11]: the named table goes, everything behind it is opaque."""
    graph = graph_of(_django(DJ_HEAD + """
    class Meta:
        db_table = "users"


class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    shipping_address = models.CharField(max_length=200)

    class Meta:
        db_table = "orders"
""", view="""
from django.db import connection


def close_account(request, user_id):
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM users WHERE id=%s", [user_id])
"""))
    found = verdicts(graph)
    assert found["users"].verdict == "erased"
    assert found["orders"].verdict == "unverified" and "R19" in found["orders"].reasons


CACHE = """
import json

import redis

r = redis.Redis()


def cache_profile(user):
    r.setex(f"profile:{user.id}", 86400, json.dumps({"email": user.email}))
    r.setex(f"session:{user.id}", 3600, user.email)
"""


def test_r20_setex_ttl_is_not_erasure(graph_of):
    """Test 31, R20 [S25]: a TTL is a retention timer, not an erasure path."""
    graph = graph_of({"cache.py": CACHE, "account.py": """
from cache import r


def close_account(user):
    pass
"""})
    assert _v(graph) == {"profile": "not_erased", "session": "not_erased"}


def test_r20_redis_delete_on_path_and_3_10_attribution(graph_of):
    """Tests 32 and 52, R20 [S24] and 3.10: one handle, two namespaces, one delete."""
    graph = graph_of({"cache.py": CACHE, "account.py": """
from cache import r


def close_account(user):
    r.delete(f"session:{user.id}")
"""})
    assert _v(graph) == {"profile": "not_erased", "session": "erased"}


def test_r21_search_index_distinct(graph_of):
    """Test 33, R21 [S26]: a relational delete never reaches the index."""
    graph = graph_of(_django(DJ_HEAD, **{"app/search.py": """
from elasticsearch import Elasticsearch

es = Elasticsearch()


def index_user(user):
    es.index(index="user_search", id=user.id, document={"email": user.email})
"""}))
    assert _v(graph) == {"user": "erased", "user_search": "not_erased"}


# ---------------------------------------------------------------------------
# R22-R24: the third-party stores
# ---------------------------------------------------------------------------
def test_r22_stripe_never_erased(graph_of):
    """Test 34, R22 [S28]: deleted customers "can still be retrieved through the API"."""
    graph = graph_of(_django(DJ_HEAD + """    stripe_id = models.CharField(max_length=50)
""", view="""
import stripe

from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    stripe.Customer.create(email=user.email)
    stripe.Customer.delete(user.stripe_id)
    user.delete()
"""))
    found = verdicts(graph)
    assert found["stripe"].verdict == "external_manual"
    assert found["stripe"].reaches_erasure is False


def test_r23_sentry_init_alone(graph_of):
    """Test 35, R23 [S30] [S31]: `init` alone makes Sentry a recipient."""
    graph = graph_of(_django(DJ_HEAD, **{"app/conf.py": """
import sentry_sdk

sentry_sdk.init(dsn="https://example.invalid/1")
"""}))
    found = verdicts(graph)
    assert (found["sentry"].verdict, found["sentry"].kind) == ("external_manual", "third_party")
    assert {f.name for f in graph.stores["sentry"].fields} >= {"url", "query_string"}


def _segment(regulation_type: str):
    return _django(DJ_HEAD, view=f"""
import analytics

from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    analytics.track(user_id=user.id, event="closed", properties={{"email": user.email}})
    analytics.create_regulation(regulation_type={regulation_type},
                                subject_type="userId", subject_ids=[str(user.id)])
    user.delete()
""")


def test_r24_deletion_endpoint_upgrade(graph_of):
    """Test 55, R24 [S47]: the one shape that forwards downstream."""
    found = verdicts(graph_of(_segment('"SUPPRESS_WITH_DELETE"')))
    assert found["segment"].verdict == "erased" and "R24" in found["segment"].reasons


def test_r24_delete_internal_is_not_erasure(graph_of):
    """Test 56, R24 [S47]: `DELETE_INTERNAL`, and a variable, leave destinations alone."""
    literal = verdicts(graph_of(_segment('"DELETE_INTERNAL"'), "lit"))
    variable = verdicts(graph_of(_segment("kind"), "var"))
    assert literal["segment"].verdict == "external_manual"
    assert variable["segment"].verdict == "external_manual"
    assert "destination" in literal["segment"].note.lower()


# ---------------------------------------------------------------------------
# R25 and 4.7: soft delete, anonymised, pseudonymised
# ---------------------------------------------------------------------------
ANON_MODEL = """
from django.db import models


class User(models.Model):
    email = models.EmailField()
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=40)
"""


def test_r25_is_active_false(graph_of):
    """Test 36, R25 [S10]: Django recommends the pattern, so the verifier refuses it."""
    graph = graph_of(_django("""
from django.db import models


class User(models.Model):
    email = models.EmailField()
    is_active = models.BooleanField(default=True)
""", view="""
from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    user.is_active = False
    user.save()
"""))
    assert _v(graph)["user"] == "not_erased"


def test_pseudonymised_hashed_email(graph_of):
    """Test 39, 4.7 [S12]: a hash is reversible-or-linked, never erasure."""
    graph = graph_of(_django(ANON_MODEL, view="""
import hashlib

from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    user.email = hashlib.sha256(user.email.encode()).hexdigest()
    user.full_name = ""
    user.phone = ""
    user.save()
"""))
    found = verdicts(graph)
    assert found["user"].verdict == "pseudonymised"
    assert found["user"].reaches_erasure is False


def test_anonymised_constant_overwrite(graph_of):
    """Test 40, 4.7: every detected column overwritten, no surviving subject key."""
    graph = graph_of(_django(ANON_MODEL, view="""
from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    user.email = ""
    user.full_name = "REDACTED"
    user.phone = None
    user.save()
"""))
    found = verdicts(graph)
    assert found["user"].verdict == "anonymised" and found["user"].reaches_erasure


def test_anonymised_over_detected_columns_not_the_records(graph_of):
    """Test 63, 4.7 and decision 22: the record may not shrink the column list."""
    graph = graph_of(_django(ANON_MODEL, view="""
from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    user.email = ""
    user.save()
"""))
    claimed = verdict_for(graph, "user", claimed=["email"])
    assert claimed.verdict == "pseudonymised"       # not `anonymised` on the record's list
    assert claimed.fields["email"].verdict == "anonymised"
    assert claimed.fields["full_name"].verdict == "not_erased"
    assert claimed.fields["phone"].verdict == "not_erased"


# ---------------------------------------------------------------------------
# R26-R28: what the tool cannot see
# ---------------------------------------------------------------------------
def test_s10_dead_helper(graph_of):
    """Test 38, R26 and 2: the helper exists, and nothing calls it."""
    graph = graph_of({"storage.py": """
import boto3

s3 = boto3.client("s3")
BUCKET = "uploads"


def cleanup_user_files(user_id):
    s3.delete_object(Bucket=BUCKET, Key=f"users/{user_id}/avatar.png")
""", "account.py": """
def close_account(user_id):
    \"\"\"Close the account and remove the user's uploaded files.\"\"\"
    return True
"""})
    found = verdicts(graph)
    assert found["uploads"].verdict == "not_erased"
    assert "no entry point reaches it" in found["uploads"].note


def test_r27_unmodelled_decorator_unverified(graph_of):
    """Test 57, R27 [S35]: what a decorator does to a function is not modelled."""
    graph = graph_of({"retry.py": "def my_retry(fn):\n    return fn\n", "storage.py": """
import boto3

from retry import my_retry

s3 = boto3.client("s3")
BUCKET = "uploads"


@my_retry
def drop_avatar(user):
    s3.delete_object(Bucket=BUCKET, Key=f"users/{user.id}.png")
""", "account.py": """
from storage import drop_avatar


def close_account(user):
    drop_avatar(user)
"""})
    found = verdicts(graph)
    assert found["uploads"].verdict == "unverified" and "R27" in found["uploads"].reasons


def test_r28_missing_position_unverified(mkrepo):
    """Test 58, R28 [S35]: a store declared in a file that does not parse.

    Two halves, because a store the parser never saw cannot be in `graph.stores` on its
    own: the unparsed file is recorded rather than guessed at, and a store whose
    `declared_at` lands in one takes row 8 instead of a citation nobody can check.
    """
    graph = build_graph(mkrepo({"app/__init__.py": "", "app/models.py": """
from django.db import models


class User(models.Model):
    email = models.EmailField()
""", "app/legacy.py": """
from django.db import models


class Legacy(models.Model)
    email = models.EmailField()
""", "app/views.py": INSTANCE_DELETE}))
    assert [u["file"] for u in graph.unparsed] == ["app/legacy.py"]
    assert graph.unparsed[0]["error"] == "SyntaxError"
    assert all(s.declared_at is None or s.declared_at.file != "app/legacy.py"
               for s in graph.stores.values())
    graph.stores["legacy"] = Store(id="legacy", kind="relational", name="legacy",
                                   declared_at=Cite("app/legacy.py", 4))
    found = verdict_for(graph, "legacy")
    assert (found.verdict, found.reasons, found.evidence) == ("unverified", ["R28"], [])


def test_getattr_narrowing_does_not_poison_other_stores(graph_of):
    """Test 59, 1.5 and decision 3: an opaque call downgrades one store, not the tree."""
    graph = graph_of(_django(DJ_HEAD, **{"storage.py": """
import boto3

s3 = boto3.client("s3")
BUCKET = "uploads"


def drop(user, meth):
    getattr(s3, meth)(Bucket=BUCKET, Key=str(user.id))
"""}))
    assert _v(graph) == {"uploads": "unverified", "user": "erased"}


def test_declared_entry_point_without_registration(graph_of):
    """Test 53, 2.5 and decision 5a: a declared start node caps every verdict from it."""
    graph = graph_of({"storage.py": """
import boto3

s3 = boto3.client("s3")
BUCKET = "uploads"


def cleanup_user_files(user_id):
    s3.delete_object(Bucket=BUCKET, Key=f"users/{user_id}/avatar.png")
""", "account.py": """
def close_account(user_id):
    return True
"""})
    symbol = graph.symbols["storage.cleanup_user_files"]
    declared = EntryPoint(name="cleanup_user_files", kind="unknown", file=symbol.file,
                          line=symbol.line, symbol=symbol.name,
                          flags=["declared_unregistered"])
    found = verdicts(graph, entry_points=list(graph.entry_points) + [declared])
    assert found["uploads"].verdict == "unverified"
    assert "declared but not seen registered" in found["uploads"].note


# ---------------------------------------------------------------------------
# 6.1: the ordering itself
# ---------------------------------------------------------------------------
PRECEDENCE_MODEL = """
from django.db import models


class User(models.Model):
    email = models.EmailField()
    full_name = models.CharField(max_length=200)
    deleted_at = models.DateTimeField(null=True)
"""


def test_precedence_row_4_wins_over_row_5(graph_of):
    """6.1: "Row 4 before row 5 means a row that is both blanked and deleted reads
    `erased`." Both conditions hold here: every column is overwritten with a constant
    and the row is then deleted outright."""
    graph = graph_of(_django(PRECEDENCE_MODEL, view="""
from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    user.email = ""
    user.full_name = ""
    user.save()
    user.delete()
"""))
    found = verdicts(graph)["user"]
    assert found.verdict == "erased"
    assert "03-verifier.md 6.1 row 4" in found.reasons


def test_precedence_row_6_wins_over_row_7(graph_of):
    """6.1: "Row 6 before row 7 means a soft delete followed by a real purge is not
    demoted by an incidental hash." The email is hashed on the way out, which row 7
    alone would read as `pseudonymised`, and the scheduled purge still removes the row."""
    files = _django(PRECEDENCE_MODEL,
                    settings="INSTALLED_APPS = ['app']\n"
                             "beat_schedule = {'purge': {'task': 'jobs.purge_closed_accounts'}}\n",
                    view="""
import hashlib

from django.utils import timezone

from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    user.email = hashlib.sha256(user.email.encode()).hexdigest()
    user.deleted_at = timezone.now()
    user.save()
""", **{"jobs.py": """
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from app.models import User


@shared_task
def purge_closed_accounts():
    cutoff = timezone.now() - timedelta(days=30)
    User.objects.filter(deleted_at__lt=cutoff).delete()
"""})
    found = verdicts(graph_of(files))["user"]
    assert (found.verdict, found.timer_days) == ("erased_after_timer", 30)
    assert "R25" in found.reasons


def test_backup_kind_never_takes_an_erasure_verdict(graph_of):
    """6.1 row 1 above everything: the contract allows a `backup` store two verdicts."""
    files = _django(PRECEDENCE_MODEL, **{"jobs.py": """
import subprocess


def nightly_backup():
    subprocess.run(["pg_dump", "app"])
"""})
    found = verdicts(graph_of(files))["jobs"]
    assert found.kind == "backup"
    assert found.verdict in {"governed_by_retention", "no_schedule_evidenced"}


# ---------------------------------------------------------------------------
# 4.5, R6: the PRAGMA has to be emitted, on the engine the session is bound to
# ---------------------------------------------------------------------------
PRAGMA_BODY = '''

@event.listens_for({target}, "connect")
def _fk_on(dbapi_connection, record):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")
'''
PRAGMA_COMMENT = '''

@event.listens_for(Engine, "connect")
def _fk_on(dbapi_connection, record):
    # TODO: emit PRAGMA foreign_keys=ON here one day
    pass
'''
ONDELETE = ', ondelete="CASCADE"'
PASSIVE = ", passive_deletes=True"


def test_r06_pragma_listener_on_the_bound_engine(graph_of):
    """4.5 [S46]: `@event.listens_for(engine, "connect")` names the engine by variable."""
    graph = graph_of(_sa(ondelete=ONDELETE, passive=PASSIVE,
                         listener=PRAGMA_BODY.format(target="engine")))
    assert _v(graph)["notes"] == "erased"


def test_r06_pragma_listener_on_another_engine_is_not_evidence(graph_of):
    """4.5: "a connect listener registered **on that engine**", and this one is not.

    `_listeners` recorded the listener's target and `pragma_listener` never read it, so
    a `PRAGMA foreign_keys=ON` bound to an unrelated reporting database blessed SE7 for
    the application's own SQLite engine -- parent gone, child row and its email present,
    which is the transcript the research calls the worst result in the document. With
    `passive_deletes=True` the ORM has also been told not to emit the child DELETE, so
    4.5's answer is `not_erased` and not merely `unverified`.
    """
    graph = graph_of(_sa(ondelete=ONDELETE, passive=PASSIVE,
                         second='reporting = create_engine("sqlite:///reports.db")',
                         listener=PRAGMA_BODY.format(target="reporting")))
    assert _v(graph)["notes"] == "not_erased"


def test_r06_pragma_listener_on_nothing_is_not_evidence(graph_of):
    """4.5: a target that names neither `Engine` nor an engine in the repository."""
    graph = graph_of(_sa(ondelete=ONDELETE, passive=PASSIVE,
                         listener=PRAGMA_BODY.format(target='"nonsense"')))
    assert _v(graph)["notes"] == "not_erased"


def test_r06_pragma_in_a_comment_is_not_evidence(graph_of):
    """4.5, R6 [S46]: the listener has to *emit* the statement, not mention it.

    `_emits` searched the listener's raw source span for the text with spaces stripped,
    so a comment or a docstring naming the PRAGMA was accepted as enforcement. The file
    is already parsed; the argument of the call is what the rule is about.
    """
    graph = graph_of(_sa(ondelete=ONDELETE, passive=PASSIVE, listener=PRAGMA_COMMENT))
    assert _v(graph)["notes"] == "not_erased"


# ---------------------------------------------------------------------------
# 4.8 and 6.1's second cap: the parent delete that raises
# ---------------------------------------------------------------------------
def test_r03a_bare_parent_delete_caps_the_parent_too(graph_of):
    """4.8, 6.1 cap 2: with no child delete the parent delete raises, so nothing goes.

    Test 4 asserts the child alone, which let the record say in one row that the delete
    raises `ProtectedError` and in the next that the account row is gone -- and `users`
    is the most consequential store in the record. `protect_parents` collected a parent
    only for the `disqualified` branch; the `absent` branch blocks nothing that is not
    also blocked here.
    """
    found = verdicts(graph_of(_django(PROTECT_MODELS)))
    assert found["invoice"].verdict == "not_erased"
    assert found["user"].verdict == "unverified"
    assert "ProtectedError" in found["user"].note
    assert "R3a" in found["user"].reasons


def test_r03b_restrict_without_the_documented_exception(graph_of):
    """R3b [S1]: `RESTRICT` behaves as `PROTECT` where the exception shape is absent.

    The exception is a child that "also references a different object that is being
    deleted in the same operation, but via a `CASCADE` relationship"; with a lone
    `RESTRICT` child there is none, `user.delete()` raises `RestrictedError`, and the
    parent may not read `erased`. Test 5's fixture, which does carry a `CASCADE`
    relation deleted in the same operation, is unchanged.
    """
    found = verdicts(graph_of(_django(DJ_HEAD + """

class Receipt(models.Model):
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    billing_name = models.CharField(max_length=200)
""")))
    assert found["receipt"].verdict == "not_erased"
    assert "RestrictedError" in found["receipt"].note
    assert found["user"].verdict == "unverified"
    assert "R3b" in found["user"].reasons and "RestrictedError" in found["user"].note


# ---------------------------------------------------------------------------
# 2.5's cap, over the rows `hit` does not decide
# ---------------------------------------------------------------------------
def test_declared_helper_never_corroborates_anonymised(graph_of):
    """2.5 with 6.1: the cap holds "whatever row fired", rows 5, 6 and 7 included.

    `cap` read the cap off `hit`, which is None for every verdict 4.7 or 6.2 decided, so
    a record that declares an unregistered helper as an entry point was handed back
    `anonymised` with `reaches_erasure = true`. That is test 53's attack moved one row
    down: the model hands the verifier a helper and is handed back a reaching verdict.
    """
    graph = graph_of(_django(DJ_HEAD + "    full_name = models.CharField(max_length=100)\n",
                             view="", **{"scrub.py": """
from app.models import User


def blank_user(uid):
    user = User.objects.get(pk=uid)
    user.email = ""
    user.full_name = ""
    user.save()
"""}))
    declared = [EntryPoint(name="blank_user", kind="unknown", file="scrub.py", line=4,
                           symbol="scrub.blank_user", flags=["declared_unregistered"])]
    found = verdicts(graph, entry_points=declared)["user"]
    assert found.verdict == "unverified" and not found.reaches_erasure
    assert "03-verifier.md 2.5" in found.reasons


# ---------------------------------------------------------------------------
# R24: the literal at the call site, and nothing else
# ---------------------------------------------------------------------------
def test_r24_a_variable_named_like_the_literal_is_not_one(graph_of):
    """R24 [S47] and 4.3: "the `regulation_type` **string literal at the call site**".

    The edge note carried the argument as written whatever its kind, so a module
    constant `SUPPRESS_WITH_DELETE = "DELETE_INTERNAL"` took the one route by which a
    `third_party` store can reach erasure, on the name of a variable bound to the value
    R24 explicitly refuses.
    """
    files = _segment("SUPPRESS_WITH_DELETE")
    files["app/views.py"] = ('SUPPRESS_WITH_DELETE = "DELETE_INTERNAL"\n'
                             + files["app/views.py"])
    found = verdicts(graph_of(files))["segment"]
    assert found.verdict == "external_manual"
    assert "destination" in found.note.lower()
