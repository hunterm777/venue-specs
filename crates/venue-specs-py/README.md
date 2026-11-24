# venue-specs (Python)

Versioned, sourced trading rules for Kalshi, Polymarket and Hyperliquid: fee formulas, tick grids, margin, funding and settlement. Every value carries the page it was read from and the date it was read. The data is embedded; nothing here makes a network call.

```python
import venue_specs as vs

vs.fee("hyperliquid", "perp", tier="0", notional=10_000, at="2026-11-24")  # Decimal('4.50000')
vs.fee("polymarket", "binary", category="sports", contracts=100, price=0.5)  # Decimal('1.25')
vs.spec_at("polymarket", "perp", "2026-11-24")["fees"]["liquidation_fee"]  # the rule in force that day
vs.evaluate("hyperliquid", "perp", "margin.maintenance_margin_rate", max_leverage=20)  # Decimal('0.025')
```

Numbers are `decimal.Decimal`. A value that has not been read from a source raises `venue_specs.UnverifiedError`; a missing row or path raises `venue_specs.NotFoundError`. Both are `ValueError`s.

See the [repository](https://github.com/hunterm777/venue-specs) for the schema, formula grammar, sources and changelog.
