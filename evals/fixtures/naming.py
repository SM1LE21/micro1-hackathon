"""Name normalisation for the fixture generator.

There is one implementation and it lives in the scorer (`05-eval-harness.md` section 2:
"It lives in evals/harness/score.py and the verifier imports it, so there is one
implementation"). This module re-exports it so the build-time assertions in `checks.py` are
run with the same function that will key the metric — a second copy drifted once already,
and assertions 3 and 4 exist precisely to make that collision impossible.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.harness.score import norm, stems  # noqa: E402

__all__ = ["IRREGULAR_PLURALS", "line_tokens", "norm", "stems"]

# Never handled by the scorer's singulariser; a fixture using one never matches rather than
# colliding (fixture-generator.md section 7 rule 3). Generator-only, so it stays here.
IRREGULAR_PLURALS = frozenset(
    {"statuses", "analyses", "indices", "matrices", "criteria", "media", "people", "children"}
)

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def line_tokens(line: str) -> set[str]:
    """Normalised identifier-ish tokens of one rendered line.

    String literals are tokenised too, so `upload_to="account/avatars/"` carries both
    halves of the `<model>.<field>` store identity (section 7 rule 1).
    """
    return {norm(t) for t in _TOKEN.findall(line)}
