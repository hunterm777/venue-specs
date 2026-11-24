//! Thin PyO3 layer over the `venue-specs` crate. Numbers cross the boundary as decimal
//! strings so nothing passes through binary floating point; `venue_specs/__init__.py`
//! turns them into `decimal.Decimal`.

use std::collections::BTreeMap;

use pyo3::create_exception;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use venue_specs::{self as vs, Error, Inputs};

create_exception!(
    _venue_specs,
    VenueSpecsError,
    PyValueError,
    "Any venue-specs error."
);
create_exception!(
    _venue_specs,
    UnverifiedError,
    VenueSpecsError,
    "The value has not been read from a source yet."
);
create_exception!(
    _venue_specs,
    NotFoundError,
    VenueSpecsError,
    "Nothing at that path, or nothing in force then."
);

fn err(e: Error) -> PyErr {
    let msg = e.to_string();
    match e {
        Error::Unverified { .. } => UnverifiedError::new_err(msg),
        Error::NotFound(_) | Error::UnknownSpec { .. } => NotFoundError::new_err(msg),
        _ => VenueSpecsError::new_err(msg),
    }
}

fn resolved(venue: &str, product: &str, at: Option<&str>) -> PyResult<vs::Spec> {
    match at {
        Some(at) => vs::spec_at(venue, product, at),
        None => vs::spec_now(venue, product),
    }
    .map_err(err)
}

#[pyfunction]
fn version() -> &'static str {
    vs::version()
}

#[pyfunction]
fn bundle_json() -> &'static str {
    vs::BUNDLE_JSON
}

#[pyfunction]
fn spec_json(venue: &str, product: &str) -> PyResult<String> {
    Ok(vs::spec(venue, product).map_err(err)?.to_json().to_string())
}

#[pyfunction]
#[pyo3(signature = (venue, product, at=None))]
fn spec_at_json(venue: &str, product: &str, at: Option<&str>) -> PyResult<String> {
    Ok(resolved(venue, product, at)?.to_json().to_string())
}

#[pyfunction]
#[pyo3(signature = (venue, product, path, at, vars, rows))]
fn evaluate(
    venue: &str,
    product: &str,
    path: &str,
    at: Option<&str>,
    vars: BTreeMap<String, String>,
    rows: Vec<String>,
) -> PyResult<String> {
    let mut inputs = Inputs::new();
    for (name, text) in vars {
        let value = vs::decimal(&text).ok_or_else(|| {
            VenueSpecsError::new_err(format!("input {name}={text:?} is not a decimal number"))
        })?;
        inputs = inputs.var(&name, value);
    }
    for row in rows {
        let (table, key) = row
            .rsplit_once('.')
            .ok_or_else(|| VenueSpecsError::new_err(format!("bad row {row:?}")))?;
        inputs = inputs.row(table, key);
    }
    let spec = resolved(venue, product, at)?;
    Ok(vs::evaluate(&spec, path, &inputs).map_err(err)?.to_string())
}

#[pymodule]
fn _venue_specs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = m.py();
    m.add("VenueSpecsError", py.get_type::<VenueSpecsError>())?;
    m.add("UnverifiedError", py.get_type::<UnverifiedError>())?;
    m.add("NotFoundError", py.get_type::<NotFoundError>())?;
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(bundle_json, m)?)?;
    m.add_function(wrap_pyfunction!(spec_json, m)?)?;
    m.add_function(wrap_pyfunction!(spec_at_json, m)?)?;
    m.add_function(wrap_pyfunction!(evaluate, m)?)?;
    Ok(())
}
