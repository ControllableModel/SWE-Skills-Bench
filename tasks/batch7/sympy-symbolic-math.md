# Task: Add a first-order IVP solver utility to sympy.solvers.ode

## Background

The `sympy/solvers/ode/` subpackage solves ordinary differential equations. This task adds a small public utility that solves a first-order ODE together with an initial condition and returns the particular solution with the integration constant resolved exactly.

## Files to Create/Modify

- `sympy/solvers/ode/ivp.py` (new) — implements the public function described below.
- `sympy/solvers/ode/__init__.py` (modify) — export the new function so it is importable as `from sympy.solvers.ode import solve_ivp_symbolic`.
- `sympy/solvers/ode/tests/test_ivp.py` (new) — the deterministic test file covering the contract and edge cases below.

## Requirements

Implement a single public function `solve_ivp_symbolic(eq, func, ics)` in `sympy/solvers/ode/ivp.py`.

### Behavior

Given a first-order ODE `eq` (a SymPy `Eq` or an expression assumed equal to `0`) in an unknown function `func` (e.g. `f(x)`), and an initial condition `ics` given as a `dict` of the form `{func.subs(x, x0): y0}`, return a single SymPy `Eq` expressing `func` as a closed-form function of its independent variable, with the integration constant fully determined by the initial condition.

### Constraints and edge cases

- The returned solution MUST satisfy the initial condition exactly: substituting `x = x0` into the right-hand side MUST simplify to `y0`.
- The returned solution MUST satisfy the ODE: substituting it back into `eq` and simplifying MUST give a true/zero identity.
- All constants MUST be exact (e.g. `exp(1)`, `Rational`), never floating point.
- The right-hand side MUST contain no free integration constants (no leftover `C1`); the symbol `C1` MUST NOT appear in `result.rhs.free_symbols`.
- If the initial condition is inconsistent or the constant cannot be solved, the function MUST raise `ValueError` (it MUST NOT return a solution still containing `C1`).
- The independent variable is taken from `func.args[0]`.

### Expected Functionality

- `solve_ivp_symbolic(Eq(f(x).diff(x), f(x)), f(x), {f(0): 1})` -> `Eq(f(x), exp(x))`.
- `solve_ivp_symbolic(Eq(f(x).diff(x), 2*x), f(x), {f(0): 3})` -> right-hand side equal to `x**2 + 3`.
- `solve_ivp_symbolic(Eq(f(x).diff(x), f(x)), f(x), {f(0): 0})` -> `Eq(f(x), 0)`.
- For any returned solution `sol`, `sol.rhs.subs(x, x0)` simplifies to the given `y0`, and `C1 not in sol.rhs.free_symbols`.

## Acceptance Criteria

- `from sympy.solvers.ode import solve_ivp_symbolic` succeeds.
- The returned object is a SymPy `Eq` whose left-hand side is `func`.
- For each example, the right-hand side matches exactly after `simplify` (e.g. `simplify(sol.rhs - exp(x)) == 0`), the initial condition holds exactly, and no `C1` remains free.
- An unsolvable/inconsistent initial condition raises `ValueError`.
- The following command passes with all tests collected and green:

```bash
python -m pytest sympy/solvers/ode/tests/test_ivp.py -q
```
