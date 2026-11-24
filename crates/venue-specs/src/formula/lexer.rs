//! Tokens of the formula language.

use rust_decimal::Decimal;

use crate::data::parse_decimal;

#[derive(Debug, Clone, PartialEq)]
pub enum Tok {
    Num(Decimal),
    Name(String),
    Op(char),
    Cmp(&'static str),
    LParen,
    RParen,
    Comma,
}

fn ident_start(c: char) -> bool {
    c.is_ascii_alphabetic() || c == '_'
}

fn ident_char(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_'
}

/// Split a formula into tokens.
pub fn lex(src: &str) -> Result<Vec<Tok>, String> {
    let chars: Vec<char> = src.chars().collect();
    let mut out = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        match c {
            ' ' | '\t' | '\n' => i += 1,
            '(' => (out.push(Tok::LParen), i += 1).1,
            ')' => (out.push(Tok::RParen), i += 1).1,
            ',' => (out.push(Tok::Comma), i += 1).1,
            '+' | '-' | '*' | '/' | '^' => (out.push(Tok::Op(c)), i += 1).1,
            '<' | '>' | '=' | '!' => {
                let two = chars.get(i + 1) == Some(&'=');
                let op = match (c, two) {
                    ('<', true) => "<=",
                    ('<', false) => "<",
                    ('>', true) => ">=",
                    ('>', false) => ">",
                    ('=', true) => "==",
                    ('!', true) => "!=",
                    _ => return Err(format!("unexpected {c:?} at {i}")),
                };
                out.push(Tok::Cmp(op));
                i += if two { 2 } else { 1 };
            }
            d if d.is_ascii_digit() => {
                let start = i;
                while i < chars.len() && chars[i].is_ascii_digit() {
                    i += 1;
                }
                if i < chars.len() && chars[i] == '.' {
                    i += 1;
                    let frac = i;
                    while i < chars.len() && chars[i].is_ascii_digit() {
                        i += 1;
                    }
                    if i == frac {
                        return Err(format!("number without digits after '.' at {start}"));
                    }
                }
                let text: String = chars[start..i].iter().collect();
                out.push(Tok::Num(
                    parse_decimal(&text).ok_or(format!("bad number {text}"))?,
                ));
            }
            a if ident_start(a) => {
                let start = i;
                loop {
                    while i < chars.len() && ident_char(chars[i]) {
                        i += 1;
                    }
                    if i + 1 < chars.len() && chars[i] == '.' && ident_start(chars[i + 1]) {
                        i += 1;
                        continue;
                    }
                    if i + 1 < chars.len() && chars[i] == '.' && chars[i + 1].is_ascii_digit() {
                        // Dotted paths may step into numbered rows, e.g. fees.tiers.0.taker.
                        i += 1;
                        continue;
                    }
                    break;
                }
                out.push(Tok::Name(chars[start..i].iter().collect()));
            }
            _ => return Err(format!("unexpected {c:?} at {i}")),
        }
    }
    Ok(out)
}
