"""`erased_after_timer` and the retention numbers (03-verifier.md 6.2 and 6.3).

Five requirements, all of them, or the verdict falls back to row 9. Requirement 3 --
a schedule registration, cited -- is the one a `@shared_task` decorator does not
supply (decision 20), and its negative twin is the test to watch: an unscheduled
purge job renders `not_erased`, never `erased_after_timer`. Requirement 4 is the
second: a retention period nothing in the repository resolves to a number of days
falls back too, rather than crediting a purge whose period the tool cannot read.

Tests 37, 37a and 49 of section 10, plus the 6.3 parsing rows.
"""

from __future__ import annotations

from art30.verify.reach import verdicts

MODELS = """
from django.db import models


class User(models.Model):
    email = models.EmailField()
    deleted_at = models.DateTimeField(null=True)
"""
ROUTE = """
from django.utils import timezone

from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    user.deleted_at = timezone.now()
    user.save()
"""
JOB = """
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from app.models import User
{constant}

@shared_task
def purge_closed_accounts():
    cutoff = timezone.now() - timedelta({period})
    User.objects.filter(deleted_at__lt=cutoff).delete()
"""
SCHEDULED = ("INSTALLED_APPS = ['app']\n"
             "beat_schedule = {'purge': {'task': 'jobs.purge_closed_accounts'}}\n")


def _repo(period: str = "days=30", settings: str = SCHEDULED, constant: str = "") -> dict:
    return {"settings.py": settings, "app/__init__.py": "", "app/models.py": MODELS,
            "app/views.py": ROUTE,
            "jobs.py": JOB.format(period=period, constant=constant)}


# ---------------------------------------------------------------------------
# 6.2: the five requirements
# ---------------------------------------------------------------------------
def test_r25_soft_delete_plus_purge(graph_of):
    """Test 37, R25 and 6.2: all five, with the schedule entry among the citations."""
    found = verdicts(graph_of(_repo()))["user"]
    assert (found.verdict, found.timer_days) == ("erased_after_timer", 30)
    assert found.reaches_erasure is True
    cited = {(c["file"], c["line"]) for c in found.evidence}
    assert ("app/views.py", 8) in cited          # 1: the soft-delete marker
    assert ("settings.py", 2) in cited           # 3: the schedule registration
    assert ("jobs.py", 11) in cited              # 4: the retention period
    assert ("jobs.py", 12) in cited              # 2: the hard delete the job reaches
    assert len(found.evidence) == 4


def test_r25_purge_job_never_scheduled(graph_of):
    """Test 37a, 6.2 requirement 3: the decorator is not evidence that anything runs it."""
    found = verdicts(graph_of(_repo(settings="INSTALLED_APPS = ['app']\n")))["user"]
    assert (found.verdict, found.timer_days) == ("not_erased", None)
    assert "nothing in the repository schedules it" in found.note


def test_purge_with_no_readable_retention_period(graph_of):
    """6.2 requirement 4 and 6.3's last row: an env var yields no number, so row 9."""
    found = verdicts(graph_of(_repo(period='days=int(os.environ["RETENTION"])')))["user"]
    assert (found.verdict, found.timer_days) == ("not_erased", None)
    assert "no retention period" in found.note and "no_timer_evidenced" in found.note


def test_soft_delete_and_nothing_else(graph_of):
    """R25 [S10]: with no purge job at all the marker is the whole of the answer."""
    files = _repo()
    del files["jobs.py"]
    found = verdicts(graph_of(files))["user"]
    assert (found.verdict, found.timer_days) == ("not_erased", None)


# ---------------------------------------------------------------------------
# 6.3: what parses to a number of days
# ---------------------------------------------------------------------------
def test_timedelta_hours_rounds_down(graph_of):
    """6.3: hours rounded down, minimum 1, the original unit kept in the citation."""
    found = verdicts(graph_of(_repo(period="hours=72")))["user"]
    assert (found.verdict, found.timer_days) == ("erased_after_timer", 3)
    assert any(c["symbol"] == "hours" for c in found.evidence)


def test_timedelta_hours_below_a_day_is_one(graph_of):
    """6.3: "hours rounded down, minimum 1"; a six-hour grace is still a timer."""
    found = verdicts(graph_of(_repo(period="hours=6")))["user"]
    assert (found.verdict, found.timer_days) == ("erased_after_timer", 1)


def test_module_constant_is_cited_at_its_own_line(graph_of):
    """6.3: `RETENTION_DAYS = 45` referenced in the filter, cited where it is declared."""
    found = verdicts(graph_of(_repo(period="days=RETENTION_DAYS",
                                    constant="\nRETENTION_DAYS = 45\n")))["user"]
    assert (found.verdict, found.timer_days) == ("erased_after_timer", 45)
    assert {"file": "jobs.py", "line": 8, "symbol": "RETENTION_DAYS"} in found.evidence


# ---------------------------------------------------------------------------
# 6.1 row 1: the backup store never takes an erasure verdict
# ---------------------------------------------------------------------------
BACKUP = """
import subprocess

{constant}

def nightly_backup():
    subprocess.run(["pg_dump", "app"])
"""


def test_backup_no_schedule(graph_of):
    """Test 49, 6.1 row 1: a `pg_dump` with no retention value anywhere."""
    found = verdicts(graph_of({"jobs.py": BACKUP.format(constant=""),
                               "app/__init__.py": "", "app/models.py": MODELS}))["jobs"]
    assert (found.verdict, found.kind, found.timer_days) == (
        "no_schedule_evidenced", "backup", None)
    assert found.reaches_erasure is False


def test_backup_with_a_retention_constant(graph_of):
    """6.1 row 1 and 6.3: a cited schedule makes it `governed_by_retention`."""
    found = verdicts(graph_of({
        "jobs.py": BACKUP.format(constant="BACKUP_RETENTION_DAYS = 35\n"),
        "app/__init__.py": "", "app/models.py": MODELS}))["jobs"]
    assert (found.verdict, found.timer_days) == ("governed_by_retention", 35)
    assert {"file": "jobs.py", "line": 3, "symbol": "BACKUP_RETENTION_DAYS"} in found.evidence


def test_backup_cron_renders_a_criteria_string(graph_of):
    """6.3's last row: a cadence is not a number of days, so a criteria string quotes it."""
    found = verdicts(graph_of({
        "jobs.py": 'import subprocess\n\nBACKUP_CRON = "0 3 * * *"\n\n\n'
                   'def nightly_backup():\n    subprocess.run(["pg_dump", "app"])\n',
        "app/__init__.py": "", "app/models.py": MODELS}))["jobs"]
    assert (found.verdict, found.timer_days) == ("governed_by_retention", None)
    assert '"0 3 * * *"' in found.note
    assert found.evidence == [{"file": "jobs.py", "line": 3, "symbol": "cron_literal"}]


# ---------------------------------------------------------------------------
# 6.2 requirement 3, for every job kind; requirement 1, scoped to the erasure path
# ---------------------------------------------------------------------------
PURGE_COMMAND = """
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from app.models import User


class Command(BaseCommand):
    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=30)
        User.objects.filter(deleted_at__lt=cutoff).delete()
"""
PURGE_CLICK = """
from datetime import timedelta

import click
from django.utils import timezone

from app.models import User


@click.command("purge-users")
def purge_users():
    cutoff = timezone.now() - timedelta(days=30)
    User.objects.filter(deleted_at__lt=cutoff).delete()
"""


def _cli_repo(command: dict[str, str]) -> dict:
    files = {"settings.py": "INSTALLED_APPS = ['app']\n", "app/__init__.py": "",
             "app/models.py": MODELS, "app/views.py": ROUTE}
    files.update(command)
    return files


def test_soft_delete_plus_an_unscheduled_management_command(graph_of):
    """6.2 requirement 3 for kind `cli`, the twin of test 37a one entry-point kind over.

    `_tasks` flags an unscheduled celery job and `Reach.starts` drops it, but a
    `BaseCommand` under `management/commands/` is kind `cli` and carries no flag, so the
    purge was a start node like any other and row 4 rendered `erased` -- the record
    saying the rows are gone today when nothing in the repository has been scheduled to
    remove them at all. Worse than the case 7.3 rejects, and 6.2's own S10-shape
    argument with `cli` substituted for `task`.
    """
    graph = graph_of(_cli_repo({
        "app/management/__init__.py": "", "app/management/commands/__init__.py": "",
        "app/management/commands/purge_users.py": PURGE_COMMAND}))
    assert [e.kind for e in graph.entry_points if e.name == "purge_users"] == ["cli"]
    found = verdicts(graph)["user"]
    assert found.verdict == "not_erased"
    assert "nothing in the repository schedules it" in found.note


def test_soft_delete_plus_an_unscheduled_click_command(graph_of):
    """The same shape spelled `@click.command("purge-users")` (2.2's other cli row)."""
    found = verdicts(graph_of(_cli_repo({"cli.py": PURGE_CLICK})))["user"]
    assert found.verdict == "not_erased"
    assert "nothing in the repository schedules it" in found.note


def test_a_manual_deletion_command_is_untouched(graph_of):
    """The gate is 6.2 requirement 1: no soft-delete marker, no exclusion.

    A `delete_user` management command in a repository that marks nothing is the manual
    data-subject-request shape, and it deletes the row when an operator runs it. It must
    keep reading `erased`, or requirement 3 would have been turned into a rule that
    every command-line deletion path fails.
    """
    graph = graph_of({"settings.py": "INSTALLED_APPS = ['app']\n", "app/__init__.py": "",
                      "app/models.py": """
    from django.db import models


    class User(models.Model):
        email = models.EmailField()
    """,
                      "app/management/__init__.py": "",
                      "app/management/commands/__init__.py": "",
                      "app/management/commands/delete_user.py": """
    from django.core.management.base import BaseCommand

    from app.models import User


    class Command(BaseCommand):
        def handle(self, *args, **options):
            User.objects.filter(pk=options["pk"]).delete()
    """})
    assert verdicts(graph)["user"].verdict == "erased"


def test_requirement_one_reads_only_the_erasure_entry_points(graph_of):
    """6.2 requirement 1 names *the erasure entry point*, not any start node.

    `writes_for` walks every start, the purge job included, so a marker written inside
    the job itself satisfied requirement 1 and could open the `erased_after_timer` row
    for a store whose user-facing path never marks anything. `markers()` passes the
    non-job starts for that reason.
    """
    from art30.verify import timers
    from art30.verify.reach import Reach

    graph = graph_of({"settings.py": SCHEDULED, "app/__init__.py": "",
                      "app/models.py": MODELS, "app/views.py": """
    from app.models import User


    def close_account(request, user_id):
        return User.objects.get(pk=user_id)
    """, "jobs.py": """
    from datetime import timedelta

    from celery import shared_task
    from django.utils import timezone

    from app.models import User


    @shared_task
    def purge_closed_accounts():
        cutoff = timezone.now() - timedelta(days=30)
        for user in User.objects.filter(is_stale=True):
            user.deleted_at = timezone.now()
            user.save()
        User.objects.filter(deleted_at__lt=cutoff).delete()
    """})
    reach = Reach(graph)
    store = graph.stores["user"]
    assert timers.markers(reach, store) == []
    assert timers.erased_after_timer(reach, store) is None
    assert verdicts(graph)["user"].verdict != "erased_after_timer"
