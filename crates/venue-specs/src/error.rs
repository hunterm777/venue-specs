//! Error type for every fallible call in the crate.

use std::fmt;

/// Anything that can go wrong reading specs or evaluating a formula.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Error {
    /// No spec file for this venue and product.
    #[allow(missing_docs)]
    UnknownSpec { venue: String, product: String },
    /// A timestamp that is not `YYYY-MM-DD` or RFC 3339.
    BadTimestamp(String),
    /// Nothing at this path, or nothing in force at the requested time.
    NotFound(String),
    /// The entry exists but has not been read from a source yet.
    #[allow(missing_docs)]
    Unverified { path: String, reason: String },
    /// The entry exists but is not a number or formula.
    NotNumeric(String),
    /// A formula failed to parse.
    #[allow(missing_docs)]
    Parse { formula: String, message: String },
    /// A formula failed to evaluate.
    #[allow(missing_docs)]
    Eval { formula: String, message: String },
    /// The bundled data is malformed.
    Data(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::UnknownSpec { venue, product } => write!(f, "no spec for {venue}/{product}"),
            Error::BadTimestamp(s) => write!(f, "bad timestamp {s:?}: use YYYY-MM-DD or RFC 3339"),
            Error::NotFound(p) => write!(f, "nothing in force at {p}"),
            Error::Unverified { path, reason } => write!(f, "{path} is unverified: {reason}"),
            Error::NotNumeric(p) => write!(f, "{p} is not a number or formula"),
            Error::Parse { formula, message } => write!(f, "cannot parse {formula:?}: {message}"),
            Error::Eval { formula, message } => write!(f, "cannot evaluate {formula:?}: {message}"),
            Error::Data(m) => write!(f, "bad bundle data: {m}"),
        }
    }
}

impl std::error::Error for Error {}

/// Result alias used across the crate.
pub type Result<T> = std::result::Result<T, Error>;
