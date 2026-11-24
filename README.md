# venue-specs

Every venue's rules, versioned, sourced and kept current automatically.

venue-specs is one machine-readable record of how Kalshi, Polymarket and Hyperliquid work for binaries and perps: fee formulas, tick grids, size steps, margin and leverage rules, funding and settlement. Every value carries the page it was read from (`source`) and the date it was read (`as_of`), and, where the venue announces a change ahead of time, the date it takes effect (`effective_from`). A value that has not been read from a source is marked `unverified` and carries no number, so nothing undocumented slips in.

The YAML files in `specs/` are the source of truth. A JSON bundle, a Rust crate and a Python package are generated from them and carry the same data and version. None of them makes a network call.

## Coverage

| Spec | Sourced values | Unverified | Read from |
| --- | ---: | ---: | --- |
| `hyperliquid/perp` | 67 | 0 | Hyperliquid docs: fees, funding, margining, margin tiers, liquidations, contract specs, tick and lot size, HIP-3 |
| `hyperliquid/outcome` (HIP-4) | 16 | 2 | Hyperliquid docs: HIP-4, fees |
| `polymarket/binary` | 27 | 6 | Polymarket trading fees page |
| `polymarket/perp` | 48 | 4 | Polymarket Perps fee change notice (Nov 2026), Perps fees, funding and margin pages, Perps changelog |
| `kalshi/binary` | 15 | 7 | Kalshi API docs: fee rounding, fixed-point, changelog |
| `kalshi/perp` | 3 | 12 | Kalshi API changelog |

Kalshi's fee schedule and help center, and Polymarket's pages other than those above, could not be read when these files were written, so the values that live there (for example Kalshi's fee coefficients and the Polymarket Perps price tick) are `unverified`. Asking for one is an error that says why, never a silent zero. The weekly watcher tracks those pages and opens an issue when they change.

## Install

The packages are not on crates.io or PyPI yet. Until then, install from this repository:

```sh
cargo add venue-specs --git https://github.com/hunterm777/venue-specs
pip install "git+https://github.com/hunterm777/venue-specs#subdirectory=crates/venue-specs-py"   # needs a Rust toolchain
```

The JSON bundle is `crates/venue-specs/data/venue-specs.json`, also attached to each GitHub release.

## Use

Python:

```python
import venue_specs as vs

vs.fee("hyperliquid", "perp", tier="0", notional=10_000, at="2026-11-24")  # Decimal('4.50000')
vs.fee("polymarket", "binary", category="sports", contracts=100, price=0.5)  # Decimal('1.25')
vs.evaluate("hyperliquid", "perp", "margin.maintenance_margin_rate", max_leverage=20)  # Decimal('0.025')

rules = vs.spec_at("polymarket", "perp", "2026-11-24")  # the rules in force at the start of that UTC day
rules["fees"]["liquidation_fee"]  # value 0.005, with its source and as_of

vs.fee("kalshi", "binary", contracts=100, price=0.5)  # raises UnverifiedError: fees.taker.model_fee ...
```

Rust:

```rust
use venue_specs::{fee, spec_at, Decimal, Inputs};

let inputs = Inputs::new().tier("0").var("notional", Decimal::from(10_000));
let taker = fee("hyperliquid", "perp", "taker", Some("2026-11-24"), &inputs)?;   // 4.50
let rules = spec_at("polymarket", "perp", "2026-11-25T00:00:00Z")?;              // after the Nov 25 change
# Ok::<(), venue_specs::Error>(())
```

- Numbers are exact decimals (`decimal.Decimal`, `rust_decimal::Decimal`), never binary floats.
- `spec(venue, product)` is the file as written, including announced values not yet in force. `spec_at(venue, product, at)` is the rule in force at `at`: a value whose `effective_from` is later is replaced by the prior value from `history/`. `fee` and `evaluate` use the rules in force now unless you pass `at`.
- Inputs are the formula's names (`C`, `P`, `Q`, `N`, or `contracts`, `price`, `quantity`, `notional`). `category=` selects `fees.categories.<key>` and `tier=` selects `fees.tiers.<key>`. Each formula's `note` says what it takes.

## Spec files

One file per venue and product, validated by [`schema/spec.schema.json`](schema/spec.schema.json). Every leaf is an object:

```yaml
taker: { value: 0.00045, source: "https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees.md", as_of: 2026-11-24 }
fee:   { formula: "abs(N) * taker", source: "...", as_of: 2026-11-24, unit: USDC, note: "N = trade notional ..." }
model_fee: { unverified: "On the Kalshi fee schedule, which was not readable here.", as_of: 2026-11-24, sources: ["https://kalshi.com/fee-schedule"] }
```

Formulas are strings in a small grammar ([`schema/formula-grammar.md`](schema/formula-grammar.md)) evaluated by the Rust crate, so a fee formula change is a data change. `history/` keeps every replaced value with the instant it stopped applying (`valid_to`).

## The weekly watcher

[`.github/workflows/watch.yml`](.github/workflows/watch.yml) runs once a week, on Mondays at 06:17 UTC:

1. Fetch every source in [`watch/sources.yaml`](watch/sources.yaml): changelogs, fee and rules pages (as `.md` where the venue offers it), the Kalshi fee schedule PDF and Hyperliquid's info endpoint.
2. Diff each against its snapshot in `watch/snapshots/`. Nothing changed: stop.
3. Parse changed sources with the venue's parser in `watch/parsers/`. Hyperliquid's fee tables and funding constants, Kalshi's contract size step, Polymarket's Perps fee tier table, funding constants and maintenance margin rule, and the per-market tick and size step changes in its Perps changelog are parsed deterministically. A page that shows today's rate while a different rate is announced on file is checked against the rate in force; a mismatch opens an issue and writes nothing.
4. Validate the specs and run every test, the fee fixtures included.
5. Commit the updated YAML, history, snapshots and a dated [`CHANGELOG.md`](CHANGELOG.md) entry to `main`, tag a calendar version and release it.

A page that changed with no value parsed (a prose announcement, or a page with no parser yet) is committed as a Docs-only entry and opens an issue quoting the diff. Parsers read only tables and the fixed sentences they know; anything else is left to the issue. When validation or a test fails, nothing is committed and an issue is opened with the log. Announced changes are stored with their `effective_from` date and logged as Upcoming.

Run it locally with `python -m watch.run --out watch-out`, or `--offline DIR` to read fetched copies from `DIR/<id>.txt`.

## Versions

Data releases use calendar versions, `YYYY.MM.DD`, with `.N` for a second release the same day. The crate writes the same version as `YYYY.(MM*100+DD).N` because crates.io needs three-part versions: crate `2026.1124.0` is data release `2026.11.24`. A spec change is never breaking; a schema change bumps `schema_version` and is released by hand.

[`release.yml`](.github/workflows/release.yml) runs only for a version tag. It attaches `venue-specs.json`, the wheels and the crate archive to a GitHub release, and publishes to crates.io and PyPI only when the `CARGO_REGISTRY_TOKEN` and `PYPI_API_TOKEN` secrets are set.

## Layout

```
specs/                 one YAML file per venue x product (the source of truth)
history/               replaced values with their validity windows
schema/                JSON Schema and formula grammar
watch/                 sources list, snapshots, parsers, diff, changelog writer, runner
crates/venue-specs/    Rust crate: typed specs, formula evaluator, spec_at (embeds the JSON bundle)
crates/venue-specs-py/ Python package (PyO3)
tests/                 watcher tests and replays; tests/fixtures/ holds the shared fee fixtures
```

## Development

```sh
pip install -r requirements-dev.txt
python -m watch.validate          # schema check of every spec and history file
python -m watch.bundle            # regenerate the JSON bundle after editing specs/ or history/
python -m pytest -q tests         # watcher, parsers, replays
cargo test --workspace            # Rust crate, including tests/fixtures/fees.json
maturin develop -m crates/venue-specs-py/Cargo.toml && python -m pytest -q crates/venue-specs-py/tests
```

Every hand edit needs a `source` and an `as_of` for each value it adds.

## License

MIT
