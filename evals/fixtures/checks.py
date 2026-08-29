"""The consistency assertions (fixture-generator.md section 8).

All of them run after rendering into memory and before anything is written, so a violation
leaves no fixture on disk. Each raises a SpecError naming the case, the store and what was
expected.
"""

from __future__ import annotations

import ast

import yaml

from emit import SpecError
from naming import IRREGULAR_PLURALS, line_tokens, norm, stems
from render_common import vendor_key
from spec_model import VENDOR_MODULE, snake


def expected_identity(spec: dict, store: dict) -> str:
    """The identity `03-verifier.md` sections 3.1-3.8 derive for this store."""
    kind, client = store["kind"], store["client"]
    if client == "file" and kind == "object_storage":
        for model in spec["models"]:
            for field in model["fields"]:
                if field["store"] == store["name"]:
                    return f"{snake(model['name'])}.{field['name']}".lower()
        raise SpecError(f"{spec['case']}: no column declares the file store {store['name']}")
    if kind == "third_party":
        return vendor_key(store)
    if kind == "cache":
        return (store["key_template"] or "").split("{")[0].rstrip(":/-_")
    return store["name"]


def _identity_tokens(spec: dict, name: str) -> str:
    """What the identity line must carry: an SDK module for a recipient, the name otherwise."""
    for store in spec["stores"]:
        if store["name"] == name and store["kind"] == "third_party":
            return VENDOR_MODULE[store["client"]]
    return name


def _line_of(files: dict[str, str], path: str, line: int) -> str:
    lines = files[path].split("\n")
    if line < 1 or line > len(lines):
        raise SpecError(f"{path}:{line} is outside the rendered file")
    return lines[line - 1]


def _module_ranges(files: dict[str, str], module: str, writer: str | None) -> list[tuple[int, int]]:
    tree = ast.parse(files[module])
    ranges = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            ranges.append((node.lineno, node.end_lineno or node.lineno))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == writer:
            ranges.append((node.lineno, node.end_lineno or node.lineno))
    return ranges


def run(spec: dict, r, split_map: dict) -> None:
    case = spec["case"]
    prefixes = tuple(spec["apps"])
    store_names = [m["store"] for m in spec["models"] if not m["negative"]] + [
        s["name"] for s in spec["stores"]
    ]

    # 2. literal in a rendered file, and equal to the identity the verifier derives.
    for store in spec["stores"]:
        identity = expected_identity(spec, store)
        if store["name"] != identity:
            raise SpecError(f"{case} store {store['name']}: identity the code carries is {identity!r}")
    for model in spec["models"]:
        if not model["negative"] and model["store"] != model["table"]:
            raise SpecError(f"{case} store {model['store']}: the table the code carries is {model['table']!r}")
    file_stores = {s["name"] for s in spec["stores"] if s["client"] == "file" and s["kind"] == "object_storage"}
    for name in store_names:
        # A Django file store is the one identity that is not a single literal: section 7
        # rule 1 asks instead that both halves sit on the rendered column line.
        if name not in file_stores and not any(name.lower() in text.lower() for text in r.files.values()):
            raise SpecError(f"{case} store {name}: the name appears in no rendered file (section 7 rule 1)")
        path, line = r.identity[name]
        tokens = line_tokens(_line_of(r.files, path, line))
        halves = [norm(part) for part in _identity_tokens(spec, name).split(".")]
        if not set(halves) <= tokens:
            raise SpecError(f"{case} store {name}: {path}:{line} does not carry the store identity")

    # 3. norm injective over store names, field names within a store, identity strings.
    known = stems(store_names, prefixes)
    seen: dict[str, str] = {}
    for name in store_names:
        key = norm(name, prefixes, known)
        if key in seen:
            raise SpecError(f"{case}: stores {seen[key]} and {name} both normalise to {key!r}")
        seen[key] = name
    identities = [m["table"] for m in spec["models"] if not m["negative"]]
    identities += [expected_identity(spec, s) for s in spec["stores"]]
    seen = {}
    for name in identities:
        key = norm(name, prefixes, known)
        if key in seen:
            raise SpecError(f"{case}: identities {seen[key]} and {name} both normalise to {key!r}")
        seen[key] = name
    for store, fields in _fields_by_store(spec).items():
        seen = {}
        for name in fields:
            key = norm(name)
            if key in seen:
                raise SpecError(f"{case} store {store}: fields {seen[key]} and {name} collide as {key!r}")
            seen[key] = name

    # 4. no irregular plural anywhere, and norm is idempotent on every name.
    for name in store_names + [f for fields in _fields_by_store(spec).values() for f in fields]:
        if name.lower() in IRREGULAR_PLURALS:
            raise SpecError(f"{case}: {name!r} is an irregular plural (section 7 rule 3)")
        if norm(norm(name)) != norm(name):
            raise SpecError(f"{case}: norm is not idempotent on {name!r}")

    # 5. every declared field cites a line that names it.
    for (store, field), (path, line) in sorted(r.field_cite.items()):
        if norm(field) not in line_tokens(_line_of(r.files, path, line)):
            raise SpecError(f"{case} {store}.{field}: {path}:{line} does not carry the field name")

    # 6. a third-party store's fields are on the lines its transmitting call writes.
    for store in spec["stores"]:
        if store["kind"] != "third_party":
            continue
        ranges = _module_ranges(r.files, store["module"], store["writes_from"])
        for field in store["fields"]:
            path, line = r.field_cite[(store["name"], field["name"])]
            if path != store["module"] or not any(lo <= line <= hi for lo, hi in ranges):
                raise SpecError(
                    f"{case} {store['name']}.{field['name']}: {path}:{line} is not on the "
                    "transmitting call or its field list"
                )

    # 7. the dead-writer trap is never reached by leaving a key at its default.
    for store in spec["stores"]:
        if store["write_called_by"] is None and store["writes_from"] and store["fields"]:
            raise SpecError(
                f"{case} store {store['name']}: write_called_by null on a store that declares fields"
            )

    # 9. the spec's split is the case's membership in evals/split.yaml.
    if split_map.get(case) != spec["split"]:
        raise SpecError(f"{case}: split {spec['split']!r} but split.yaml says {split_map.get(case)!r}")


def _fields_by_store(spec: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for model in spec["models"]:
        if model["negative"]:
            continue
        out.setdefault(model["store"], [])
        for field in model["fields"]:
            if field["category"] and not field["store"]:
                out[model["store"]].append(field["name"])
    for store in spec["stores"]:
        out.setdefault(store["name"], [])
        out[store["name"]].extend(f["name"] for f in store["fields"])
    return out


def load_split(path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {case: split for split in ("dev", "test", "reserve") for case in data.get(split, [])}
