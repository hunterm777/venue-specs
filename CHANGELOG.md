# Changelog

Written by the weekly watcher (`watch/run.py`). Entries are dated by the day a change was detected
and say when it takes effect at the venue. Entry types: Changed, Added, Removed, Upcoming
(announced, not yet in force) and Docs-only (a watched page changed, no spec value affected).

## 2026-11-24

### Hyperliquid — outcome
- Added: first spec, 16 sourced values, 2 unverified (tick and size decimals are not documented)
  Source: https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-4-outcome-markets.md
  Spec: specs/hyperliquid/outcome.yaml

### Hyperliquid — perp
- Added: first spec, 67 sourced values
  Source: https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees.md
  Spec: specs/hyperliquid/perp.yaml

### Kalshi — binary
- Added: first spec, 15 sourced values, 7 unverified (fee schedule not readable when written)
  Source: https://docs.kalshi.com/getting_started/fee_rounding.md
  Spec: specs/kalshi/binary.yaml

### Kalshi — perp
- Added: first spec, 3 sourced values, 12 unverified (help center and fee schedule not readable when written)
  Source: https://docs.kalshi.com/changelog.md
  Spec: specs/kalshi/perp.yaml

### Polymarket — binary
- Added: first spec, 27 sourced values, 6 unverified
  Source: https://docs.polymarket.com/trading/fees.md
  Spec: specs/polymarket/binary.yaml

### Polymarket — perp
- Added: first spec, 26 sourced values, 8 unverified
  Source: https://docs.polymarket.com/perps/fee-and-liquidity-reward-changes-november-2026.md
  Spec: specs/polymarket/perp.yaml
- Upcoming: fee tiers 0, 1, 2, 5 and 6 and the liquidation fee (0.5% -> 1%) change (takes effect 2026-11-25)
  Source: https://docs.polymarket.com/perps/fee-and-liquidity-reward-changes-november-2026.md
  Spec: specs/polymarket/perp.yaml → fees
- Added: tick and size step of 0.001 for ANT and INTC (in force from 2026-11-19 11:00 UTC) and SNDK (from 2026-11-20 13:00 UTC)
  Source: https://docs.polymarket.com/changelog/perps
  Spec: specs/polymarket/perp.yaml → price_grid, size
- Added: funding (hourly window, 5-second premium samples, 1,000 pUSD impact notional, 0.01% per 8 hours interest, +/-0.05% clamp, 4% per hour cap, scale 1.0 crypto and 0.5 otherwise), margin (IM = N / leverage, MMR = 0.5 / max leverage, cross or isolated, isolated by default) and the tier 5 maker rate of 0% in force until 2026-11-25
  Source: https://docs.polymarket.com/perps/learn-about-trading/funding.md, https://docs.polymarket.com/perps/learn-about-trading/margin.md, https://docs.polymarket.com/perps/learn-about-trading/fees.md
  Spec: specs/polymarket/perp.yaml → funding, margin, position_model, asset_classes, fees
