"""Rule-set loading, validation and matching (03-verifier.md section 0).

Five YAML files under `verify/rules/`, split from `docs/spec/verifier-rules-draft.yaml`
exactly as that file's header maps its sections: scan surface and store kinds to
`stores.yaml`, recipients to `recipients.yaml`, entry points to `entrypoints.yaml`,
framework semantics to `primitives.yaml`, patterns to `patterns.yaml`. The draft's
`path_modes` and `verdict_precedence` blocks are deliberately absent: they are the
search's own state space and the safety ordering, and ship as constants in `reach.py`.

Every rule block carries the rule it implements and the source IDs behind it, and
`load_rules()` refuses a file where one is missing. This module knows nothing about
the graph: it loads data and matches strings.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RULES_DIR = Path(__file__).resolve().parent / "rules"
FILES = ("stores", "recipients", "entrypoints", "primitives", "patterns")

# R1-R28, CG-1..CG-20, SE1..SE12, or a section of 03-verifier.md for a spec decision.
RULE_ID = re.compile(r"^(R\d{1,2}[ab]?|CG-\d{1,2}|SE\d{1,2}|03-verifier\.md .+)$")
SOURCE_ID = re.compile(r"^S\d{1,2}[a-z]?$")

# Blocks whose every member is itself a rule entry and must carry rule + source.
_ENTRY_LISTS = ("deletion_primitives", "retention_only")


from art30.naming import norm  # one implementation (05-eval-harness.md Decision 5)


class RuleError(ValueError):
    """A rule file that does not carry what 03-verifier.md says it must."""


@dataclass(frozen=True)
class RuleSet:
    stores: dict[str, Any]
    recipients: dict[str, Any]
    entrypoints: dict[str, Any]
    primitives: dict[str, Any]
    patterns: dict[str, Any]

    # -- scan surface (1.1) ------------------------------------------------
    @property
    def scan(self) -> dict:
        return self.stores["scan"]

    @property
    def kinds(self) -> dict:
        return self.stores["store_kinds"]

    @property
    def entry(self) -> dict:
        return self.entrypoints["entry_points"]

    @property
    def guard(self) -> dict:
        return self.patterns["personal_data_field_patterns"]

    def kind(self, name: str) -> dict:
        return self.kinds[name]

    # -- matching ----------------------------------------------------------
    def vocabulary_hit(self, name: str) -> str | None:
        """The 2.1 erasure vocabulary over a normalised name; longest token wins.

        A bare action verb (`purge`, `erase`, `wipe`) qualifies only where the rest of
        the name says whose data it acts on, the same reason bare `delete` and bare
        `destroy` are excluded outright (decision 6).
        """
        text = norm(split_camel(name))
        hits = [w for w in self.entry["vocabulary"]["names"] if w in text]
        if not hits:
            return None
        best = max(hits, key=len)
        action_only = self.entry.get("action_only_vocabulary") or {}
        if best in set(action_only.get("names") or []) and not self.subject_word(text):
            longer = [w for w in hits if w not in set(action_only.get("names") or [])]
            return max(longer, key=len) if longer else None
        return best

    def subject_path_segment(self, path: str) -> bool:
        """2.2 qualifier 3: the route's terminal resource segment names the subject.

        `/users/{id}` and `/me` qualify; `/posts/{post_id}` does not. A trailing bare
        verb (`.../delete/`) is stepped over, since it names the action and not the
        resource; anything further up the path is not read, because `/users/{id}/posts`
        deletes something a user owns and not the user (decision 6a).
        """
        raw = [s for s in re.split(r"[/\\]+", path or "") if s]
        segments = [s for s in raw if not re.match(r"^[{<:%$]", s) and re.search(r"[a-zA-Z]", s)]
        excluded = {norm(w) for w in self.entry["excluded_vocabulary"]["names"]}
        wanted = {norm(w) for w in self.entry["vocabulary_or_subject_root"]["subject_path_segments"]}
        for segment in reversed(segments):
            cleaned = norm(re.sub(r"[^\w-]", " ", segment))
            if cleaned in wanted:
                return True
            if cleaned in excluded:
                continue          # a trailing action verb, not the resource
            return False
        return False

    def guard_hit(self, field_name: str) -> str:
        """3.9, completeness guard only: "" | strong | qualified.

        Exact after normalisation, with one extension: a compound name whose last
        token is a strong name is strong (`owner_email`, `signup_ip`). The qualified
        list stays exact, so `product_name` is still only qualified and still needs a
        subject link -- the measurement 3.9 rests on is unchanged.
        """
        text = norm(field_name)
        strong = {norm(w) for w in self.guard["strong"]}
        if text in strong:
            return "strong"
        if text in {norm(w) for w in self.guard["qualified"]}:
            return "qualified"
        if "_" in text and text.rsplit("_", 1)[1] in strong:
            return "strong"
        return ""

    def subject_word(self, name: str) -> bool:
        text = norm(split_camel(name))
        return any(word in text for word in self.guard["subject_link_names"])

    def subject_root_name(self, name: str) -> bool:
        names = self.kind("relational")["detect"]["subject_root_names"]
        return norm(name) in {norm(w) for w in names}

    def soft_delete_field(self, name: str) -> bool:
        return norm(name) in {norm(w) for w in self.patterns["soft_delete_markers"]["fields"]}

    def modelled_decorators(self) -> set[str]:
        """R27 [S35]: what the rules model. Anything else is read and not interpreted."""
        names = {"property", "staticmethod", "classmethod", "cached_property",
                 "register", "listens_for", "wraps", "dataclass"}
        for key, group in sorted(self.entry["decorators"].items()):
            if key in {"rule", "source"}:
                continue
            names.update(entry["name"] for entry in group)
        cleanup = self.primitives["django_cleanup"]
        names.update({cleanup["select_decorator"].split(".")[-1],
                      cleanup["ignore_decorator"].split(".")[-1]})
        return names

    def primitives_for(self, kind: str) -> list[dict]:
        return list(self.kind(kind).get("deletion_primitives") or [])

    def all_primitives(self) -> list[tuple[str, dict]]:
        """Most specific pattern first: `session.delete` must win over `.delete`."""
        out: list[tuple[str, dict]] = []
        for kind in sorted(self.kinds):
            for entry in self.primitives_for(kind):
                out.append((kind, entry))

        def specificity(item: tuple[str, dict]) -> tuple:
            patterns = item[1].get("call") or []
            depth = max((p.strip(".").count(".") + 1 for p in patterns), default=0)
            return (-depth, 0 if item[1].get("arg0_call") else 1, item[0])

        return sorted(out, key=specificity)

    def recipient_names(self) -> list[str]:
        return sorted(self.recipients["recipients"])

    def recipient(self, name: str) -> dict:
        return self.recipients["recipients"][name]

    def on_delete(self, token: str) -> dict:
        return self.primitives["django_on_delete"]["tokens"].get(token, {})

    def cascade_is_delete(self, cascade: str) -> bool:
        """R5 [S15]: exact tokens after splitting on ",". `delete-orphan` is not one."""
        tokens = {t.strip() for t in (cascade or "").split(",")}
        wanted = set(self.primitives["sqlalchemy"]["cascade_delete_tokens"])
        return bool(tokens & wanted)

    # -- the 1.1 skip list -------------------------------------------------
    def always_scan(self, rel: str) -> bool:
        """The two 1.1 exceptions, matched at any depth: `settings/*.py` covers
        `project/settings/base.py`, and the commands glob covers any app."""
        posix = rel.replace("\\", "/")
        for pattern in self.scan["always_scan"]:
            bare = pattern[3:] if pattern.startswith("**/") else pattern
            candidates = {pattern, bare, f"*/{bare}", f"**/{bare}"}
            if any(fnmatch.fnmatch(posix, candidate) for candidate in sorted(candidates)):
                return True
            if "/" not in bare and fnmatch.fnmatch(Path(posix).name, bare):
                return True
        return False

    def skip_reason(self, rel: str) -> str | None:
        """The 1.1 table, first match wins; the reason is the tally key."""
        posix = rel.replace("\\", "/")
        parts = Path(posix).parts
        name = Path(posix).name
        if self.always_scan(posix):
            return None
        for part in parts[:-1]:
            if part in set(self.scan["excluded_dirs"]):
                return f"dir:{part}"
        for pattern in self.scan["excluded_files"]:
            if fnmatch.fnmatch(name, pattern):
                return f"file:{pattern}"
        return None


def _require(block: Any, where: str) -> None:
    if not isinstance(block, dict):
        raise RuleError(f"{where}: a rule block must be a mapping")
    rule = block.get("rule")
    source = block.get("source")
    if not isinstance(rule, str) or not RULE_ID.match(rule):
        raise RuleError(f"{where}: missing or malformed rule id ({rule!r})")
    if not isinstance(source, list):
        raise RuleError(f"{where}: missing source list")
    for item in source:
        if not isinstance(item, str) or not SOURCE_ID.match(item):
            raise RuleError(f"{where}: malformed source id ({item!r})")


def _validate(name: str, doc: dict) -> None:
    if doc.get("version") != 1:
        raise RuleError(f"{name}.yaml: version must be 1")
    roots = {
        "stores": ("scan", "store_kinds"),
        "recipients": ("recipients",),
        "entrypoints": ("entry_points",),
        "primitives": ("django_on_delete", "django_signals", "django_cleanup", "sqlalchemy"),
        "patterns": ("soft_delete_markers", "anonymisation", "timers",
                     "versioning_declarations", "personal_data_field_patterns"),
    }[name]
    for root in roots:
        if root not in doc:
            raise RuleError(f"{name}.yaml: missing section {root}")
    if name == "stores":
        _require(doc["scan"], "stores.yaml scan")
        for kind, block in sorted(doc["store_kinds"].items()):
            _require(block, f"stores.yaml store_kinds.{kind}")
            for listname in _ENTRY_LISTS:
                for i, entry in enumerate(block.get(listname) or []):
                    _require(entry, f"stores.yaml {kind}.{listname}[{i}]")
    elif name == "recipients":
        for key, block in sorted(doc["recipients"].items()):
            _require(block, f"recipients.yaml recipients.{key}")
    elif name == "entrypoints":
        for key, block in sorted(doc["entry_points"].items()):
            _require(block, f"entrypoints.yaml entry_points.{key}")
    elif name == "primitives":
        for key in roots:
            _require(doc[key], f"primitives.yaml {key}")
        for token, block in sorted(doc["django_on_delete"]["tokens"].items()):
            _require(block, f"primitives.yaml django_on_delete.tokens.{token}")
    else:
        for key in roots:
            _require(doc[key], f"patterns.yaml {key}")


def load_file(name: str, directory: Path | None = None) -> dict:
    path = (directory or RULES_DIR) / f"{name}.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise RuleError(f"{path}: a rule file is a mapping")
    _validate(name, doc)
    return doc


@lru_cache(maxsize=4)
def load_rules(directory: str | None = None) -> RuleSet:
    """The five files, validated. Cached: the bytes do not change inside a run."""
    where = Path(directory) if directory else None
    loaded = {name: load_file(name, where) for name in FILES}
    return RuleSet(**loaded)


def split_camel(name: str) -> str:
    """`AccountDeleteView` -> `Account_Delete_View`. Django names its views in camel
    case and 00-contract.md's normalisation does not split it, so the vocabulary
    would never see the words inside one."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name or "")
