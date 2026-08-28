# pinry — vendored for evaluation case R03

- Upstream: https://github.com/pinry/pinry
- Commit: `05476b112401cf34a38bfbffc67c37f5f6c3b38f` (checked out 2026-08-28, UTC)
- Licence: BSD-2-Clause — the upstream LICENSE file is kept in this directory unchanged
- Purpose: a real repository read (never executed) by both evaluation arms; ground truth is hand-labelled under the protocol in `evals/CASES.md` and lives in `evals/fixtures/manifests/R03.yaml`
- Stripped from the copy: `.git`, directories named `tests`/`test`/`docs`/`doc`/`.github`, files matching `test_*.py`/`*_test.py`/`conftest.py`, `node_modules`, and binary assets (images, fonts, video, pdf). Nothing else was changed.
- After stripping: 166 files, 71 Python files, 1140 KB
