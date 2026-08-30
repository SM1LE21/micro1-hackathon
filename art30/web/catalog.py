"""What the page may start: the cases, where they live, and whether a key exists.

Read from `evals/split.yaml` and the two fixture roots, so the website offers
exactly the repositories the evaluation knows about. A case is `replayable`
when `evals/cache/<id>/<arm>/s1` is on disk: that is the run a judge with no
API key can watch.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from art30 import config

REPO_ROOT = Path(__file__).resolve().parents[2]
SPLIT_FILE = REPO_ROOT / "evals" / "split.yaml"
SYNTHETIC = REPO_ROOT / "evals" / "fixtures" / "synthetic"
REAL = REPO_ROOT / "evals" / "fixtures" / "real"
MANIFESTS = REPO_ROOT / "evals" / "fixtures" / "manifests"
KEY_NAME = "ANTHROPIC_API_KEY"
ARMS = ("baseline", "advanced")
GROUPS = ("dev", "test", "demo", "reserve")
# evals/harness/plan.py REAL_DIRS: the vendored directory each real case reads.
# Copied rather than imported because the installed CLI ships without `evals/`.
REAL_DIRS = {"R01": "full-stack-fastapi-template", "R02": "flaskbb", "R03": "pinry",
             "R04": "microblog", "R05": "Django-Styleguide-Example"}


NO_SPLIT = ("no evals/split.yaml under {root}, so there is no case list here."
            " Start `art30 serve` from the project directory")


def project_root() -> Path:
    """Where the cases and the repositories live: the checkout when the package sits
    inside one, the working directory when it is installed as a wheel."""
    return REPO_ROOT if SPLIT_FILE.is_file() else Path.cwd().resolve()


def missing_split() -> str | None:
    return None if SPLIT_FILE.is_file() else NO_SPLIT.format(root=project_root())


def split_data() -> dict:
    try:
        return yaml.safe_load(SPLIT_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def cache_root() -> Path:
    raw = Path(os.environ.get("ART30_CACHE_DIR") or "evals/cache")
    return raw if raw.is_absolute() else REPO_ROOT / raw


def kind_of(case_id: str) -> str:
    """`demo` names the two hand-testing repositories; the CLI's own split is
    synthetic vs real, and the tool budget follows that one (config.for_case_kind)."""
    if case_id.upper().startswith("R"):
        return "real"
    return "demo" if case_id.upper().startswith("D") else "synthetic"


def path_of(case_id: str) -> Path:
    if kind_of(case_id) == "real":
        return REAL / REAL_DIRS.get(case_id, case_id)
    return SYNTHETIC / case_id


def name_of(case_id: str) -> str:
    """The manifest's `intent` line, which is what the case is for, in one sentence."""
    manifest = MANIFESTS / f"{case_id}.yaml"
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    intent = str(data.get("intent") or "").strip()
    return intent or path_of(case_id).name


def replay_arms(case_id: str) -> list[str]:
    root = cache_root()
    return [arm for arm in ARMS if (root / case_id / arm / "s1").is_dir()]


def live_enabled() -> bool:
    """The key's presence, never its value: the environment, then `.env` by name."""
    if os.environ.get(KEY_NAME):
        return True
    return KEY_NAME in config.read_dotenv(REPO_ROOT / ".env")


def cases() -> list[dict]:
    data = split_data()
    rows: list[dict] = []
    for group in GROUPS:
        for case_id in [str(c) for c in data.get(group) or []]:
            root = path_of(case_id)
            arms = replay_arms(case_id)
            rows.append({
                "id": case_id,
                "kind": kind_of(case_id),
                "split": group,
                "path": str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT)
                        else str(root),
                "present": root.is_dir(),
                "replayable": bool(arms),
                "replay_arms": arms,
                "name": name_of(case_id),
            })
    return rows


def by_id() -> dict[str, dict]:
    return {row["id"]: row for row in cases()}


def test_cases() -> set[str]:
    """The split the CLI itself refuses to run live without ART30_UNLOCK_TEST."""
    return {str(c) for c in split_data().get("test") or []}
