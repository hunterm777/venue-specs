# Changelog

Written by the daily watcher (`watch/run.py`). Entries are dated by the day a change was detected
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
