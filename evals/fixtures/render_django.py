"""Django flavour (fixture-generator.md section 3.2).

Django needs a project package, so `package` is the project directory and `apps[0]` holds
the models with personal data. Every model names its table explicitly: a manifest store
name that appears in no line of the repository is an alias (section 7 rule 1).
"""

from __future__ import annotations

from emit import Doc, SpecError
from render_common import Rendered, helpers, readme, requirements
from spec_model import children_of, model_named, snake, subject_model, var_of

FIELD_CALLS = {
    "str": "models.CharField(max_length=255)",
    "int": "models.IntegerField()",
    "bool": "models.BooleanField(default=True)",
    "datetime": "models.DateTimeField(auto_now_add=True)",
    "json": "models.JSONField(default=dict)",
    "text": "models.TextField()",
    "decimal": "models.DecimalField(max_digits=10, decimal_places=2)",
}


def _engine_name(spec: dict) -> tuple[str, str]:
    engine = spec["engine"]
    if engine.startswith("sqlite"):
        return "django.db.backends.sqlite3", engine.rsplit("/", 1)[-1]
    raise SpecError(f"{spec['case']}: no settings template for engine {engine!r}")


def _column(spec: dict, model: dict, field: dict) -> str:
    if field["pk"]:
        call = "models.AutoField(primary_key=True)"
    elif field["type"] == "image":
        call = f'models.ImageField(upload_to="{snake(model["name"])}/{field["name"]}s/")'
    elif field["name"] == "email":
        call = "models.EmailField(max_length=255)"
    else:
        call = FIELD_CALLS[field["type"]]
    line = f"    {field['name']} = {call}"
    return line + (f"  # {field['comment']}" if field["comment"] else "")


def _models_module(spec: dict, r: Rendered, app: str, models: list[dict], subject: dict) -> None:
    doc = Doc()
    doc.add(f'"""Data models for the {app} app.')
    doc.blank()
    doc.add("One class per table. Every model names its table explicitly.")
    doc.add('"""')
    doc.blank()
    doc.add("from django.db import models")
    for model in models:
        doc.blank(2)
        declared = doc.add(f"class {model['name']}(models.Model):")
        for field in model["fields"]:
            line = doc.add(_column(spec, model, field))
            target = field["store"] or model["store"]
            if field["category"]:
                r.cite_field(target, field["name"], f"{app}/models.py", line)
            if field["store"]:
                store = next(s for s in spec["stores"] if s["name"] == field["store"])
                for own in store["fields"]:
                    r.cite_field(store["name"], own["name"], f"{app}/models.py", line)
                r.identity[store["name"]] = (f"{app}/models.py", line)
                r.declared_at[store["name"]] = (f"{app}/models.py", line)
                r.subject_link[store["name"]] = (f"{app}/models.py", line)
        if model["parent"]:
            parent = model_named(spec, model["parent"])
            extra = ", null=True" if model["on_delete"] == "SET_NULL" else ""
            fk = doc.add(
                f"    {var_of(parent)} = models.ForeignKey"
                f"({parent['name']}, on_delete=models.{model['on_delete']}{extra})"
            )
            r.subject_link[model["store"]] = (f"{app}/models.py", fk)
        elif not model["negative"]:
            r.subject_link[model["store"]] = (f"{app}/models.py", declared)
        doc.blank()
        doc.add("    class Meta:")
        identity = doc.add(f'        db_table = "{model["table"]}"')
        r.identity[model["store"]] = (f"{app}/models.py", identity)
    r.put(f"{app}/models.py", doc)


def _views(spec: dict, r: Rendered, app: str, subject: dict) -> None:
    doc = Doc()
    doc.add(f'"""Views for the {app} app."""')
    doc.blank()
    doc.add("from django.http import JsonResponse", "from django.shortcuts import get_object_or_404")
    doc.blank()
    used = [subject["name"]] + [
        read.split(".", 1)[0] for route in spec["routes"] for read in route.get("reads", [])
    ]
    names = [m["name"] for m in spec["models"] if not m["negative"] and m["name"] in set(used)]
    doc.add("from .models import " + ", ".join(names))
    for entry in spec["entry_points"]:
        doc.blank(2)
        line = doc.add(f"def {entry['name']}(request, pk):")
        r.entry_lines[entry["name"]] = (entry["module"], line)
        if entry["docstring"]:
            doc.add(f'    """{entry["docstring"]}"""')
        var = var_of(subject)
        if entry["deletes_via"] == "model_delete":
            doc.add(f"    {var} = get_object_or_404({subject['name']}, pk=pk)")
            doc.add(f"    {var}.delete()")
        else:
            doc.add(f"    {subject['name']}.objects.filter(pk=pk).delete()")
        doc.add('    return JsonResponse({"deleted": True})')
    for route in spec["routes"]:
        doc.blank(2)
        doc.add(f"def {route['name']}(request, pk):")
        pairs = []
        for name in dict.fromkeys(read.split(".", 1)[0] for read in route.get("reads", [])):
            model = model_named(spec, name)
            if model["name"] == subject["name"]:
                doc.add(f"    {var_of(model)} = get_object_or_404({model['name']}, pk=pk)")
            else:
                parent = model_named(spec, model["parent"])
                doc.add(
                    f"    {var_of(model)} = {model['name']}.objects"
                    f".filter({var_of(parent)}_id=pk).first()"
                )
        for read in route.get("reads", []):
            model, attr = read.split(".", 1)
            pairs.append(f'"{attr}": {snake(model)}.{attr}')
        doc.add("    return JsonResponse({" + ", ".join(pairs) + "})")
    r.put(f"{app}/views.py", doc)


def _signals(spec: dict, r: Rendered, app: str) -> None:
    doc = Doc()
    doc.add(f'"""Signal receivers for the {app} app."""')
    doc.blank()
    doc.add("from django.db.models.signals import post_delete", "from django.dispatch import receiver")
    doc.blank()
    senders = [rec["sender"] for rec in spec["receivers"] if rec["sender"]]
    doc.add("from .models import " + ", ".join(dict.fromkeys(senders)))
    file_field = next((s for s in spec["stores"] if s["client"] == "file"), None)
    for rec in spec["receivers"]:
        if rec["body"] != "delete_file" or file_field is None:
            raise SpecError(f"{spec['case']}: receiver {rec['name']} has no template behind its body")
        doc.blank(2)
        doc.add(f"@receiver({rec['signal']}, sender={rec['sender']})")
        doc.add(f"def {rec['name']}(sender, instance, **kwargs):")
        doc.add(f"    instance.{file_field['fields'][0]['name']}.delete(save=False)")
    r.put(f"{app}/signals.py", doc)


def _admin(spec: dict, r: Rendered, app: str) -> None:
    doc = Doc()
    doc.add(f'"""Admin registrations for the {app} app."""')
    doc.blank()
    doc.add("from django.contrib import admin")
    doc.blank()
    doc.add("from .models import " + ", ".join(spec["admin"]))
    doc.blank()
    first = None
    for name in spec["admin"]:
        line = doc.add(f"admin.site.register({name})")
        first = first or line
    r.admin_line = (f"{app}/admin.py", first)
    r.put(f"{app}/admin.py", doc)


def _project(spec: dict, r: Rendered, app: str) -> None:
    project = spec["package"]
    doc = Doc()
    doc.add('"""Django command-line utility."""')
    doc.blank()
    doc.add("import os", "import sys")
    doc.blank()
    doc.add("from django.core.management import execute_from_command_line")
    doc.blank()
    doc.add(
        'if __name__ == "__main__":',
        f'    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{project}.settings")',
        "    execute_from_command_line(sys.argv)",
    )
    r.put("manage.py", doc)

    r.files[f"{project}/__init__.py"] = ""

    doc = Doc()
    doc.add(f'"""URL routing for {project}."""')
    doc.blank()
    if spec["admin"]:
        doc.add("from django.contrib import admin")
    doc.add("from django.urls import path")
    doc.blank()
    doc.add(f"from {app} import views")
    doc.blank()
    doc.add("urlpatterns = [")
    if spec["admin"]:
        doc.add('    path("admin/", admin.site.urls),')
    for entry in spec["entry_points"]:
        doc.add(f'    path("{app}/<int:pk>/delete/", views.{entry["name"]}, name="{entry["name"]}"),')
    for route in spec["routes"]:
        doc.add(f'    path("{app}/<int:pk>/{route["name"]}/", views.{route["name"]}, name="{route["name"]}"),')
    doc.add("]")
    r.put(f"{project}/urls.py", doc)

    engine, name = _engine_name(spec)
    doc = Doc()
    doc.add(f'"""Django settings for {project}."""')
    doc.blank()
    doc.add("import os", "from pathlib import Path")
    doc.blank()
    doc.add("BASE_DIR = Path(__file__).resolve().parent.parent")
    doc.add('SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")')
    doc.add("DEBUG = False")
    doc.add("ALLOWED_HOSTS = []")
    doc.add("SECURE_SSL_REDIRECT = True")
    doc.blank()
    doc.add("INSTALLED_APPS = [")
    doc.add('    "django.contrib.admin",', '    "django.contrib.auth",', '    "django.contrib.contenttypes",')
    for label in spec["apps"]:
        doc.add(f'    "{label}",')
    doc.add("]")
    doc.blank()
    doc.add("DATABASES = {")
    doc.add('    "default": {')
    doc.add(f'        "ENGINE": "{engine}",')
    doc.add(f'        "NAME": BASE_DIR / "{name}",')
    doc.add("    }")
    doc.add("}")
    doc.blank()
    doc.add(f'ROOT_URLCONF = "{project}.urls"')
    doc.add('DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"')
    r.put(f"{project}/settings.py", doc)


def render(spec: dict) -> Rendered:
    r = Rendered()
    app = spec["apps"][0]
    subject = subject_model(spec)
    r.files["README.md"] = readme(spec)
    r.files["requirements.txt"] = requirements(spec)
    _project(spec, r, app)
    r.files[f"{app}/__init__.py"] = ""
    doc = Doc()
    doc.add(f'"""Application configuration for the {app} app."""')
    doc.blank()
    doc.add("from django.apps import AppConfig")
    doc.blank(2)
    doc.add(f"class {app.title()}Config(AppConfig):")
    doc.add('    default_auto_field = "django.db.models.BigAutoField"')
    doc.add(f'    name = "{app}"')
    if spec["receivers"]:
        doc.blank()
        doc.add("    def ready(self):")
        doc.add("        from . import signals  # noqa: F401")
    r.put(f"{app}/apps.py", doc)
    _models_module(spec, r, app, [m for m in spec["models"] if not m["negative"]], subject)
    _views(spec, r, app, subject)
    if spec["receivers"]:
        _signals(spec, r, app)
    if spec["admin"]:
        _admin(spec, r, app)
    negatives = [m for m in spec["models"] if m["negative"]]
    if negatives:
        second = spec["apps"][1]
        r.files[f"{second}/__init__.py"] = ""
        _models_module(spec, r, second, negatives, subject)
    for extra in spec["extra_files"]:
        if extra.get("kind") != "helpers":
            raise SpecError(f"{spec['case']}: extra_files kind {extra.get('kind')!r} has no template")
        r.files[extra["path"]] = helpers(spec)
    if any(children_of(spec, m["name"]) for m in spec["models"] if m["negative"]):
        raise SpecError(f"{spec['case']}: a negative model may not be a parent")
    if spec["jobs"]:
        # jobs[] drives erased_after_timer and both backup verdicts; this flavour has no job
        # template, so a declared job would be dropped and the manifest left ahead of the repo.
        raise SpecError(f"{spec['case']}: jobs[] has no template in the django flavour (section 9)")
    return r
