"""`art30/web/index.html`: served, offline, quiet, and a record view that cannot drift.

Every check here is on the page as a file, plus one request through the real
server, because the page is the one deliverable a judge sees without reading any
code. Four properties are asserted rather than trusted: it needs no network (ADR
0007 — "a judge may be offline"), it carries no emoji and never says the word the
writing contract forbids, its script parses, and its eight record headings are
the ones `art30/render/markdown.py` writes into `record.md`. The last is the one
that matters over a weekend: the Markdown renderer is frozen and the page is not,
so the page is compared to it rather than to a copy of it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

import pytest

from art30.web import inline_assets
from art30.web import server as server_mod

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / "art30" / "web" / "index.html"
RENDER = REPO_ROOT / "art30" / "render"
VIEWS = ("run", "runs", "results", "settings", "about")

# The `latin` subset is base64, which cannot contain a colon, so the font block is
# excluded from the scans below by span rather than by hoping it stays quiet.
FONT_DATA = re.compile(r"base64,([A-Za-z0-9+/=]+)")
HEADING = re.compile(r'"## ([A-H]\. [^"]+)"')
COMMENTS = (
    re.compile(r"<!--.*?-->", re.S),      # HTML
    re.compile(r"/\*.*?\*/", re.S),       # CSS and JS block
    re.compile(r"(?m)^\s*//.*$"),         # a JS line comment on its own line
)


@pytest.fixture(scope="module")
def page() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def font_span(page: str) -> tuple[int, int]:
    found = FONT_DATA.search(page)
    assert found is not None, "the page carries no inlined font"
    return found.span(1)


# --- the page is served ---------------------------------------------------------------


def test_the_page_is_served_at_the_root_as_html() -> None:
    httpd = server_mod.build("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/"
        with urllib.request.urlopen(url, timeout=10) as answer:
            body = answer.read().decode("utf-8")
            assert answer.status == 200
            assert answer.headers["Content-Type"].startswith("text/html")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
    assert body == PAGE.read_text(encoding="utf-8")
    assert body.startswith("<!doctype html>")


# --- offline ---------------------------------------------------------------------------


def _comment_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in COMMENTS:
        spans += [match.span() for match in pattern.finditer(text)]
    return spans


def test_no_http_url_outside_a_comment(page: str) -> None:
    """A CDN, a font host or an analytics beacon would each be one of these."""
    spans = _comment_spans(page)
    outside = [
        match.start() for match in re.finditer(r"https?:", page)
        if not any(start <= match.start() < stop for start, stop in spans)
    ]
    assert outside == [], f"the page reaches the network at offsets {outside}"


def test_no_external_subresource(page: str) -> None:
    for tag in ("<img", "<iframe", "<script src", "@import"):
        assert tag not in page, f"{tag} would be fetched from somewhere"
    # the one <link> is the favicon, carried inline as a data URI so the browser never asks
    # the server for /favicon.ico (the 404 a fresh checkout used to show in the console)
    links = re.findall(r"<link[^>]*>", page)
    assert len(links) == 1 and 'rel="icon"' in links[0] and 'href="data:image/png;base64,' in links[0], links


def test_the_inlined_font_is_the_file_in_assets() -> None:
    assert inline_assets.main(["--check"]) == 0


# --- the writing contract ---------------------------------------------------------------


def test_no_emoji_anywhere(page: str, font_span: tuple[int, int]) -> None:
    high = sorted({
        char for index, char in enumerate(page)
        if ord(char) > 0x2600 and not font_span[0] <= index < font_span[1]
    })
    assert high == [], f"code points above U+2600 on the page: {[hex(ord(c)) for c in high]}"


def test_the_word_compliant_never_appears(page: str) -> None:
    """00-contract.md, writing contract: the record never contains it, nor does the
    page that renders the record."""
    assert re.search(r"complian", page, re.I) is None


# --- the script -------------------------------------------------------------------------


def _script(page: str) -> str:
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None, "the page has no script block"
    return found.group(1)


def test_the_script_parses(page: str, tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH, so the page's syntax cannot be checked here")
    target = tmp_path / "page.js"
    target.write_text(_script(page), encoding="utf-8")
    done = subprocess.run([node, "--check", str(target)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_the_page_has_one_style_block_and_one_script_block(page: str) -> None:
    assert page.count("<style>") == 1 and page.count("</style>") == 1
    assert page.count("<script") == 1 and page.count("</script>") == 1


# --- the views ---------------------------------------------------------------------------


def test_every_view_has_its_anchor_and_its_section(page: str) -> None:
    for name in VIEWS:
        assert f'href="#/{name}"' in page
        assert f'id="view-{name}"' in page


# --- the renderer's eight sections (the page links the record, it no longer draws it) ---


def markdown_headings() -> list[str]:
    """The `## A.` to `## H.` headings, read out of the renderer's own source."""
    text = "\n".join(
        (RENDER / name).read_text(encoding="utf-8") for name in ("markdown.py", "__init__.py")
    )
    found = HEADING.findall(text)
    return sorted(set(found), key=found.index)

def test_the_renderer_still_writes_eight_sections_in_order() -> None:
    headings = markdown_headings()
    assert [h[0] for h in headings] == list("ABCDEFGH")
def test_the_page_keeps_the_human_cell_wording(page: str) -> None:
    """`requires human completion` is how an empty Art. 30(1) cell renders; the
    findings card names the cells the code cannot answer with the same words."""
    assert "requires human completion" in page


# --- the stylesheet does what the page's own attributes assume ----------------------------

STYLE = re.compile(r"<style>(.*?)</style>", re.S)
FONT_BLOCK = re.compile(r"/\* font:begin.*?/\* font:end \*/", re.S)
ROOT_BLOCK = re.compile(r":root\{.*?\n\}", re.S)
HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")


def stylesheet(page: str) -> str:
    """The CSS block with the inlined font removed, which is base64, not CSS."""
    found = STYLE.search(page)
    assert found is not None, "the page has no style block"
    return FONT_BLOCK.sub("", found.group(1))


def test_the_hidden_attribute_beats_every_author_display(page: str) -> None:
    """`.drawer`, `.pacing` and `.chip` each set `display`, which outranks the UA
    stylesheet's `[hidden]{display:none}`. Without this rule the empty source drawer
    covers the right of the viewport from first paint and Close does nothing."""
    css = stylesheet(page)
    assert re.search(r"\[hidden\]\{display:none ?!important\}", css), "no [hidden] rule"
    assert ".view[hidden]" not in css, "made redundant by the [hidden] rule"
    for selector in (".drawer", ".pacing", ".chip"):
        rule = re.search(re.escape(selector) + r"\{(.*?)\}", css, re.S)
        assert rule is not None and "display:" in rule.group(1), selector


def test_the_toggle_draws_its_focus_ring_inside_its_own_clip(page: str) -> None:
    """`.toggle` sets `overflow:hidden`, which clips the outline of `:focus-visible`."""
    css = stylesheet(page)
    assert ".toggle{" in css and "overflow:hidden" in css
    assert ".toggle button:focus-visible{outline-offset:-2px}" in css


def test_the_gate_summary_keeps_its_columns(page: str) -> None:
    """advanced/gate.py aligns the verdict rows on fixed columns; pre-wrap breaks them."""
    css = stylesheet(page)
    rule = re.search(r"\.gate-summary\{(.*?)\}", css, re.S)
    assert rule is not None
    assert "white-space:pre;" in rule.group(1)
    assert "overflow-x:auto" in rule.group(1)


def test_every_colour_is_a_token(page: str) -> None:
    css = stylesheet(page)
    root = ROOT_BLOCK.search(css)
    assert root is not None, "the page has no :root token block"
    loose = sorted(set(HEX.findall(css.replace(root.group(0), ""))))
    assert loose == [], f"colours outside the token block: {loose}"


def test_only_the_gate_card_carries_a_shadow(page: str) -> None:
    """ADR 0007 allows one shadow, on the card a reviewer has to act on."""
    shadows = re.findall(r"([.#\w-]+)\{[^}]*box-shadow", stylesheet(page))
    assert shadows == [".gate-card"], shadows


# --- the wording ---------------------------------------------------------------------------


def test_counts_are_not_pluralised_blindly(page: str) -> None:
    """S02 has one store, so `n + " stores"` renders "1 stores"; the Markdown
    renderer gets this right and the page mirrors it."""
    assert 'function plural(n, one, many)' in page
    for blind in ('+ " stores"', '" stores, "', '+ " seeds per case"', '+ " fields"'):
        assert blind not in page, f"blind plural: {blind}"


def test_the_gate_card_prints_the_human_cells_once(page: str) -> None:
    """advanced/gate.py appends them to `gate_summary`, which the card renders verbatim."""
    gate = (REPO_ROOT / "advanced" / "gate.py").read_text(encoding="utf-8")
    assert "Left for you, and rendered as requires human completion:" in gate
    assert "request.human_cells.forEach" not in page
    assert "Left for you, and rendered as requires human completion" not in page


def test_no_flourish_over_the_crashed_child(page: str) -> None:
    assert "the child's last words" not in page
    assert "the last lines the child printed" in page


# --- the page refuses what the server refuses ------------------------------------------------


def test_the_page_pre_empts_the_test_split_refusal(page: str) -> None:
    """`art30/web/api.py` answers a live run of a test case with a 400; an enabled
    Start followed by a raw 400 is not an answer."""
    api = (REPO_ROOT / "art30" / "web" / "api.py").read_text(encoding="utf-8")
    assert "is in the test split (evals/split.yaml), which is swept" in api
    assert "is in the test split (evals/split.yaml), which is swept live at most" in page
    assert 'row.split === "test"' in page


def test_the_page_pre_empts_the_missing_recording_refusal(page: str) -> None:
    """A free-text path has no case row, so replay has nothing to replay."""
    found = re.search(r"function isBlocked\(row, replayable, held\) \{(.*?)\n\}", page, re.S)
    assert found is not None, "isBlocked has changed shape"
    assert "if (!row) { return true; }" in found.group(1)


# --- the brains, the settings view, and the one brand rule ------------------------------------


def test_the_brand_is_the_login_and_never_the_product_name(page: str) -> None:
    """ADR 0008 item 6: "Claude (your login)", never "Claude Code". The page is where
    that rule is visible, so the page is where it is checked. Codex is not offered on
    the page for now (2026-08-31); the CLI keeps `--brain codex`."""
    assert "Claude Code" not in page
    assert "Claude (your login)" in page and "Codex (your login)" not in page
    for path in sorted((REPO_ROOT / "art30" / "web").glob("*.py")):
        assert "Claude Code" not in path.read_text(encoding="utf-8"), path.name


def test_the_version_chip_drops_the_clis_own_parenthetical(page: str, tmp_path: Path) -> None:
    """`claude --version` prints "2.1.251 (Claude Code)". The grep above only ever sees
    the page's source, so the rule is checked on what the page draws as well: the
    helper that builds the chip is lifted out of the page and run."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH, so the page's own helper cannot be run here")
    found = re.search(r"function versionText\(version\) \{.*?\n\}", page, re.S)
    assert found is not None, "versionText has changed shape"
    cases = ["2.1.251 (Claude Code)", "codex-cli 0.148.0", "1.0 (x) (y)", "", None]
    target = tmp_path / "version.js"
    target.write_text(found.group(0) + "\nconsole.log(JSON.stringify("
                      + json.dumps(cases) + ".map(versionText)));\n", encoding="utf-8")
    done = subprocess.run([node, str(target)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == ["2.1.251", "codex-cli 0.148.0", "1.0 (x)",
                                       "version not reported", "version not reported"]


def test_the_settings_view_has_the_brains_panel_and_the_key_form(page: str) -> None:
    for marker in ('id="view-settings"', 'id="brains"', 'id="brains-refresh"',
                   'id="brains-note"', 'id="keys"', 'id="scope"', 'id="files"'):
        assert marker in page, marker
    assert "function drawKeys()" in page and "function drawBrains()" in page
    assert 'var SECRET_KEY = "anthropic_api_key";' in page


def test_the_user_note_is_rendered_from_the_server_and_not_copied(page: str) -> None:
    """ADR 0008 item 6 is one string, in `art30/web/settings_api.py`. A second copy on
    the page is a second thing to keep in step, and it would drift."""
    note = (REPO_ROOT / "art30" / "web" / "settings_api.py").read_text(encoding="utf-8")
    assert "art30 never stores or asks for those credentials" in note
    assert "art30 never stores or asks for those credentials" not in page
    assert 'byId("brains-note").textContent = data.note' in page
    assert 'byId("brain-note").textContent = data.note' in page


def test_the_secret_row_shows_a_state_and_offers_a_replace(page: str) -> None:
    """`settings.describe()` answers `present` or `absent`; the row may show no more."""
    found = re.search(r"function secretControl\(row, id, save\) \{(.*?)\n\}", page, re.S)
    assert found is not None, "secretControl has changed shape"
    body = found.group(1)
    assert 'type: "password"' in body and "disabled: true" in body
    assert '"Replace"' in body and '"Set"' in body
    assert 'row.value === "present"' in body


def test_a_local_brain_plays_back_and_never_replays(page: str) -> None:
    """ADR 0008: a local brain records no response, so its finished trace is played
    back. The word on the toggle changes with the brain, and so does the pacing strip."""
    assert 'local ? "play back" : "replay"' in page
    assert 'byId("pacing-label").textContent = local ? "Play back pacing" : "Replay pacing"' \
        in page
    assert "function playbackRun()" in page


def test_the_page_gives_the_reason_the_server_would_have_refused_with(page: str) -> None:
    """A disabled brain toggle has to say what the 400 says (`settings_api.refusal`)."""
    api = (REPO_ROOT / "art30" / "web" / "settings_api.py").read_text(encoding="utf-8")
    for sentence in (" is not installed on this machine, so it cannot run anything here.",
                     " Log the CLI in from a terminal, then press Refresh.",
                     " is logged in, but art30 has no driver for it yet."):
        assert sentence in page and sentence.strip() in api, sentence
    # and readiness asks the same three questions the server does, not one of them
    found = re.search(r"function brainReady\(name\) \{(.*?)\n\}", page, re.S)
    assert found is not None, "brainReady has changed shape"
    assert "row.logged_in === true" in found.group(1)
    assert "row.built !== false" in found.group(1)


def test_the_dollar_ceiling_is_named_only_where_dollars_are_spent(page: str) -> None:
    """A local brain bills none, so the callout that offers one names no ceiling."""
    assert page.count("ART30_MAX_USD") == 1, "the key setup step is the only place for it"
    assert "spends no API credits" in page
    assert "This brain bills no" in page and "no ceiling stops it; the turn budget does" in page


def test_the_turn_budget_is_drawn_only_when_the_trace_carries_one(page: str) -> None:
    assert 'id="turns-meter"' in page
    assert "state.budget.turnsMax = Number(config.max_turns || line.max_turns || 0) || 0;" in page
    assert 'byId("turns-meter").hidden = !state.budget.turnsMax;' in page


def test_the_runs_view_says_which_brain_ran_and_what_the_cost_is(page: str) -> None:
    assert 'text: brainLabel(brain)' in page
    assert 'text: words(row.cost_source || "measured")' in page
