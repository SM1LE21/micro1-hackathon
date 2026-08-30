"""What a sweep is about to run: the case selection, the two pre-flight gates and the cell plan.

Split out of `run.py` so neither file passes AGENTS.md's ~300 lines. Nothing here launches a child
or writes a file: every function is a pure reading of `evals/split.yaml`, the manifests and the
specs, and the only way out of a refusal is `Abort` carrying section 5.5's exit code. `run.py` owns
every path a test may redirect - `SPLIT_FILE`, `SPECS`, `SYNTHETIC`, `REAL`, `MANIFESTS`, `TRACES`,
`RESULTS`, `ADR_DIR` - and passes each one in, so a sandboxed sweep stays sandboxed. No path
constant lives here: a module-level default would be read here and never rebound there, which is a
redirection seam that silently does nothing. What is left is data (`TIMEOUTS`, `ARMS`, `REAL_DIRS`).
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

TIMEOUTS = {"synthetic": 900, "real": 1800}  # section 5.3
TOOL_BUDGETS = {"synthetic": 60, "real": 120}  # contract, Budgets; pinned into the cell's env
ARMS = ("baseline", "advanced")
BRAINS = ("api", "claude", "codex")  # ADR 0008 item 1; `api` is the loop as built
DEFAULT_BRAIN = "api"
# The request settings a sweep pins per cell (ADR 0008 item 5). They are the harness's own
# numbers, spelled here rather than read from `art30.config`, because a cell that inherited
# the runtime's defaults would change silently when a default changed and the sweep would
# have no record of it. `cells.cell_env` writes each one into the child's environment.
# The three local-brain settings are pinned to the empty string, which `art30/settings.py`
# reads as "no value" (`_env_layer` skips a falsy one), so a cell runs at the CLI's own
# default whatever the operator exported. Unpinned, an exported `ART30_CLAUDE_MODEL` moved
# every cell of a sweep and `ART30_CODEX_PRICES` moved every dollar in the cost column,
# and neither shows up in `provenance.config.overridden`, which is computed from
# `art30/config.py`'s five request variables. What the CLI then chose is not a pin but an
# observation, and the report reads it back off each record's `provenance.brain_model`.
PINS = {"ART30_MODEL": "claude-opus-5", "ART30_EFFORT": "high", "ART30_MAX_TOKENS": "32000",
        "ART30_SUBMIT_BUDGET": "5", "ART30_MAX_TURNS": "60",
        "ART30_CLAUDE_MODEL": "", "ART30_CODEX_MODEL": "", "ART30_CODEX_PRICES": ""}
# CASES.md, Real cases: the vendored directory each real case reads. A hand-written real manifest
# may name its own with a `repo` key; none exists yet, so the mapping lives here.
REAL_DIRS = {"R01": "full-stack-fastapi-template", "R02": "flaskbb", "R03": "pinry",
             "R04": "microblog", "R05": "Django-Styleguide-Example"}


class Abort(Exception):
    """A harness refusal carrying one of section 5.5's exit codes."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Cell:
    """One (case, arm, seed) and everything the child needs. Picklable for the pool."""

    case: str
    arm: str
    seed: int
    repo: str
    out: str
    trace: str
    trace_dir: str
    mode: str
    approve: str
    timeout: int
    unlock: bool
    # ADR 0008 items 4 and 5. `brain` reaches the child as `--brain`; `tool_budget` is the
    # kind's budget, pinned into the child's environment rather than left to the runtime to
    # infer, so what a sweep bought is on the cell and not in a default two files away.
    brain: str = DEFAULT_BRAIN
    tool_budget: int = TOOL_BUDGETS["synthetic"]


# --- selection and the two pre-flight gates -------------------------------------------------


def load_split(split_file: Path) -> dict:
    """`run.SPLIT_FILE` is passed in, so a test that redirects it redirects the sweep's split."""
    try:
        return yaml.safe_load(split_file.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise Abort(1, f"cannot read {split_file}: {exc}") from None


def cases_for(split_data: dict, name: str, include_reserve: bool = False) -> list[str]:
    """`--split all` is dev + test; reserve is never implied by a split (section 5)."""
    groups = ["dev", "test"] if name == "all" else [name]
    return [str(c) for g in groups + (["reserve"] if include_reserve else [])
            for c in split_data.get(g) or []]


def membership(split_data: dict) -> dict[str, str]:
    return {str(c): g for g in ("dev", "test", "reserve") for c in split_data.get(g) or []}


def select_cases(split_data: dict, split: str, cases: str | None,
                 include_reserve: bool = False, *, split_file: Path) -> list[str]:
    """The one selection. `report.py` expands the same one, or it reports a plan nobody ran.

    `split_file` names the file in the refusal only, and is required rather than defaulted so the
    message cannot name a path the caller did not read.
    """
    if cases:
        chosen = [c.strip() for c in cases.split(",") if c.strip()]
        chosen += cases_for(split_data, "reserve") if include_reserve else []
    else:
        chosen = cases_for(split_data, split, include_reserve)
    unknown = [c for c in chosen if c not in membership(split_data)]
    if unknown:
        raise Abort(1, f"cases not in {split_file}: {', '.join(unknown)}")
    return list(dict.fromkeys(chosen))  # an explicit list keeps its order, a split keeps the file's


def manifest(case: str, manifests: Path) -> tuple[dict, str]:
    path = manifests / f"{case}.yaml"
    try:
        raw = path.read_bytes()
        data = yaml.safe_load(raw.decode("utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise Abort(1, f"cannot read manifest {path}: {exc}") from None
    return data, hashlib.sha256(raw).hexdigest()


def fixture(case: str, manifest_data: dict, synthetic: Path, real: Path) -> Path:
    """The two fixture roots are `run.py`'s, passed in, for the same reason `MANIFESTS` is."""
    if str(manifest_data.get("source") or "synthetic") == "real":
        root = real / str(manifest_data.get("repo") or REAL_DIRS.get(case) or case)
    else:
        root = synthetic / case
    if not root.is_dir():
        raise Abort(1, f"fixture for {case} not found at {root}")
    return root


def check_freeze(cases: list[str], manifests: dict[str, dict], split_data: dict,
                 specs: Path) -> None:
    """Section 5.1: the spec freeze and the split declaration, both before any model call.

    `specs` is `run.SPECS`, passed in: a sandboxed sweep must be able to point the freeze check at
    its own spec directory, which a module-level default here would quietly prevent.
    """
    member = membership(split_data)
    for case in cases:
        # Keyed on the manifest's source, not on truthiness: a real manifest carries
        # `spec_sha256: null` by construction, a synthetic one without it is unfrozen
        # (fixture-generator.md sections 6 and 8).
        if str(manifests[case].get("source") or "synthetic") != "real":
            expected = manifests[case].get("spec_sha256")
            if not expected:
                raise Abort(4, f"{case}: synthetic manifest carries no spec_sha256; the spec is not frozen")
            spec = specs / f"{case}.yaml"
            if not spec.is_file():
                raise Abort(1, f"spec for {case} not found at {spec}")
            actual = hashlib.sha256(spec.read_bytes()).hexdigest()
            if actual != expected:
                raise Abort(4, f"{case}: spec sha256 {actual} != manifest spec_sha256 {expected}")
        declared, group = str(manifests[case].get("split") or ""), member[case]
        # CASES.md calls R05 "reserve (test)", so a reserve manifest may declare either.
        if declared != group and not (group == "reserve" and declared == "test"):
            raise Abort(4, f"{case}: manifest split {declared!r} != split.yaml {group!r}")


# --- the plan ---------------------------------------------------------------------------------


def seeds(raw: str) -> list[int]:
    try:
        return [int(s) for s in raw.split(",") if s.strip()]
    except ValueError:
        raise Abort(1, f"--seeds must be whole numbers, got {raw!r}") from None


def build_cells(args: argparse.Namespace, cases: list[str], manifests: dict[str, dict],
                traces: Path, synthetic: Path, real: Path) -> list[Cell]:
    """Order case -> seed -> arm, so a case's two arms are adjacent and share any drift (01 section 8)."""
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    if [a for a in arms if a not in ARMS]:
        raise Abort(1, f"unknown arm in {args.arms!r}")
    cells: list[Cell] = []
    for case in cases:
        kind = "real" if str(manifests[case].get("source") or "") == "real" else "synthetic"
        repo = fixture(case, manifests[case], synthetic, real)
        for seed in seeds(args.seeds):
            for arm in arms:
                cells.append(Cell(
                    case=case, arm=arm, seed=seed, repo=str(repo),
                    out=str(Path(args.out) / arm / case / f"s{seed}"),
                    trace=str(traces / arm / f"{case}-s{seed}.jsonl"), trace_dir=str(traces),
                    mode=args.mode, approve=args.approve,
                    timeout=args.timeout or TIMEOUTS[kind], unlock=bool(args.unlock_test),
                    brain=str(getattr(args, "brain", None) or DEFAULT_BRAIN),
                    tool_budget=TOOL_BUDGETS[kind]))
    return cells


def timing_scope(args: argparse.Namespace, cases: list[str], split_data: dict) -> tuple[bool, str]:
    """Whether this sweep is the one that may claim `results/timing.json`, and a scratch name."""
    arms = {a.strip() for a in args.arms.split(",") if a.strip()}
    full = arms == set(ARMS) and set(cases) >= set(cases_for(split_data, "all"))
    if not args.cases:
        return full, args.split
    digest = hashlib.sha256(",".join(sorted(cases)).encode("utf-8")).hexdigest()[:7]
    return full, f"cases-{digest}"
