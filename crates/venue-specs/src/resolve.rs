//! Evaluating a formula or value at a path of a spec, with the name lookup of
//! `schema/formula-grammar.md`.

use std::collections::BTreeMap;

use rust_decimal::Decimal;

use crate::data::{parse_decimal, Leaf, Node, Spec};
use crate::error::{Error, Result};
use crate::formula::{eval, parse};

/// Where each row selector points: `category="crypto"` selects `fees.categories.crypto`.
pub const SELECTORS: [(&str, &str); 2] = [("category", "fees.categories"), ("tier", "fees.tiers")];

/// Long input names the packages accept, and the formula names they stand for.
pub const ALIASES: [(&str, &str); 4] = [
    ("contracts", "C"),
    ("price", "P"),
    ("quantity", "Q"),
    ("notional", "N"),
];

/// Caller inputs to a formula: variables such as `C` and `P`, and selected rows.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Inputs {
    vars: BTreeMap<String, Decimal>,
    rows: Vec<String>,
}

impl Inputs {
    /// No inputs.
    pub fn new() -> Inputs {
        Inputs::default()
    }

    /// Set a variable. `contracts`, `price`, `quantity` and `notional` are stored as
    /// `C`, `P`, `Q` and `N`.
    pub fn var(mut self, name: &str, value: Decimal) -> Inputs {
        let name = ALIASES
            .iter()
            .find(|(a, _)| *a == name)
            .map_or(name, |(_, f)| *f);
        self.vars.insert(name.to_owned(), value);
        self
    }

    /// Select a fee category row, `fees.categories.<key>`.
    pub fn category(self, key: &str) -> Inputs {
        self.row("fees.categories", key)
    }

    /// Select a fee tier row, `fees.tiers.<key>`.
    pub fn tier(self, key: &str) -> Inputs {
        self.row("fees.tiers", key)
    }

    /// Select any row by its table path and key.
    pub fn row(mut self, table: &str, key: &str) -> Inputs {
        self.rows.push(format!("{table}.{key}"));
        self
    }

    /// The variables set.
    pub fn vars(&self) -> &BTreeMap<String, Decimal> {
        &self.vars
    }

    /// The selected rows, as paths.
    pub fn rows(&self) -> &[String] {
        &self.rows
    }
}

const MAX_DEPTH: usize = 32;

struct Ctx<'a> {
    spec: &'a Spec,
    inputs: &'a Inputs,
    stack: Vec<String>,
}

fn parent(path: &str) -> &str {
    path.rsplit_once('.').map_or("", |(p, _)| p)
}

fn join(base: &str, name: &str) -> String {
    if base.is_empty() {
        name.to_owned()
    } else {
        format!("{base}.{name}")
    }
}

fn leaf_number(leaf: &Leaf, path: &str) -> Result<Decimal> {
    leaf.number().ok_or_else(|| {
        // Text such as "0" written as a string still counts as a number.
        Error::NotNumeric(path.to_owned())
    })
}

impl Ctx<'_> {
    fn value(&mut self, path: &str) -> Result<Decimal> {
        match self.spec.get(path) {
            Some(Node::Leaf(leaf)) => match &leaf.formula {
                Some(f) => self.formula(path, f),
                None => leaf_number(leaf, path),
            },
            Some(Node::Unverified(u)) => Err(Error::Unverified {
                path: path.to_owned(),
                reason: u.reason.clone(),
            }),
            Some(Node::Map(_)) => Err(Error::NotNumeric(path.to_owned())),
            None => match self.unverified_above(path) {
                Some(e) => Err(e),
                None => Err(Error::NotFound(path.to_owned())),
            },
        }
    }

    /// When a whole group above `path` is unverified, that is why `path` has no value.
    fn unverified_above(&self, path: &str) -> Option<Error> {
        let mut at = parent(path);
        while !at.is_empty() {
            if let Some(Node::Unverified(u)) = self.spec.get(at) {
                return Some(Error::Unverified {
                    path: at.to_owned(),
                    reason: u.reason.clone(),
                });
            }
            at = parent(at);
        }
        None
    }

    fn formula(&mut self, path: &str, src: &str) -> Result<Decimal> {
        if self.stack.iter().any(|p| p == path) {
            return Err(Error::Eval {
                formula: src.to_owned(),
                message: format!("{path} refers to itself"),
            });
        }
        if self.stack.len() >= MAX_DEPTH {
            return Err(Error::Eval {
                formula: src.to_owned(),
                message: "formulas nest too deeply".into(),
            });
        }
        let expr = parse(src)?;
        self.stack.push(path.to_owned());
        let mut inner: Option<Error> = None;
        let out = eval(&expr, &mut |name: &str| match self.name(path, name) {
            Ok(v) => Ok(v),
            Err(e) => {
                let msg = e.to_string();
                inner.get_or_insert(e);
                Err(msg)
            }
        });
        self.stack.pop();
        out.map_err(|message| {
            inner.unwrap_or(Error::Eval {
                formula: src.to_owned(),
                message,
            })
        })
    }

    /// Candidate paths for `name` used by the formula at `at`, in lookup order.
    fn candidates(&self, at: &str, name: &str) -> Vec<String> {
        if name.contains('.') {
            return vec![name.to_owned()];
        }
        let mut out = vec![join(parent(at), name)];
        out.extend(self.inputs.rows.iter().map(|r| join(r, name)));
        let mut up = parent(parent(at));
        loop {
            out.push(join(up, name));
            if up.is_empty() {
                break;
            }
            up = parent(up);
        }
        out
    }

    fn name(&mut self, at: &str, name: &str) -> Result<Decimal> {
        if let Some(v) = self.inputs.vars.get(name) {
            return Ok(*v);
        }
        let paths = self.candidates(at, name);
        for p in &paths {
            match self.spec.get(p) {
                // A group of entries is not a value; keep looking further out.
                None | Some(Node::Map(_)) => continue,
                Some(_) => return self.value(p),
            }
        }
        if let Some(e) = paths.iter().find_map(|p| self.unverified_above(p)) {
            return Err(e);
        }
        Err(Error::NotFound(format!(
            "{name} (used at {at}; pass it as an input{})",
            if self.inputs.rows.is_empty() {
                " or select a row such as a tier or category"
            } else {
                ""
            }
        )))
    }
}

/// Evaluate the value or formula at `path` of `spec`.
pub fn evaluate(spec: &Spec, path: &str, inputs: &Inputs) -> Result<Decimal> {
    for row in &inputs.rows {
        if !matches!(spec.get(row), Some(Node::Map(_))) {
            return Err(Error::NotFound(format!("row {row}")));
        }
    }
    Ctx {
        spec,
        inputs,
        stack: Vec::new(),
    }
    .value(path)
}

/// Parse a decimal from text, as the packages accept it.
pub fn decimal(text: &str) -> Option<Decimal> {
    parse_decimal(text.trim())
}
