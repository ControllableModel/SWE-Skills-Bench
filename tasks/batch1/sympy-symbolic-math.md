# Task: Add a local polynomial approximation utility to sympy.calculus

## Background

The `sympy/calculus/` subpackage already ships focused utilities such as `finite_diff` and `singularities`. This task adds a new public utility for building the degree-`n` *local polynomial approximation* of a univariate symbolic expression about a chosen base point, together with a helper that returns an individual approximation coefficient.

## Files to Create/Modify

- `sympy/calculus/taylor.py` (new) — implements the two public functions described below.
- `sympy/calculus/__init__.py` (modify) — export the two new functions so they are importable as `from sympy.calculus import taylor_polynomial, taylor_coefficient`.
- `sympy/calculus/tests/test_taylor.py` (new) — the deterministic test file covering the contract and edge cases below.

## Requirements

Implement two public functions in `sympy/calculus/taylor.py`.

### `taylor_polynomial(expr, x, x0, n)`

Given a SymPy expression `expr` that depends on the symbol `x`, a base point `x0` (a number, a SymPy constant such as `pi`, or another symbol), and a non-negative integer `n`, return a single SymPy expression equal to the degree-`n` local polynomial approximation of `expr` about `x = x0`.

- The returned object MUST be an ordinary SymPy expression with **no order/remainder term** attached (it must not contain an `O(...)` factor).
- The approximation MUST be expressed in powers of `(x - x0)`. For example, the degree-2 approximation of `exp(x)` about `x0 = 1` is `E + E*(x - 1) + E*(x - 1)**2/2`, and `taylor_polynomial(...)` returned for `x0 = 1` must be mathematically equal to that, i.e. `sympy.expand(result - (E + E*(x-1) + E*(x-1)**2/2))` simplifies to `0`.
- All coefficients MUST be produced with **exact arithmetic** — e.g. the `x**3` coefficient of the approximation of `exp(x)` about `0` must be the exact rational `1/6`, never a floating-point value like `0.16666...`.

### `taylor_coefficient(expr, x, x0, k)`

Return the single exact coefficient that multiplies `(x - x0)**k` in the local polynomial approximation of `expr` about `x = x0`, where `k` is a non-negative integer. The result is a SymPy expression (a number, constant, or expression in the remaining symbols), again using exact arithmetic.

### Constraints and edge cases

- `n` and `k` must be non-negative integers; a negative value MUST raise `ValueError`.
- `n = 0` yields the constant approximation `expr` evaluated at `x0`; `taylor_coefficient(..., k=0)` returns that same constant.
- If `expr` does not contain `x`, the degree-`n` approximation is `expr` itself for any `n`, and every coefficient with `k >= 1` is `0`.
- For a polynomial `expr` whose degree is `d`, choosing `n >= d` MUST reproduce the polynomial **exactly** (every higher coefficient is `0`).
- Coefficients/terms that are mathematically zero MUST come back as `0` (e.g. for `cos(x)` about `0`, the `k = 3` coefficient is `0`).
- `x0` may itself be symbolic; the returned expressions may then involve that symbol.

### Expected Functionality

- `taylor_polynomial(exp(x), x, 0, 3)` -> equal to `1 + x + x**2/2 + x**3/6`.
- `taylor_polynomial(cos(x), x, 0, 4)` -> equal to `1 - x**2/2 + x**4/24`.
- `taylor_polynomial(1/(1 - x), x, 0, 3)` -> equal to `1 + x + x**2 + x**3`.
- `taylor_polynomial(x**3 + 2*x + 1, x, 0, 5)` -> equal to `x**3 + 2*x + 1` (exact, no spurious terms).
- `taylor_coefficient(exp(x), x, 0, 3)` -> `Rational(1, 6)`.
- `taylor_coefficient(cos(x), x, 0, 2)` -> `Rational(-1, 2)`; `taylor_coefficient(cos(x), x, 0, 3)` -> `0`.
- `taylor_coefficient(exp(x), x, 1, 0)` -> `E`.
- `taylor_polynomial(sin(x), x, 0, -1)` -> raises `ValueError`.

## Acceptance Criteria

- `from sympy.calculus import taylor_polynomial, taylor_coefficient` succeeds.
- Returned approximations contain no order term: `taylor_polynomial(exp(x), x, 0, 3).getO()` is `None`.
- For each `(expr, x0, n)` example above, `sympy.expand(taylor_polynomial(expr, x, x0, n) - expected)` equals `0` (exact symbolic equality, not floating point).
- Each coefficient example returns the exact SymPy value shown (e.g. `taylor_coefficient(exp(x), x, 0, 3) == Rational(1, 6)` is `True`), and zero coefficients are returned as the SymPy `0`.
- Negative `n` or `k` raises `ValueError`.
- The following command passes with all tests collected and green:

```bash
python -m pytest sympy/calculus/tests/test_taylor.py -q
```
