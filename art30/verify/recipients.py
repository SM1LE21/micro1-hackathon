"""Third-party recipients (03-verifier.md 3.6; R22, R23, R24).

Detected by import plus a call that carries personal data, never by import alone
(AMBIGUITIES 7 reading B). Sentry is the exception R23 states: `init` alone makes
it a recipient, with the fields the SDK sends under its own defaults [S31] [S42].
"""

from __future__ import annotations

from art30.verify.context import personal_names as _personal
from art30.verify.findings import Cite, Store, StoreField
from art30.verify.rules import norm


# ---------------------------------------------------------------------------
# 3.6 third-party recipients (R22, R23, R24)
# ---------------------------------------------------------------------------
def detect_recipients(ctx) -> None:
    for name in ctx.rules.recipient_names():
        data = ctx.rules.recipient(name)
        imports = list(data.get("import") or [])
        literals = list(data.get("literal") or [])
        transmitting = list(data.get("transmitting_calls") or [])
        defaults = list(data.get("fields_by_default") or [])
        if not imports and not literals:
            continue                             # nothing to discover it by
        for module in sorted(ctx.graph.modules):
            source = ctx.graph.modules[module].source
            if imports and not ctx.imports_any(module, imports):
                continue
            if literals and not any(text in source for text in literals):
                continue
            for site in ctx.calls_by_module.get(module, []):
                if not _matches_call(site, transmitting):
                    continue
                personal = _personal(ctx, site)
                if not personal and not defaults:
                    continue                     # import alone is not evidence
                store = Store(id=name, kind="third_party", name=name,
                              declared_at=Cite(site.file, site.line),
                              subject_link=Cite(site.file, site.line), identity=name,
                              flags=[f"recipient:{name}"])
                if defaults:                     # R23 [S31] [S42]: init alone
                    for item in defaults:
                        store.fields.append(StoreField(
                            name=item["name"], file=site.file, line=site.line,
                            declared="sdk_default", category=item.get("category")))
                    if _pii_enabled(ctx, module, data):
                        for item in data.get("fields_when_pii_enabled") or []:
                            store.fields.append(StoreField(
                                name=item["name"], file=site.file, line=site.line,
                                declared="sdk_pii", category=item.get("category")))
                for found in personal:
                    store.fields.append(StoreField(name=found, file=site.file, line=site.line))
                ctx.add(store)


def _matches_call(site, transmitting: list[str]) -> bool:
    dotted = site.dotted or site.name
    for call in transmitting:
        if dotted == call or dotted.endswith(f".{call}") or site.name == call:
            return True
    return False


def _pii_enabled(ctx, module: str, data: dict) -> bool:
    flag = data.get("pii_flag_kwarg")
    supersedes = (data.get("supersedes_flag") or "").split(".")[0]
    for site in ctx.calls_by_module.get(module, []):
        if flag and flag in site.keywords and norm(site.keywords[flag].value) == "true":
            return True
        if supersedes and supersedes in site.keywords:
            return True
        if site.name in set(data.get("pii_calls") or []):
            return True
    return False
