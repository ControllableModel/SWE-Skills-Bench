# Task: Add a calculus LaTeX-report utility to sympy.printing

## Background

The `sympy/printing/` subpackage converts SymPy objects into formatted output, including LaTeX via `latex.py`. This task adds a public utility that produces a structured LaTeX report pairing an unevaluated calculus operation with its evaluated result.

## Files to Create/Modify

- `sympy/printing/mathreport.py` (new) — implements the public function described below.
- `sympy/printing/__init__.py` (modify) — export the new function so it is importable as `from sympy.printing import latex_derivative_report` and `from sympy.printing import latex_integral_report`.
- `sympy/printing/tests/test_mathreport.py` (new) — the deterministic test file covering the contract and edge cases below.

## Requirements

Implement two public functions in `sympy/printing/mathreport.py`.

### `latex_derivative_report(expr, x)`

Return a Python `dict` with exactly these string keys:

- `"operation"` — the LaTeX string of the unevaluated derivative of `expr` with respect to `x` (i.e. the LaTeX of `Derivative(expr, x)`, not yet computed).
- `"result"` — the LaTeX string of the evaluated derivative.
- `"equation"` — the LaTeX string `"<operation> = <result>"` (the two joined by `" = "`).

### `latex_integral_report(expr, x, a=None, b=None)`

Return a `dict` with the same three keys, for an integral of `expr` with respect to `x`. If both `a` and `b` are given, the operation is the definite integral `Integral(expr, (x, a, b))`; otherwise it is the indefinite `Integral(expr, x)`. The `"result"` is the LaTeX of the evaluated integral.

### Constraints and edge cases

- The `"operation"` LaTeX MUST come from the **unevaluated** `Derivative`/`Integral` object, so it MUST contain the LaTeX derivative/integral notation (e.g. the string contains `\frac{d}{d x}` for a derivative, and `\int` for an integral).
- The `"result"` MUST be the LaTeX of the **evaluated** expression and MUST match `latex(Derivative(expr, x).doit())` (respectively the integral) exactly.
- The `"equation"` value MUST be exactly `operation + " = " + result`.
- Each returned value MUST be a Python `str`.
- For a definite integral, both `a` and `b` MUST be provided; providing only one of them MUST raise `ValueError`.
- Inputs may be symbolic; the LaTeX output reflects the symbols.

### Expected Functionality

- `latex_derivative_report(x**2, x)["result"]` -> `"2 x"`.
- `latex_derivative_report(sin(x), x)["operation"]` -> contains `"\\frac{d}{d x}"`.
- `latex_integral_report(x**2, x)["result"]` -> `"\\frac{x^{3}}{3}"`.
- `latex_integral_report(x**2, x, 0, 1)["operation"]` -> contains `"\\int"` and the limits `0` and `1`.
- `latex_integral_report(x**2, x, 0, 1)["equation"]` -> equals `operation + " = " + result`.
- `latex_integral_report(x**2, x, 0)` -> raises `ValueError`.

## Acceptance Criteria

- `from sympy.printing import latex_derivative_report, latex_integral_report` succeeds.
- Each returned object is a `dict` with exactly the keys `{"operation", "result", "equation"}`, all string values.
- `"result"` equals `latex(...doit())` for the corresponding operation; `"operation"` contains the unevaluated derivative/integral notation; `"equation"` equals `operation + " = " + result`.
- Supplying only one definite limit raises `ValueError`.
- The following command passes with all tests collected and green:

```bash
python -m pytest sympy/printing/tests/test_mathreport.py -q
```
