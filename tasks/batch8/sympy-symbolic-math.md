# Task: Add a series-coefficient extraction utility to sympy.series

## Background

The `sympy/series/` subpackage handles power series, limits and asymptotics. This task adds a public utility that returns the list of exact Maclaurin/Taylor coefficients of an expression up to a requested order.

## Files to Create/Modify

- `sympy/series/coeffs.py` (new) — implements the public function described below.
- `sympy/series/__init__.py` (modify) — export the new function so it is importable as `from sympy.series import series_coefficients`.
- `sympy/series/tests/test_coeffs.py` (new) — the deterministic test file covering the contract and edge cases below.

## Requirements

Implement a single public function `series_coefficients(expr, x, n, x0=0)` in `sympy/series/coeffs.py`.

### Behavior

Given a SymPy `expr` in the symbol `x`, a non-negative integer `n`, and an expansion point `x0`, return a Python `list` of length `n + 1` whose entry at index `k` is the exact coefficient of `(x - x0)**k` in the power-series expansion of `expr` about `x = x0`.

### Constraints and edge cases

- Coefficients MUST be exact SymPy values. The index-`2` coefficient of `exp(x)` about `0` MUST be `Rational(1, 2)`, never `0.5`.
- The returned list MUST have exactly `n + 1` entries (indices `0..n` inclusive).
- Coefficients that are mathematically zero MUST be returned as the SymPy integer `0` (e.g. for `cos(x)` about `0`, the index-`1` and index-`3` entries are `0`).
- `n` MUST be a non-negative integer; a negative `n` MUST raise `ValueError`.
- For a polynomial `expr`, indices beyond its degree MUST be `0`, and the lower indices MUST reproduce the polynomial's coefficients exactly.
- `x0` may be a number, a SymPy constant such as `pi`, or another symbol; returned coefficients may then involve that symbol.
- The result MUST NOT contain any `O(...)` order term.

### Expected Functionality

- `series_coefficients(exp(x), x, 3)` -> `[1, 1, Rational(1, 2), Rational(1, 6)]`.
- `series_coefficients(cos(x), x, 4)` -> `[1, 0, Rational(-1, 2), 0, Rational(1, 24)]`.
- `series_coefficients(1/(1 - x), x, 4)` -> `[1, 1, 1, 1, 1]`.
- `series_coefficients(x**2 + 3, x, 5)` -> `[3, 0, 1, 0, 0, 0]`.
- `series_coefficients(exp(x), x, 2, x0=1)` -> index-0 entry equals `E`.
- `series_coefficients(sin(x), x, -1)` -> raises `ValueError`.

## Acceptance Criteria

- `from sympy.series import series_coefficients` succeeds.
- The returned list has length `n + 1` for each call.
- Each coefficient is an exact SymPy value matching the examples (e.g. `series_coefficients(exp(x), x, 3)[2] == Rational(1, 2)` is `True`); zero coefficients are the SymPy `0`.
- A negative `n` raises `ValueError`.
- The following command passes with all tests collected and green:

```bash
python -m pytest sympy/series/tests/test_coeffs.py -q
```
