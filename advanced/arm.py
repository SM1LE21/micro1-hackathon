"""Advanced arm: tool set, submit handler with the verifier, gate before render.

01-architecture.md section 3 is the shape, and the whole difference from
`baseline/arm.py` is the four lines of `handle_submit` after validation plus a gate
body that returns a `Decision` instead of `None`. Same prompt bytes, same tool
schemas, same five attempts (ADR 0003 item 4).

The risk rating is computed from **the accepted record** (03-verifier.md 6.4): the
document the human is about to approve, not the verifier's own set, which 7.3 lets
diverge in the conservative direction by design. The verifier's rating is carried
beside it as a cross-check and both are shown at the gate when they differ.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from advanced import gate as terminal
from art30 import tools
from art30.arm import REACHING, Decision, Feedback, RunCtx, validate
from art30.verify import build_graph, load_rules
from art30.verify.rules import rules_sha
from art30.verify.check import check
from art30.verify.completeness import matched
from art30.verify.findings import Graph
from art30.verify.reach import risk_flags, verdicts

# 00-contract.md, Trace contract: the verdicts and the categories that make a row
# `high`. `evals/harness/trace_check.py` recomputes the rating from the record with
# this same reading, so a run whose checkpoint disagrees fails its own validator.
HIGH_VERDICTS = frozenset({"not_erased", "pseudonymised", "external_manual",
                           "no_entry_point", "no_schedule_evidenced", "unverified"})
HIGH_CATEGORIES = frozenset({"identifier", "contact"})


def _verdict(store: dict) -> str:
    return str((store.get("erasure") or {}).get("verdict") or "")


def high_store(record: dict) -> dict | None:
    """The first store, in the record's own order, that turns the rating `high`."""
    for store in record.get("stores") or []:
        categories = {f.get("category") for f in store.get("fields") or []}
        if _verdict(store) in HIGH_VERDICTS and categories & HIGH_CATEGORIES:
            return store
    return None


def risk_rating(record: dict) -> str:
    """00-contract.md, Trace contract, over the record the human is about to sign."""
    if high_store(record) is not None:
        return "high"
    found = [_verdict(store) for store in record.get("stores") or []]
    if found and all(verdict in REACHING for verdict in found):
        return "medium" if "erased_after_timer" in found else "low"
    return "low"


def cross_check(record: dict, graph: Graph, rules=None) -> dict | None:
    """6.4: the verifier's own rating, and the stores the two readings disagree on.

    The record's own columns are handed to `verdicts` exactly as `check.Check._verdicts`
    hands them, because 4.7's union can flip a store between `anonymised` and
    `pseudonymised` on them: without it the gate would cross-check the accepted record
    against a verdict set the record was never checked against.

    6.4 shows the block "where the two ratings differ", so a per-store difference is not
    the trigger -- 7.3 accepts conservative divergences by design, and every conservative
    record would otherwise print "The verifier's own rating is LOW." on a screen already
    rating LOW. The differing stores are what the block names once it fires.
    """
    pairs = matched(record, graph)
    stores = record.get("stores") or []
    claimed = {store.id: sorted({str(f.get("name") or "")
                                 for f in stores[index].get("fields") or []})
               for index, store in pairs.items()}
    found = verdicts(graph, rules, claimed=claimed)
    flags = risk_flags(found)
    if flags["rating"] == risk_rating(record):
        return None
    differ = sorted(str(stores[index].get("name") or "")
                    for index, store in pairs.items()
                    if _verdict(stores[index]) != found[store.id].verdict)
    return {"rating": flags["rating"], "stores": differ}


class AdvancedArm:
    name = "advanced"

    def __init__(self, rules=None) -> None:
        self.rules = rules or load_rules()
        self.rule_set_sha = rules_sha()   # verification.rule_set_sha in record.json
        self._graphs: dict[str, Graph] = {}

    def graph(self, root: Path) -> Graph:
        """One graph per repository per run: the record is checked up to five times."""
        key = str(Path(root).resolve())
        if key not in self._graphs:
            self._graphs[key] = build_graph(Path(root))
        return self._graphs[key]

    def tools(self) -> tuple[dict, ...]:
        return tools.SPEC

    def handle_submit(self, record: dict, ctx: RunCtx) -> Feedback:
        left = ctx.cfg.max_submits - ctx.submits
        errors = validate(record)
        if errors:
            return Feedback(accepted=False, attempt=ctx.submits, attempts_left=left,
                            schema_errors=errors)
        found = check(record, ctx.root, self.rules, self.graph(ctx.root))
        # `unverified`, `missing_entry_points` and `conservative_divergences` are kept
        # on an accepted feedback too: 07-ui.md section 2 rule 3 prints all three on an
        # accepted record, and `to_tool_result` drops every empty list for the model.
        return replace(found, attempt=ctx.submits, attempts_left=left)

    def gate(self, record: dict, ctx: RunCtx) -> Decision | None:
        risk = risk_rating(record)
        cross = cross_check(record, self.graph(ctx.root), self.rules)
        summary = terminal.gate_summary(record, risk, cross)
        # `out_dir` is the run's own directory: `--approve file` exchanges the
        # request and the decision inside it, which is where the website looks.
        return terminal.decide(record, risk, summary, ctx.cfg.approve,
                               out_dir=ctx.cfg.out_dir)
