"""Polymarket parsers.

The Perps changelog states per-market tick and size step changes in two fixed phrasings, read
here: a maintenance-window change ("ANT and INTC tick size. During the maintenance window, both
markets move to 3 quantity decimals and 3 price decimals: a 0.001 size step and a 0.001 price
tick.") and a stock split ("SNDK 8-for-1 split. Trading pauses ... and resumes ... SNDK moves to
the 0.001 tick and size step at the same time."). An entry that mentions a tick size change in any
other wording is reported as a problem, so the watcher opens an issue instead of guessing.

Fee and margin changes appear in the changelog as prose, so they are not read from it (the PRD's
default, no LLM extraction); the page change opens an issue.

The Perps fees, funding and margin pages are read from their tables and formula lines. The pages
were checked from copies of the rendered pages, so the text is read with Markdown marks and line
breaks removed; anything a parser expects and cannot find is reported, and nothing is proposed from
it. Other Polymarket pages have no parser yet: their layouts have not been checked.
"""

from __future__ import annotations

import re
from decimal import Decimal

from ..model import ParseResult, Proposal, Source
from .common import amount, percent

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_FULL = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
# An entry heading: "Nov 19, 2026"
_HEADING = re.compile(r"\b(" + "|".join(_MONTHS) + r") (\d{1,2}), (\d{4})\b")
_MARKETS = r"[A-Z][A-Z0-9]{1,9}(?:(?:,\s*|,?\s+and\s+)[A-Z][A-Z0-9]{1,9})*"
_UTC_AT = r"\w+, (" + "|".join(_FULL) + r") (\d{1,2}) at [^()]{0,40}\((\d{1,2}):(\d{2}) UTC"
# "ANT and INTC tick size. During the maintenance window, both markets move to 3 quantity decimals
# and 3 price decimals: a 0.001 size step and a 0.001 price tick."
_WINDOW = re.compile(
    r"(" + _MARKETS + r") tick sizes?\. During the maintenance window, [\w ]{1,30}? moves? to "
    r"\d+ quantity decimals and \d+ price decimals: an? ([\d.]+) size step and an? ([\d.]+) price tick\."
)
_WINDOW_START = re.compile(r"Maintenance starts " + _UTC_AT)
# "SNDK 8-for-1 split. Trading pauses ... and resumes Friday, November 20 at 8:00 AM ET (13:00 UTC),
# ... SNDK moves to the 0.001 tick and size step at the same time."
_SPLIT = re.compile(
    r"\b([A-Z][A-Z0-9]{1,9}) \d+-for-\d+ split\. Trading pauses .{0,200}? and resumes " + _UTC_AT + r".{0,300}?"
    r"\b\1 moves to the ([\d.]+) tick and size step\b"
)
_MENTIONS_TICK = re.compile(r"\btick[- ](?:size|change)", re.I)


def _instant(heading: str, month: str, day: str, hour: str, minute: str) -> str:
    """A time named in an entry, in the entry's year (the next year if its month is earlier)."""
    head = _HEADING.match(heading)
    assert head is not None
    year = int(head.group(3)) + (_FULL.index(month) < _MONTHS.index(head.group(1)))
    return f"{year}-{_FULL.index(month) + 1:02d}-{int(day):02d}T{int(hour):02d}:{minute}:00Z"


def _entries(text: str) -> list[tuple[str, str]]:
    """(heading, body) for each dated entry, newest first as on the page."""
    flat = " ".join(text.split())
    marks = list(_HEADING.finditer(flat))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(flat)
        out.append((m.group(0), flat[m.end() : end]))
    return out


def _markets(names: str) -> list[str]:
    return [n for n in re.split(r",\s*|\s+and\s+", names.replace(", and ", ", ")) if n]


def perps_changelog(text: str, src: Source) -> ParseResult:
    """Per-market tick (price_grid.markets.<M>.tick) and size step (size.markets.<M>.step).

    The newest entry for each market wins, so re-reading the whole page proposes each market's
    current values only."""
    out = ParseResult()
    seen: set[str] = set()

    def put(market: str, tick: str, step: str, starts: str, note: str) -> None:
        if market in seen:
            return
        seen.add(market)
        for path, value in ((f"price_grid.markets.{market}.tick", tick), (f"size.markets.{market}.step", step)):
            out.proposals.append(
                Proposal("polymarket", "perp", path, src.url, value=Decimal(value), effective_from=starts, note=note)
            )

    entries = _entries(text)
    if not entries:
        out.problems.append("perps changelog: no dated entries ('Mon D, YYYY') found")
    for heading, body in entries:
        found = 0
        for m in _WINDOW.finditer(body):
            names, step, tick = m.groups()
            start = _WINDOW_START.search(body)
            if not start:
                out.problems.append(f"{heading}: tick change for {names} without a 'Maintenance starts ... UTC' time")
                continue
            starts = _instant(heading, *start.groups())
            for market in _markets(names):
                put(market, tick, step, starts, f"Set in the {heading} maintenance window, which started {starts}.")
                found += 1
        for m in _SPLIT.finditer(body):
            market, month, day, hour, minute, size = m.groups()
            starts = _instant(heading, month, day, hour, minute)
            put(market, size, size, starts, f"Set by the stock split in the {heading} entry; trading resumed {starts}.")
            found += 1
        if not found and _MENTIONS_TICK.search(body):
            out.problems.append(f"{heading}: mentions a tick size change in a wording this parser does not read")
    return out


def _plain(text: str) -> str:
    """Page text with Markdown table pipes, emphasis, code marks and escapes removed and
    whitespace collapsed, so a rendered copy and the fetched .md read the same."""
    text = text.replace("\\_", "_").replace("\\*", "*").replace("±", "+/-")
    text = re.sub(r"[|`]|\*\*", " ", text)
    return " ".join(text.split())


_FEE_FORMULA = re.compile(r"Fee = abs\(Price \* Quantity\) \* Rate\b")
_FEE_HEADER = re.compile(r"30-Day Volume\s*(?:≥|>=)\s*Taker\s+Maker\b")
_FEE_ROW = re.compile(r"\$\s*(\d[\d,.]*\s*[KMB]?)\s+(-?[\d.]+)%\s+(-?[\d.]+)%")
FEE_TIERS = 7


def perps_fees(text: str, src: Source) -> ParseResult:
    """The Perps fee tier table (rates in force today) and the fee formula sentence."""
    out = ParseResult()
    flat = _plain(text)
    if not _FEE_FORMULA.search(flat):
        out.problems.append("perps fees: 'Fee = abs(Price * Quantity) * Rate' not found")
    head = _FEE_HEADER.search(flat)
    rows = [m.groups() for m in _FEE_ROW.finditer(flat[head.end() : head.end() + 600])] if head else []
    if len(rows) < FEE_TIERS:
        out.problems.append(f"perps fee tier table: expected {FEE_TIERS} rows, found {len(rows)}")
        return out
    for tier, (volume, taker, maker) in enumerate(rows[:FEE_TIERS]):
        for path, value in (("min_30d_volume", amount(volume)), ("taker", percent(taker)), ("maker", percent(maker))):
            out.proposals.append(Proposal("polymarket", "perp", f"fees.tiers.{tier}.{path}", src.url, value=value))
    return out


_PM = r"(?:\+/-)"
_FUNDING = {
    "funding.sample_interval_seconds": re.compile(r"premium index is sampled from the order book every (\d+) seconds"),
    "funding.impact_notional": re.compile(r"bid_impact = VWAP of top bids filling ([\d,]+) quote notional"),
    "funding.interval_hours": re.compile(r"The charge window is (\d+) hours?\b"),
    "funding.cap_per_hour": re.compile(r"FR_hour = clamp\(F_8h / 8, " + _PM + r"([\d.]+)\)"),
}
_SCALE = re.compile(r"scale = ([\d.]+) for crypto markets; ([\d.]+) otherwise")
_F8H = re.compile(r"F_8h = scale \* \(mean_P \+ clamp\(([\d.]+) - mean_P, " + _PM + r"([\d.]+)\)\)")


def perps_funding(text: str, src: Source) -> ParseResult:
    """Funding constants: sample interval, impact notional, charge window, interest leg,
    clamp, hourly cap and the crypto / non-crypto scale."""
    out = ParseResult()
    flat = _plain(text)

    def put(path: str, value: Decimal) -> None:
        out.proposals.append(Proposal("polymarket", "perp", path, src.url, value=value))

    for path, rx in _FUNDING.items():
        if m := rx.search(flat):
            put(path, Decimal(m.group(1).replace(",", "")))
        else:
            out.problems.append(f"perps funding: {path} not found ({rx.pattern})")
    if m := _F8H.search(flat):
        put("funding.interest_rate_8h", Decimal(m.group(1)))
        put("funding.premium_clamp", Decimal(m.group(2)))
    else:
        out.problems.append("perps funding: the F_8h formula not found")
    if m := _SCALE.search(flat):
        put("asset_classes.crypto.funding_scale", Decimal(m.group(1)))
        put("asset_classes.other.funding_scale", Decimal(m.group(2)))
    else:
        out.problems.append("perps funding: 'scale = ... for crypto markets; ... otherwise' not found")
    return out


_MMR = re.compile(r"MMR = ([\d.]+) / MaxLeverage\b")
_IM = re.compile(r"IM = Notional / Leverage\b")


def perps_margin(text: str, src: Source) -> ParseResult:
    """The maintenance margin rate rule (MMR = k / MaxLeverage) and the initial margin rule."""
    out = ParseResult()
    flat = _plain(text)
    if m := _MMR.search(flat):
        out.proposals.append(
            Proposal(
                "polymarket", "perp", "margin.maintenance_margin_rate", src.url, formula=f"{m.group(1)} / max_leverage"
            )
        )
    else:
        out.problems.append("perps margin: 'MMR = ... / MaxLeverage' not found")
    if not _IM.search(flat):
        out.problems.append("perps margin: 'IM = Notional / Leverage' not found")
    return out
