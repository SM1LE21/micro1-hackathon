# flaskbb — vendored for evaluation case R02

- Upstream: https://github.com/flaskbb/flaskbb
- Commit: `fc64c745bbe17d038402fb648179274b05d5b00a` (checked out 2026-08-28, UTC)
- Licence: BSD-3-Clause — the upstream LICENSE file is kept in this directory unchanged
- Purpose: a real repository read (never executed) by both evaluation arms; ground truth is hand-labelled under the protocol in `evals/CASES.md` and lives in `evals/fixtures/manifests/R02.yaml`
- Stripped from the copy: `.git`, directories named `tests`/`test`/`docs`/`doc`/`.github`, files matching `test_*.py`/`*_test.py`/`conftest.py`, `node_modules`, and binary assets (images, fonts, video, pdf). Nothing else was changed.
- After stripping: 282 files, 129 Python files, 7380 KB
