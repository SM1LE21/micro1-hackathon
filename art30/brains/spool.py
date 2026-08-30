"""The spool: the one file the MCP server and the driver share.

A local brain runs in two processes. The CLI's MCP server holds the arm and
answers `submit_record`; the driver holds the trace, the gate and the renderer.
Nothing may be passed between them in memory, so every submission is appended to
`<spool>/submissions.jsonl` as it is answered, the accepted record is written
once to `<spool>/accepted.json`, and a budget that ran out leaves `<spool>/exhausted`.
The driver reads those three after the CLI exits and builds `record.json` from
them exactly as `art30/loop.py` builds it from `RunCtx` (ADR 0008 item 1).

One line per submission: `{"attempt", "record", "feedback"}`, where `feedback` is
the verifier's full dict (`loop._feedback_dict`), not the string the model saw.
The rejected attempts are what `verification.rejected_history` is made of.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SUBMISSIONS = "submissions.jsonl"
ACCEPTED = "accepted.json"
EXHAUSTED = "exhausted"
_DUMP = {"ensure_ascii": False, "separators": (",", ":")}


@dataclass(frozen=True)
class Spool:
    """A directory two processes agree on. Creating it is the driver's job."""

    root: Path

    @property
    def submissions(self) -> Path:
        return self.root / SUBMISSIONS

    @property
    def accepted(self) -> Path:
        return self.root / ACCEPTED

    @property
    def exhausted(self) -> Path:
        return self.root / EXHAUSTED

    def prepare(self) -> "Spool":
        self.root.mkdir(parents=True, exist_ok=True)
        return self

    def reset(self) -> "Spool":
        """Clear a previous run's spool. The driver calls this before the CLI starts.

        Only the driver: the server calls `prepare` and nothing else, because a CLI
        that restarts its MCP server mid-run would otherwise erase the attempts the
        record is built from. A second scan into one `--out` directory would
        otherwise inherit the first scan's acceptance and finish without submitting.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        for path in (self.submissions, self.accepted, self.exhausted):
            path.unlink(missing_ok=True)
        return self

    def append(self, attempt: int, record: dict, feedback: dict) -> None:
        """One line, flushed: a crashed CLI still leaves every answered attempt."""
        line = json.dumps({"attempt": attempt, "record": record, "feedback": feedback}, **_DUMP)
        with self.submissions.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
            handle.flush()

    def entries(self) -> list[dict]:
        """Every submission in order. A half-written last line is dropped, not raised."""
        if not self.submissions.is_file():
            return []
        found: list[dict] = []
        for raw in self.submissions.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                found.append(item)
        return found

    def rejections(self) -> list[dict]:
        """`RunCtx.rejections`: `{"attempt", **feedback}` for the attempts that failed."""
        out = []
        for entry in self.entries():
            feedback = entry.get("feedback") or {}
            if feedback.get("accepted"):
                continue
            out.append({"attempt": entry.get("attempt"),
                        **{k: v for k, v in feedback.items() if k != "accepted"}})
        return out

    def final_feedback(self) -> dict:
        """The accepted attempt's own lists, for `verification.unverified` (04 section 5)."""
        for entry in reversed(self.entries()):
            feedback = entry.get("feedback") or {}
            if feedback.get("accepted"):
                return {k: v for k, v in feedback.items() if k != "accepted"}
        return {}

    def write_accepted(self, record: dict) -> None:
        self.accepted.write_text(json.dumps(record, **_DUMP) + "\n", encoding="utf-8")

    def accepted_record(self) -> dict | None:
        if not self.accepted.is_file():
            return None
        try:
            record = json.loads(self.accepted.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return record if isinstance(record, dict) else None

    def mark_exhausted(self, note: str) -> None:
        self.exhausted.write_text(note + "\n", encoding="utf-8")

    def is_exhausted(self) -> bool:
        return self.exhausted.is_file()
