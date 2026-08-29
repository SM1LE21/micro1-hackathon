"""Route modules for the SQLAlchemy flavour (fixture-generator.md section 3.1, section 5).

`api/account.py` always exists, with or without a deletion route: S08 needs an account
module that has no delete in it.
"""

from __future__ import annotations

from emit import Doc, SpecError
from render_common import Rendered, placeholders, value_models
from render_stores import writer_params
from spec_model import model_named, snake, subject_model, var_of

MODULE_DOC = (
    "One function per route. The application object in app.py imports this module",
    "and registers each of them.",
)


def _symbol_module(spec: dict, symbol: str) -> str:
    for store in spec["stores"]:
        if symbol in {store["writes_from"], store["delete_call"]} and symbol:
            return store["module"]
    if symbol == "anonymize_user":
        return "privacy.py"
    raise SpecError(f"{spec['case']}: no module defines {symbol!r}")


def _import_path(module: str) -> str:
    return module[:-3].replace("/", ".")


def _call_args(spec: dict, store: dict, available: set[str]) -> list[str]:
    args = []
    for param in writer_params(spec, store):
        if param.endswith("_id") and param[: -len("_id")] in available:
            args.append(f"{param[: -len('_id')]}.id")
        else:
            args.append(param)
    return args


def _extra_params(spec: dict, store: dict, available: set[str]) -> list[str]:
    keep = []
    for param in writer_params(spec, store):
        if param in available or (param.endswith("_id") and param[: -len("_id")] in available):
            continue
        keep.append(param)
    return keep


def _writers_called_by(spec: dict, name: str) -> list[dict]:
    return [s for s in spec["stores"] if s["write_called_by"] == name and s["writes_from"]]


def _models_for_route(spec: dict, route: dict) -> list[dict]:
    wanted, subject = [], subject_model(spec)
    for read in route.get("reads", []):
        wanted.append(read.split(".", 1)[0])
    for store in _writers_called_by(spec, route["name"]):
        wanted.extend(m["name"] for m in value_models(spec, [f["name"] for f in store["fields"]]))
        wanted.extend(
            "".join(part.title() for part in p[: -len("_id")].split("_"))
            for p in placeholders(store["key_template"])
            if p.endswith("_id")
        )
    ordered = [m for m in spec["models"] if not m["negative"] and m["name"] in set(wanted)]
    return ordered or [subject]


def _bind(spec: dict, model: dict, subject: dict) -> str:
    if model["name"] == subject["name"]:
        return f"    {var_of(model)} = session.get({model['name']}, {var_of(subject)}_id)"
    parent = model_named(spec, model["parent"])
    fk = f"{var_of(parent)}_id"
    return (
        f"    {var_of(model)} = session.query({model['name']})"
        f".filter({model['name']}.{fk} == {var_of(subject)}_id).first()"
    )


def _returns(reads: list[str]) -> list[str]:
    if not reads:
        return ["    return {}"]
    pairs = []
    for read in reads:
        model, attr = read.split(".", 1)
        pairs.append(f'"{attr}": {snake(model)}.{attr}')
    one = "    return {" + ", ".join(pairs) + "}"
    if len(one) <= 100:
        return [one]
    return ["    return {", *[f"        {pair}," for pair in pairs], "    }"]


def _route(spec: dict, r: Rendered, doc: Doc, route: dict) -> None:
    subject = subject_model(spec)
    models = _models_for_route(spec, route)
    available = {var_of(m) for m in models}
    stores = _writers_called_by(spec, route["name"])
    params = ["session", f"{var_of(subject)}_id"]
    for store in stores:
        for extra in _extra_params(spec, store, available):
            if extra not in params:
                params.append(extra)
    doc.add(f"def {route['name']}({', '.join(params)}):")
    for model in models:
        doc.add(_bind(spec, model, subject))
    for store in stores:
        doc.add(f"    {store['writes_from']}({', '.join(_call_args(spec, store, available))})")
    doc.add(*_returns(route.get("reads", [])))


def _entry(spec: dict, r: Rendered, doc: Doc, entry: dict) -> None:
    subject = subject_model(spec)
    var = var_of(subject)
    line = doc.add(f"def {entry['name']}(session, {var}_id):")
    r.entry_lines[entry["name"]] = (entry["module"], line)
    if entry["docstring"]:
        doc.add(f'    """{entry["docstring"]}"""')
    doc.add(f"    {var} = session.get({subject['name']}, {var}_id)")
    for symbol in entry["calls"]:
        store = next((s for s in spec["stores"] if s["delete_call"] == symbol), None)
        if store is not None:
            keys = [f"{var}.{p[len(var) + 1:]}" if p.startswith(f"{var}_") else f"{var}.{p}"
                    for p in placeholders(store["key_template"])]
            # a helper keyed on a subject attribute receives that attribute off the loaded row,
            # never a bare name the route does not define (audit B-1: D02 raised NameError)
            doc.add(f"    {symbol}({', '.join(keys)})")
        else:
            doc.add(f"    {symbol}({var})")
    if entry["action"] == "hard_delete":
        doc.add(f"    session.delete({var})")
    elif entry["action"] == "soft_delete":
        marker = next((f for f in subject["fields"] if f["name"] == "deleted_at"), None)
        if marker is None:
            raise SpecError(f"{spec['case']}: soft delete needs a deleted_at column on {subject['name']}")
        doc.add(f"    {var}.deleted_at = datetime.now(timezone.utc)")
        if any(f["name"] == "is_active" for f in subject["fields"]):
            doc.add(f"    {var}.is_active = False")
    doc.add("    session.commit()")


def render_module(spec: dict, r: Rendered, module: str) -> None:
    entries = [e for e in spec["entry_points"] if e["module"] == module]
    routes = [rt for rt in spec["routes"] if rt["module"] == module]
    doc = Doc()
    stem = module.split("/")[-1][: -len(".py")]
    doc.add(f'"""HTTP routes for the {stem} area.')
    doc.blank()
    doc.add(*MODULE_DOC)
    doc.add('"""')
    doc.blank()
    if any(e["action"] == "soft_delete" for e in entries):
        doc.add("from datetime import datetime, timezone")
        doc.blank()
    used: set[str] = set()
    for entry in entries:
        used.add(subject_model(spec)["name"])
    for route in routes:
        used.update(m["name"] for m in _models_for_route(spec, route))
    models = [m["name"] for m in spec["models"] if not m["negative"] and m["name"] in used]
    imports = {}
    if models:
        imports["models"] = models
    for entry in entries:
        for symbol in entry["calls"]:
            imports.setdefault(_import_path(_symbol_module(spec, symbol)), []).append(symbol)
    for route in routes:
        for store in _writers_called_by(spec, route["name"]):
            imports.setdefault(_import_path(store["module"]), []).append(store["writes_from"])
    for path in sorted(imports):
        doc.add(f"from {path} import " + ", ".join(imports[path]))
    for function in entries + routes:
        doc.blank(2)
        if function in entries:
            _entry(spec, r, doc, function)
        else:
            _route(spec, r, doc, function)
    r.put(module, doc)
