"""Store identity, the completeness guard, and the entry points the record walked past.

03-verifier.md 7.4 (the guard and its two conditions), 7.3's file-store reconciliation
by `declared_at`, and 10-instructions.md 4.2 / 4.2a (the two strings). The guard is the
only list here that blocks acceptance, and it is deliberately narrow: it fires for a
store the detectors saw *and* whose fields say personal data, never for a store the
model would have to predict.

Name matching is the contract's own rule -- lowercase, non-alphanumerics collapsed,
plural and singular equal, a leading app prefix stripped where the remainder matches a
known model name -- with the file-store fallback keyed on the citation the model has to
get right anyway.
"""

from __future__ import annotations

from art30.verify import feedback
from art30.verify.declared import reconcile
from art30.verify.findings import Graph, Store
from art30.verify.rules import RuleSet, norm

NAMED_FIELDS = 3                        # how many columns the evidence phrase names


def store_keys(store: Store) -> set[str]:
    """Every name this store answers to, normalised: id, name, model, app-stripped.

    The model's own name is a key only for the row store. A Django file store shares
    the class (R8) and is `<model>.<field>` (3.1), so offering `member` for
    `member.avatar` would let the record's `members_member` match the bytes rather
    than the rows -- and the row store would then read as a missing store.
    """
    keys = {norm(store.id), norm(store.name)}
    if store.model and store.kind == "relational":
        parts = store.model.split(".")
        keys.add(norm(parts[-1]))
        prefix = norm(parts[0]) + "_"
        keys.update(key[len(prefix):] for key in list(keys) if key.startswith(prefix))
    keys.discard("")
    return keys


def name_matches(name: str, store: Store, strip_prefix: bool = True) -> bool:
    """00-contract.md, Name normalisation, applied from both sides."""
    keys = store_keys(store)
    key = norm(name)
    if key in keys:
        return True
    # "app_users in the record matches users in the scan" (7.4).
    return strip_prefix and "_" in key and key.split("_", 1)[1] in keys


def declared_matches(record_store: dict, store: Store) -> bool:
    """7.3: a record store whose `declared_at` is the FileField line is that store."""
    cite = record_store.get("declared_at") or {}
    if store.declared_at is None or not cite:
        return False
    return (cite.get("file") == store.declared_at.file
            and cite.get("line") == store.declared_at.line)


def match(record_store: dict, graph: Graph, taken: set[str] = frozenset(),
          strip_prefix: bool = False) -> Store | None:
    """The verifier store this record store is about, or None.

    `strip_prefix` gates the app-prefix loop alone; `matched` runs the whole record
    without it before it runs the whole record with it (7.4).
    """
    ordered = [graph.stores[key] for key in sorted(graph.stores) if key not in taken]
    name = record_store.get("name") or ""
    for store in ordered:
        if name_matches(name, store, strip_prefix=False):
            return store
    for store in ordered:                 # the fallback, keyed on the citation (7.3)
        if declared_matches(record_store, store):
            return store
    if not strip_prefix:
        return None
    for store in ordered:                 # 7.4: "app_users in the record matches users"
        if name_matches(name, store, strip_prefix=True):
            return store
    return None


def matched(record: dict, graph: Graph) -> dict[int, Store]:
    """Record store index -> verifier store, each verifier store claimed at most once.

    Two sweeps over the whole record, not two loops inside one store: an exact name
    beats an app-prefix strip (7.4), and the strip is tried for a record store only
    after every other record store has had its exact-name and `declared_at` pass.
    Per-store ordering let a plausible real name (`admin_users`) claim `user` before
    the record's own `user` row was looked at, and the true claim was then rejected.
    """
    out: dict[int, Store] = {}
    taken: set[str] = set()
    items = list(enumerate(record.get("stores") or []))
    for strip_prefix in (False, True):
        for index, item in items:
            if index in out:
                continue
            store = match(item, graph, taken, strip_prefix)
            if store is not None:
                out[index] = store
                taken.add(store.id)
    return out


def fires(store: Store) -> bool:
    """7.4: a strong 3.9 match, or a qualified one together with a subject link."""
    if store.guard == "strong":
        return True
    return store.guard == "qualified" and store.subject_link is not None


def evidence(store: Store, rules: RuleSet) -> str:
    """4.2: `"{file}:{line} {verb} {what}"`, read off the store's own citations."""
    names = sorted({f.name for f in store.fields if rules.guard_hit(f.name)})
    if not names:
        names = sorted({f.name for f in store.fields})
    cite = store.declared_at or (store.fields[0] if store.fields else None)
    where = f"{cite.file}:{cite.line}" if cite is not None else store.id
    verb = feedback.VERB.get(store.kind, "writes")
    what = ", ".join(names[:NAMED_FIELDS]) or "personal data"
    return f"{where} {verb} {what}"


def missing_stores(record: dict, graph: Graph, rules: RuleSet) -> list[dict]:
    """7.4: every detected store the record does not carry, guard conditions met."""
    covered = {store.id for store in matched(record, graph).values()}
    found = [feedback.missing_store(store.id, store.kind, evidence(store, rules))
             for key, store in sorted(graph.stores.items())
             if key not in covered and fires(store)]
    return feedback.ordered("missing_stores", found)


def declarations(record: dict) -> list[dict]:
    """2.5's `E`: the record's own entry points, in `reconcile`'s input shape."""
    return [{"name": item.get("name", ""), "file": item.get("file", ""),
             "line": int(item.get("line") or 0)}
            for item in record.get("entry_points") or []]


def missing_entry_points(record: dict, graph: Graph,
                         rows: list[dict] | None = None) -> list[dict]:
    """4.2a: a discovered erasure entry point the record does not declare. Never blocks.

    `rows` is the reconciliation `check.py` already built for 2.5's `D union E_valid`;
    computing it twice would let the list and the start set disagree.
    """
    if rows is None:
        rows = reconcile(graph, declarations(record))
    found = [feedback.missing_entry(row["name"], row["file"], row["line"],
                                    row.get("kind", "unknown"))
             for row in rows if row["status"] == "missing"]
    return feedback.ordered("missing_entry_points", found)
