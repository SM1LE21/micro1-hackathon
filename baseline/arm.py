"""Baseline arm: tool set, schema-only submit handler, no gate.

The comparison rests on this file being small. Same prompt bytes, same tool
schemas, same five attempts as the advanced arm (ADR 0003 item 4); the whole
difference is that nothing here reads the repository a second time.
"""

from __future__ import annotations

from art30 import tools
from art30.arm import Decision, Feedback, RunCtx, validate


class BaselineArm:
    name = "baseline"
    # The `[verify]` banner of 07-ui.md section 5. Read by the loop with
    # getattr, so the loop still branches on nothing an arm is named.
    verify_label = "schema only"

    def tools(self) -> tuple[dict, ...]:
        return tools.SPEC

    def handle_submit(self, record: dict, ctx: RunCtx) -> Feedback:
        errors = validate(record)
        if errors:
            return Feedback(
                accepted=False,
                attempt=ctx.submits,
                attempts_left=ctx.cfg.max_submits - ctx.submits,
                schema_errors=errors,
            )
        return Feedback(accepted=True)

    def gate(self, record: dict, ctx: RunCtx) -> Decision | None:
        return None
