"""Entry-point discovery and reconciliation (03-verifier.md section 2).

Every discovery source of 2.2, the subject qualification of decision 6a, the two
admin entry points of R16, the empty case of 2.3, the task table of 2.4 and the
declared-versus-discovered reconciliation of 2.5 with its `declared_unregistered`
cap. The ten synthetic cases are checked against the entry points their manifests
declare (the manifest is test data; the verifier never reads one).
"""

from __future__ import annotations

import pytest
import yaml

from art30.verify import build_graph, reconcile
from art30.verify.registration import ADMIN_NAMES
from tests.verify.conftest import CASES, FIXTURES, entry_names


def _entry(graph, name):
    found = [e for e in graph.entry_points if e.name == name]
    return found[0] if found else None


# --------------------------------------------------------------------------
# 2.2 discovery sources
# --------------------------------------------------------------------------
def test_flask_delete_route_with_vocabulary(graph_of):
    graph = graph_of({"app.py": """
    from flask import Blueprint

    bp = Blueprint("bp", __name__)


    @bp.route("/account", methods=["DELETE"])
    def delete_account():
        pass
    """})
    entry = _entry(graph, "delete_account")
    assert (entry.kind, entry.line, entry.path) == ("route", 7, "/account")


def test_fastapi_delete_route_qualifies_on_the_path(graph_of):
    graph = graph_of({"app.py": """
    from fastapi import APIRouter

    router = APIRouter()


    @router.delete("/users/{user_id}")
    def remove(user_id: int):
        pass
    """})
    assert _entry(graph, "remove").kind == "route"


def test_unrelated_delete_route_is_not_an_entry_point(graph_of):
    """Decision 6a: the method is not the qualification, the subject is."""
    graph = graph_of({"app.py": """
    from fastapi import APIRouter

    router = APIRouter()


    @router.delete("/posts/{post_id}")
    def delete_post(post_id: int, s):
        s.delete(s.get(Post, post_id))
    """})
    assert graph.entry_points == []


def test_drf_viewset_destroy_on_the_user_model(graph_of):
    graph = graph_of({
        "models.py": "from django.db import models\n\n\nclass User(models.Model):\n"
                     "    email = models.EmailField()\n",
        "views.py": """
        from rest_framework import viewsets

        from models import User


        class UserViewSet(viewsets.ModelViewSet):
            queryset = User.objects.all()

            def destroy(self, request, pk=None):
                pass
        """,
    })
    entry = _entry(graph, "destroy")
    assert entry is not None and entry.kind == "route" and entry.models == ["models.User"]


def test_django_urlpatterns_view(graph_of):
    graph = graph_of({
        "app/__init__.py": "",
        "app/views.py": "def delete_account(request, pk):\n    pass\n\n\n"
                        "def profile(request, pk):\n    pass\n",
        "urls.py": """
        from django.urls import path

        from app import views

        urlpatterns = [
            path("accounts/<int:pk>/delete/", views.delete_account, name="delete_account"),
            path("accounts/<int:pk>/profile/", views.profile, name="profile"),
        ]
        """,
    })
    assert entry_names(graph) == ["delete_account"]
    assert _entry(graph, "delete_account").kind == "view"


def test_delete_view_subclass(graph_of):
    graph = graph_of({"views.py": """
    from django.views.generic import DeleteView


    class AccountDeleteView(DeleteView):
        def delete(self, request, *args, **kwargs):
            pass
    """})
    entry = _entry(graph, "delete")
    assert entry is not None and entry.kind == "view"


def test_management_command(graph_of):
    graph = graph_of({
        "app/__init__.py": "",
        "app/management/__init__.py": "",
        "app/management/commands/__init__.py": "",
        "app/management/commands/delete_user.py": """
        from django.core.management.base import BaseCommand


        class Command(BaseCommand):
            def handle(self, *args, **options):
                pass
        """,
    })
    entry = _entry(graph, "delete_user")
    assert entry is not None and entry.kind == "cli"
    assert entry.file.endswith("commands/delete_user.py")


def test_click_command(graph_of):
    graph = graph_of({"cli.py": """
    import click


    @click.command("purge-users")
    def purge_users():
        pass
    """})
    assert _entry(graph, "purge_users").kind == "cli"


def test_celery_task_and_the_task_table(graph_of):
    graph = graph_of({
        "jobs/__init__.py": "",
        "jobs/purge.py": """
        from celery import shared_task


        @shared_task
        def purge_closed_accounts():
            pass


        @shared_task(name="jobs.other")
        def unrelated_job():
            pass
        """,
    })
    assert entry_names(graph) == ["purge_closed_accounts"]
    assert _entry(graph, "purge_closed_accounts").kind == "task"
    assert graph.task_table == {
        "jobs.other": "jobs.purge.unrelated_job",
        "jobs.purge.purge_closed_accounts": "jobs.purge.purge_closed_accounts",
    }


def test_send_task_resolves_through_the_table(graph_of):
    graph = graph_of({
        "jobs/__init__.py": "",
        "jobs/purge.py": "from celery import shared_task\n\n\n@shared_task\n"
                         "def purge_closed_accounts():\n    pass\n",
        "app.py": 'def go(app):\n    app.send_task("jobs.purge.purge_closed_accounts")\n',
    })
    edge = [e for e in graph.edges if e.kind == "SE11"]
    assert [(e.src, e.dst) for e in edge] == [("app.go", "jobs.purge.purge_closed_accounts")]


def test_module_level_function_is_kind_unknown(graph_of):
    graph = graph_of({"api.py": "def close_account(session, uid):\n    pass\n"})
    assert (_entry(graph, "close_account").kind, _entry(graph, "close_account").line) == ("unknown", 1)


def test_bare_action_verb_needs_a_subject(graph_of):
    """`purge_session` is a helper; `purge_closed_accounts` is an erasure job."""
    graph = graph_of({"cache.py": "def purge_session(user):\n    pass\n"})
    assert graph.entry_points == []


def test_cleanup_is_not_vocabulary(graph_of):
    graph = graph_of({"storage.py": "def cleanup_user_files(uid):\n    pass\n"})
    assert graph.entry_points == []


def test_no_entry_point_repository(graph_of):
    graph = graph_of({
        "models.py": "class User:\n    __tablename__ = 'users'\n    email = Column(String)\n",
        "api.py": "def create_document(s, uid):\n    pass\n",
    })
    assert graph.entry_points == []


# --------------------------------------------------------------------------
# R16: the admin
# --------------------------------------------------------------------------
ADMIN_REPO = {
    "settings.py": "INSTALLED_APPS = ['app']\n",
    "app/__init__.py": "",
    "app/models.py": "from django.db import models\n\n\nclass Account(models.Model):\n"
                     "    email = models.EmailField()\n\n    class Meta:\n"
                     "        db_table = 'account'\n",
    "app/admin.py": "from django.contrib import admin\n\nfrom .models import Account\n\n"
                    "admin.site.register(Account)\n",
}


def test_admin_gives_exactly_two_entry_points(graph_of):
    graph = graph_of(ADMIN_REPO)
    admin = [e for e in graph.entry_points if e.admin_only]
    assert [e.name for e in admin] == ["admin_delete_model", "admin_delete_selected"]
    assert [e.mode for e in admin] == ["none", "none"]        # 4.2: mode_of(entry)
    assert [e.sets_mode for e in admin] == ["model_delete", "queryset_delete"]
    assert {(e.file, e.line) for e in admin} == {("app/admin.py", 5)}
    assert [e.kind for e in admin] == ["admin", "admin"]


def test_admin_registration_of_a_non_personal_model_is_not_an_entry_point(graph_of):
    files = dict(ADMIN_REPO)
    files["app/models.py"] = ("from django.db import models\n\n\nclass Product(models.Model):\n"
                              "    sku = models.CharField(max_length=9)\n\n    class Meta:\n"
                              "        db_table = 'product'\n")
    files["app/admin.py"] = ("from django.contrib import admin\n\nfrom .models import Product\n\n"
                             "admin.site.register(Product)\n")
    assert graph_of(files).entry_points == []


def test_admin_delete_permission_denied_removes_both(graph_of):
    files = dict(ADMIN_REPO)
    files["app/admin.py"] = """
    from django.contrib import admin

    from .models import Account


    class AccountAdmin(admin.ModelAdmin):
        def has_delete_permission(self, request, obj=None):
            return False


    admin.site.register(Account, AccountAdmin)
    """
    assert [e for e in graph_of(files).entry_points if e.admin_only] == []


# --------------------------------------------------------------------------
# 2.5 declared against discovered
# --------------------------------------------------------------------------
S10_LIKE = {
    "api/__init__.py": "",
    "api/account.py": "def close_account(session, uid):\n    pass\n",
    "storage.py": "import boto3\n\nBUCKET = 'uploads'\ns3 = boto3.client('s3')\n\n\n"
                  "def avatar_key(uid):\n    return f'avatars/{uid}.jpg'\n\n\n"
                  "def cleanup_user_files(uid):\n    s3.delete_object(Bucket=BUCKET, Key=avatar_key(uid))\n",
}


def test_reconcile_confirms_a_discovered_entry_point(graph_of):
    graph = graph_of(S10_LIKE)
    rows = reconcile(graph, [{"name": "close_account", "file": "api/account.py", "line": 1}])
    assert rows[0]["status"] == "confirmed" and rows[0]["capped"] is False


def test_reconcile_caps_a_declared_unregistered_helper(graph_of):
    """Decision 5a: S10 falls in four lines without this cap."""
    graph = graph_of(S10_LIKE)
    rows = reconcile(graph, [{"name": "cleanup_user_files", "file": "storage.py", "line": 11}])
    row = [r for r in rows if r["name"] == "cleanup_user_files"][0]
    assert row["status"] == "declared_unregistered" and row["capped"] is True


def test_reconcile_reports_an_unresolvable_citation(graph_of):
    graph = graph_of(S10_LIKE)
    rows = reconcile(graph, [{"name": "delete_everything", "file": "storage.py", "line": 3}])
    row = [r for r in rows if r["name"] == "delete_everything"][0]
    assert row["status"] == "unresolved" and row["capped"] is True


def test_reconcile_lists_a_discovered_entry_point_the_record_missed(graph_of):
    graph = graph_of(S10_LIKE)
    rows = reconcile(graph, [])
    assert [r["name"] for r in rows if r["status"] == "missing"] == ["close_account"]


def test_reconcile_accepts_a_declared_registered_route(graph_of):
    graph = graph_of({"app.py": """
    from fastapi import APIRouter

    router = APIRouter()


    @router.delete("/posts/{post_id}")
    def delete_post(post_id: int):
        pass
    """})
    rows = reconcile(graph, [{"name": "delete_post", "file": "app.py", "line": 8}])
    row = [r for r in rows if r["name"] == "delete_post"][0]
    assert row["status"] == "declared_only" and row["capped"] is False


# --------------------------------------------------------------------------
# the ten synthetic cases
# --------------------------------------------------------------------------
@pytest.mark.parametrize("case", CASES)
def test_manifest_entry_points_are_discovered(case):
    manifest = yaml.safe_load((FIXTURES / "manifests" / f"{case}.yaml").read_text())
    graph = build_graph(FIXTURES / "synthetic" / case)
    found = {(e.name, e.file, e.line) for e in graph.entry_points}
    declared = {(e["name"], e["file"], e["line"]) for e in (manifest.get("entry_points") or [])}
    assert declared <= found, f"{case}: missing {sorted(declared - found)}"
    if not declared:
        assert graph.entry_points == []


def test_url_with_a_string_view_reference(graph_of):
    """CG-17: `url(r"^x$", "app.views.close_account")` is a declaration, not a call."""
    graph = graph_of({
        "app/__init__.py": "",
        "app/views.py": "def close_account(request):\n    pass\n",
        "urls.py": 'from django.conf.urls import url\n\n'
                   'urlpatterns = [url(r"^close$", "app.views.close_account")]\n',
    })
    entry = _entry(graph, "close_account")
    assert (entry.kind, entry.file, entry.line) == ("view", "app/views.py", 1)
    assert not [e for e in graph.edges if e.src.startswith("urls")]


# --------------------------------------------------------------------------
# 6.2 requirement 3: a task decorator is a candidate, not a schedule
# --------------------------------------------------------------------------
UNSCHEDULED_JOB = {
    "jobs/__init__.py": "",
    "jobs/purge.py": "from celery import shared_task\n\n\n@shared_task\n"
                     "def purge_closed_accounts():\n    pass\n",
}


def test_an_unscheduled_task_is_flagged_unscheduled(graph_of):
    """2.2: the decorator is never on its own evidence that anything runs the job."""
    entry = _entry(graph_of(UNSCHEDULED_JOB), "purge_closed_accounts")
    assert entry.kind == "task" and "unscheduled" in entry.flags
    assert "schedule_registered" not in entry.flags
    assert "nothing in the repository schedules it" in entry.note


def test_a_beat_schedule_entry_registers_the_task_and_is_cited(graph_of):
    files = dict(UNSCHEDULED_JOB)
    files["config.py"] = """
    from celery.schedules import crontab

    CELERYBEAT_SCHEDULE = {
        "purge-closed-accounts": {
            "task": "jobs.purge.purge_closed_accounts",
            "schedule": crontab(minute="0", hour="4"),
        },
    }
    """
    entry = _entry(graph_of(files), "purge_closed_accounts")
    assert "schedule_registered" in entry.flags and "unscheduled" not in entry.flags
    assert entry.note == "schedule registered at config.py:3 (CELERYBEAT_SCHEDULE)"


def test_a_dispatch_call_also_registers_the_task(graph_of):
    files = dict(UNSCHEDULED_JOB)
    files["app.py"] = ('def go(app):\n'
                       '    app.send_task("jobs.purge.purge_closed_accounts")\n')
    entry = _entry(graph_of(files), "purge_closed_accounts")
    assert "schedule_registered" in entry.flags


def test_the_scheduled_synthetic_jobs_keep_their_registration():
    for case in ("S03", "S10"):
        graph = build_graph(FIXTURES / "synthetic" / case)
        jobs = [e for e in graph.entry_points if e.kind == "task"]
        assert jobs and all("schedule_registered" in e.flags for e in jobs), case


# --------------------------------------------------------------------------
# 2.2: the admin denial is scoped to its own model
# --------------------------------------------------------------------------
def test_admin_delete_permission_denial_is_scoped_to_its_model(graph_of):
    """One `ModelAdmin` denying deletion took the two entry points away for every
    registered model in the repository."""
    files = dict(ADMIN_REPO)
    files["app/models.py"] = ("from django.db import models\n\n\n"
                              "class Account(models.Model):\n"
                              "    email = models.EmailField()\n\n"
                              "    class Meta:\n        db_table = 'account'\n\n\n"
                              "class Invoice(models.Model):\n"
                              "    account = models.ForeignKey(Account, on_delete=models.CASCADE)\n"
                              "    email = models.EmailField()\n\n"
                              "    class Meta:\n        db_table = 'invoice'\n")
    files["app/admin.py"] = """
    from django.contrib import admin

    from .models import Account, Invoice


    class InvoiceAdmin(admin.ModelAdmin):
        def has_delete_permission(self, request, obj=None):
            return False


    admin.site.register(Account)
    admin.site.register(Invoice, InvoiceAdmin)
    """
    admin = [e for e in graph_of(files).entry_points if e.admin_only]
    assert [e.name for e in admin] == ["admin_delete_model", "admin_delete_selected"]
    assert all(e.models == ["app.models.Account"] for e in admin)


def test_a_conditional_delete_permission_is_not_a_denial(graph_of):
    """The text test stays the approximation, restricted to the method's only return."""
    files = dict(ADMIN_REPO)
    files["app/admin.py"] = """
    from django.contrib import admin

    from .models import Account


    class AccountAdmin(admin.ModelAdmin):
        def has_delete_permission(self, request, obj=None):
            if obj is not None and obj.locked:
                return False
            return True


    admin.site.register(Account, AccountAdmin)
    """
    assert [e.name for e in graph_of(files).entry_points if e.admin_only] == list(ADMIN_NAMES)


# --------------------------------------------------------------------------
# 2.2 route row: the non-decorator registration
# --------------------------------------------------------------------------
def test_add_url_rule_registers_a_delete_route(graph_of):
    graph = graph_of({"app.py": """
    from flask import Flask

    app = Flask(__name__)


    def delete_user(uid):
        pass


    def read_post(pid):
        pass


    app.add_url_rule("/account", "delete_user", delete_user, methods=["DELETE"])
    app.add_url_rule("/posts/<pid>", "read_post", read_post, methods=["GET"])
    """})
    entry = _entry(graph, "delete_user")
    assert (entry.kind, entry.path, entry.line) == ("route", "/account", 6)
    assert entry.flags == ["route_registration"]
    assert _entry(graph, "read_post") is None


def test_add_url_rule_qualifies_on_the_subject_path(graph_of):
    """Decision 6a binds this shape too: the name need not hit the vocabulary."""
    graph = graph_of({"app.py": """
    from flask import Flask

    app = Flask(__name__)


    def drop(uid):
        pass


    app.add_url_rule("/users/<uid>", "drop", view_func=drop, methods=["DELETE"])
    """})
    assert _entry(graph, "drop").kind == "route"


def test_add_url_rule_on_an_unrelated_resource_is_not_an_entry_point(graph_of):
    graph = graph_of({"app.py": """
    from flask import Flask

    app = Flask(__name__)


    def drop_post(pid):
        pass


    app.add_url_rule("/posts/<pid>", "drop_post", drop_post, methods=["DELETE"])
    """})
    assert graph.entry_points == []
