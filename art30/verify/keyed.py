"""3.10: which store a keyed deletion primitive touches (03-verifier.md 3.10).

For `cache`, `object_storage`, `search_index` and `queue` the store's identity is a
namespace and the client handle is not: one Redis handle, one boto3 client and one
Elasticsearch client each serve several. So an edge is added only where the
primitive's **own literal** matches the store's identity after normalisation
(decision 21); a literal naming another namespace adds nothing, and a fully dynamic
argument leaves the store to 1.5's narrowing.

The literal itself is resolved through `Ctx.literal`, the one module-scoped name
resolver (context.py): a private copy that scanned every module by tail name, first
assign winning, attributed `delete_object(Bucket=BUCKET)` in a module that imports
`BUCKET` from one config to a sibling bucket named by another -- 3.10's own named
false safe (`delete_object(Bucket="thumbs")` against an `uploads` bucket) one layer
below the fix written for it.

Split out of `primitives.py` to keep both files inside the 300-line rule.
"""

from __future__ import annotations

from art30.verify.context import Ctx
from art30.verify.findings import Graph, Store
from art30.verify.rules import norm


def keyed_target(ctx: Ctx, graph: Graph, site, kind: str, module: str) -> Store | None:
    """3.10: the store the primitive's own literal names, or none at all."""
    candidates = [s for s in graph.stores.values() if s.kind == kind]
    if kind == "object_storage":
        bucket = site.keywords.get("Bucket")
        literal = ctx.literal(module, bucket) if bucket else ""
        if literal:
            return next((s for s in candidates if norm(s.identity) == norm(literal)), None)
        return None
    if kind == "cache":
        arg = site.args[0] if site.args else None
        if arg is None:
            return None
        text = arg.prefix if arg.kind == "fstring" else ctx.literal(module, arg)
        for sep in (":", "/", "|", "-"):
            if sep in text:
                text = text.split(sep)[0]
                break
        return next((s for s in candidates if text and norm(s.identity) == norm(text)), None)
    if kind == "search_index":
        arg = site.keywords.get("index")
        literal = ctx.literal(module, arg) if arg else ""
        return next((s for s in candidates if literal and norm(s.identity) == norm(literal)), None)
    if kind == "queue":
        for key in ("queue", "routing_key", "queue_name", "QueueUrl"):
            arg = site.keywords.get(key)
            literal = ctx.literal(module, arg) if arg else ""
            if literal:
                return next((s for s in candidates if norm(s.identity) == norm(literal)), None)
    return None

