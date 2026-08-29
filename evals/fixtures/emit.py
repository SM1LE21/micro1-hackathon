"""Rendering primitives: the error the build raises, and a line-numbered buffer.

Line numbers are recorded while the token that names a field is written, never searched
for afterwards (fixture-generator.md section 6.1), so `Doc.add` returns the 1-based line
number of the first line it appended.
"""

from __future__ import annotations


class SpecError(Exception):
    """A spec, an anchor or a consistency assertion failed. Aborts the whole case."""


class Doc:
    """A file under construction. Text is joined with LF and ends in one newline."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, *lines: str) -> int:
        first = len(self.lines) + 1
        for line in lines:
            self.lines.append(line.rstrip())
        return first

    def blank(self, count: int = 1) -> int:
        return self.add(*([""] * count))

    def text(self) -> str:
        lines = list(self.lines)
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines) + "\n"
