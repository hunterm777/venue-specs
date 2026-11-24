//! Typed view of the bundled specs and history.

use std::collections::BTreeMap;
use std::str::FromStr;

use rust_decimal::Decimal;
use serde_json::{Map, Value};

use crate::error::{Error, Result};

/// One sourced value: a number, text, table or formula, with its provenance.
#[derive(Debug, Clone, PartialEq)]
pub struct Leaf {
    /// The value, when the entry is not a formula.
    pub value: Option<Value>,
    /// The formula string, when the entry is a formula (see `schema/formula-grammar.md`).
    pub formula: Option<String>,
    /// Page the value was read from.
    pub source: String,
    /// Date the value was read.
    pub as_of: String,
    /// When the rule takes effect at the venue; `None` when the venue does not say.
    pub effective_from: Option<String>,
    /// Unit, when the value has one.
    pub unit: Option<String>,
    /// What the source says, in brief.
    pub note: Option<String>,
}

impl Leaf {
    /// The value as an exact decimal, if it is a number.
    pub fn number(&self) -> Option<Decimal> {
        match self.value.as_ref()? {
            Value::Number(n) => parse_decimal(&n.to_string()),
            Value::Bool(b) => Some(Decimal::from(u8::from(*b))),
            _ => None,
        }
    }

    fn from_json(map: &Map<String, Value>, at: &str) -> Result<Leaf> {
        let text = |k: &str| map.get(k).and_then(Value::as_str).map(str::to_owned);
        let leaf = Leaf {
            value: map.get("value").cloned(),
            formula: text("formula"),
            source: text("source").ok_or_else(|| Error::Data(format!("{at}: no source")))?,
            as_of: text("as_of").ok_or_else(|| Error::Data(format!("{at}: no as_of")))?,
            effective_from: text("effective_from"),
            unit: text("unit"),
            note: text("note"),
        };
        if leaf.value.is_some() == leaf.formula.is_some() {
            return Err(Error::Data(format!(
                "{at}: needs exactly one of value or formula"
            )));
        }
        Ok(leaf)
    }

    /// Back to the JSON shape used in the spec files.
    pub fn to_json(&self) -> Value {
        let mut m = Map::new();
        if let Some(v) = &self.value {
            m.insert("value".into(), v.clone());
        }
        if let Some(f) = &self.formula {
            m.insert("formula".into(), Value::String(f.clone()));
        }
        m.insert("source".into(), Value::String(self.source.clone()));
        m.insert("as_of".into(), Value::String(self.as_of.clone()));
        m.insert(
            "effective_from".into(),
            self.effective_from
                .clone()
                .map_or(Value::Null, Value::String),
        );
        for (k, v) in [("unit", &self.unit), ("note", &self.note)] {
            if let Some(v) = v {
                m.insert(k.into(), Value::String(v.clone()));
            }
        }
        Value::Object(m)
    }
}

/// An entry that has not been read from a source yet. It carries no value.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Unverified {
    /// Why it is unverified.
    pub reason: String,
    /// When that was recorded.
    pub as_of: String,
    /// Where the value should come from.
    pub sources: Vec<String>,
}

/// A node of a spec tree.
#[derive(Debug, Clone, PartialEq)]
pub enum Node {
    /// A sourced value.
    Leaf(Leaf),
    /// Not yet read from a source.
    Unverified(Unverified),
    /// A group of named children.
    Map(BTreeMap<String, Node>),
}

impl Node {
    fn from_json(v: &Value, at: &str) -> Result<Node> {
        let map = v
            .as_object()
            .ok_or_else(|| Error::Data(format!("{at}: expected an object")))?;
        if map.contains_key("source") {
            return Leaf::from_json(map, at).map(Node::Leaf);
        }
        if let Some(reason) = map.get("unverified").and_then(Value::as_str) {
            let sources = map
                .get("sources")
                .and_then(Value::as_array)
                .map(|a| {
                    a.iter()
                        .filter_map(|s| s.as_str().map(str::to_owned))
                        .collect()
                })
                .unwrap_or_default();
            let as_of = map
                .get("as_of")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_owned();
            return Ok(Node::Unverified(Unverified {
                reason: reason.to_owned(),
                as_of,
                sources,
            }));
        }
        let mut out = BTreeMap::new();
        for (k, child) in map {
            out.insert(k.clone(), Node::from_json(child, &format!("{at}.{k}"))?);
        }
        Ok(Node::Map(out))
    }

    /// Back to the JSON shape used in the spec files.
    pub fn to_json(&self) -> Value {
        match self {
            Node::Leaf(l) => l.to_json(),
            Node::Unverified(u) => {
                let mut m = Map::new();
                m.insert("unverified".into(), Value::String(u.reason.clone()));
                m.insert("as_of".into(), Value::String(u.as_of.clone()));
                if !u.sources.is_empty() {
                    m.insert(
                        "sources".into(),
                        u.sources.iter().cloned().map(Value::String).collect(),
                    );
                }
                Value::Object(m)
            }
            Node::Map(children) => Value::Object(
                children
                    .iter()
                    .map(|(k, v)| (k.clone(), v.to_json()))
                    .collect(),
            ),
        }
    }
}

/// The rules for one venue and product.
#[derive(Debug, Clone, PartialEq)]
pub struct Spec {
    /// `kalshi`, `polymarket` or `hyperliquid`.
    pub venue: String,
    /// `binary`, `perp` or `outcome`.
    pub product: String,
    /// Date of the newest rule in the file.
    pub version_of_rules: String,
    /// Schema version of the file.
    pub schema_version: u64,
    /// Sections such as `fees` and `margin`.
    pub sections: BTreeMap<String, Node>,
}

const HEADER: [&str; 4] = ["schema_version", "venue", "product", "version_of_rules"];

impl Spec {
    pub(crate) fn from_json(v: &Value) -> Result<Spec> {
        let map = v
            .as_object()
            .ok_or_else(|| Error::Data("spec is not an object".into()))?;
        let text = |k: &str| {
            map.get(k)
                .and_then(Value::as_str)
                .map(str::to_owned)
                .ok_or_else(|| Error::Data(format!("spec has no {k}")))
        };
        let (venue, product) = (text("venue")?, text("product")?);
        let mut sections = BTreeMap::new();
        for (k, child) in map.iter().filter(|(k, _)| !HEADER.contains(&k.as_str())) {
            sections.insert(
                k.clone(),
                Node::from_json(child, &format!("{venue}/{product}:{k}"))?,
            );
        }
        Ok(Spec {
            schema_version: map
                .get("schema_version")
                .and_then(Value::as_u64)
                .unwrap_or(0),
            version_of_rules: text("version_of_rules")?,
            venue,
            product,
            sections,
        })
    }

    /// The node at a dotted path such as `fees.taker.fee`.
    pub fn get(&self, path: &str) -> Option<&Node> {
        let mut parts = path.split('.');
        let mut node = self.sections.get(parts.next()?)?;
        for p in parts {
            match node {
                Node::Map(children) => node = children.get(p)?,
                _ => return None,
            }
        }
        Some(node)
    }

    /// The leaf at a dotted path, if that path holds a sourced value.
    pub fn leaf(&self, path: &str) -> Option<&Leaf> {
        match self.get(path)? {
            Node::Leaf(l) => Some(l),
            _ => None,
        }
    }

    /// The spec as JSON, in the shape of the spec files.
    pub fn to_json(&self) -> Value {
        let mut m = Map::new();
        m.insert("schema_version".into(), Value::from(self.schema_version));
        m.insert("venue".into(), Value::String(self.venue.clone()));
        m.insert("product".into(), Value::String(self.product.clone()));
        m.insert(
            "version_of_rules".into(),
            Value::String(self.version_of_rules.clone()),
        );
        for (k, v) in &self.sections {
            m.insert(k.clone(), v.to_json());
        }
        Value::Object(m)
    }
}

/// A prior value with the end of its validity window.
#[derive(Debug, Clone, PartialEq)]
pub struct HistoryEntry {
    /// Dotted path of the value in the spec.
    pub path: String,
    /// The value as it was.
    pub leaf: Leaf,
    /// First instant the value was no longer in force.
    pub valid_to: String,
}

/// Everything in `venue-specs.json`.
#[derive(Debug, Clone, PartialEq)]
pub struct Bundle {
    /// Calendar version of the data, `YYYY.MM.DD` or `YYYY.MM.DD.N`.
    pub version: String,
    /// Schema version of the data.
    pub schema_version: u64,
    /// Current spec files.
    pub specs: Vec<Spec>,
    /// Prior values, keyed by (venue, product).
    pub history: BTreeMap<(String, String), Vec<HistoryEntry>>,
}

impl Bundle {
    /// Parse a bundle from its JSON text.
    pub fn from_json_str(text: &str) -> Result<Bundle> {
        let v: Value = serde_json::from_str(text).map_err(|e| Error::Data(e.to_string()))?;
        let specs = v
            .get("specs")
            .and_then(Value::as_array)
            .ok_or_else(|| Error::Data("no specs".into()))?
            .iter()
            .map(Spec::from_json)
            .collect::<Result<Vec<_>>>()?;
        let mut history = BTreeMap::new();
        for h in v
            .get("history")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            let key = |k: &str| {
                h.get(k)
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_owned()
            };
            let mut entries = Vec::new();
            for e in h
                .get("entries")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
            {
                let path = e
                    .get("path")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_owned();
                let leaf_map = e
                    .get("leaf")
                    .and_then(Value::as_object)
                    .ok_or_else(|| Error::Data(format!("history {path}: no leaf")))?;
                entries.push(HistoryEntry {
                    leaf: Leaf::from_json(leaf_map, &path)?,
                    valid_to: e
                        .get("valid_to")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_owned(),
                    path,
                });
            }
            history.insert((key("venue"), key("product")), entries);
        }
        Ok(Bundle {
            version: v
                .get("version")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_owned(),
            schema_version: v.get("schema_version").and_then(Value::as_u64).unwrap_or(0),
            specs,
            history,
        })
    }

    /// The spec file for a venue and product, as written.
    pub fn spec(&self, venue: &str, product: &str) -> Result<&Spec> {
        self.specs
            .iter()
            .find(|s| s.venue == venue && s.product == product)
            .ok_or_else(|| Error::UnknownSpec {
                venue: venue.into(),
                product: product.into(),
            })
    }

    /// Prior values for a venue and product.
    pub fn history(&self, venue: &str, product: &str) -> &[HistoryEntry] {
        self.history
            .get(&(venue.to_owned(), product.to_owned()))
            .map_or(&[], Vec::as_slice)
    }
}

/// Parse decimal text, including scientific notation.
pub(crate) fn parse_decimal(s: &str) -> Option<Decimal> {
    Decimal::from_str_exact(s)
        .ok()
        .or_else(|| Decimal::from_scientific(s).ok())
        .or_else(|| Decimal::from_str(s).ok())
}
