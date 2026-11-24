# venue-specs (Rust)

Versioned, sourced trading rules for Kalshi, Polymarket and Hyperliquid: fee formulas, tick grids, margin, funding and settlement. Every value carries the page it was read from and the date it was read. The specs are embedded at compile time; nothing here makes a network call. Formulas are evaluated in exact decimal arithmetic.

```rust
use venue_specs::{fee, spec_at, Decimal, Inputs};

let inputs = Inputs::new().tier("0").var("notional", Decimal::from(10_000));
let taker = fee("hyperliquid", "perp", "taker", Some("2026-11-24"), &inputs)?; // 4.50
let rules = spec_at("polymarket", "perp", "2026-11-24")?;                      // in force that day
# Ok::<(), venue_specs::Error>(())
```

A value not yet read from a source evaluates to `Error::Unverified`, never to a guess.

Crate versions encode the calendar data version: `2026.1124.0` is data release `2026.11.24`.

See the [repository](https://github.com/hunterm777/venue-specs) for the schema, formula grammar, sources and changelog.
