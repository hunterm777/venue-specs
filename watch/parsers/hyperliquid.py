"""Hyperliquid parsers. The docs are GitBook pages fetched as Markdown; fee tables and the
funding constants are read deterministically. Anything the parser expects and cannot find is
reported as a problem, and nothing is proposed from that table."""

from __future__ import annotations

import re
from decimal import Decimal

from ..model import ParseResult, Proposal, Source
from .common import amount, percent, section

# | 0 | | 0.045% | 0.015% | ...   and   | 1 | >5M | 0.040% | 0.012% | ...
_TIER_ROW = re.compile(r"\|\s*(\d)\s*\|\s*(>?\s*\$?[\d.,]*\s*[KMB]?)\s*\|\s*(-?[\d.]+)%\s*\|\s*(-?[\d.]+)%\s*\|")
# | 1 | >0.5% | -0.001% |
_REBATE_ROW = re.compile(r"\|\s*(\d)\s*\|\s*>\s*([\d.]+)%\s*\|\s*(-?[\d.]+)%\s*\|")
TIERS = 7
REBATE_TIERS = 3


def fees(text: str, src: Source) -> ParseResult:
    """Perps fee tiers (base rate columns) and maker rebate tiers."""
    out = ParseResult()

    def put(path: str, value: object) -> None:
        out.proposals.append(Proposal("hyperliquid", "perp", path, src.url, value=value))

    perps = section(text, "Perps fee tiers")
    rows = [m.groups() for m in _TIER_ROW.finditer(perps or "")]
    if [int(r[0]) for r in rows] != list(range(TIERS)):
        out.problems.append(f"perps fee tier table: expected tiers 0-{TIERS - 1}, found {[r[0] for r in rows]}")
    else:
        for tier, volume, taker, maker in rows:
            put(f"fees.tiers.{tier}.min_14d_weighted_volume", amount(volume))
            put(f"fees.tiers.{tier}.taker", percent(taker))
            put(f"fees.tiers.{tier}.maker", percent(maker))

    rebates = section(text, "Maker rebates")
    rows = [m.groups() for m in _REBATE_ROW.finditer(rebates or "")]
    if [int(r[0]) for r in rows] != list(range(1, REBATE_TIERS + 1)):
        out.problems.append(f"maker rebate table: expected tiers 1-{REBATE_TIERS}, found {[r[0] for r in rows]}")
    else:
        for tier, share, maker in rows:
            put(f"fees.maker_rebates.{tier}.min_14d_maker_volume_share", percent(share))
            put(f"fees.maker_rebates.{tier}.maker", percent(maker))
    return out


_INTEREST = re.compile(r"interest rate component is predetermined at\s+([\d.]+)%\s+every 8 hours", re.I)
_CLAMP = re.compile(r"clamp\s*\(\s*interest rate\s*-\s*Premium Index \(P\)\s*,\s*-([\d.]+)\s*,\s*([\d.]+)\s*\)", re.I)
_CAP = re.compile(r"Funding on Hyperliquid is capped at\s+([\d.]+)%\s*/\s*hour", re.I)


def funding(text: str, src: Source) -> ParseResult:
    """The fixed interest rate, the premium clamp and the hourly cap."""
    out = ParseResult()

    def put(path: str, value: object) -> None:
        out.proposals.append(Proposal("hyperliquid", "perp", path, src.url, value=value))

    if m := _INTEREST.search(text):
        put("funding.interest_rate_8h", percent(m.group(1)))
    else:
        out.problems.append("funding: interest rate sentence not found")
    if (m := _CLAMP.search(text)) and m.group(1) == m.group(2):
        put("funding.premium_clamp", Decimal(m.group(2)))
    else:
        out.problems.append("funding: clamp bounds in the funding formula not found or not symmetric")
    if m := _CAP.search(text):
        put("funding.cap_per_hour", percent(m.group(1)))
    else:
        out.problems.append("funding: hourly cap sentence not found")
    return out
