"""What `uv tool install .` actually installs.

The rules, the schema and the instruction text are data files, not modules, and
a wheel that leaves them behind fails on the first scan a stranger runs rather
than on this machine. So the wheel is built and opened here, and the installed
console script is run in an isolated environment (ADR 0007 item 2) — once for
`--help`, once for a whole scan, because `--help` builds a parser and touches
nothing else the install path needs.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_PAGE = REPO_ROOT / "art30" / "web" / "index.html"
DATA_FILES = (
    "art30/prompts/system.md",
    "art30/prompts/taxonomy.md",
    "art30/schema/record.schema.json",
)
RULES = sorted(path.name for path in (REPO_ROOT / "art30" / "verify" / "rules").glob("*.yaml"))
# `uv run --isolated` resolves this project's dependencies from PyPI and ignores
# uv.lock, so on a machine with a cold cache and no network there is nothing to
# install. That is uv failing, not the wheel failing, and a judge running the
# suite offline should read a skip. The three markers are what uv prints when the
# network is off ("network was disabled") or refused (`--offline`: "anthropic was
# not found in the cache"); a plain resolution conflict still fails. The namelist
# cases below need neither network nor cache and keep the real guarantee.
OFFLINE = ("network was disabled", "not found in the cache", "Failed to fetch")

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv builds the wheel")


def _uv(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", *args], cwd=cwd, capture_output=True, text=True, timeout=300, check=False
    )


def _offline(done: subprocess.CompletedProcess) -> bool:
    return done.returncode != 0 and any(marker in done.stderr for marker in OFFLINE)


def _installed(wheel: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """The console script from an environment that holds the wheel and nothing of
    this repository. A dependency uv could not fetch is a skip, never a failure."""
    done = _uv("run", "--isolated", "--with", str(wheel), "art30", *args, cwd=cwd)
    if _offline(done):
        pytest.skip("uv could not resolve the wheel's dependencies offline")
    return done


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One build for the module: `uv build` is the slowest thing in the suite."""
    out = tmp_path_factory.mktemp("wheel")
    built = _uv("build", "--wheel", "-o", str(out), cwd=REPO_ROOT)
    if _offline(built):   # the build backend is a download too
        pytest.skip("uv could not fetch the build backend offline")
    assert built.returncode == 0, built.stderr
    wheels = sorted(out.glob("*.whl"))
    assert len(wheels) == 1, [path.name for path in wheels]
    return wheels[0]


@pytest.fixture(scope="module")
def packed(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        return archive.namelist()


def test_the_wheel_carries_the_prompts_and_the_schema(packed: list[str]) -> None:
    missing = [name for name in DATA_FILES if name not in packed]
    assert missing == [], missing


def test_the_wheel_carries_every_rule_set(packed: list[str]) -> None:
    """A missing rule file is not an import error: the verifier would simply stop
    finding one kind of store, quietly, on somebody else's repository."""
    assert RULES, "no rule sets found in art30/verify/rules/"
    assert [f"art30/verify/rules/{name}" for name in RULES if
            f"art30/verify/rules/{name}" not in packed] == []


@pytest.mark.skipif(not WEB_PAGE.is_file(), reason="art30/web/index.html is not built yet")
def test_the_wheel_carries_the_web_page(packed: list[str]) -> None:
    assert "art30/web/index.html" in packed


def test_the_installed_console_script_runs(wheel: Path, tmp_path: Path) -> None:
    """`art30 scan --help`: the entry point resolves and the parser builds."""
    helped = _installed(wheel, tmp_path, "scan", "--help")
    assert helped.returncode == 0, helped.stderr
    assert "--arm" in helped.stdout and "--approve" in helped.stdout


def test_the_installed_console_script_scans(wheel: Path, tmp_path: Path) -> None:
    """A whole scan, which is what `--help` never proved. `baseline/` and
    `advanced/` are packages of their own, outside `art30/`: a wheel without them
    ended `art30 scan <repo> --arm baseline` in `ModuleNotFoundError: No module
    named 'baseline'` while this module stayed green. Replay against an empty
    cache runs the install path end to end with no key and no network, and stops
    at the replay miss, exit 4 (docs/cli.md, Exit codes).

    A failure here is `pyproject.toml` `[tool.hatch.build.targets.wheel]`:
    `packages` must name all three, not `art30` alone.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "models.py").write_text("class User:\n    email = None\n", encoding="utf-8")

    scanned = _installed(wheel, tmp_path, "scan", "repo", "--arm", "baseline", "--mode", "replay")

    assert "Traceback" not in scanned.stderr, scanned.stderr
    assert scanned.returncode == 4, (scanned.returncode, scanned.stdout, scanned.stderr)
    assert "replay miss" in scanned.stdout
