# full-stack-fastapi-template — vendored for evaluation case R01

- Upstream: https://github.com/fastapi/full-stack-fastapi-template
- Commit: `486f054cc8d1aead59ec96cc0a16933d06c10e0d` (checked out 2026-08-28, UTC)
- Licence: MIT — the upstream LICENSE file is kept in this directory unchanged
- Purpose: a real repository read (never executed) by both evaluation arms; ground truth is hand-labelled under the protocol in `evals/CASES.md` and lives in `evals/fixtures/manifests/R01.yaml`
- Stripped from the copy: `.git`, directories named `tests`/`test`/`docs`/`doc`/`.github`, files matching `test_*.py`/`*_test.py`/`conftest.py`, `node_modules`, and binary assets (images, fonts, video, pdf). Nothing else was changed.
- After stripping: 188 files, 28 Python files, 1380 KB
- Note (2026-08-29): `backend/app/api/deps.py:36` uses `except InvalidTokenError, ValidationError:` (PEP 758, Python 3.14 syntax). It is identical upstream at this commit, not a vendoring artefact. Under Python 3.12 the file does not parse and the verifier records it as unparsed (R28); the labelling protocol reads it by eye.
