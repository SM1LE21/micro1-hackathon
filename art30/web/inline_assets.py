"""Fold `art30/web/assets/` into `index.html` as a data URI, and check it stayed folded.

The page makes no external request: a judge may be offline, and the static half of
it opens from `file://`. A web font therefore cannot be linked, so the one bundled
face is written into the stylesheet between two markers by this script rather than
by hand. `--check` is the test's half: it re-derives the block and compares, so an
asset replaced without a rebuild fails a test instead of shipping a page whose CSS
and whose `assets/` disagree.

    uv run python -m art30.web.inline_assets          # write
    uv run python -m art30.web.inline_assets --check  # exit 1 if it would change
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = HERE / "index.html"
FONT = HERE / "assets" / "manrope-latin.woff2"
BEGIN = "/* font:begin"
END = "/* font:end */"
# The subset Google Fonts serves as `latin` for Manrope v20. Anything outside it —
# the record's `↳`, a Cyrillic identifier in a repository — falls through to the
# stack in `--sans`, which is what a fallback is for.
UNICODE_RANGE = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,"
    "U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
)
HEADER = (
    "/* font:begin - written by art30/web/inline_assets.py from art30/web/assets/;"
    " do not edit by hand */"
)


def font_block(data: bytes) -> str:
    """The two comment markers and the `@font-face` between them, on three lines."""
    encoded = base64.b64encode(data).decode("ascii")
    face = (
        '@font-face{font-family:"Manrope";font-style:normal;font-weight:400 800;'
        'font-display:swap;src:url("data:font/woff2;base64,' + encoded + '") format("woff2");'
        "unicode-range:" + UNICODE_RANGE + ";}"
    )
    return "\n".join([HEADER, face, END])


def rebuilt(page: str, data: bytes) -> str:
    start = page.index(BEGIN)
    stop = page.index(END, start) + len(END)
    return page[:start] + font_block(data) + page[stop:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="art30.web.inline_assets",
                                     description="inline art30/web/assets/ into index.html")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when the page and the asset disagree")
    args = parser.parse_args(argv)
    page = PAGE.read_text(encoding="utf-8")
    data = FONT.read_bytes()
    updated = rebuilt(page, data)
    if args.check:
        if updated == page:
            print("index.html carries the font in art30/web/assets/")
            return 0
        print(f"index.html does not carry {FONT.name}; run python -m art30.web.inline_assets",
              file=sys.stderr)
        return 1
    if updated != page:
        PAGE.write_text(updated, encoding="utf-8")
        print(f"wrote {len(data)} bytes of {FONT.name} into {PAGE.name}")
    else:
        print("no change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
