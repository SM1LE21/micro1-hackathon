"""Shared fixtures. `mkrepo` writes files in reverse-alphabetical order.

Creation order is what `os.scandir` returns on the author's APFS volume, so a
fixture built backwards is the cheapest test that the tools sort before they
emit (01-architecture.md section 4.5).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Mapping

import pytest

from art30.tools import ToolCtx

# Small tree with a nested package, a non-Python file and an excluded directory.
FILES: dict[str, str] = {
    "zeta.py": "import os\n\n\ndef zeta():\n    return os.name\n",
    "storage.py": 'BUCKET = "uploads"\n\n\ndef cleanup_user_files(user_id):\n    delete(user_id)\n',
    "models.py": "class User:\n    email = None\n    deleted_at = None\n",
    "billing.py": "def charge(user_id):\n    return user_id\n",
    "alpha.py": "ALPHA = 1\n",
    "README.md": "delete\n",
    "api/account.py": "def close_account(user_id):\n    return delete_later(user_id)\n",
    "api/__init__.py": "",
    "__pycache__/models.cpython-312.pyc": "delete\n",
}


def mkrepo(root: Path, files: Mapping[str, str] | None = None) -> Path:
    """Create a repository fixture, writing entries in reverse-name order."""
    payload = FILES if files is None else files
    for name in sorted(payload, reverse=True):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as handle:
            handle.write(payload[name])
    return root


@pytest.fixture(autouse=True)
def restore_environ() -> Iterator[None]:
    """`config.load()` pushes `.env` into `os.environ` with `setdefault`.

    That is deliberate (the SDK reads the key from the environment) but it is
    not undoable per test, so the isolation is structural here rather than
    accidentally provided by whichever test happens to monkeypatch first.
    """
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    return mkrepo(tmp_path / "fx")


@pytest.fixture()
def ctx(repo: Path) -> ToolCtx:
    return ToolCtx(root=repo.resolve())
