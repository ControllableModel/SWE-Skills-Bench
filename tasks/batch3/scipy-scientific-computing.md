# Task: Add a tridiagonal boundary-value solver to scipy.linalg

## Background

The SciPy repository (`scipy/linalg`) provides structured-matrix solvers, but
has no single helper that assembles and solves the symmetric tridiagonal system
arising from a 1-D second-order boundary-value problem. This task adds such a
helper as a new private module inside `scipy/linalg`, with its own test suite.

## Files to Create/Modify

- `scipy/linalg/_tridiag_bvp.py` (new) — implementation of the solver.
- `scipy/linalg/meson.build` (modify) — add `_tridiag_bvp.py` to a
  `py3.install_sources([...])` list whose `subdir` is `'scipy/linalg'`.
- `scipy/linalg/tests/test_tridiag_bvp.py` (new) — deterministic unit tests.
- `scipy/linalg/tests/meson.build` (modify) — add `test_tridiag_bvp.py` to the
  `py3.install_sources([...])` list whose `subdir` is `'scipy/linalg/tests'`.

(The test file imports the implementation directly, e.g.
`from scipy.linalg._tridiag_bvp import solve_poisson_1d`. No change to the public
`scipy/linalg/__init__.py` API surface is required.)

## Requirements

### Public function

Implement a single function in `scipy/linalg/_tridiag_bvp.py`:

```
solve_poisson_1d(rhs, *, domain=(0.0, 1.0), bc=(0.0, 0.0))
```

with the following contract.

- The function solves the 1-D Poisson equation `-u''(x) = g(x)` on `[x0, x1]`
  with Dirichlet boundary conditions `u(x0)=bc[0]`, `u(x1)=bc[1]`, using a
  uniform interior grid and the standard 3-point finite-difference stencil.
- `rhs` is either a 1-D array-like giving `g` sampled at the `N` interior grid
  points, or a Python callable `g(x)` evaluated by the function at those points.
- `domain` is the `(x0, x1)` interval with `x0 < x1`.
- `bc` is the `(left, right)` Dirichlet boundary value pair.

The function returns a dictionary with exactly these keys:

- `"x"` — a 1-D float array of length `N+2` of grid coordinates including both
  boundary nodes, ascending and uniformly spaced.
- `"u"` — a 1-D float array of length `N+2` giving the solution at those nodes;
  `u[0]` and `u[-1]` must equal the supplied boundary values exactly.
- `"residual"` — a non-negative float: the maximum absolute value of
  `-u'' - g` evaluated by the discrete stencil at the interior nodes.

### Behavioral constraints

- The assembled coefficient matrix must be the symmetric tridiagonal Laplacian;
  the system must be solved without forming an explicit dense inverse.
- For problems with a known analytic solution, the numerical `"u"` must converge
  to the analytic solution as `N` grows, and the discrete `"residual"` must be at
  the level of floating-point round-off (not a large value).
- Boundary values must be honored exactly at `u[0]` and `u[-1]`.
- The function must not mutate a caller-supplied `rhs` array.

### Input validation (edge cases)

Raise `ValueError` with an informative message when:

- `rhs` is an array but is not 1-D or has fewer than 1 interior point.
- `domain` does not satisfy `x0 < x1`.
- `bc` is not a length-2 pair of finite numbers.

### Expected Functionality

- `-u'' = pi^2 sin(pi x)` on `[0,1]` with `bc=(0,0)` -> `"u"` ≈ `sin(pi x)`
  (max error shrinks as `N` increases) and `"residual"` ≈ 0.
- `-u'' = 0` with `bc=(1, 3)` -> `"u"` is the straight line from 1 to 3 (a
  harmonic function), recovered to round-off at every node.
- `-u'' = 2` with `bc=(0,0)` on `[0,1]` -> `"u"` ≈ `x(1-x)` (the analytic
  parabola).

## Acceptance Criteria

- A new module `scipy/linalg/_tridiag_bvp.py` exists and exposes
  `solve_poisson_1d` with the signature and return contract above.
- `scipy/linalg/tests/test_tridiag_bvp.py` exists with at least 10 test cases
  that, using `numpy.testing.assert_allclose` with appropriate tolerances,
  verify: the linear BC case is reproduced to round-off; the sinusoidal and
  parabolic cases match their analytic solutions and improve with grid
  refinement; boundary nodes equal the prescribed values exactly; `rhs` may be
  given as an array or a callable with identical results; `"residual"` is at the
  round-off level for solved systems; the input array is not mutated; and each
  invalid-input case raises `ValueError`.
- A naive or hardcoded implementation (e.g. linear interpolation between the
  boundary values, or ignoring `rhs`) must fail these tests.
- The following command passes from the repository root after building SciPy:

  ```
  python -m pytest scipy/linalg/tests/test_tridiag_bvp.py -v
  ```
