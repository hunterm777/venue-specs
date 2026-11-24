"""Kalshi parsers.

Kalshi announces rule changes in changelog prose and in its fee schedule PDF, so most Kalshi
sources have no parser: a change opens an issue quoting the diff (the PRD's default, no LLM
extraction). The fixed-point page states the contract size step in one sentence, read here.
"""

from __future__ import annotations

import re
from decimal import Decimal

from ..model import ParseResult, Proposal, Source

_STEP = re.compile(r"Minimum granularity is\s+([\d.]+)\s+contracts", re.I)


def fixed_point(text: str, src: Source) -> ParseResult:
    """size.step from 'Minimum granularity is 0.01 contracts'."""
    out = ParseResult()
    if m := _STEP.search(text):
        out.proposals.append(Proposal("kalshi", "binary", "size.step", src.url, value=Decimal(m.group(1))))
    else:
        out.problems.append("fixed point: 'Minimum granularity is ... contracts' not found")
    return out
