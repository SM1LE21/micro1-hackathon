#!/usr/bin/env python3
"""Generate the synthetic fixtures and their manifests (docs/spec/fixture-generator.md).

    uv run python evals/fixtures/gen.py --all      write every case
    uv run python evals/fixtures/gen.py --case S10 write one case
    uv run python evals/fixtures/gen.py --check    render into memory, diff against disk

One YAML spec produces both the repository the agent reads and the manifest the scorer
grades against, in one pass, so the ground truth cannot drift from the fixture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helper modules

import checks  # noqa: E402
import manifest as manifest_module  # noqa: E402
import render_django  # noqa: E402
import render_sqlalchemy  # noqa: E402
from emit import SpecError  # noqa: E402
from spec_model import load_spec  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "evals" / "fixtures"
SPECS = FIXTURES / "specs"
SYNTHETIC = FIXTURES / "synthetic"
MANIFESTS = FIXTURES / "manifests"
INDEX = SYNTHETIC / ".gen-index.json"
SPLIT = ROOT / "evals" / "split.yaml"

RENDERERS = {"sqlalchemy": render_sqlalchemy.render, "django": render_django.render}


@dataclass(frozen=True)
class Case:
    """One rendered case, still in memory."""

    name: str
    files: dict[str, str]
    manifest_text: str
    index_entry: dict


def all_cases() -> list[str]:
    return sorted(path.stem for path in SPECS.glob("*.yaml"))


def generate(case: str) -> Case:
    spec = load_spec(SPECS / f"{case}.yaml")
    rendered = RENDERERS[spec["flavour"]](spec)
    checks.run(spec, rendered, checks.load_split(SPLIT))
    manifest = manifest_module.build(spec, rendered)
    entry = {
        "case": case,
        "spec_sha256": spec["spec_sha256"],
        "gen_version": manifest_module.GEN_VERSION,
        "files": {
            path: hashlib.sha256(text.encode("utf-8")).hexdigest()
            for path, text in sorted(rendered.files.items())
        },
    }
    return Case(case, dict(sorted(rendered.files.items())), manifest_module.dump(manifest), entry)


def index_text(entries: list[dict]) -> str:
    return json.dumps(sorted(entries, key=lambda e: e["case"]), indent=2, sort_keys=False) + "\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_case(case: Case) -> None:
    target = SYNTHETIC / case.name
    if target.exists():
        shutil.rmtree(target)
    for path, text in case.files.items():
        _write(target / path, text)
    _write(MANIFESTS / f"{case.name}.yaml", case.manifest_text)


def on_disk(case: str) -> dict[str, str]:
    target = SYNTHETIC / case
    if not target.exists():
        return {}
    files = {}
    for path in sorted(target.rglob("*")):
        if path.is_file():
            files[str(path.relative_to(target))] = path.read_text(encoding="utf-8")
    return files


def differences(cases: list[Case]) -> list[str]:
    out = []
    for case in cases:
        disk = on_disk(case.name)
        for path in sorted(set(disk) | set(case.files)):
            if path not in disk:
                out.append(f"missing on disk: {case.name}/{path}")
            elif path not in case.files:
                out.append(f"not generated: {case.name}/{path}")
            elif disk[path] != case.files[path]:
                out.append(f"differs: {case.name}/{path}")
        path = MANIFESTS / f"{case.name}.yaml"
        if not path.exists():
            out.append(f"missing on disk: {path.relative_to(ROOT)}")
        elif path.read_text(encoding="utf-8") != case.manifest_text:
            out.append(f"differs: {path.relative_to(ROOT)}")
    known = {case.name for case in cases}
    for path in sorted(SYNTHETIC.glob("*")):
        if path.is_dir() and path.name not in known:
            out.append(f"not generated: {path.relative_to(ROOT)}")
    expected = index_text([case.index_entry for case in cases])
    if not INDEX.exists():
        out.append(f"missing on disk: {INDEX.relative_to(ROOT)}")
    elif INDEX.read_text(encoding="utf-8") != expected:
        out.append(f"differs: {INDEX.relative_to(ROOT)}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--case", help="one case id, e.g. S10")
    group.add_argument("--all", action="store_true", help="write every case")
    group.add_argument("--check", action="store_true", help="diff the rendered cases against disk")
    args = parser.parse_args(argv)

    names = [args.case] if args.case else all_cases()
    try:
        cases = [generate(name) for name in names]
    except SpecError as exc:
        print(f"SpecError: {exc}", file=sys.stderr)
        return 2

    if args.check:
        diffs = differences(cases)
        for line in diffs:
            print(line)
        print("fixtures clean" if not diffs else f"{len(diffs)} difference(s)")
        return 1 if diffs else 0

    entries = {case.name: case.index_entry for case in cases}
    if args.case and INDEX.exists():
        for entry in json.loads(INDEX.read_text(encoding="utf-8")):
            entries.setdefault(entry["case"], entry)
    for case in cases:
        write_case(case)
        print(f"{case.name}: {len(case.files)} files")
    _write(INDEX, index_text(list(entries.values())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
