"""Name normalisation shared by the scorer, the verifier and the fixture generator.

One implementation (05-eval-harness.md Decision 5), inside the package so an installed
wheel carries it: the metric and the tool can never drift apart.
"""

from __future__ import annotations

import re
from typing import Iterable

SUFFIX_KEEP = ("ss", "us", "is")  # address, status, analysis: not plurals
E_STEM = ("ss", "x", "z", "ch", "sh")  # stems that take -es: address, box, batch


def _base(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
    return re.sub(r"_+", "_", s).strip("_")


def _singular(s: str) -> str:
    if s.endswith("ies") and len(s) > 4:  # companies -> company
        return s[:-3] + "y"
    if s.endswith("s") and not s.endswith(SUFFIX_KEEP) and len(s) > 3:
        s = s[:-1]  # addresses -> addresse
        if s.endswith("e") and len(s) > 3 and s[:-1].endswith(E_STEM):
            s = s[:-1]  # addresse -> address
    return s


def _strip_prefix(s: str, prefixes: tuple[str, ...]) -> str:
    for p in prefixes:  # manifest header: normalisation.prefixes
        p = _base(p)
        if s.startswith(p + "_") and len(s) > len(p) + 1:
            return s[len(p) + 1 :]
    return s


def norm(name: str, prefixes: tuple[str, ...] = (), known: set[str] | None = None) -> str:
    """known: the case's known store stems. A leading app prefix is stripped only
    when the remainder is one of them (00-contract.md, Name normalisation:
    'strip a leading app prefix when the remainder matches a known model name').
    known=None strips unconditionally and exists only to build the set."""
    s = _base(name)
    if prefixes:
        stripped = _strip_prefix(s, prefixes)
        if stripped != s and (known is None or _singular(stripped) in known):
            s = stripped
    # _base again: _singular can strip the "s" off "user_s" and leave the separator, and
    # 05 section 2 states norm(norm(x)) == norm(x) as a property the snippet does not hold.
    return _base(_singular(s))


def stems(store_names: Iterable[str], prefixes: tuple[str, ...]) -> set[str]:
    """The known-stem set for one case, built once from the manifest's store names."""
    return {norm(n, prefixes) for n in store_names}
