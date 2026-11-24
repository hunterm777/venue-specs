//! Exact decimal evaluation of an expression tree.

use rust_decimal::{Decimal, RoundingStrategy};

use super::parser::Expr;

fn step_op(x: Decimal, step: Decimal, how: RoundingStrategy) -> Result<Decimal, String> {
    if step <= Decimal::ZERO {
        return Err(format!("step must be positive, got {step}"));
    }
    let q = x.checked_div(step).ok_or("overflow")?;
    Ok((q.round_dp_with_strategy(0, how) * step).normalize())
}

fn pow(base: Decimal, exp: Decimal) -> Result<Decimal, String> {
    if exp.fract() != Decimal::ZERO {
        return Err(format!("exponent must be an integer, got {exp}"));
    }
    let n: i64 = exp.trunc().try_into().map_err(|_| "exponent too large")?;
    let mut acc = Decimal::ONE;
    for _ in 0..n.unsigned_abs() {
        acc = acc.checked_mul(base).ok_or("overflow")?;
    }
    if n < 0 {
        acc = Decimal::ONE.checked_div(acc).ok_or("division by zero")?;
    }
    Ok(acc)
}

fn call(name: &str, a: &[Decimal]) -> Result<Decimal, String> {
    let arity = |n: usize| {
        if a.len() == n {
            Ok(())
        } else {
            Err(format!("{name} takes {n} arguments, got {}", a.len()))
        }
    };
    match name {
        "abs" => arity(1).map(|()| a[0].abs()),
        "min" | "max" if a.len() < 2 => Err(format!("{name} takes two or more arguments")),
        "min" => Ok(a.iter().copied().fold(a[0], Decimal::min)),
        "max" => Ok(a.iter().copied().fold(a[0], Decimal::max)),
        "clamp" => {
            arity(3)?;
            if a[1] > a[2] {
                return Err("clamp needs lo <= hi".into());
            }
            Ok(a[0].max(a[1]).min(a[2]))
        }
        "ceil_to" => {
            arity(2).and_then(|()| step_op(a[0], a[1], RoundingStrategy::ToPositiveInfinity))
        }
        "floor_to" => {
            arity(2).and_then(|()| step_op(a[0], a[1], RoundingStrategy::ToNegativeInfinity))
        }
        "round_to" => {
            arity(2).and_then(|()| step_op(a[0], a[1], RoundingStrategy::MidpointAwayFromZero))
        }
        "ceil_cents" => arity(1).and_then(|()| {
            step_op(
                a[0],
                Decimal::new(1, 2),
                RoundingStrategy::ToPositiveInfinity,
            )
        }),
        "if" => arity(3).map(|()| if a[0].is_zero() { a[2] } else { a[1] }),
        _ => Err(format!("unknown function {name}")),
    }
}

fn truth(b: bool) -> Decimal {
    if b {
        Decimal::ONE
    } else {
        Decimal::ZERO
    }
}

/// Evaluate `e`, resolving names with `lookup`. Errors are plain messages.
pub fn eval<F>(e: &Expr, lookup: &mut F) -> Result<Decimal, String>
where
    F: FnMut(&str) -> Result<Decimal, String>,
{
    match e {
        Expr::Num(n) => Ok(*n),
        Expr::Name(n) => lookup(n),
        Expr::Neg(x) => Ok(-eval(x, lookup)?),
        Expr::Call(name, args) if name == "if" && args.len() == 3 => {
            // Only the chosen branch is evaluated, so the other may name unset inputs.
            if eval(&args[0], lookup)?.is_zero() {
                eval(&args[2], lookup)
            } else {
                eval(&args[1], lookup)
            }
        }
        Expr::Call(name, args) => {
            let vals = args
                .iter()
                .map(|x| eval(x, lookup))
                .collect::<Result<Vec<_>, _>>()?;
            call(name, &vals)
        }
        Expr::Cmp(op, l, r) => {
            let (l, r) = (eval(l, lookup)?, eval(r, lookup)?);
            Ok(truth(match *op {
                "<" => l < r,
                "<=" => l <= r,
                ">" => l > r,
                ">=" => l >= r,
                "==" => l == r,
                _ => l != r,
            }))
        }
        Expr::Bin(op, l, r) => {
            let (l, r) = (eval(l, lookup)?, eval(r, lookup)?);
            match op {
                '+' => l.checked_add(r).ok_or_else(|| "overflow".into()),
                '-' => l.checked_sub(r).ok_or_else(|| "overflow".into()),
                '*' => l.checked_mul(r).ok_or_else(|| "overflow".into()),
                '/' if r.is_zero() => Err("division by zero".into()),
                '/' => l.checked_div(r).ok_or_else(|| "overflow".into()),
                _ => pow(l, r),
            }
        }
    }
}
