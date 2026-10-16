# Task: Add a sparse grid-graph Laplacian solver to scipy.sparse

## Background

The SciPy repository (`scipy/sparse`) provides sparse matrix formats and
iterative solvers, but has no single helper that builds the graph Laplacian of a
2-D grid as a sparse matrix and solves a steady-state diffusion problem on it.
This task adds such a helper as a new private module inside `scipy/sparse`, with
its own test suite.

## Files to Create/Modify

- `scipy/sparse/_gridlaplace.py` (new) — implementation of the builder/solver.
- `scipy/sparse/meson.build` (modify) — add `_gridlaplace.py` to the
  `py3.install_sources([...])` list whose `subdir` is `'scipy/sparse'`.
- `scipy/sparse/tests/test_gridlaplace.py` (new) — deterministic unit tests.
- `scipy/sparse/tests/meson.build` (modify) — add `test_gridlaplace.py` to the
  `py3.install_sources([...])` list whose `subdir` is `'scipy/sparse/tests'`.

(The test file imports the implementation directly, e.g.
`from scipy.sparse._gridlaplace import grid_laplacian, solve_steady_state`. No
change to the public `scipy/sparse/__init__.py` API surface is required.)

## Requirements

### Public functions

Implement two functions in `scipy/sparse/_gridlaplace.py`:

```
grid_laplacian(nx, ny)
solve_steady_state(nx, ny, source, *, fixed=None)
```

with the following contract.

- `grid_laplacian(nx, ny)` returns a sparse matrix (CSR) of shape
  `(nx*ny, nx*ny)` representing the 5-point graph Laplacian of an `nx`-by-`ny`
  grid with row-major node numbering. Each interior node connects to its 4
  orthogonal neighbours; the diagonal equals each node's degree and off-diagonal
  entries are `-1` for adjacent nodes.
- `solve_steady_state(nx, ny, source, *, fixed)` solves `L u = source` for the
  node potentials `u`, where `source` is a length-`nx*ny` array-like of injected
  values. `fixed`, when given, is a dict mapping flat node indices to fixed
  potential values (Dirichlet anchors); those nodes' potentials are pinned and
  the rest solved consistently.

`solve_steady_state` returns a dictionary with exactly these keys:

- `"u"` — a 1-D float array of length `nx*ny`, the solved node potentials.
- `"residual"` — a non-negative float: the maximum absolute residual of the
  governing equations at the non-anchored nodes.
- `"nnz"` — an int: the number of stored nonzeros in the Laplacian used.

### Behavioral constraints

- The Laplacian must be symmetric, each row must sum to zero, and the off-diagonal
  sparsity pattern must exactly match grid adjacency (no spurious nonzeros).
- The matrix must be stored and solved in a sparse format; it must not be
  densified to solve.
- With a single source node and a single sink anchored to `0`, the solved `"u"`
  must satisfy the discrete balance at every interior node (`"residual"` at
  round-off level).
- Anchored nodes in `fixed` must equal their prescribed values in `"u"` exactly.
- Inputs must not be mutated.

### Input validation (edge cases)

Raise `ValueError` with an informative message when:

- `nx < 1` or `ny < 1`.
- `source` length is not `nx*ny`.
- `fixed` contains an index outside `[0, nx*ny)`.
- The system is singular and `fixed` provides no anchor (an all-Neumann pure
  Laplacian with nonzero net source has no solution).

### Expected Functionality

- `grid_laplacian(3, 3)` -> a 9x9 symmetric matrix whose rows sum to zero, with
  corner nodes having degree 2, edge nodes degree 3, the centre degree 4.
- A 5x5 grid with `source` injecting `+1` at one corner, `-1` at the opposite
  corner, and that opposite corner anchored to `0` -> a consistent `"u"` with
  `"residual"` ≈ 0.
- `"nnz"` equals the analytic count of grid edges (times two) plus diagonal
  entries.

## Acceptance Criteria

- A new module `scipy/sparse/_gridlaplace.py` exists and exposes `grid_laplacian`
  and `solve_steady_state` with the signatures and return contract above.
- `scipy/sparse/tests/test_gridlaplace.py` exists with at least 10 test cases
  that, using `numpy.testing.assert_allclose` / exact assertions, verify:
  Laplacian symmetry and zero row sums; correct degrees for corner/edge/interior
  nodes; the adjacency sparsity pattern and `"nnz"` count; the solved potentials
  satisfy the discrete balance with round-off `"residual"`; anchored nodes equal
  their fixed values exactly; the matrix is a sparse type (not dense); inputs are
  not mutated; and each invalid-input case raises `ValueError`.
- A naive or hardcoded implementation (e.g. a dense identity, a wrong stencil, or
  ignoring `fixed`) must fail these tests.
- The following command passes from the repository root after building SciPy:

  ```
  python -m pytest scipy/sparse/tests/test_gridlaplace.py -v
  ```
