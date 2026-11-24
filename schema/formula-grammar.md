# Formula grammar

Fee, margin and funding rules are stored as formula strings so a rule change is a data change. The Rust crate evaluates them in exact decimal arithmetic (28 significant digits), never in binary floating point, so `0.07 * 100 * 0.25` is exactly `1.75`.

## Syntax

```
expr       := comparison
comparison := sum (("<" | "<=" | ">" | ">=" | "==" | "!=") sum)?
sum        := product (("+" | "-") product)*
product    := unary (("*" | "/") unary)*
unary      := "-" unary | power
power      := primary ("^" unary)?
primary    := number | name | call | "(" expr ")"
call       := ident "(" expr ("," expr)* ")"
name       := ident ("." ident)*
ident      := [A-Za-z_][A-Za-z0-9_]*
number     := [0-9]+ ("." [0-9]+)?
```

`^` takes an integer exponent. A comparison yields `1` or `0`.

## Functions

| Function | Meaning |
| --- | --- |
| `abs(x)` | Absolute value |
| `min(a, b, ...)`, `max(a, b, ...)` | Smallest, largest of two or more |
| `clamp(x, lo, hi)` | `min(max(x, lo), hi)` |
| `ceil_to(x, step)` | Smallest multiple of `step` that is `>= x` |
| `floor_to(x, step)` | Largest multiple of `step` that is `<= x` |
| `round_to(x, step)` | Nearest multiple of `step`, ties away from zero |
| `ceil_cents(x)` | `ceil_to(x, 0.01)` |
| `if(cond, a, b)` | `a` when `cond` is not zero, else `b` |

## Names

A dotted name such as `fees.rounding.trade_fee_step` is a path from the top of the spec. A bare name such as `coef` is looked up in this order:

1. Inputs the caller passes (for example `C` and `P`).
2. Siblings of the formula, the other entries in the same object.
3. The rows the caller selects, for example `category="crypto"` selects `fees.categories.crypto`, and `tier="0"` selects `fees.tiers.0`.
4. Entries of each enclosing object, walking up to the top of the spec.

A name that resolves to another formula is evaluated first, so formulas can build on each other. A name that resolves to an unverified entry, or to nothing in force at the requested time, is an error, never a silent zero.

## Input names

Each formula's leaf `note` says which inputs it takes. The packages accept these long names as aliases:

| Alias | Formula name |
| --- | --- |
| `contracts` | `C` |
| `price` | `P` |
| `quantity` | `Q` |
| `notional` | `N` |
