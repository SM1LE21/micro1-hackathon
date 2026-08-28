# microblog — vendored for evaluation case R04

- Upstream: https://github.com/miguelgrinberg/microblog
- Commit: `a975ef64864354867c88e0ed3a17ba7d17dca752` (checked out 2026-08-28, UTC)
- Licence: MIT — the upstream LICENSE file is kept in this directory unchanged
- Purpose: a real repository read (never executed) by both evaluation arms; ground truth is hand-labelled under the protocol in `evals/CASES.md` and lives in `evals/fixtures/manifests/R04.yaml`
- Stripped from the copy: `.git`, directories named `tests`/`test`/`docs`/`doc`/`.github`, files matching `test_*.py`/`*_test.py`/`conftest.py`, `node_modules`, and binary assets (images, fonts, video, pdf). Nothing else was changed.
- After stripping: 72 files, 34 Python files, 316 KB
