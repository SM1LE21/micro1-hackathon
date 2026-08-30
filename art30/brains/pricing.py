"""Cost for a local brain: an estimate at API list prices, never a measurement.

`claude -p` reports token counts per assistant message and a `total_cost_usd` of
its own. Neither is a bill: a subscription run costs no dollars. ADR 0008 item 3
therefore reports the estimate and labels it `cost_source: "cli_estimate"`, and
carries the CLI's own number beside it as `cli_total_cost_usd`.

The prices are `art30.llm`'s table, imported rather than repeated, so a run's
dollars mean the same thing whichever brain produced it. `ALIASES` only maps the
names the CLI answers with onto that table's keys: the CLI may report a family
member (`claude-opus-4-8`), the short alias a user typed (`opus`), or the same
model with its context window appended (`claude-opus-5[1m]`). A model with
no entry prices to `None`, which the trace and the report print as "n/a" rather
than as a guess.
"""

from __future__ import annotations

import re
from typing import Mapping

from art30 import llm

# Same list prices, different id. The Opus family bills $5/$25 per MTok, Sonnet
# $2/$10, Haiku $1/$5; `claude-sonnet-4-6` is $3/$15 and has no entry, so a run on
# it reports tokens and no dollars instead of the wrong dollars.
ALIASES: dict[str, str] = {
    "opus": "claude-opus-5",
    "sonnet": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5",
    "claude-opus-4-8": "claude-opus-5",
    "claude-opus-4-7": "claude-opus-5",
    "claude-opus-4-6": "claude-opus-5",
    "claude-haiku-4-5": "claude-haiku-4-5",
}
DATED = re.compile(r"-20\d{6}\Z")   # a dated snapshot prices as its family
# `claude-opus-5[1m]` is the 1M-context window of `claude-opus-5`. The CLI's init
# line reports the suffixed name and the per-message `model` field usually does not,
# so without this a run priced or did not price depending on which field was read.
WINDOW = re.compile(r"\[[0-9]+[km]\]\Z")
# A one-hour cache write costs twice the input price; `llm.prices` carries the
# five-minute rate (1.25x), which is the one the API brain writes at.
CACHE_1H_MULTIPLIER = 2.0


def table() -> dict[str, tuple[float, float, float, float]]:
    """`{model: (input, output, cache_write, cache_read)}` in USD per million tokens."""
    out: dict[str, tuple[float, float, float, float]] = {}
    for model in llm._IO_USD_PER_MTOK:
        price = llm.prices(model)
        out[model] = (price["input"], price["output"], price["cache_write"], price["cache_read"])
    return out


def resolve(model: str | None) -> str | None:
    """The table key for what the CLI called the model, or None when it has none."""
    if not model:
        return None
    name = WINDOW.sub("", str(model).strip().lower())
    if name in llm._IO_USD_PER_MTOK:
        return name
    if name in ALIASES:
        return ALIASES[name]
    stripped = DATED.sub("", name)
    if stripped in llm._IO_USD_PER_MTOK:
        return stripped
    return ALIASES.get(stripped)


def priced(model: str | None) -> bool:
    """Whether a dollar figure can be put on a run made with `model`.

    `None` is the CLI's own default, which no layer has named yet: it is answered
    optimistically here and settled by `driver._cost_source` once a step has been
    priced or failed to be. A named model is priced when this table knows it or
    when the user put it in `codex_prices`.
    """
    if model is None:
        return True
    return resolve(model) is not None or str(model).strip().lower() in codex_prices()


def estimate(usage: Mapping[str, int], model: str | None, cache_1h: int = 0) -> float | None:
    """Dollars at list prices for one message's token counts, or None.

    `cache_1h` is the part of `cache_write` the CLI wrote at the one-hour TTL, which
    Claude Code uses for every prefix it caches. A one-hour write is twice the input
    price where the five-minute write `art30.llm` prices is 1.25 times it, and on a
    scan the cache write is most of the bill: pricing the whole of it at the shorter
    TTL is what made this estimate read $0.36 against the CLI's own $0.76 on the
    first D02 run (the scratch copy of that run's stream is the evidence).
    """
    key = resolve(model)
    if key is None:
        # Not an Anthropic model this table knows. It may still be a `codex` one the
        # user has priced; `codex_estimate` answers None when it is not, and the
        # driver then records the run `unpriced` rather than free.
        return codex_estimate(usage, model)
    hourly = max(0, min(int(cache_1h or 0), int(usage.get("cache_write", 0) or 0)))
    short = {**dict(usage), "cache_write": int(usage.get("cache_write", 0) or 0) - hourly}
    price = llm.prices(key)["input"] * CACHE_1H_MULTIPLIER
    return round(llm.cost_of(short, key) + hourly * price / 1_000_000, 6)


# --- codex ------------------------------------------------------------------------------------
# The `codex` brain reports tokens and nothing else: no price, no `total_cost_usd`,
# no model name in its event stream. There is no list price this repository could
# hard-code without inventing one, so a codex run is unpriced -- tokens and "n/a" --
# until the user puts a price in `codex_prices` (ADR 0008 item 3).
#
#     codex_prices = '{"gpt-5-codex": [1.25, 0.125, 10.0]}'
#
# Three numbers are `[input, cached_input, output]` in dollars per million tokens,
# which is how OpenAI publishes them and what `art30/settings.py` and
# `docs/settings.md` both document. Two are accepted and read as `[input, output]`,
# with cached input at the input rate, which overstates rather than flatters.
# `cache_write` has no rate of its own on that provider and prices as input; the
# tokens it counts are already inside what codex reported as input, so
# `codex_events.usage_of` takes them out of `input` before either is priced.
CODEX_PRICES_KEY = "codex_prices"


def codex_prices(values: Mapping[str, object] | None = None) -> dict[str, tuple[float, float, float]]:
    """`{model: (input, cached_input, output)}` USD/MTok from the settings layer.

    A malformed entry is dropped rather than raised: an unusable price makes the run
    unpriced, and a settings file must not be able to kill a scan that is under way.
    """
    raw = _codex_setting() if values is None else values
    table: dict[str, tuple[float, float, float]] = {}
    for name, price in (raw or {}).items():
        triple = _triple(price)
        if triple is not None:
            table[str(name).strip().lower()] = triple
    return table


def _codex_setting() -> Mapping[str, object]:
    from art30 import settings   # late: `settings` is read per run, not per import

    try:
        return settings.read().values.get(CODEX_PRICES_KEY) or {}
    except (ValueError, OSError):   # a broken settings file leaves the run unpriced
        return {}


def _triple(price: object) -> tuple[float, float, float] | None:
    if not isinstance(price, (list, tuple)):
        return None
    try:
        numbers = [float(x) for x in price if not isinstance(x, bool)]
    except (TypeError, ValueError):
        return None
    if len(numbers) != len(price) or any(x < 0 for x in numbers):
        return None
    if len(numbers) == 3:
        return (numbers[0], numbers[1], numbers[2])
    if len(numbers) == 2:
        return (numbers[0], numbers[0], numbers[1])
    return None


def codex_estimate(usage: Mapping[str, int], model: str | None,
                   table: Mapping[str, tuple[float, float, float]] | None = None) -> float | None:
    """Dollars for one step's tokens at the configured codex price, or None."""
    prices = codex_prices() if table is None else table
    entry = prices.get(str(model or "").strip().lower())
    if entry is None:
        return None
    inp, cached, out = entry
    return round((
        int(usage.get("input", 0) or 0) * inp
        + int(usage.get("cache_read", 0) or 0) * cached
        + int(usage.get("cache_write", 0) or 0) * inp
        + int(usage.get("output", 0) or 0) * out
    ) / 1_000_000, 6)
