//! Versioned, sourced trading rules for Kalshi, Polymarket and Hyperliquid.
//!
//! The specs are embedded at compile time; nothing here makes a network call. Every value
//! carries the page it was read from and the date it was read. Values not yet read from a
//! source are unverified and evaluate to an error, never to a guess.
//!
//! ```
//! use rust_decimal::Decimal;
//! use venue_specs::{fee, Inputs};
//!
//! // Hyperliquid perp taker fee on $10,000 notional at the base tier.
//! let inputs = Inputs::new().tier("0").var("notional", Decimal::from(10_000));
//! let f = fee("hyperliquid", "perp", "taker", Some("2026-11-24"), &inputs).unwrap();
//! assert_eq!(f.to_string(), "4.50000");
//! ```

#![forbid(unsafe_code)]
#![warn(missing_docs)]

mod data;
mod error;
pub mod formula;
mod history;
mod resolve;
pub mod time;

use std::sync::OnceLock;

pub use rust_decimal::Decimal;

pub use data::{Bundle, HistoryEntry, Leaf, Node, Spec, Unverified};
pub use error::{Error, Result};
pub use resolve::{decimal, evaluate, Inputs, ALIASES, SELECTORS};

/// The embedded `venue-specs.json`.
pub const BUNDLE_JSON: &str = include_str!("../data/venue-specs.json");

/// The embedded bundle, parsed once.
pub fn bundle() -> &'static Bundle {
    static B: OnceLock<Bundle> = OnceLock::new();
    B.get_or_init(|| {
        Bundle::from_json_str(BUNDLE_JSON).expect("embedded venue-specs.json is valid")
    })
}

/// Data version of the embedded bundle, `YYYY.MM.DD` or `YYYY.MM.DD.N`.
pub fn version() -> &'static str {
    &bundle().version
}

/// The spec file for a venue and product as written, including announced values that are
/// not in force yet. Use [`spec_at`] for the rules in force at a time.
pub fn spec(venue: &str, product: &str) -> Result<&'static Spec> {
    bundle().spec(venue, product)
}

/// The rules in force at `at` (`YYYY-MM-DD`, the start of that UTC day, or RFC 3339).
pub fn spec_at(venue: &str, product: &str, at: &str) -> Result<Spec> {
    history::resolve(bundle(), venue, product, at)
}

/// The rules in force now, by the system clock.
pub fn spec_now(venue: &str, product: &str) -> Result<Spec> {
    history::resolve_at(bundle(), venue, product, time::now())
}

/// Evaluate the entry at `path` (for example `margin.maintenance_margin_rate`) in the rules
/// in force at `at`, or now when `at` is `None`.
pub fn evaluate_at(
    venue: &str,
    product: &str,
    path: &str,
    at: Option<&str>,
    inputs: &Inputs,
) -> Result<Decimal> {
    let spec = match at {
        Some(at) => spec_at(venue, product, at)?,
        None => spec_now(venue, product)?,
    };
    evaluate(&spec, path, inputs)
}

/// The fee for one fill: evaluates `fees.<side>.fee`, where `side` is `taker` or `maker`.
///
/// Inputs are the formula's names (`C`, `P`, `Q`, `N`, or their long aliases), and the row
/// selectors `category` and `tier` where the venue prices by row.
pub fn fee(
    venue: &str,
    product: &str,
    side: &str,
    at: Option<&str>,
    inputs: &Inputs,
) -> Result<Decimal> {
    evaluate_at(venue, product, &format!("fees.{side}.fee"), at, inputs)
}
