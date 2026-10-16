# Task: Add a characteristic-data utility for square matrices to sympy.matrices

## Background

The `sympy/matrices/` subpackage already ships eigen utilities in `eigen.py`. This task adds a small public utility module that, given a square SymPy `Matrix`, returns a structured bundle of its characteristic data computed with exact arithmetic.

## Files to Create/Modify

- `sympy/matrices/charutil.py` (new) — implements the public function described below.
- `sympy/matrices/__init__.py` (modify) — export the new function so it is importable as `from sympy.matrices import characteristic_data`.
- `sympy/matrices/tests/test_charutil.py` (new) — the deterministic test file covering the contract and edge cases below.

## Requirements

Implement a single public function `characteristic_data(M, lam=None)` in `sympy/matrices/charutil.py`.

### Behavior

Given a square SymPy `Matrix` `M` and an optional symbol `lam` (the variable used for the characteristic polynomial), return a Python `dict` with exactly these string keys:

- `"char_poly"` — the characteristic polynomial of `M` as a SymPy expression in `lam`, expanded into a sum of monomials. If `lam` is `None`, a symbol named `lambda` is used internally.
- `"trace"` — the trace of `M` as a SymPy expression.
- `"determinant"` — the determinant of `M` as a SymPy expression.
- `"eigenvalues"` — a `dict` mapping each eigenvalue (SymPy expression) to its algebraic multiplicity (a Python/SymPy integer).

### Constraints and edge cases

- All values MUST be exact. For `Matrix([[2, 0], [0, 3]])` the determinant MUST be the integer `6`, never `6.0`.
- The characteristic polynomial MUST be monic up to sign exactly as produced by expanding `det(M - lam*I)`; evaluating it at any eigenvalue MUST give `0` after `simplify`.
- The sum of the eigenvalue multiplicities MUST equal the number of rows of `M`.
- Passing a non-square matrix MUST raise `sympy.matrices.exceptions.NonSquareMatrixError` (or its alias importable from `sympy.matrices`).
- The function MUST accept matrices whose entries are symbolic; e.g. for `Matrix([[a, 0], [0, a]])` the determinant is `a**2` and the trace is `2*a`.

### Expected Functionality

- `characteristic_data(Matrix([[1, 2], [2, 1]]))["eigenvalues"]` -> equals `{3: 1, -1: 1}`.
- `characteristic_data(Matrix([[2, 0], [0, 3]]))["trace"]` -> `5`; `["determinant"]` -> `6`.
- For `M = Matrix([[0, -1], [1, 0]])`, substituting an eigenvalue into `["char_poly"]` gives `0`.
- `characteristic_data(Matrix([[1, 2, 3], [4, 5, 6]]))` -> raises a non-square error.

## Acceptance Criteria

- `from sympy.matrices import characteristic_data` succeeds.
- The returned object is a `dict` with exactly the four keys named above.
- Each example above matches exactly (exact integers/expressions, not floats); for every eigenvalue `e`, `simplify(char_poly.subs(lam, e)) == 0`.
- A non-square input raises the documented error.
- The following command passes with all tests collected and green:

```bash
python -m pytest sympy/matrices/tests/test_charutil.py -q
```
