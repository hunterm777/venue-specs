//! The shared fee fixtures in `tests/fixtures/fees.json`, also run by the Python tests.

use std::path::PathBuf;

use serde_json::Value;
use venue_specs::{decimal, evaluate_at, Error, Inputs};

fn fixtures() -> Vec<Value> {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/fees.json");
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    let v: Value = serde_json::from_str(&text).unwrap();
    v["cases"].as_array().unwrap().clone()
}

fn inputs(case: &Value) -> Inputs {
    let mut inputs = Inputs::new();
    for (k, v) in case["inputs"].as_object().unwrap() {
        inputs = inputs.var(k, decimal(v.as_str().unwrap()).unwrap());
    }
    for row in case["rows"].as_array().unwrap() {
        let (table, key) = row.as_str().unwrap().rsplit_once('.').unwrap();
        inputs = inputs.row(table, key);
    }
    inputs
}

#[test]
fn fee_fixtures() {
    let cases = fixtures();
    assert!(cases.len() >= 15);
    for case in &cases {
        let name = case["name"].as_str().unwrap();
        let got = evaluate_at(
            case["venue"].as_str().unwrap(),
            case["product"].as_str().unwrap(),
            case["path"].as_str().unwrap(),
            case["at"].as_str(),
            &inputs(case),
        );
        match case.get("expect_error").and_then(Value::as_str) {
            Some("unverified") => assert!(
                matches!(got, Err(Error::Unverified { .. })),
                "{name}: {got:?}"
            ),
            Some("not_found") => assert!(matches!(got, Err(Error::NotFound(_))), "{name}: {got:?}"),
            Some(other) => panic!("{name}: unknown expect_error {other}"),
            None => {
                let want = decimal(case["expected"].as_str().unwrap()).unwrap();
                assert_eq!(got.as_ref().ok(), Some(&want), "{name}: {got:?}");
            }
        }
    }
}
