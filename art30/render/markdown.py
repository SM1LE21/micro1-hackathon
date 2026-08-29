"""`record.json` to `record.md`, section by section (04-output-schema.md section 6).

The renderer invents no value and paraphrases nothing: the only free text on
the page is the model's `note` strings and the verifier's `reason` strings,
both printed as written.
"""

from __future__ import annotations

from art30.arm import norm
from art30.render import (
    CATEGORY_ORDER, HUMAN, cite, erasure_rows, evidence_index, ordered_stores, table,
    verdict_text, words,
)

BOUNDARY = (
    "This is the technical half of a record of processing activities under Article 30(1) GDPR. It"
    " was derived from source code by static reading, on the date above. It is not legal advice, it"
    " states no legal basis, and it is incomplete until the cells marked `requires human completion`"
    " are filled by a person. It covers Article 30(1) — the controller's own record — for the"
    " repository named above; a processor's record under Article 30(2), and any personal data held"
    " outside this repository, are not in it."
)
RECIPIENTS_NOTE = (
    "Personal data flows into the call at the cited lines. Whether this recipient acts as a processor"
    " on the controller's instructions or as an independent controller, and whether a contract under"
    " Article 28(3) exists, is not visible in code."
)
RETENTION_NOTE = (
    "A period found in code is evidence for a retention schedule. The schedule itself is a policy the"
    " controller sets, and the reason for each period belongs in the justification column."
)
BACKUP_NOTE = (
    "No erasure verdict is rendered for a store of kind backup; it carries a retention verdict"
    " instead. This tool reports the retention schedule it found in code and cites it; whether that"
    " schedule and the procedure applied to restored systems are adequate is not visible here."
)
VERSIONING_NOTE = (
    "Object storage: where bucket versioning is enabled, a delete that passes no `versionId` leaves"
    " the previous version of the object in place."
)
ACTIVITIES_NOTE = (
    "Processing activities. Article 30 records processing activities; this document records stores."
    " No activity grouping is derived from code. The stores in section A are the input to the fiche"
    " below, one copy per activity."
)
UNSCANNED_REASONS = {
    "not_python": "not Python", "orm_not_supported": "ORM not supported",
    "generated_or_vendored": "generated or vendored", "read_budget_exhausted": "read budget exhausted",
}
OBSERVATIONS = (
    (
        "Module names. A module name says what the code was called, not what it is for."
        " Article 30(1)(b) purposes are in section F.",
        "observed_module_names", ("Name", "File"), lambda m: (m["name"], f"`{m['file']}`"),
    ),
    (
        "Region hints. A region string says where a service was configured to run. It is not a"
        " finding about a transfer under Article 30(1)(e); that cell is in section F.",
        "observed_region_hints", ("Value", "Evidence"), lambda r: (f"`{r['symbol']}`", cite(r)),
    ),
    (
        "Security measures. Technical measures under Article 32(1)(a) only, one line each. The"
        " organisational half is in section F.",
        "security_evidence", ("Measure", "Evidence", "Symbol"),
        lambda s: (words(s["measure"]), cite(s), f"`{s['symbol']}`"),
    ),
)
# Section F, in Article 30(1) order; the recipient-kind rows are added per store.
HUMAN_CELLS = (
    ("Controller — name, contact", "(a)"), ("Joint controller — name, contact", "(a)"),
    ("Representative — name, contact", "(a)"), ("Data protection officer — name, contact", "(a)"),
    ("Purposes of the processing", "(b)"), ("Confirmation of data-subject categories", "(c)"),
    ("Categories of personal data held outside this repository", "(c)"),
)
LATE_CELLS = (
    ("Transfer to a third country — occurs", "(e)"),
    ("Transfer to a third country — countries", "(e)"),
    ("Transfer to a third country — safeguards", "(e)"),
    ("Justification for each retention period", "(f)"),
    ("Organisational security measures", "(g)"),
    ("Special categories of data (Article 9)", "—"), ("Legal basis", "—"),
)
FICHE = (
    "Activity name", "Purposes", "Categories of data subjects", "Categories of personal data",
    "Categories of recipients", "Transfers outside the EU", "Retention", "Security measures",
)


def render_markdown(record: dict) -> str:
    """The whole document. A deterministic function of `record.json`."""
    stores = ordered_stores(record)
    lines = _title(record)
    lines += _inventory(record, stores)
    lines += _recipients(stores)
    lines += _retention(record, stores)
    lines += _erasure(record, stores)
    lines += _observations(record)
    lines += _human(stores)
    lines += _verification(record)
    lines += evidence_index(record, stores)
    return "\n".join(lines).rstrip("\n") + "\n"


def _stamp(value: object) -> str:
    return str(value).replace("T", " ").replace("Z", " UTC")


def _title(record: dict) -> list[str]:
    prov, ver = record.get("provenance") or {}, record.get("verification") or {}
    fixture = prov.get("fixture") or {}
    kind = "real" if "real" in str(fixture.get("path", "")).split("/") else "synthetic"
    count = ver.get("submits")
    word = "submission" if count == 1 else "submissions"
    verified = f"{count} {word}, accepted on attempt {ver.get('accepted_on_attempt')}"
    if ver.get("rule_set_sha"):
        verified += f", rule set `{ver['rule_set_sha']}`"
    rows = [
        ("Case", f"{prov.get('case')} ({kind})"),
        ("Arm", str(prov.get("arm"))),
        ("Model", f"{prov.get('model')}, effort {prov.get('effort')}"),
        ("Run", f"`{prov.get('run_id')}`"),
        ("Code read", f"`{fixture.get('path')}`, sha256 `{fixture.get('sha256')}`"),
        ("Instructions", f"sha256 `{prov.get('instruction_sha256')}`"),
        ("Generated", _stamp(prov.get("finished_at"))),
        ("Trace", f"`{prov.get('trace')}`"),
        ("Verification", verified),
    ]
    gate = prov.get("gate")
    if gate:
        rows.append((
            "Approved",
            f"{_stamp(gate.get('at'))} at the terminal, {round(gate.get('wait_s') or 0)} s at the"
            f" checkpoint, risk {str(gate.get('risk', '')).upper()}",
        ))
    rows.append(("Cost", f"USD {prov.get('cost_usd')}, {prov.get('tool_calls')} tool calls"))
    head = [f"# Record of processing — {record.get('repository')}", ""]
    return head + table(("", ""), rows) + ["", BOUNDARY, ""]


def _inventory(record: dict, stores: list[dict]) -> list[str]:
    out = ["## A. Data inventory", ""]
    subjects = [
        f"{s['label']} — inferred from {words(s['basis'])} ({cite(s)})"
        for s in record.get("data_subjects") or []
    ]
    if not subjects:
        out += ["Data subjects: none inferred from the code.", ""]
    elif len(subjects) == 1:
        out += [f"Data subjects: {subjects[0]}.", ""]
    else:
        out += ["Data subjects:", ""] + [f"- {s}." for s in subjects] + [""]
    for store in stores:
        declared = cite(store["declared_at"]) if store.get("declared_at") else None
        out += [
            f"### {store['name']} — {store['kind']} — "
            + (declared or "declaration not on a single line"),
            "",
        ]
        if store.get("note"):
            out += [store["note"], ""]
        out += table(
            ("Field", "Category", "Evidence", "Note"),
            [
                (f"`{f['name']}`", f["category"], cite(f), f.get("note") or "")
                for f in store.get("fields") or []
            ],
        )
        link = store.get("subject_link")
        linked = f"Linked to the data subject at {cite(link)}." if link else (
            "No link to a data subject found in code."
        )
        out += ["", linked, ""]
    listed = [
        f"`{u['path']}` ({UNSCANNED_REASONS.get(u['reason'], words(u['reason']))})"
        for u in record.get("unscanned") or []
    ]
    return out + _one_per_line("Not scanned", listed, "nothing")


def _recipients(stores: list[dict]) -> list[str]:
    out = ["## B. Recipients", ""]
    third = [s for s in stores if s["kind"] == "third_party"]
    if not third:
        return out + ["No store of kind third_party was found in the code.", ""]
    rows = []
    for store in third:
        fields = store.get("fields") or []
        kind = store.get("recipient_kind") or "unknown"
        rows.append(
            (
                store["name"],
                ", ".join(f"`{f['name']}` ({f['category']})" for f in fields),
                ", ".join(cite(f) for f in fields) or "—",
                f"UNKNOWN — {HUMAN}" if kind == "unknown" else words(kind).upper(),
            )
        )
    header = ("Recipient", "Fields disclosed", "Evidence", "Recipient kind")
    return out + table(header, rows) + ["", RECIPIENTS_NOTE, ""]


def _limit(item: dict) -> str:
    parts = []
    if item.get("days") is not None:
        parts.append(f"{item['days']} days")
    if item.get("criteria"):
        parts.append(item["criteria"])
    return " ".join(parts) or "NO TIMER EVIDENCED"


def _retention(record: dict, stores: list[dict]) -> list[str]:
    by_store: dict[str, list[dict]] = {}
    for item in record.get("retention") or []:
        # Normalised on both sides, as invariant I6 matched them: a period found
        # in code must not be dropped for a synthesised NO TIMER EVIDENCED row.
        by_store.setdefault(norm(item["store"]), []).append(item)
    rows = []
    for store in stores:
        own = sorted(
            by_store.get(norm(store["name"]), []),
            key=lambda i: CATEGORY_ORDER.index(i["category"]) if i.get("category") else -1,
        )
        if not own:
            # The synthesised row evidences nothing, so its category cell claims nothing.
            rows.append((store["name"], "—", "NO TIMER EVIDENCED", "—", HUMAN))
        for item in own:
            rows.append(
                (
                    store["name"],
                    item.get("category") or "all categories",
                    _limit(item),
                    cite(item) if item.get("file") else "—",
                    HUMAN,
                )
            )
    header = ("Store", "Category", "Envisaged limit", "Evidence", "Justification")
    return ["## C. Retention", ""] + table(header, rows) + ["", RETENTION_NOTE, ""]


def _one_per_line(label: str, items: list[str], empty: str) -> list[str]:
    """One item per line (04 section 6 A and D). Adjacent lines are one paragraph."""
    if not items:
        return [f"{label}: {empty}.", ""]
    if len(items) == 1:
        return [f"{label}: {items[0]}.", ""]
    return [f"{label}:", ""] + [f"- {item}." for item in items] + [""]


def _entry_point(entry: dict) -> str:
    text = f"`{entry['name']}` — {words(entry['kind'])} — {cite(entry)}"
    if entry.get("admin_only"):
        text += ", admin only"
    return text + (f" ({entry['note']})" if entry.get("note") else "")


def _evidence(block: dict) -> str:
    items = sorted(block.get("evidence") or [], key=lambda c: (c["file"], c["line"]))
    return "<br>".join(cite(c) for c in items) or "—"


def _erasure(record: dict, stores: list[dict]) -> list[str]:
    out = ["## D. Erasure", ""]
    entries = [_entry_point(e) for e in record.get("entry_points") or []]
    out += _one_per_line("Erasure entry points", entries, "none found")
    rows = []
    for store in erasure_rows(stores):
        block = store["erasure"]
        rows.append((store["name"], verdict_text(block), _evidence(block), block.get("note") or ""))
        for item in store.get("fields") or []:
            override = item.get("erasure")
            if override:
                rows.append(
                    (
                        f"↳ `{item['name']}`",
                        verdict_text(override),
                        _evidence(override),
                        override.get("note") or "",
                    )
                )
    out += table(("Store", "Verdict", "Evidence", "Note"), rows) + [""]
    if any(s["kind"] == "backup" for s in stores):
        out += [BACKUP_NOTE, ""]
    if any(s["kind"] == "object_storage" for s in stores):
        out += [VERSIONING_NOTE, ""]
    return out


def _observations(record: dict) -> list[str]:
    hints = record.get("hints") or {}
    out = ["## E. Observations from the code (not findings)", ""]
    for sentence, key, header, row in OBSERVATIONS:
        items = hints.get(key) or []
        out += [sentence, ""]
        out += (table(header, [row(item) for item in items]) if items else ["None."]) + [""]
    return out


def _human(stores: list[dict]) -> list[str]:
    rows = [(label, article, HUMAN) for label, article in HUMAN_CELLS]
    rows += [
        (f"Recipient kind — {store['name']}", "(d)", HUMAN)
        for store in stores
        if store["kind"] == "third_party"
    ]
    rows += [(label, article, HUMAN) for label, article in LATE_CELLS]
    return (
        ["## F. Requires human completion", ""]
        + table(("Cell", "Article 30(1)", "Value"), rows)
        + ["", ACTIVITIES_NOTE, ""]
        + table(("Fiche field", "Value"), [(name, HUMAN) for name in FICHE])
        + [""]
    )


def _verification(record: dict) -> list[str]:
    ver = record.get("verification") or {}
    if not ver.get("rule_set_sha"):
        head = "Verification: none. This record was accepted on schema validity alone."
        return ["## G. Verification appendix", "", head, ""]
    rejected = [
        (str(r.get("attempt")), str(r.get("store")), f"`{r.get('claim')}`", str(r.get("reason")),
         words(r.get("revised_to")).upper())
        for r in ver.get("rejected_history") or []
    ]
    missing = [
        (str(x.get("attempt")), str(x.get("store")), str(x.get("kind")), str(x.get("evidence")),
         f"round {x['added_on_attempt']}" if x.get("added_on_attempt") else "not added")
        for x in ver.get("missing_stores_resolved") or []
    ]
    none_row = [("—", "—", "—", "none", "—")]
    bad = len(ver.get("bad_citations_resolved") or []) or "none"
    unverified = len(ver.get("unverified") or []) or "none"
    return (
        ["## G. Verification appendix", "", "Claims rejected and what replaced them.", ""]
        + table(("Round", "Store", "Claim", "Reason", "Rendered instead"), rejected or none_row)
        + ["", "Stores the record did not contain, found by the scan of the repository.", ""]
        + table(("Round", "Store", "Kind", "Evidence", "Added"), missing or none_row)
        + ["", f"Citations that did not resolve: {bad}."
             f" Claims that could not be decided: {unverified}.", ""]
    )
