//! The rule in force at a given instant: current values plus `history/`.

use std::collections::BTreeMap;

use crate::data::{Bundle, HistoryEntry, Leaf, Node, Spec};
use crate::error::Result;
use crate::time::{self, Instant};

fn starts_by(leaf: &Leaf, at: Instant) -> Result<bool> {
    match &leaf.effective_from {
        None => Ok(true),
        Some(s) => Ok(time::parse(s)? <= at),
    }
}

fn covers(entry: &HistoryEntry, at: Instant) -> Result<bool> {
    Ok(starts_by(&entry.leaf, at)? && at < time::parse(&entry.valid_to)?)
}

/// Drop leaves not yet in force at `at`, depth first; returns whether anything is left.
fn prune(node: &mut Node, path: &str, at: Instant, gone: &mut Vec<String>) -> Result<bool> {
    match node {
        Node::Leaf(leaf) => {
            if starts_by(leaf, at)? {
                return Ok(true);
            }
            gone.push(path.to_owned());
            Ok(false)
        }
        Node::Unverified(_) => Ok(true),
        Node::Map(children) => {
            let mut keep = BTreeMap::new();
            for (k, mut child) in std::mem::take(children) {
                if prune(&mut child, &format!("{path}.{k}"), at, gone)? {
                    keep.insert(k, child);
                }
            }
            *children = keep;
            Ok(!children.is_empty())
        }
    }
}

fn insert(spec: &mut Spec, path: &str, leaf: Leaf) {
    let mut parts: Vec<&str> = path.split('.').collect();
    let last = parts.pop().unwrap_or_default();
    let mut map = &mut spec.sections;
    for p in parts {
        let next = map
            .entry(p.to_owned())
            .or_insert_with(|| Node::Map(BTreeMap::new()));
        if !matches!(next, Node::Map(_)) {
            *next = Node::Map(BTreeMap::new());
        }
        let Node::Map(children) = next else {
            unreachable!()
        };
        map = children;
    }
    map.insert(last.to_owned(), Node::Leaf(leaf));
}

/// The spec as it stood at `at`: values whose `effective_from` is later are replaced by the
/// history entry in force then, or dropped when no prior value is recorded.
pub fn resolve(bundle: &Bundle, venue: &str, product: &str, at: &str) -> Result<Spec> {
    resolve_at(bundle, venue, product, time::parse(at)?)
}

/// [`resolve`] for an instant already parsed.
pub fn resolve_at(bundle: &Bundle, venue: &str, product: &str, at: Instant) -> Result<Spec> {
    let mut spec = bundle.spec(venue, product)?.clone();
    let mut gone = Vec::new();
    let mut sections = std::mem::take(&mut spec.sections);
    for (k, node) in sections.iter_mut() {
        prune(node, k, at, &mut gone)?;
    }
    spec.sections = sections;
    for entry in bundle.history(venue, product) {
        if covers(entry, at)? && spec.leaf(&entry.path).is_none() {
            insert(&mut spec, &entry.path, entry.leaf.clone());
        }
    }
    Ok(spec)
}
