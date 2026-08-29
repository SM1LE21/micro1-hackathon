"""Subject links and the completeness guard's field list (03-verifier.md 3.9).

The citation that ties a store to a data subject (contract, per-store `subject_link`)
and the one job 3.9's short field list has: deciding that a store the verifier found
is missing from the record. It never assigns a category, never appears in the record
and never decides a verdict. Split out of `stores.py` to keep it inside the
300-line rule.
"""

from __future__ import annotations

from art30.verify.context import Ctx
from art30.verify.findings import Cite


def subject_links(ctx: Ctx) -> None:
    roots = {s.id for s in ctx.graph.stores.values() if s.subject_root}
    for store in ctx.graph.stores.values():
        if store.subject_link is not None:
            continue
        if store.kind != "relational":
            continue
        if store.subject_root:
            store.subject_link = store.declared_at
            continue
        # The foreign key on the child is the citation that ties the row to the
        # subject; a `relationship()` on the parent names the same pair one class up.
        for wanted in ("fk", "secondary", "relationship"):
            for relation in ctx.graph.relations:
                if relation.kind != wanted:
                    continue
                if relation.child == store.id and relation.parent in roots:
                    store.subject_link = Cite(relation.file, relation.line)
                    break
                if relation.parent == store.id and relation.child in roots:
                    store.subject_link = Cite(relation.file, relation.line)
                    break
            if store.subject_link is not None:
                break


def guard(ctx: Ctx) -> None:
    """3.9, the completeness guard only: never a category, never a verdict."""
    for store in ctx.graph.stores.values():
        hits = {ctx.rules.guard_hit(f.name) for f in store.fields}
        linked = store.subject_link is not None or ctx.rules.subject_word(store.name)
        if "strong" in hits:
            store.guard = "strong"
        elif "qualified" in hits and linked:
            store.guard = "qualified"
