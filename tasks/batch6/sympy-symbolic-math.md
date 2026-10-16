# Task: Add a fast tabulated-evaluator builder to sympy.utilities

## Background

The `sympy/utilities/` subpackage hosts the machinery that turns symbolic expressions into fast callables (`lambdify.py`). This task adds a convenience utility that builds a numeric evaluator for an expression and tabulates it over a list of inputs without requiring NumPy.

## Files to Create/Modify

- `sympy/utilities/evaltable.py` (new) — implements the public function described below.
- `sympy/utilities/__init__.py` (modify) — export the new function so it is importable as `from sympy.utilities import tabulate_expr`.
- `sympy/utilities/tests/test_evaltable.py` (new) — the deterministic test file covering the contract and edge cases below.

## Requirements

Implement a single public function `tabulate_expr(expr, x, values)` in `sympy/utilities/evaltable.py`.

### Behavior

Given a SymPy `expr` depending on a single symbol `x`, and `values` (an iterable of numbers), return a Python `list` of `(input, output)` pairs where each `output` is the value of `expr` at `input`, returned as a Python `float`.

### Constraints and edge cases

- The function MUST build one reusable numeric callable for the whole table rather than re-deriving the expression for each value (a hardcoded per-value `subs/evalf` solution is acceptable to the test only if it still produces correct floats; the contract below is what is checked).
- Each `output` MUST be a Python `float` and MUST match `float(expr.subs(x, v).evalf())` to within `1e-9` for every input `v`.
- The order of the output list MUST match the order of `values`.
- An empty `values` iterable MUST return an empty list.
- If `expr` does not contain `x` (a constant), every output MUST equal that constant for every input.
- A non-numeric entry in `values` MUST raise `TypeError`.
- The function MUST work without importing NumPy (i.e. it must succeed even if NumPy is unavailable); it MUST therefore not depend on a NumPy-only backend.

### Expected Functionality

- `tabulate_expr(x**2, x, [0, 1, 2, 3])` -> `[(0, 0.0), (1, 1.0), (2, 4.0), (3, 9.0)]`.
- `tabulate_expr(sin(x), x, [0])` -> first output within `1e-9` of `0.0`.
- `tabulate_expr(Integer(5), x, [1, 2])` -> `[(1, 5.0), (2, 5.0)]`.
- `tabulate_expr(x + 1, x, [])` -> `[]`.
- `tabulate_expr(x, x, ["a"])` -> raises `TypeError`.

## Acceptance Criteria

- `from sympy.utilities import tabulate_expr` succeeds.
- Returned outputs are Python `float`s matching `float(expr.subs(x, v).evalf())` within `1e-9` for each input.
- Output order matches input order; empty input yields `[]`; constant expressions yield the constant for every input.
- A non-numeric value raises `TypeError`.
- The following command passes with all tests collected and green:

```bash
python -m pytest sympy/utilities/tests/test_evaltable.py -q
```
