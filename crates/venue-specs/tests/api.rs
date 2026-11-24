//! Spec lookup, history and evaluation behaviour.

use venue_specs::formula::{eval, parse};
use venue_specs::{
    bundle, decimal, evaluate, fee, spec, spec_at, version, Decimal, Error, Inputs, Node,
};

fn d(s: &str) -> Decimal {
    decimal(s).unwrap()
}

fn calc(src: &str) -> Result<Decimal, String> {
    eval(&parse(src).map_err(|e| e.to_string())?, &mut |n: &str| {
        Err(format!("no {n}"))
    })
}

#[test]
fn bundle_has_all_six_specs() {
    let b = bundle();
    assert_eq!(b.specs.len(), 6);
    assert_eq!(b.schema_version, 1);
    assert!(version().starts_with("20"));
    for (v, p) in [
        ("kalshi", "binary"),
        ("kalshi", "perp"),
        ("polymarket", "binary"),
        ("polymarket", "perp"),
        ("hyperliquid", "perp"),
        ("hyperliquid", "outcome"),
    ] {
        let s = spec(v, p).unwrap();
        assert_eq!((s.venue.as_str(), s.product.as_str()), (v, p));
    }
    assert!(matches!(
        spec("kalshi", "option"),
        Err(Error::UnknownSpec { .. })
    ));
}

#[test]
fn every_leaf_has_source_and_as_of() {
    fn walk(n: &Node, count: &mut usize) {
        match n {
            Node::Leaf(l) => {
                assert!(l.source.starts_with("https://"));
                assert_eq!(l.as_of.len(), 10);
                *count += 1;
            }
            Node::Unverified(u) => assert!(!u.reason.is_empty()),
            Node::Map(m) => m.values().for_each(|c| walk(c, count)),
        }
    }
    let mut count = 0;
    for s in &bundle().specs {
        s.sections.values().for_each(|n| walk(n, &mut count));
    }
    assert!(count > 100);
}

#[test]
fn spec_at_swaps_in_history() {
    let before = spec_at("polymarket", "perp", "2026-11-24").unwrap();
    let after = spec_at("polymarket", "perp", "2026-11-25").unwrap();
    let liq = |s: &venue_specs::Spec| s.leaf("fees.liquidation_fee").unwrap().number().unwrap();
    assert_eq!(liq(&before), d("0.005"));
    assert_eq!(liq(&after), d("0.01"));
    // The file as written carries the announced value.
    assert_eq!(
        spec("polymarket", "perp")
            .unwrap()
            .leaf("fees.liquidation_fee")
            .unwrap()
            .number(),
        Some(d("0.01"))
    );
}

#[test]
fn spec_at_kalshi_combos_tick_structure() {
    let path = "price_grid.series_overrides.multivariate_combos";
    let text = |at: &str| {
        let s = spec_at("kalshi", "binary", at).unwrap();
        s.get(path).map(|n| n.to_json().to_string()).unwrap()
    };
    assert!(text("2026-09-02").contains("deci_cent"));
    assert!(!text("2026-09-02").contains("center_deci_edge_centi_cent"));
    assert!(text("2026-09-03").contains("center_deci_edge_centi_cent"));
}

#[test]
fn values_not_yet_in_force_and_without_history_are_absent() {
    let s = spec_at("kalshi", "perp", "2026-10-21").unwrap();
    assert!(s.get("funding.premium_averaging").is_none());
    let s = spec_at("kalshi", "perp", "2026-10-22").unwrap();
    assert!(s.get("funding.premium_averaging").is_some());
}

#[test]
fn bad_timestamps_are_errors() {
    assert!(matches!(
        spec_at("kalshi", "binary", "yesterday"),
        Err(Error::BadTimestamp(_))
    ));
}

#[test]
fn fee_helper_and_aliases() {
    let i = Inputs::new()
        .category("crypto")
        .var("contracts", d("100"))
        .var("price", d("0.5"));
    assert_eq!(
        fee("polymarket", "binary", "taker", Some("2026-11-24"), &i).unwrap(),
        d("1.75")
    );
    // No category: the rate cannot be found, and the error says so.
    let i = Inputs::new().var("C", d("100")).var("P", d("0.5"));
    let e = fee("polymarket", "binary", "taker", Some("2026-11-24"), &i).unwrap_err();
    assert!(e.to_string().contains("rate"), "{e}");
    // Unknown row.
    let i = Inputs::new().tier("99").var("N", d("1"));
    assert!(matches!(
        fee("hyperliquid", "perp", "taker", Some("2026-11-24"), &i),
        Err(Error::NotFound(_))
    ));
    // Now (no timestamp) works too.
    let i = Inputs::new().tier("0").var("notional", d("10000"));
    assert_eq!(
        fee("hyperliquid", "perp", "taker", None, &i).unwrap(),
        d("4.5")
    );
}

#[test]
fn hip3_fee_scale() {
    let s = spec("hyperliquid", "perp").unwrap();
    let scale = |x: &str| {
        evaluate(
            s,
            "asset_classes.hip3.fee_scale",
            &Inputs::new().var("deployer_fee_scale", d(x)),
        )
        .unwrap()
    };
    assert_eq!(scale("0.5"), d("1.5"));
    assert_eq!(scale("1"), d("2"));
    assert_eq!(scale("2"), d("4"));
    let i = Inputs::new()
        .tier("0")
        .var("N", d("10000"))
        .var("deployer_fee_scale", d("1"))
        .var("growth_mode", d("1"));
    // 0.045% x 2 x 0.1 = 0.009%.
    assert_eq!(
        evaluate(s, "asset_classes.hip3.taker_fee", &i).unwrap(),
        d("0.9")
    );
}

#[test]
fn hyperliquid_order_value_caps() {
    let s = spec("hyperliquid", "perp").unwrap();
    let cap = |l: &str| {
        evaluate(
            s,
            "size.max_limit_order_value",
            &Inputs::new().var("max_leverage", d(l)),
        )
        .unwrap()
    };
    assert_eq!(cap("40"), d("300000000"));
    assert_eq!(cap("20"), d("50000000"));
    assert_eq!(cap("10"), d("20000000"));
    assert_eq!(cap("3"), d("5000000"));
}

#[test]
fn outcome_settlement() {
    let s = spec("hyperliquid", "outcome").unwrap();
    let i = Inputs::new().var("settle_fraction", d("1"));
    assert_eq!(evaluate(s, "settlement.yes_payout", &i).unwrap(), d("1"));
    assert_eq!(evaluate(s, "settlement.no_payout", &i).unwrap(), d("0"));
}

#[test]
fn formula_arithmetic_is_exact() {
    assert_eq!(calc("0.07 * 100 * 0.5 * (1 - 0.5)").unwrap(), d("1.75"));
    assert_eq!(calc("0.1 + 0.2").unwrap(), d("0.3"));
    assert_eq!(calc("2 ^ 10").unwrap(), d("1024"));
    assert_eq!(calc("2 ^ -2").unwrap(), d("0.25"));
    assert_eq!(calc("-2 ^ 2").unwrap(), d("-4"));
    assert_eq!(calc("1 - 2 - 3").unwrap(), d("-4"));
    assert_eq!(calc("8 / 4 / 2").unwrap(), d("1"));
    assert_eq!(calc("2 / 3 * 3").unwrap().round_dp(20), d("2"));
}

#[test]
fn formula_functions() {
    assert_eq!(calc("abs(-3)").unwrap(), d("3"));
    assert_eq!(calc("min(3, 1, 2)").unwrap(), d("1"));
    assert_eq!(calc("max(3, 1, 2)").unwrap(), d("3"));
    assert_eq!(calc("clamp(5, 0, 1)").unwrap(), d("1"));
    assert_eq!(calc("clamp(-5, 0, 1)").unwrap(), d("0"));
    assert_eq!(
        calc("ceil_to(0.00363825, 0.000001)").unwrap(),
        d("0.003639")
    );
    assert_eq!(calc("ceil_to(-0.015, 0.01)").unwrap(), d("-0.01"));
    assert_eq!(calc("floor_to(0.019, 0.01)").unwrap(), d("0.01"));
    assert_eq!(calc("floor_to(-0.011, 0.01)").unwrap(), d("-0.02"));
    assert_eq!(calc("round_to(0.125, 0.01)").unwrap(), d("0.13"));
    assert_eq!(calc("round_to(-0.125, 0.01)").unwrap(), d("-0.13"));
    assert_eq!(calc("round_to(0.124, 0.01)").unwrap(), d("0.12"));
    assert_eq!(calc("ceil_cents(1.001)").unwrap(), d("1.01"));
    assert_eq!(calc("ceil_cents(1)").unwrap(), d("1"));
    assert_eq!(calc("if(1 > 2, 10, 20)").unwrap(), d("20"));
    assert_eq!(calc("if(2 >= 2, 10, missing)").unwrap(), d("10"));
    assert_eq!(
        calc("(1 == 1) + (1 != 1) + (1 < 2) + (2 <= 1)").unwrap(),
        d("2")
    );
}

#[test]
fn formula_errors() {
    for bad in [
        "", "1 +", "(1", "1 2", "foo(", "1 & 2", "1.", "a = b", "a ! b",
    ] {
        assert!(parse(bad).is_err(), "{bad:?}");
    }
    for bad in [
        "1 / 0",
        "2 ^ 0.5",
        "nope(1)",
        "abs(1, 2)",
        "min(1)",
        "clamp(1, 2, 1)",
        "ceil_to(1, 0)",
        "x + 1",
    ] {
        assert!(calc(bad).is_err(), "{bad:?}");
    }
}

#[test]
fn self_reference_is_an_error_not_a_hang() {
    // fees.taker.fee refers to trade_fee, which refers to model_fee; an input named after the
    // formula itself is used as the input, not as a loop.
    let s = spec("kalshi", "binary").unwrap();
    let i = Inputs::new()
        .var("C", d("1"))
        .var("P", d("0.5"))
        .var("trade_fee", d("0.02"));
    assert_eq!(evaluate(s, "fees.taker.fee", &i).unwrap(), d("0.02"));
}

#[test]
fn unverified_is_an_error_with_a_reason() {
    let s = spec("kalshi", "binary").unwrap();
    let e = evaluate(
        s,
        "fees.taker.fee",
        &Inputs::new().var("C", d("1")).var("P", d("0.5")),
    )
    .unwrap_err();
    match e {
        Error::Unverified { path, reason } => {
            assert_eq!(path, "fees.taker.model_fee");
            assert!(!reason.is_empty());
        }
        other => panic!("{other:?}"),
    }
}
