"""Helpers shared by the venue parsers."""

from __future__ import annotations

import re
from decimal import Decimal

_SCALE = {"": 1, "K": 10**3, "M": 10**6, "B": 10**9}


def percent(text: str) -> Decimal:
    """'0.045%' -> Decimal('0.00045')."""
    return Decimal(text.strip().rstrip("%").replace(",", "")) / 100


def amount(text: str) -> Decimal:
    """'>5M' -> 5000000, '' -> 0, '>$1,000' -> 1000."""
    t = text.strip().lstrip(">≥").lstrip("$").replace(",", "").strip()
    if not t:
        return Decimal(0)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMB]?)", t, re.I)
    if not m:
        raise ValueError(f"not an amount: {text!r}")
    return Decimal(m.group(1)) * _SCALE[m.group(2).upper()]


def section(text: str, heading: str) -> str | None:
    """Text from a markdown heading to the next heading of any level, or None."""
    m = re.search(r"(^|\s)#{1,6}\s+" + re.escape(heading) + r"\s", text)
    if not m:
        return None
    rest = text[m.end() :]
    nxt = re.search(r"(^|\s)#{1,6}\s+\S", rest)
    return rest[: nxt.start()] if nxt else rest
