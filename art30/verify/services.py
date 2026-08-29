"""The stores that are not the database (03-verifier.md 3.2 to 3.8).

Object storage, cache, search index, queue, third-party recipient, log sink and
backup. Each store's identity is the identifier the code carries -- the bucket or
prefix constant, the key namespace, the index name, the queue name, the SDK name,
the job's own name constant -- because 3.10 attributes a keyed deletion by that
literal and never by the client handle.
"""

from __future__ import annotations

from art30.verify import recipients
from art30.verify.context import personal_names as _personal
from art30.verify.findings import Cite, Store, StoreField
from art30.verify.rules import norm

WRITE_HINT = ("put_object", "upload_file", "upload_fileobj", "save", "index", "create",
              "set", "setex", "hset", "basic_publish", "publish", "send_message")


def detect(ctx) -> None:
    _object_storage(ctx)
    _cache(ctx)
    _search_index(ctx)
    _queue(ctx)
    recipients.detect_recipients(ctx)
    _log(ctx)
    _backup(ctx)


def _assign_target(ctx, module: str, line: int) -> str:
    info = ctx.graph.modules.get(module)
    if info is None:
        return ""
    for assign in info.assigns:
        if assign.line == line and "." not in assign.target:
            return assign.target
    return ""


def _clients(ctx, module: str, imports: list[str], names: set[str]) -> list[tuple[str, int]]:
    """Every handle bound from one of the SDK's constructors, with its line."""
    found: list[tuple[str, int]] = []
    if not ctx.imports_any(module, imports):
        return found
    for site in ctx.calls_by_module.get(module, []):
        tail = (site.dotted or site.name).split(".")[-1]
        if tail in names and ctx.external_head(module, site, imports):
            found.append((_assign_target(ctx, module, site.line) or tail, site.line))
    return found


# ---------------------------------------------------------------------------
# 3.2 object storage
# ---------------------------------------------------------------------------
def _object_storage(ctx) -> None:
    detect = ctx.rules.kind("object_storage")["detect"]
    bucket_kwarg = detect["bucket_kwarg"]
    for module in sorted(ctx.graph.modules):
        clients = [
            (_assign_target(ctx, module, site.line) or "s3", site.line)
            for site in ctx.calls_by_module.get(module, [])
            if (site.dotted in set(detect["boto3_client"]["call"])
                and site.args and str(site.args[0].value) in set(detect["boto3_client"]["arg0_literal"]))
        ]
        storages = [
            (_assign_target(ctx, module, site.line) or "storage", site.line)
            for site in ctx.calls_by_module.get(module, [])
            if (site.dotted or site.name).split(".")[-1] in set(detect["django_storages"]["base"])
        ]
        handles = clients + storages
        if not handles:
            continue
        for site in ctx.calls_by_module.get(module, []):
            if bucket_kwarg not in site.keywords:
                continue
            name = ctx.literal(module, site.keywords[bucket_kwarg])
            if not name:
                continue
            const = ctx.constant(module, site.keywords[bucket_kwarg].value)
            line = const[1] if const else handles[0][1]
            store = Store(id=name, kind="object_storage", name=name,
                          declared_at=Cite(ctx.file_of(module), line), identity=name,
                          client_vars=[h[0] for h in handles])
            store.fields += _key_fields(ctx, module)
            if store.fields:
                store.subject_link = Cite(store.fields[0].file, store.fields[0].line)
            ctx.add(store)


def _key_fields(ctx, module: str) -> list[StoreField]:
    """The key builder is what ties the bucket to a subject: `avatar_key(user_id)`."""
    out: list[StoreField] = []
    for symbol in sorted(ctx.graph.symbols.values(), key=lambda s: (s.file, s.line)):
        if symbol.module != module or symbol.owner:
            continue
        if symbol.short.endswith("_key") or (
            "key" in symbol.short and any(ctx.rules.subject_word(a) for a in symbol.args)
        ):
            out.append(StoreField(name=symbol.short, file=symbol.file, line=symbol.line,
                                  declared="key"))
    return out


# ---------------------------------------------------------------------------
# 3.3 cache
# ---------------------------------------------------------------------------
def _cache(ctx) -> None:
    kind = ctx.rules.kind("cache")
    detect = kind["detect"]
    imports = list(detect["redis"]["import"]) + list(detect["django_cache"]["import"])
    ctors = {c.split(".")[-1] for c in detect["redis"]["call"]}
    writes = set(detect["write_calls"])
    for module in sorted(ctx.graph.modules):
        handles = _clients(ctx, module, imports, ctors)
        names = {h[0] for h in handles} | {"cache"}
        for site in ctx.calls_by_module.get(module, []):
            if site.name not in writes or site.receiver.split(".")[0] not in names:
                continue
            if not site.args:
                continue
            namespace = _namespace(ctx, module, site.args[0])
            if not namespace:
                continue
            store = Store(id=namespace, kind="cache", name=namespace,
                          declared_at=Cite(site.file, site.line),
                          subject_link=Cite(site.file, site.line), identity=namespace,
                          client_vars=sorted(names & {site.receiver.split(".")[0]}))
            for found in _personal(ctx, site):
                store.fields.append(StoreField(name=found, file=site.file, line=site.line))
            ctx.add(store)


def _namespace(ctx, module: str, arg) -> str:
    """3.3: the key's literal prefix up to the first placeholder."""
    text = arg.prefix if arg.kind == "fstring" else ctx.literal(module, arg)
    if not text:
        return ""
    for sep in (":", "/", "|", "-"):
        if sep in text:
            return text.split(sep)[0]
    return text


# ---------------------------------------------------------------------------
# 3.4 search index
# ---------------------------------------------------------------------------
def _search_index(ctx) -> None:
    detect = ctx.rules.kind("search_index")["detect"]
    kwarg = ctx.rules.kind("search_index")["index_name_from_kwarg"]
    writes = set(detect["write_calls"])
    for module in sorted(ctx.graph.modules):
        if not ctx.imports_any(module, list(detect["import"])):
            continue
        for site in ctx.calls_by_module.get(module, []):
            if site.name not in writes or kwarg not in site.keywords:
                continue
            name = ctx.literal(module, site.keywords[kwarg])
            if not name:
                continue
            const = ctx.constant(module, site.keywords[kwarg].value)
            store = Store(id=name, kind="search_index", name=name,
                          declared_at=Cite(site.file, const[1] if const else site.line),
                          subject_link=Cite(site.file, site.line),
                          identity=name, client_vars=[site.receiver.split(".")[0]])
            for found in _personal(ctx, site):
                store.fields.append(StoreField(name=found, file=site.file, line=site.line))
            ctx.add(store)


# ---------------------------------------------------------------------------
# 3.5 queue
# ---------------------------------------------------------------------------
def _queue(ctx) -> None:
    kind = ctx.rules.kind("queue")
    detect = kind["detect"]
    imports = sorted({n for block in ("celery", "rq", "other")
                      for n in detect[block]["import"]})
    calls = {c for block in ("celery", "rq", "other") for c in detect[block]["call"]}
    name_kwargs = list(detect["queue_name_kwargs"])
    for module in sorted(ctx.graph.modules):
        if not ctx.imports_any(module, imports):
            continue
        for site in ctx.calls_by_module.get(module, []):
            if site.name not in calls:
                continue
            personal = _personal(ctx, site)
            if not personal:                    # an id-only payload is not a store
                continue
            name = ""
            for kwarg in name_kwargs:
                if kwarg in site.keywords:
                    name = ctx.literal(module, site.keywords[kwarg]) or name
                if name:
                    break
            name = name or site.receiver.split(".")[0] or site.name
            store = Store(id=name, kind="queue", name=name,
                          declared_at=Cite(site.file, site.line),
                          subject_link=Cite(site.file, site.line), identity=name)
            for found in personal:
                store.fields.append(StoreField(name=found, file=site.file, line=site.line))
            ctx.add(store)


# ---------------------------------------------------------------------------
# 3.7 log sinks
# ---------------------------------------------------------------------------
def _log(ctx) -> None:
    detect = ctx.rules.kind("log")["detect"]
    factories = set(detect["logger_factory"])
    calls = {c.split(".")[-1] for c in detect["call"]}
    for module in sorted(ctx.graph.modules):
        if not ctx.imports_any(module, list(detect["import"])):
            continue
        name, line = "", 0
        for site in ctx.calls_by_module.get(module, []):
            if site.name in factories and site.args:
                literal = ctx.literal(module, site.args[0])
                name = literal or module
                line = site.line
                break
        for site in ctx.calls_by_module.get(module, []):
            if site.name not in calls and site.dotted not in set(detect["call"]):
                continue
            personal = _personal(ctx, site) + _personal_names(ctx, site)
            if not personal:
                continue
            label = name or module or "stdout"
            store = Store(id=label, kind="log", name=label,
                          declared_at=Cite(ctx.file_of(module), line or site.line),
                          subject_link=Cite(site.file, site.line), identity=label)
            for found in dict.fromkeys(personal):
                store.fields.append(StoreField(name=found, file=site.file, line=site.line))
            ctx.add(store)


def _personal_names(ctx, site) -> list[str]:
    out = []
    for arg in list(site.args) + [site.keywords[k] for k in sorted(site.keywords)]:
        if arg.kind == "name" and ctx.rules.guard_hit(arg.value):
            out.append(arg.value)
    return out


# ---------------------------------------------------------------------------
# 3.8 backups
# ---------------------------------------------------------------------------
def _backup(ctx) -> None:
    detect = ctx.rules.kind("backup")["detect"]
    words = list(detect["name_matches"])
    for module in sorted(ctx.graph.modules):
        info = ctx.graph.modules[module]
        basename = module.split(".")[-1]
        symbols = [s for s in ctx.graph.symbols.values() if s.module == module]
        hit = any(word in norm(basename) for word in words) or any(
            any(word in norm(s.short) for word in words) for s in symbols)
        snapshot = [s for s in ctx.calls_by_module.get(module, [])
                    if s.name in set(detect["call"])]
        if not hit and not snapshot:
            continue
        name, declared = basename, Cite(info.file, 1)
        for constant in detect["name_constants"]:
            found = ctx.constant(module, constant)
            if found:
                name, declared = found[0], Cite(info.file, found[1])
                break
        store = Store(id=name, kind="backup", name=name, declared_at=declared,
                      identity=name)
        for constant in detect["column_constants"]:
            found = ctx.constant(module, constant)
            if not found:
                continue
            store.subject_link = Cite(info.file, found[1])
            for column in found[0].split("|"):
                store.fields.append(StoreField(name=column, file=info.file, line=found[1]))
            break
        if snapshot and not store.fields:
            store.flags.append("opaque_dump")
        ctx.add(store)
