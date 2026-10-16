# Task: Add an arc-length utility to sympy.calculus

## Background

The `sympy/calculus/` subpackage groups focused calculus utilities (e.g. `finite_diff`, `singularities`, `util`). This task adds a new public utility that computes the exact symbolic arc length of a curve over an interval.

## Files to Create/Modify

- `sympy/calculus/arclength.py` (new) — implements the public function described below.
- `sympy/calculus/__init__.py` (modify) — export the new function so it is importable as `from sympy.calculus import arc_length`.
- `sympy/calculus/tests/test_arclength.py` (new) — the deterministic test file covering the contract and edge cases below.

## Requirements

Implement a single public function `arc_length(expr, x, a, b)` in `sympy/calculus/arclength.py`.

### Behavior

Given `y = expr` (a SymPy expression in the symbol `x`) and real limits `a < b`, return the exact symbolic arc length of the graph of `y = expr` from `x = a` to `x = b` — that is, the definite integral of `sqrt(1 + (dy/dx)**2)` over `[a, b]`, evaluated to a closed form when SymPy can do so.

### Constraints and edge cases

- The result MUST be exact. The arc length of `y = x` from `0` to `1` MUST equal `sqrt(2)`, never `1.4142...`.
- The derivative used MUST be the exact symbolic derivative of `expr` with respect to `x`.
- For a constant `expr` (no dependence on `x`), the arc length over `[a, b]` MUST simplify to `b - a`.
- The limits `a` and `b` may be SymPy constants such as `pi` or symbolic; returned expressions may then involve those symbols.
- If the closed-form integral cannot be evaluated by SymPy, the function MUST return an unevaluated `Integral` object (it MUST NOT raise and MUST NOT silently return a float).
- Requiring `a` and `b` such that they are not symbolically equal is NOT required; if `a == b` the result MUST simplify to `0`.

### Expected Functionality

- `arc_length(x, x, 0, 1)` -> equal to `sqrt(2)`.
- `arc_length(Integer(3), x, 0, 5)` -> simplifies to `5` (constant curve).
- `arc_length(x, x, 2, 2)` -> simplifies to `0`.
- `arc_length((2*x**Rational(3,2))/3, x, 0, 3)` -> simplifies to `Rational(14, 3)`.
- For an expression whose arc-length integral has no elementary closed form (e.g. `sin(x)` over `(0, pi)`), the result is an unevaluated `Integral`.

## Acceptance Criteria

- `from sympy.calculus import arc_length` succeeds.
- For each closed-form example, `simplify(arc_length(...) - expected) == 0` (exact symbolic equality, not floating point).
- A constant integrand yields `b - a`; equal limits yield `0`.
- A non-elementary case returns an object that `is` an instance of `sympy.Integral`.
- The following command passes with all tests collected and green:

```bash
python -m pytest sympy/calculus/tests/test_arclength.py -q
```
