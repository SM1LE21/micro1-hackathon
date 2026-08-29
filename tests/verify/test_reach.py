"""`path_exists` and the search state (03-verifier.md 5), plus 6.4's risk inputs.

Breadth-first over `(node, mode, passed)`: the cycle terminates, `must_pass_through`
is honoured, the walk starts in mode `none` and only a primitive or SE10 sets one,
an ambiguous edge can be walked but never carries `erased`, and two runs over the
same repository cite the same path. Tests 29, 41, 47, 48 and 51 of section 10 live
here because each is a statement about the walk rather than about one rule.
"""

from __future__ import annotations

from art30.verify.reach import path_exists, risk_flags, verdicts

MODELS = """
from django.db import models


class User(models.Model):
    email = models.EmailField()


class Avatar(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="avatars/")
"""

CHAIN = """
import boto3

s3 = boto3.client("s3")
BUCKET = "uploads"


def close_account(user):
    step_a(user)


def step_a(user):
    step_b(user)


def step_b(user):
    step_a(user)
    drop(user)


def drop(user):
    s3.delete_object(Bucket=BUCKET, Key=str(user.id))
"""


def _verdicts(graph) -> dict[str, str]:
    return {k: v.verdict for k, v in verdicts(graph).items()}


def _entry(graph, name: str):
    return next(e for e in graph.entry_points if e.name == name)


# ---------------------------------------------------------------------------
# 5.1 and 5.2
# ---------------------------------------------------------------------------
def test_path_steps_carry_a_citation_each(graph_of):
    """5.1: a step is `{from, to, kind, file, line, rule, ambiguous}` (Privado [S12a])."""
    graph = graph_of({"storage.py": CHAIN})
    path = path_exists(graph, _entry(graph, "close_account"), "store:uploads")
    assert path is not None and path.ambiguous is False
    step = path.steps[-1].as_dict()
    assert set(step) == {"from", "to", "kind", "file", "line", "rule", "ambiguous"}
    assert (step["to"], step["kind"], step["file"]) == ("store:uploads", "SE12", "storage.py")
    assert step["line"] == 21


def test_cycle_terminates(graph_of):
    """Test 47, 5.2: `seen` is over states, so mutual recursion is walked once."""
    graph = graph_of({"storage.py": CHAIN})
    path = path_exists(graph, _entry(graph, "close_account"), "store:uploads")
    assert path is not None
    assert path.nodes == ["entry:close_account", "storage.close_account", "storage.step_a",
                          "storage.step_b", "storage.drop", "store:uploads"]


def test_must_pass_through(graph_of):
    """Test 48, 5.2: the AI Act extension's boolean, unused by the GDPR rule set."""
    graph = graph_of({"storage.py": CHAIN})
    entry = _entry(graph, "close_account")
    assert path_exists(graph, entry, "store:uploads",
                       must_pass_through={"storage.step_b"}) is not None
    assert path_exists(graph, entry, "store:uploads",
                       must_pass_through={"storage.never_defined"}) is None


def test_walk_starts_in_mode_none_and_a_primitive_sets_it(graph_of):
    """4.2, decision 19: `mode_of(entry) = none`; SE12 sets the mode it names."""
    graph = graph_of({"settings.py": "INSTALLED_APPS = ['app']\n", "app/__init__.py": "",
                      "app/models.py": MODELS, "app/views.py": """
    from app.models import User


    def close_account(request, user_id):
        user = User.objects.get(pk=user_id)
        user.delete()
    """})
    entry = _entry(graph, "close_account")
    assert entry.mode == "none" and entry.sets_mode is None
    path = path_exists(graph, entry, "store:avatar")
    # SE1 is admissible in `model_delete` and `queryset_delete` and in neither `none`
    # nor any other, so reaching the cascaded child at all is the proof that the SE12
    # step set a mode the entry point did not carry.
    assert path is not None and path.mode in {"model_delete", "queryset_delete"}
    assert [s.kind for s in path.steps] == ["entry", "SE12", "SE1"]
    assert path.steps[0].kind == "entry" and path.steps[1].kind == "SE12"


def test_r16_admin_two_paths_differ_by_mode(graph_of):
    """Test 29, R16 [S8] [S9]: `delete_model` runs the override, `delete_selected` does not."""
    graph = graph_of({"settings.py": "INSTALLED_APPS = ['app']\n", "app/__init__.py": "",
                      "app/models.py": MODELS + """

    def delete(self, *args, **kwargs):
        self.image.delete(save=False)
        return super().delete(*args, **kwargs)
""", "app/admin.py": """
    from django.contrib import admin

    from app.models import Avatar, User

    admin.site.register(User)
    admin.site.register(Avatar)
    """})
    single, bulk = _entry(graph, "admin_delete_model"), _entry(graph, "admin_delete_selected")
    assert single.admin_only and bulk.admin_only
    assert (single.sets_mode, bulk.sets_mode) == ("model_delete", "queryset_delete")
    reached = path_exists(graph, single, "store:avatar.image")
    assert reached is not None and reached.mode == "model_delete"
    assert path_exists(graph, bulk, "store:avatar.image") is None


def test_ambiguous_edge_never_produces_erased(graph_of):
    """Decision 2, R26: the two edge sets differ, and the difference is `unverified`."""
    graph = graph_of({"settings.py": "INSTALLED_APPS = ['app']\n", "app/__init__.py": "",
                      "app/models.py": MODELS + """

    def delete(self, *args, **kwargs):
        self.image.delete(save=False)
        return super().delete(*args, **kwargs)
""", "app/views.py": """
    from app.models import Avatar


    def close_account(request, user):
        Avatar.objects.filter(user=user).delete()
    """})
    assert _verdicts(graph)["avatar.image"] == "unverified"


def test_the_walk_is_deterministic(graph_of):
    """5.2 and 7.5: sorted out-edges, so the same repository cites the same path."""
    files = {"storage.py": CHAIN}
    first, second = graph_of(files, "one"), graph_of(files, "two")
    a = path_exists(first, _entry(first, "close_account"), "store:uploads")
    b = path_exists(second, _entry(second, "close_account"), "store:uploads")
    assert a.as_list() == b.as_list()
    assert verdicts(first)["uploads"].as_dict() == verdicts(second)["uploads"].as_dict()


# ---------------------------------------------------------------------------
# 2.3 and 2.2: the repositories with no start node
# ---------------------------------------------------------------------------
def test_no_entry_point_repo(graph_of):
    """Test 41, 2.3: five stores and no way in means every store says so."""
    graph = graph_of({"app/__init__.py": "", "app/models.py": MODELS})
    assert set(_verdicts(graph).values()) == {"no_entry_point"}


def test_unrelated_delete_route_is_not_an_entry_point(graph_of):
    """Test 51, 2.2: the HTTP method is not the qualification; the subject is."""
    graph = graph_of({"app/__init__.py": "", "app/models.py": """
    from sqlalchemy import Column, Integer, String
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()


    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)
        email = Column(String)


    class Post(Base):
        __tablename__ = "posts"
        id = Column(Integer, primary_key=True)
        body = Column(String)
    """, "app/api.py": """
    from fastapi import APIRouter

    from app.models import Post

    router = APIRouter()


    @router.delete("/posts/{post_id}")
    def delete_post(post_id, session):
        session.delete(session.get(Post, post_id))
    """})
    assert graph.entry_points == []
    assert _verdicts(graph) == {"posts": "no_entry_point", "users": "no_entry_point"}


# ---------------------------------------------------------------------------
# 6.4: the inputs the harness rates from
# ---------------------------------------------------------------------------
def test_risk_flags_no_entry_point_is_high(graph_of):
    """6.4 with ADR 0004 P-09: S08 and R04 must not fall to `low`."""
    graph = graph_of({"app/__init__.py": "", "app/models.py": MODELS})
    flags = risk_flags(verdicts(graph))
    assert flags["rating"] == "high" and "user" in flags["high_stores"]
    assert flags["verdicts"]["user"] == "no_entry_point"


def test_risk_flags_timer_only_is_medium(graph_of):
    """6.4: every store reaches, at least one only after a timer."""
    graph = graph_of({
        "settings.py": "INSTALLED_APPS = ['app']\n"
                       "beat_schedule = {'purge': {'task': 'jobs.purge_closed_accounts'}}\n",
        "app/__init__.py": "", "app/models.py": """
    from django.db import models


    class User(models.Model):
        email = models.EmailField()
        deleted_at = models.DateTimeField(null=True)
    """, "app/views.py": """
    from django.utils import timezone

    from app.models import User


    def close_account(request, user_id):
        user = User.objects.get(pk=user_id)
        user.deleted_at = timezone.now()
        user.save()
    """, "jobs.py": """
    from datetime import timedelta

    from celery import shared_task
    from django.utils import timezone

    from app.models import User


    @shared_task
    def purge_closed_accounts():
        cutoff = timezone.now() - timedelta(days=30)
        User.objects.filter(deleted_at__lt=cutoff).delete()
    """})
    flags = risk_flags(verdicts(graph))
    assert flags["verdicts"]["user"] == "erased_after_timer"
    assert (flags["rating"], flags["timer_only"]) == ("medium", True)


MODE_BEARING = {"SE1", "SE2", "SE3", "SE4", "SE5", "SE6", "SE7", "SE8", "SE9"}
SA_ONDELETE = """
from sqlalchemy import Column, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()
engine = create_engine("postgresql://host/db")
Session = sessionmaker(bind=engine)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String)
    notes = relationship("Note")


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    body = Column(String)
"""


def test_no_mode_bearing_edge_is_walked_before_a_mode_is_set(graph_of):
    """4.2, decision 19: SE1-SE9 stay inadmissible until a primitive edge sets a mode.

    SE7's own row in the 4.2 table reads "all modes incl. `bulk_dml`", which taken
    literally would include `none` and make an `ondelete="CASCADE"` child reachable
    before any delete had been called at all. `ADMISSIBLE_IN_NONE` is what settles it
    inside the search, so this walks every path of a repository that has an SE7 edge
    and checks the mode was already set at every mode-bearing step.
    """
    from art30.verify.reach import Reach

    graph = graph_of({"models.py": SA_ONDELETE, "account.py": """
    from models import Session, User


    def close_account(user_id):
        session = Session()
        user = session.get(User, user_id)
        session.delete(user)
    """})
    assert any(e.kind == "SE7" for e in graph.edges)
    reach = Reach(graph)
    walks = [reach.walk(entry) for entry in reach.starts]
    assert walks, "the fixture must have a start node for the walk to say anything"
    for found in walks:
        for path in found.values():
            mode = "none"
            for step in path.steps:
                assert not (mode == "none" and step.kind in MODE_BEARING), (
                    f"{step.kind} was walked in mode none at {step.file}:{step.line}")
                edge = next(e for e in graph.edges
                            if (e.src, e.dst, e.kind) == (step.src, step.dst, step.kind))
                mode = edge.sets_mode or mode


# ---------------------------------------------------------------------------
# 6.4: the third signal, and the negative that must not turn a rating
# ---------------------------------------------------------------------------
LINKED_MODELS = """
from django.db import models


class User(models.Model):
    email = models.EmailField()


class Invoice(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    billing_name = models.CharField(max_length=200)


class Product(models.Model):
    title = models.CharField(max_length=200)
    price = models.IntegerField()
"""
CLOSE = """
from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    user.delete()
"""


def test_risk_flags_a_subject_linked_store_rates_high(graph_of):
    """6.4: a store carrying a subject link is the third signal the rating needs.

    `guard` is a 3.9 strong-list match and `billing_name` is not on it, so a store with
    detected columns and no strong hit rated `low` whatever its verdict -- S03 rated
    `low` while `invoices` was `unverified` with a `billing_name` its manifest
    categorises as an identifier, which is the failure 6.4 names ("the gate would
    under-warn on exactly the divergence the spec is proud of allowing"). Under-warning
    is the unsafe direction for a rating.
    """
    graph = graph_of({"settings.py": "INSTALLED_APPS = ['app']\n", "app/__init__.py": "",
                      "app/models.py": LINKED_MODELS, "app/views.py": CLOSE})
    found = verdicts(graph)
    assert (found["invoice"].guard, found["invoice"].linked) == ("", True)
    flags = risk_flags(found)
    assert flags["rating"] == "high" and flags["high_stores"] == ["invoice"]


def test_risk_flags_a_negative_store_does_not_turn_the_rating(graph_of):
    """3.9's precision test: `products` has columns, no strong match and no subject link."""
    graph = graph_of({"settings.py": "INSTALLED_APPS = ['app']\n", "app/__init__.py": "",
                      "app/models.py": LINKED_MODELS.replace("""

class Invoice(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    billing_name = models.CharField(max_length=200)
""", ""), "app/views.py": CLOSE})
    found = verdicts(graph)
    assert (found["product"].verdict, found["product"].linked) == ("not_erased", False)
    assert risk_flags(found)["rating"] == "low"


# ---------------------------------------------------------------------------
# 1.5, CG-15: a reference is not a call edge, in either direction
# ---------------------------------------------------------------------------
def test_a_reference_to_a_scheduler_leaves_the_store_unverified(graph_of):
    """1.5: "the store stays `unverified` rather than `not_erased` if that reference is
    the only thing standing between the store and a primitive".

    `graph.references` was built and read by nothing. A helper handed to a queue is a
    different finding from a helper mentioned nowhere, and `not_erased` asserted more
    than the AST can see: whether `my_queue.push` ever calls it is outside the repository.
    """
    graph = graph_of({"storage.py": """
    import boto3

    s3 = boto3.client("s3")
    BUCKET = "uploads"


    def cleanup_user_files(user):
        s3.delete_object(Bucket=BUCKET, Key=str(user.id))
    """, "views.py": """
    import my_queue

    from storage import cleanup_user_files


    def close_account(request):
        my_queue.push(cleanup_user_files, request.user)
    """})
    found = verdicts(graph)["uploads"]
    assert found.verdict == "unverified" and not found.reaches_erasure
    assert "03-verifier.md 1.5" in found.reasons


def test_a_helper_named_nowhere_stays_not_erased(graph_of):
    """Test 38's shape is not the reference shape: nothing mentions the helper at all."""
    graph = graph_of({"storage.py": """
    import boto3

    s3 = boto3.client("s3")
    BUCKET = "uploads"


    def cleanup_user_files(user):
        s3.delete_object(Bucket=BUCKET, Key=str(user.id))
    """, "views.py": '''
    def close_account(request):
        """Closes the account and removes the user's files."""
        return None
    '''})
    found = verdicts(graph)["uploads"]
    assert found.verdict == "not_erased" and "no entry point reaches it" in found.note


def test_admissible_in_none_names_only_edge_kinds_that_exist(graph_of):
    """4.2: the constant is the search's own state space, so a member no builder emits
    is a claim about the graph that is not true. 1.5's promotion half -- a reference
    passed to a known scheduler becoming an edge -- is not implemented, so `reference`
    is not an edge kind and is not named."""
    from art30.verify.reach import ADMISSIBLE_IN_NONE

    assert "reference" not in ADMISSIBLE_IN_NONE
