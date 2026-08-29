"""Claim checking, row by row (03-verifier.md 7).

Every row of 7.3's verdict-consistency table is a named test here, so a row that
loses its check is visible as a missing name. The other three halves of section 7 are
pinned too: 7.1 (what blocks and what does not), 7.2 on a call the formatter broke
across three lines, 7.4 on an omitted store and an omitted entry point, and 7.5 on
the bytes.

The asymmetry the whole arm rests on is tests `row4` and `row5`: a record safer than
the evidence is recorded and accepted, a record safer than the code is rejected, and
nothing here can turn a conservative claim into a reaching one.
"""

from __future__ import annotations

import json

from jsonschema import Draft202012Validator

from art30.verify import feedback as strings
from art30.verify.check import check

# ---------------------------------------------------------------------------
# inline repositories
# ---------------------------------------------------------------------------
MODELS = """
from django.db import models


class User(models.Model):
    email = models.EmailField()
"""
ROUTE = """
from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    user.delete()
"""
SOFT_DELETE_ROUTE = """
from django.utils import timezone

from app.models import User


def close_account(request, user_id):
    user = User.objects.get(pk=user_id)
    user.deleted_at = timezone.now()
    user.save()
"""
PURGE = """
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from app.models import User


@shared_task
def purge_closed_accounts():
    cutoff = timezone.now() - timedelta(days=30)
    User.objects.filter(deleted_at__lt=cutoff).delete()
"""
SCHEDULED = ("INSTALLED_APPS = ['app']\n"
             "beat_schedule = {'purge': {'task': 'jobs.purge_closed_accounts'}}\n")


def repo(models_body: str = MODELS, view: str = ROUTE,
         settings: str = "INSTALLED_APPS = ['app']\n", **extra) -> dict[str, str]:
    files = {"settings.py": settings, "app/__init__.py": "", "app/models.py": models_body,
             "app/views.py": view}
    files.update(extra)
    return files


def child(token: str) -> str:
    return MODELS + f"""

class Post(models.Model):
    user = models.ForeignKey(User, on_delete=models.{token})
    body = models.TextField()
"""


# ---------------------------------------------------------------------------
# record building
# ---------------------------------------------------------------------------
HUMAN: dict = {
    "controller": {"name": None, "contact": None},
    "joint_controller": {"name": None, "contact": None},
    "representative": {"name": None, "contact": None},
    "dpo": {"name": None, "contact": None},
    "purposes": None, "legal_basis": None, "data_subject_categories_confirmed": None,
    "data_categories_outside_code": None, "special_categories": None,
    "transfers": {"occurs": None, "countries": None, "safeguards": None},
    "retention_justification": None, "security_organisational": None,
}
ENTRY = {"name": "close_account", "kind": "route", "file": "app/views.py", "line": 4,
         "admin_only": False, "note": None}
SOFT_ENTRY = dict(ENTRY, line=6)        # the soft-delete route sits two imports lower
USER_STORE = {
    "name": "user", "kind": "relational",
    "declared_at": {"file": "app/models.py", "line": 4, "symbol": "User"},
    "subject_link": {"file": "app/models.py", "line": 4},
    "fields": [{"name": "email", "category": "contact", "file": "app/models.py",
                "line": 5, "note": None, "erasure": None}],
    "erasure": {"verdict": "erased", "evidence": [{"file": "app/views.py", "line": 6,
                                                   "symbol": "delete"}],
                "timer_days": None, "note": None},
    "recipient_kind": None, "note": None,
}


def cite(file: str, line: int, symbol: str) -> dict:
    return {"file": file, "line": line, "symbol": symbol}


def erasure(verdict: str, evidence=(), timer_days=None, note=None) -> dict:
    return {"verdict": verdict, "evidence": list(evidence), "timer_days": timer_days,
            "note": note}


def store(name: str, kind: str, declared_at, subject_link, fields, block) -> dict:
    return {"name": name, "kind": kind, "declared_at": declared_at,
            "subject_link": subject_link, "fields": fields, "erasure": block,
            "recipient_kind": None, "note": None}


def field(name: str, category: str, file: str, line: int, block=None) -> dict:
    return {"name": name, "category": category, "file": file, "line": line,
            "note": None, "erasure": block}


def record(stores, entry_points=(ENTRY,)) -> dict:
    return {"schema_version": "1", "repository": "app", "unscanned": [],
            "data_subjects": [], "entry_points": [dict(e) for e in entry_points],
            "stores": [json.loads(json.dumps(s)) for s in stores], "retention": [],
            "activities": [],
            "hints": {"observed_module_names": [], "observed_region_hints": [],
                      "security_evidence": []},
            "human": json.loads(json.dumps(HUMAN))}


def post_store(verdict: str, evidence=(), timer_days=None) -> dict:
    return store("post", "relational", cite("app/models.py", 8, "Post"),
                 {"file": "app/models.py", "line": 9},
                 [field("body", "free_text_may_contain", "app/models.py", 10)],
                 erasure(verdict, evidence, timer_days))


def soft_delete_repo() -> dict[str, str]:
    """The S10 shape in five files: a marker on the route, a scheduled purge behind it."""
    return repo(MODELS + "    deleted_at = models.DateTimeField(null=True)\n",
                view=SOFT_DELETE_ROUTE, settings=SCHEDULED, **{"jobs.py": PURGE})


# ---------------------------------------------------------------------------
# 7.3, row by row
# ---------------------------------------------------------------------------
def test_row1_a_reaching_claim_over_a_surviving_row_is_rejected(mkrepo):
    """Row 1, the false-safe direction: `SET_NULL` leaves the row and its columns."""
    root = mkrepo(repo(child("SET_NULL")))
    found = check(record([USER_STORE, post_store("erased")]), root)

    assert found.accepted is False
    entry = found.rejected_claims[0]
    assert (entry["store"], entry["field"]) == ("post", None)
    assert entry["claim"] == "erasure.verdict=erased"
    assert entry["expected"] == "verdict not_erased, or cite the path"
    assert entry["reason"].startswith(
        "no path from entry point close_account (app/views.py:4) to any relational"
        " row-deletion primitive; ")
    assert "is SET_NULL; the row survives" in entry["reason"]


def test_row2_a_reaching_claim_on_an_unverified_store_is_rejected(mkrepo):
    """Row 2, R3b: an unverifiable safe claim is a safe claim without evidence."""
    models = MODELS + """

class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total = models.IntegerField()


class Receipt(models.Model):
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    billing_name = models.CharField(max_length=200)
"""
    receipt = store("receipt", "relational", cite("app/models.py", 13, "Receipt"),
                    {"file": "app/models.py", "line": 14},
                    [field("billing_name", "identifier", "app/models.py", 15)],
                    erasure("erased", [cite("app/views.py", 6, "delete")]))
    found = check(record([USER_STORE, receipt]), mkrepo(repo(models)))

    entry = found.rejected_claims[0]
    assert (entry["store"], found.accepted) == ("receipt", False)
    assert entry["expected"] == "verdict unverified, or cite the path"
    assert entry["reason"].endswith("the path cannot be decided from the source")


def test_row3_erased_where_the_verifier_found_a_timer_is_rejected(mkrepo):
    """Row 3: the retention column would say the data is gone today; it survives 30."""
    root = mkrepo(soft_delete_repo())
    item = json.loads(json.dumps(USER_STORE))
    item["erasure"] = erasure("erased", [cite("jobs.py", 12, "delete")])
    found = check(record([item], [SOFT_ENTRY]), root)

    entry = found.rejected_claims[0]
    assert (entry["store"], found.accepted) == ("user", False)
    assert entry["expected"] == "verdict erased_after_timer, or cite the path"
    assert "scheduled job" in entry["reason"]


def test_row4_a_timer_claimed_over_a_direct_delete_is_a_divergence(mkrepo):
    """Row 4: conservative, and the timer is cited. Accepted, and recorded."""
    root = mkrepo(repo())
    safer = json.loads(json.dumps(USER_STORE))
    safer["erasure"] = erasure("erased_after_timer",
                               [cite("app/views.py", 6, "delete")], 30)
    found = check(record([safer]), root)

    assert found.accepted is True and found.rejected_claims == []
    assert found.conservative_divergences == [
        {"store": "user", "claim": "erasure.verdict=erased_after_timer",
         "verifier": found.conservative_divergences[0]["verifier"],
         "note": "accepted; the record is more conservative than the evidence"}]
    assert found.conservative_divergences[0]["verifier"].startswith("erased via ")


def test_row4_a_divergence_is_never_also_an_off_path_rejection(mkrepo):
    """7.3 rows 4 and 6 against the last row: a divergence is accepted, never rejected.

    The evidence check is "a citation that points at the right file and the wrong
    reason", which presupposes the verifier corroborates the claim. Where the labels
    differ the store is already decided, and a rejection here would contradict the
    `conservative_divergences` entry the same pass wrote.
    """
    root = mkrepo(repo())
    safer = json.loads(json.dumps(USER_STORE))
    safer["erasure"] = erasure("erased_after_timer",
                               [cite("app/models.py", 5, "email")], 30)
    found = check(record([safer]), root)

    assert found.accepted is True and found.rejected_claims == []
    assert found.conservative_divergences[0]["store"] == "user"


def test_row5_a_conservative_verdict_is_accepted_and_recorded(mkrepo):
    """Row 5: the verifier never upgrades a claim to safer than the model wrote."""
    root = mkrepo(repo(child("CASCADE")))
    found = check(record([USER_STORE, post_store("not_erased")]), root)

    assert found.accepted is True and found.rejected_claims == []
    entry = found.conservative_divergences[0]
    assert (entry["store"], entry["claim"]) == ("post", "erasure.verdict=not_erased")
    assert entry["verifier"] == "erased via on_delete=CASCADE app/models.py:9"
    assert entry["note"] == "accepted; the record is more conservative than the evidence"


def test_row6_two_false_side_labels_are_accepted(mkrepo):
    """Row 6: the scored tuple is `reaches_erasure`; the label is rendered, not scored."""
    root = mkrepo(repo(child("SET_NULL")))
    found = check(record([USER_STORE, post_store("unverified")]), root)

    assert found.accepted is True
    assert (found.rejected_claims, found.conservative_divergences) == ([], [])


def test_row7_a_backup_verdict_on_a_relational_store_is_rejected(mkrepo):
    """Row 7: those two verdicts belong to one kind and the kind decides the render."""
    root = mkrepo(repo())
    wrong = json.loads(json.dumps(USER_STORE))
    wrong["erasure"] = erasure("governed_by_retention", [cite("app/views.py", 6, "delete")], 35)
    found = check(record([wrong]), root)

    entry = found.rejected_claims[0]
    assert found.accepted is False
    assert entry["reason"] == ("governed_by_retention is not a verdict a store of kind"
                              " relational takes")
    assert entry["expected"].startswith("a verdict for kind relational")


def test_row7_a_backup_store_takes_only_its_two_verdicts(mkrepo):
    """Row 7, the other direction: `not_erased` is not a verdict for a dump."""
    root = mkrepo(repo())
    dump = store("nightly_dump", "backup", cite("app/models.py", 4, "User"),
                 {"file": "app/models.py", "line": 4},
                 [field("email", "contact", "app/models.py", 5)],
                 erasure("not_erased"))
    found = check(record([USER_STORE, dump]), root)

    entry = found.rejected_claims[0]
    assert (entry["store"], found.accepted) == ("nightly_dump", False)
    assert entry["expected"] == ("verdict governed_by_retention or no_schedule_evidenced,"
                                 " the only two a backup store takes")


def test_row8_a_kind_disagreement_is_recorded_and_does_not_block(mkrepo):
    """Row 8: the detectors can be wrong about kind; the document still says so."""
    root = mkrepo(repo())
    wrong = json.loads(json.dumps(USER_STORE))
    wrong["kind"] = "cache"
    found = check(record([wrong]), root)

    assert found.accepted is True
    assert found.unverified[0]["claim"] == "kind=cache"
    assert "not cache" in found.unverified[0]["reason"]


def test_row9_a_store_the_verifier_never_saw_may_not_claim_erasure(mkrepo):
    """Row 9 (Decision 11): a safe claim with no corroboration is a safe claim."""
    root = mkrepo(repo())
    ghost = store("sessions", "cache", None, None,
                  [field("email", "contact", "app/models.py", 5)],
                  erasure("erased", [cite("app/views.py", 6, "delete")]))
    found = check(record([USER_STORE, ghost]), root)

    entry = found.rejected_claims[0]
    assert (entry["store"], found.accepted) == ("sessions", False)
    assert entry["expected"] == "verdict unverified, or cite the path"
    assert entry["path"] == []


def test_a_store_the_verifier_could_not_decide_is_reported_and_does_not_block(mkrepo):
    """4.4: `unverified` is informational, so a repository with one `RESTRICT` in it
    can still produce an accepted record (7.1)."""
    models = MODELS + """

class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total = models.IntegerField()


class Receipt(models.Model):
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    billing_name = models.CharField(max_length=200)
"""
    receipt = store("receipt", "relational", cite("app/models.py", 13, "Receipt"),
                    {"file": "app/models.py", "line": 14},
                    [field("billing_name", "identifier", "app/models.py", 15)],
                    erasure("not_erased"))
    found = check(record([USER_STORE, receipt]), mkrepo(repo(models)))

    assert found.accepted is True and found.rejected_claims == []
    entry = next(i for i in found.unverified if i["store"] == "receipt")
    assert entry["claim"] == "erasure.verdict=not_erased"
    assert entry["expected"].startswith("keep the verdict")


def test_an_opaque_call_names_getattr_as_the_mechanism(mkrepo):
    """4.4's `{mechanism}` is a closed set, and `getattr` is the contract's own worked
    example. R26 names two shapes, so the note tells them apart: without that, both of
    the reasons `downgrades.py` produces most often fell through to a sentence that
    named no mechanism at all."""
    root = mkrepo(repo(**{"storage.py": """
import boto3

s3 = boto3.client("s3")
BUCKET = "uploads"


def drop(user, meth):
    getattr(s3, meth)(Bucket=BUCKET, Key=str(user.id))
"""}))
    uploads = store("uploads", "object_storage", None, None,
                    [field("key", "identifier", "storage.py", 8)], erasure("not_erased"))
    found = check(record([USER_STORE, uploads]), root)

    entry = next(i for i in found.unverified if i["store"] == "uploads")
    assert found.accepted is True
    assert entry["reason"].endswith(
        "resolves through getattr; the path cannot be decided from the source")
    assert entry["expected"] == ("verdict unverified for uploads, or cite a path that "
                                 "does not pass through getattr")


def test_row10_a_store_the_verifier_never_saw_may_be_conservative(mkrepo):
    """Row 10: the model may see a store the detectors do not; that costs nothing."""
    root = mkrepo(repo())
    ghost = store("sessions", "cache", None, None,
                  [field("email", "contact", "app/models.py", 5)],
                  erasure("not_erased"))
    found = check(record([USER_STORE, ghost]), root)

    assert found.accepted is True and found.rejected_claims == []
    assert found.unverified[0]["store"] == "sessions"
    assert found.unverified[0]["expected"].startswith("keep the verdict")
    # The claim does not reach erasure, so row 9's sentence about a claim that does
    # would be false on an informational list the trace and the CLI both print.
    assert found.unverified[0]["reason"] == (
        "no store this scan detected corresponds to sessions; the verifier cannot "
        "corroborate or contradict this row")


def test_row11_evidence_on_no_path_is_rejected(mkrepo):
    """Row 11: a citation that points at the right file and the wrong reason."""
    root = mkrepo(repo(child("CASCADE")))
    wrong = post_store("erased", [cite("app/models.py", 4, "User")])
    found = check(record([USER_STORE, wrong]), root)

    entry = found.rejected_claims[0]
    assert (entry["store"], found.accepted) == ("post", False)
    assert entry["reason"].startswith("the cited evidence at app/models.py:4 is on no path")
    assert entry["path"], "the walk the verifier did find is carried on the rejection"
    # The row fires only where the verifier reached the claimed verdict, so 4.1's
    # "verdict erased, or cite the path" would be a tautology; the edit is the citation.
    assert entry["expected"] == "cite a line on the path above, or drop the claim"


def test_an_app_prefix_strip_never_takes_a_store_an_exact_name_wants(mkrepo):
    """7.4: "an exact name beats an app-prefix strip", across the whole record.

    Tried per record store, the strip let a plausible real name (`admin_users`) claim
    `user` before the record's own `user` row was looked at; the true claim was then
    rejected as uncorroborated and an attempt was spent on the verifier's own ordering.
    """
    root = mkrepo(repo())
    ghost = store("admin_users", "relational", None, None,
                  [field("email", "contact", "app/models.py", 5)], erasure("not_erased"))
    found = check(record([ghost, USER_STORE]), root)

    assert found.accepted is True and found.rejected_claims == []
    assert [item["store"] for item in found.unverified] == ["admin_users"]


def test_a_file_store_is_reconciled_by_its_declaration_line(mkrepo):
    """7.3: `<model>.<field>` never normalises to `avatars`; `declared_at` decides."""
    models = MODELS + """

class Avatar(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="avatars/")
"""
    uploads = store("uploads", "object_storage", cite("app/models.py", 10, "image"),
                    {"file": "app/models.py", "line": 10},
                    [field("image", "identifier", "app/models.py", 10)],
                    erasure("erased", [cite("app/views.py", 6, "delete")]))
    found = check(record([USER_STORE, uploads]), mkrepo(repo(models)))

    entry = found.rejected_claims[0]
    assert (entry["store"], found.accepted) == ("uploads", False)
    assert "is a file field; a row cascade does not delete the file" in entry["reason"]
    assert found.missing_stores == [], "the file store is not also reported as missing"


# ---------------------------------------------------------------------------
# 2.5: verdicts over `D union E_valid`
# ---------------------------------------------------------------------------
DECLARED_ROUTE = """
from flask import Flask

from app.models import User

app = Flask(__name__)


@app.route("/kill", methods=["DELETE"])
def remove_it(user_id):
    do_it(user_id)


def do_it(user_id):
    User.objects.filter(pk=user_id).delete()
"""
DEAD_HELPER = """
from app.models import User


def cleanup_user_files(user_id):
    User.objects.filter(pk=user_id).delete()
"""


def test_a_declared_registered_entry_point_is_a_start_node(mkrepo):
    """2.5: "the model is allowed to know a route the rules do not cover".

    `remove_it` is not in the 2.1 vocabulary, deletes through a helper so no variable
    binds the subject model at the handler, and its path segment names no subject, so
    discovery does not claim it -- but the route decorator is in plain sight, which is
    2.5's registration test. Walking only `D` rejected this with a sentence
    ("no entry point exists in this repository") the verifier's own scan contradicts.
    """
    root = mkrepo(repo(view=DECLARED_ROUTE))
    entry = {"name": "remove_it", "kind": "route", "file": "app/views.py", "line": 9,
             "admin_only": False, "note": None}
    item = json.loads(json.dumps(USER_STORE))
    item["erasure"] = erasure("erased", [cite("app/views.py", 14, "delete")])
    found = check(record([item], [entry]), root)

    assert found.accepted is True and found.rejected_claims == []


def test_a_declared_unregistered_entry_point_is_capped(mkrepo):
    """2.5 and 6.1's first cap, which is the S10 shape: the start node is used and
    every verdict derived from it is `unverified`, never `erased`."""
    root = mkrepo(repo(view="def nothing():\n    pass\n", **{"storage.py": DEAD_HELPER}))
    entry = {"name": "cleanup_user_files", "kind": "unknown", "file": "storage.py",
             "line": 4, "admin_only": False, "note": None}
    item = json.loads(json.dumps(USER_STORE))
    item["erasure"] = erasure("erased", [cite("storage.py", 5, "delete")])
    found = check(record([item], [entry]), root)

    reject = found.rejected_claims[0]
    assert (reject["store"], found.accepted) == ("user", False)
    assert reject["expected"] == "verdict unverified, or cite the path"
    assert "declared but not seen registered as externally invocable" in reject["reason"]


# ---------------------------------------------------------------------------
# 7.2 citation re-read
# ---------------------------------------------------------------------------
WRAPPED = """
from django.db import models


class User(models.Model):
    email = models.EmailField(
        max_length=255,
        unique=True,
    )
"""


def test_a_citation_is_read_on_the_logical_line(mkrepo):
    """7.2 rule 3: a declaration a formatter broke is cited by its first line."""
    root = mkrepo(repo(WRAPPED))
    item = json.loads(json.dumps(USER_STORE))
    item["fields"] = [field("email", "contact", "app/models.py", 5)]
    item["erasure"] = erasure("erased", [cite("app/views.py", 6, "delete")])
    assert check(record([item]), root).bad_citations == []

    inside = json.loads(json.dumps(item))
    inside["fields"] = [field("email", "contact", "app/models.py", 6)]
    assert check(record([inside]), root).bad_citations == [], "the span carries the line"


def test_a_citation_on_another_statement_is_a_bad_citation(mkrepo):
    """7.2: the check exists to catch a plausible line number produced without looking."""
    root = mkrepo(repo(WRAPPED))
    item = json.loads(json.dumps(USER_STORE))
    item["fields"] = [field("email", "contact", "app/models.py", 1)]
    found = check(record([item]), root)

    assert found.accepted is False
    assert found.bad_citations == [
        {"file": "app/models.py", "line": 1, "symbol": "email",
         "problem": "line 1 does not contain 'email'",
         "expected": "cite the line where email appears, or drop the claim"}]


FOUR_FIELDS = """
from django.db import models


class User(models.Model):
    email = models.EmailField()
    phone = models.CharField(max_length=40)
    address = models.TextField()
    surname = models.CharField(max_length=40)
"""


def test_a_compound_header_is_not_the_logical_line_of_its_body(mkrepo):
    """7.2 rule 3 is about a statement a formatter broke, not about a block.

    A `class`/`def` span covers the whole body, so citing the header passed for any
    token inside it: on a real repository a forty-field model would have passed
    wholesale, which is exactly the plausible-line-without-looking 7.2 exists to catch.
    """
    root = mkrepo(repo(FOUR_FIELDS))
    item = json.loads(json.dumps(USER_STORE))
    item["fields"] = [field(name, "contact", "app/models.py", 4)
                      for name in ("email", "phone", "address", "surname")]
    found = check(record([item]), root)

    assert found.accepted is False
    assert [(i["symbol"], i["problem"]) for i in found.bad_citations] == [
        ("address", "line 4 does not contain 'address'"),
        ("email", "line 4 does not contain 'email'"),
        ("phone", "line 4 does not contain 'phone'"),
        ("surname", "line 4 does not contain 'surname'")]


def test_a_class_line_still_carries_its_own_name(mkrepo):
    """The physical-line fallback: `declared_at` on `class User(...)` keeps passing."""
    root = mkrepo(repo(FOUR_FIELDS))
    item = json.loads(json.dumps(USER_STORE))
    item["fields"] = [field("email", "contact", "app/models.py", 5)]

    assert check(record([item]), root).bad_citations == []


def test_a_citation_that_names_no_symbol_is_a_bad_citation(mkrepo):
    """7.2 is silent on a `symbol` that normalises to nothing and `record.schema.json`
    sets no `minLength`; the conservative reading is to reject rather than pass rule 3
    vacuously, which would satisfy a blocking list with a citation carrying no claim."""
    root = mkrepo(repo())
    item = json.loads(json.dumps(USER_STORE))
    item["declared_at"] = {"file": "app/models.py", "line": 1, "symbol": "!!!"}
    found = check(record([item]), root)

    assert found.accepted is False
    assert found.bad_citations == [
        {"file": "app/models.py", "line": 1, "symbol": "!!!",
         "problem": "the citation names no symbol to check",
         "expected": "name the symbol that line carries, or drop the claim"}]


# ---------------------------------------------------------------------------
# 7.4 completeness guard
# ---------------------------------------------------------------------------
def test_the_guard_fires_for_an_omitted_store_with_a_strong_field(mkrepo):
    """7.4: a strong 3.9 match the record does not carry blocks acceptance."""
    root = mkrepo(repo(MODELS + """

class Profile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=40)
"""))
    found = check(record([USER_STORE]), root)

    assert found.accepted is False
    assert found.missing_stores == [
        {"store": "profile", "kind": "relational",
         "evidence": "app/models.py:8 writes phone",
         "expected": "add store profile (kind relational) with its personal-data fields"
                     " and an erasure verdict"}]


def test_the_guard_stays_silent_for_a_store_with_no_qualifying_field(mkrepo):
    """7.4: predicting `products` costs precision, and demanding it costs credibility."""
    root = mkrepo(repo(MODELS + """

class Product(models.Model):
    sku = models.CharField(max_length=40)
    price = models.IntegerField()
"""))
    found = check(record([USER_STORE]), root)

    assert found.missing_stores == [] and found.accepted is True


def test_an_omitted_entry_point_is_reported_and_does_not_block(mkrepo):
    """4.2a and 7.1: it costs no attempt and it says what the record walked past."""
    root = mkrepo(soft_delete_repo())
    item = json.loads(json.dumps(USER_STORE))
    item["erasure"] = erasure("erased_after_timer",
                              [cite("jobs.py", 12, "delete")], 30)
    found = check(record([item], [SOFT_ENTRY]), root)

    assert found.accepted is True
    assert found.missing_entry_points == [
        {"name": "purge_closed_accounts", "file": "jobs.py", "line": 10, "kind": "task",
         "expected": "declare purge_closed_accounts as an entry point, or say in its note"
                     " why it is not one"}]


# ---------------------------------------------------------------------------
# 7.1 and 7.5
# ---------------------------------------------------------------------------
def test_only_three_lists_block_acceptance(mkrepo):
    """7.1: `unverified`, `missing_entry_points` and divergences are informational."""
    root = mkrepo(repo(child("CASCADE")))
    ghost = store("sessions", "cache", None, None,
                  [field("email", "contact", "app/models.py", 5)], erasure("not_erased"))
    found = check(record([USER_STORE, post_store("not_erased"), ghost]), root)

    assert found.accepted is True
    assert found.unverified and found.conservative_divergences


FEEDBACK_SCHEMA: dict = {
    "type": "object", "additionalProperties": False,
    "required": ["accepted", "attempt", "attempts_left", "schema_errors",
                 "rejected_claims", "missing_stores", "missing_entry_points",
                 "bad_citations", "unverified", "conservative_divergences"],
    "properties": {
        "accepted": {"type": "boolean"},
        "attempt": {"type": "integer"}, "attempts_left": {"type": "integer"},
        "schema_errors": {"type": "array", "items": {"type": "string"}},
        "rejected_claims": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["store", "field", "claim", "reason", "path", "expected"],
            "properties": {
                "store": {"type": "string"},
                "field": {"type": ["string", "null"]},
                "claim": {"type": "string"}, "reason": {"type": "string"},
                "expected": {"type": "string"},
                "path": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["file", "line", "symbol"],
                    "properties": {"file": {"type": "string"},
                                   "line": {"type": "integer"},
                                   "symbol": {"type": "string"}}}}}}},
        "missing_stores": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["store", "kind", "evidence", "expected"],
            "properties": {"store": {"type": "string"}, "kind": {"type": "string"},
                           "evidence": {"type": "string"},
                           "expected": {"type": "string"}}}},
        "missing_entry_points": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "file", "line", "kind", "expected"],
            "properties": {"name": {"type": "string"}, "file": {"type": "string"},
                           "line": {"type": "integer"}, "kind": {"type": "string"},
                           "expected": {"type": "string"}}}},
        "bad_citations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["file", "line", "symbol", "problem", "expected"],
            "properties": {"file": {"type": "string"}, "line": {"type": "integer"},
                           "symbol": {"type": "string"}, "problem": {"type": "string"},
                           "expected": {"type": "string"}}}},
        "unverified": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["store", "claim", "reason", "expected"],
            "properties": {"store": {"type": "string"}, "claim": {"type": "string"},
                           "reason": {"type": "string"},
                           "expected": {"type": "string"}}}},
        "conservative_divergences": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["store", "claim", "verifier", "note"],
            "properties": {"store": {"type": "string"}, "claim": {"type": "string"},
                           "verifier": {"type": "string"}, "note": {"type": "string"}}}},
    },
}


def _payload(found) -> dict:
    return {name: getattr(found, name) for name in FEEDBACK_SCHEMA["required"]}


def test_the_feedback_object_carries_the_contract_field_names(mkrepo):
    """00-contract.md, Feedback object: exactly those keys, and `expected` on five."""
    root = mkrepo(repo(child("SET_NULL")))
    ghost = store("sessions", "cache", None, None,
                  [field("email", "contact", "app/models.py", 5)], erasure("not_erased"))
    bad = json.loads(json.dumps(USER_STORE))
    bad["fields"] = [field("email", "contact", "app/models.py", 1)]
    found = check(record([bad, post_store("erased"), ghost]), root)

    Draft202012Validator(FEEDBACK_SCHEMA).validate(_payload(found))
    assert found.rejected_claims and found.bad_citations and found.unverified


def test_the_same_record_and_repository_produce_the_same_bytes(mkrepo):
    """7.5: sets are never iterated and no list leaves in dict order."""
    root = mkrepo(repo(child("SET_NULL")))
    ghost = store("sessions", "cache", None, None,
                  [field("email", "contact", "app/models.py", 5)], erasure("not_erased"))
    submitted = record([post_store("erased"), USER_STORE, ghost])
    first = json.dumps(_payload(check(submitted, root)), sort_keys=False)
    second = json.dumps(_payload(check(submitted, root)), sort_keys=False)

    assert first == second


def test_every_list_leaves_in_the_order_7_5_names(mkrepo):
    """7.5: `rejected_claims` by `(store, field, claim)`, whatever the record's order."""
    root = mkrepo(repo(child("SET_NULL")))
    zebra = store("zebra", "cache", None, None,
                  [field("email", "contact", "app/models.py", 5)],
                  erasure("erased", [cite("app/views.py", 6, "delete")]))
    alpha = store("alpha", "cache", None, None,
                  [field("email", "contact", "app/models.py", 5)],
                  erasure("erased", [cite("app/views.py", 6, "delete")]))
    found = check(record([zebra, USER_STORE, post_store("erased"), alpha]), root)

    assert [item["store"] for item in found.rejected_claims] == ["alpha", "post", "zebra"]


def test_the_primitive_is_named_in_the_kind_s_own_words():
    """4.1: the six phrases the contract's example uses, and no invented seventh."""
    assert strings.primitive_words("object_storage") == "any object-storage deletion primitive"
    assert strings.primitive_words("queue") == "any queue purge"
    assert strings.primitive_words("log") == strings.DEFAULT_PRIMITIVE
