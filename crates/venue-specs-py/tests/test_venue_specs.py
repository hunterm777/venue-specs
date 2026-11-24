"""Python API tests, including the shared fee fixtures in tests/fixtures/fees.json."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest
import venue_specs as vs

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "fees.json"
CASES = json.loads(FIXTURES.read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_fee_fixtures(case: dict) -> None:
    rows = {r.rsplit(".", 2)[1]: r.rsplit(".", 1)[1] for r in case["rows"]}
    kwargs = {"category" if t == "categories" else "tier": k for t, k in rows.items()}
    call = lambda: vs.evaluate(case["venue"], case["product"], case["path"], at=case["at"], **kwargs, **case["inputs"])
    expect = case.get("expect_error")
    if expect == "unverified":
        with pytest.raises(vs.UnverifiedError):
            call()
    elif expect == "not_found":
        with pytest.raises(vs.NotFoundError):
            call()
    else:
        got = call()
        assert isinstance(got, Decimal)
        assert got == Decimal(case["expected"])


def test_prd_call_shapes() -> None:
    k = vs.spec_at("kalshi", "binary", "2026-08-19")
    assert k["venue"] == "kalshi" and k["product"] == "binary"
    # The PRD's example names a category the fees page does not have.
    with pytest.raises(vs.NotFoundError):
        vs.fee("polymarket", "binary", category="crypto_btc_15m", contracts=100, price=0.5)
    assert vs.fee("polymarket", "binary", category="sports", contracts=100, price=0.5) == Decimal("1.25")


def test_floats_and_ints_are_exact() -> None:
    got = vs.fee("polymarket", "binary", category="crypto", at="2026-11-24", C=100, P=0.5)
    assert got == Decimal("1.75")
    got = vs.fee("polymarket", "binary", category="crypto", at="2026-11-24", C=Decimal("100"), P="0.50")
    assert got == Decimal("1.75")


def test_history_by_date_and_datetime() -> None:
    def liq(at: object) -> Decimal:
        return vs.spec_at("polymarket", "perp", at)["fees"]["liquidation_fee"]["value"]  # type: ignore[arg-type]

    assert liq("2026-11-24") == Decimal("0.005")
    assert liq(dt.date(2026, 11, 25)) == Decimal("0.01")
    assert liq(dt.datetime(2026, 11, 24, 23, 59, tzinfo=dt.timezone.utc)) == Decimal("0.005")
    assert liq(dt.datetime(2026, 11, 24, 19, 0, tzinfo=dt.timezone(dt.timedelta(hours=-5)))) == Decimal("0.01")
    with pytest.raises(vs.VenueSpecsError):
        liq(dt.datetime(2026, 11, 25))
    with pytest.raises(vs.VenueSpecsError):
        liq("tomorrow")


def test_spec_and_bundle() -> None:
    b = vs.bundle()
    assert b["version"] == vs.__version__
    assert len(b["specs"]) == 6
    s = vs.spec("hyperliquid", "perp")
    assert s["fees"]["tiers"]["0"]["taker"]["value"] == Decimal("0.00045")
    assert s["fees"]["tiers"]["0"]["taker"]["source"].startswith("https://")
    with pytest.raises(vs.NotFoundError):
        vs.spec("kalshi", "option")


def test_errors_are_value_errors() -> None:
    with pytest.raises(ValueError):
        vs.fee("kalshi", "binary", C=1, P=0.5)
    with pytest.raises(vs.VenueSpecsError):
        vs.fee("hyperliquid", "perp", tier=0, notional=object())  # type: ignore[arg-type]
    with pytest.raises(vs.VenueSpecsError):
        vs.fee("hyperliquid", "perp", tier=0, notional="ten")


def test_bool_inputs() -> None:
    got = vs.evaluate(
        "hyperliquid",
        "perp",
        "asset_classes.hip3.taker_fee",
        at="2026-11-24",
        tier=0,
        N=10_000,
        deployer_fee_scale=1,
        growth_mode=True,
    )
    assert got == Decimal("0.9")
