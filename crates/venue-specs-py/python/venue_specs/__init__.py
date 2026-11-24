"""Versioned, sourced trading rules for Kalshi, Polymarket and Hyperliquid.

The data is embedded in the package; nothing here makes a network call. Numbers come back
as :class:`decimal.Decimal`, never ``float``. A value that has not been read from a source
raises :class:`UnverifiedError` instead of returning a guess.

>>> import venue_specs as vs
>>> vs.fee("hyperliquid", "perp", tier="0", notional=10_000, at="2026-11-24")
Decimal('4.50000')
"""

from __future__ import annotations

import datetime as _dt
import json as _json
from decimal import Decimal
from typing import Any

from . import _venue_specs as _native
from ._venue_specs import NotFoundError, UnverifiedError, VenueSpecsError

__all__ = [
    "NotFoundError",
    "UnverifiedError",
    "VenueSpecsError",
    "__version__",
    "bundle",
    "evaluate",
    "fee",
    "spec",
    "spec_at",
]

__version__: str = _native.version()

Number = Decimal | int | float | str | bool
When = str | _dt.date | _dt.datetime | None

_ROWS = {"category": "fees.categories", "tier": "fees.tiers"}


def _loads(text: str) -> Any:
    return _json.loads(text, parse_float=Decimal, parse_int=Decimal)


def _when(at: When) -> str | None:
    if at is None or isinstance(at, str):
        return at
    if isinstance(at, _dt.datetime):
        if at.tzinfo is None:
            raise VenueSpecsError("datetime must be timezone-aware; venue rules change at UTC instants")
        return at.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(at, _dt.date):
        return at.isoformat()
    raise VenueSpecsError(f"at must be a date, datetime or string, not {type(at).__name__}")


def _number(name: str, value: Number) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (Decimal, int)):
        return str(value)
    if isinstance(value, float):
        # repr gives the shortest decimal that round-trips, so 0.5 stays 0.5.
        return repr(value)
    if isinstance(value, str):
        return value
    raise VenueSpecsError(f"input {name} must be a number, not {type(value).__name__}")


def bundle() -> dict[str, Any]:
    """Everything in ``venue-specs.json``: specs and history."""
    out: dict[str, Any] = _loads(_native.bundle_json())
    return out


def spec(venue: str, product: str) -> dict[str, Any]:
    """The spec file as written, including announced values not yet in force."""
    out: dict[str, Any] = _loads(_native.spec_json(venue, product))
    return out


def spec_at(venue: str, product: str, at: When = None) -> dict[str, Any]:
    """The rules in force at ``at`` (a date means the start of that UTC day); now when omitted."""
    out: dict[str, Any] = _loads(_native.spec_at_json(venue, product, _when(at)))
    return out


def evaluate(
    venue: str,
    product: str,
    path: str,
    *,
    at: When = None,
    category: str | None = None,
    tier: str | int | None = None,
    **inputs: Number,
) -> Decimal:
    """Evaluate the value or formula at ``path``, such as ``"margin.maintenance_margin_rate"``.

    ``inputs`` are the formula's names, for example ``C`` and ``P``, or the aliases
    ``contracts``, ``price``, ``quantity`` and ``notional``. ``category`` and ``tier``
    select a row of the venue's fee table.
    """
    rows = [f"{_ROWS[k]}.{v}" for k, v in (("category", category), ("tier", tier)) if v is not None]
    values = {k: _number(k, v) for k, v in inputs.items()}
    return Decimal(_native.evaluate(venue, product, path, _when(at), values, rows))


def fee(
    venue: str,
    product: str,
    side: str = "taker",
    *,
    at: When = None,
    category: str | None = None,
    tier: str | int | None = None,
    **inputs: Number,
) -> Decimal:
    """The fee for one fill, ``fees.<side>.fee``, in the rules in force at ``at`` (now when omitted)."""
    return evaluate(venue, product, f"fees.{side}.fee", at=at, category=category, tier=tier, **inputs)
