//! Recursive-descent parser producing an expression tree.

use rust_decimal::Decimal;

use super::lexer::{lex, Tok};
use crate::error::{Error, Result};

/// A parsed formula.
#[derive(Debug, Clone, PartialEq)]
pub enum Expr {
    /// A literal number.
    Num(Decimal),
    /// A name, bare (`coef`) or dotted (`fees.rounding.step`).
    Name(String),
    /// Negation.
    Neg(Box<Expr>),
    /// `+ - * / ^`.
    Bin(char, Box<Expr>, Box<Expr>),
    /// `< <= > >= == !=`.
    Cmp(&'static str, Box<Expr>, Box<Expr>),
    /// A function call.
    Call(String, Vec<Expr>),
}

struct P {
    toks: Vec<Tok>,
    pos: usize,
}

impl P {
    fn peek(&self) -> Option<&Tok> {
        self.toks.get(self.pos)
    }

    fn next(&mut self) -> Option<Tok> {
        let t = self.toks.get(self.pos).cloned();
        self.pos += 1;
        t
    }

    fn expect(&mut self, want: &Tok) -> std::result::Result<(), String> {
        match self.next() {
            Some(ref t) if t == want => Ok(()),
            other => Err(format!("expected {want:?}, found {other:?}")),
        }
    }

    fn comparison(&mut self) -> std::result::Result<Expr, String> {
        let left = self.sum()?;
        if let Some(Tok::Cmp(op)) = self.peek().cloned() {
            self.pos += 1;
            let right = self.sum()?;
            return Ok(Expr::Cmp(op, Box::new(left), Box::new(right)));
        }
        Ok(left)
    }

    fn sum(&mut self) -> std::result::Result<Expr, String> {
        let mut left = self.product()?;
        while let Some(Tok::Op(op @ ('+' | '-'))) = self.peek().cloned() {
            self.pos += 1;
            left = Expr::Bin(op, Box::new(left), Box::new(self.product()?));
        }
        Ok(left)
    }

    fn product(&mut self) -> std::result::Result<Expr, String> {
        let mut left = self.unary()?;
        while let Some(Tok::Op(op @ ('*' | '/'))) = self.peek().cloned() {
            self.pos += 1;
            left = Expr::Bin(op, Box::new(left), Box::new(self.unary()?));
        }
        Ok(left)
    }

    fn unary(&mut self) -> std::result::Result<Expr, String> {
        if self.peek() == Some(&Tok::Op('-')) {
            self.pos += 1;
            return Ok(Expr::Neg(Box::new(self.unary()?)));
        }
        self.power()
    }

    fn power(&mut self) -> std::result::Result<Expr, String> {
        let base = self.primary()?;
        if self.peek() == Some(&Tok::Op('^')) {
            self.pos += 1;
            return Ok(Expr::Bin('^', Box::new(base), Box::new(self.unary()?)));
        }
        Ok(base)
    }

    fn primary(&mut self) -> std::result::Result<Expr, String> {
        match self.next() {
            Some(Tok::Num(n)) => Ok(Expr::Num(n)),
            Some(Tok::LParen) => {
                let e = self.comparison()?;
                self.expect(&Tok::RParen)?;
                Ok(e)
            }
            Some(Tok::Name(name)) => {
                if self.peek() != Some(&Tok::LParen) {
                    return Ok(Expr::Name(name));
                }
                self.pos += 1;
                let mut args = vec![self.comparison()?];
                while self.peek() == Some(&Tok::Comma) {
                    self.pos += 1;
                    args.push(self.comparison()?);
                }
                self.expect(&Tok::RParen)?;
                Ok(Expr::Call(name, args))
            }
            other => Err(format!("unexpected {other:?}")),
        }
    }
}

/// Parse a formula string.
pub fn parse(src: &str) -> Result<Expr> {
    let err = |message: String| Error::Parse {
        formula: src.to_owned(),
        message,
    };
    let mut p = P {
        toks: lex(src).map_err(err)?,
        pos: 0,
    };
    if p.toks.is_empty() {
        return Err(err("empty formula".into()));
    }
    let e = p.comparison().map_err(err)?;
    if p.pos != p.toks.len() {
        return Err(err(format!("unexpected {:?}", p.toks[p.pos])));
    }
    Ok(e)
}
