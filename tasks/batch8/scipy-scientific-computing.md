# Task: Add a constrained budget-allocation optimizer to scipy.optimize

## Background

The SciPy repository (`scipy/optimize`) provides constrained minimizers, but has
no single helper that allocates a fixed budget across activities to maximize a
concave return subject to per-activity caps and a total-spend equality. This task
adds such a helper as a new private module inside `scipy/optimize`, with its own
test suite.

## Files to Create/Modify

- `scipy/optimize/_allocate.py` (new) — implementation of the allocator.
- `scipy/optimize/meson.build` (modify) — add `_allocate.py` to a
  `py3.install_sources([...])` list whose `subdir` is `'scipy/optimize'`.
- `scipy/optimize/tests/test_allocate.py` (new) — deterministic unit tests.
- `scipy/optimize/tests/meson.build` (modify) — add `test_allocate.py` to the
  `py3.install_sources([...])` list whose `subdir` is `'scipy/optimize/tests'`.

(The test file imports the implementation directly, e.g.
`from scipy.optimize._allocate import allocate_budget`. No change to the public
`scipy/optimize/__init__.py` API surface is required.)

## Requirements

### Public function

Implement a single function in `scipy/optimize/_allocate.py`:

```
allocate_budget(gains, budget, *, caps=None)
```

with the following contract.

- Each activity `i` has a diminishing-returns payoff `gains[i] * sqrt(x_i)` where
  `x_i >= 0` is the amount allocated to it; the objective is to maximize the total
  payoff `sum_i gains[i] * sqrt(x_i)`.
- `gains` is a 1-D array-like of `n` strictly positive marginal-gain coefficients.
- `budget` is the total amount that must be fully allocated:
  `sum_i x_i == budget` exactly (an equality constraint), with `budget > 0`.
- `caps`, when given, is a length-`n` array-like of per-activity upper bounds
  `x_i <= caps[i]`; `None` means unbounded above.

The function returns a dictionary with exactly these keys:

- `"x"` — a 1-D float array of length `n`, the optimal non-negative allocation.
- `"payoff"` — a float: the achieved total payoff at `"x"`.
- `"success"` — a bool reflecting whether the optimizer reported convergence.

### Behavioral constraints

- The returned `"x"` must sum to `budget` (to tight tolerance), have all
  components `>= 0`, and respect `caps` when supplied.
- For the uncapped concave problem the optimum is unique; the returned `"x"` must
  match the analytic solution (allocation proportional to `gains[i]**2`).
- The achieved `"payoff"` must be at least that of any simple feasible baseline
  (e.g. equal split), confirming a genuine maximization rather than an arbitrary
  feasible point.
- When `caps` bind, saturated activities must sit exactly at their cap and the
  remaining budget must redistribute among unsaturated activities.
- Inputs must not be mutated.

### Input validation (edge cases)

Raise `ValueError` with an informative message when:

- `gains` is empty, not 1-D, or contains a non-positive entry.
- `budget <= 0`.
- `caps` is provided with the wrong length, a negative entry, or a total cap
  `sum(caps) < budget` (the equality constraint then being infeasible).

### Expected Functionality

- `gains=[1,1]`, `budget=10`, no caps -> `"x"` ≈ `[5,5]` (symmetric optimum) and
  `"payoff"` equals the analytic maximum.
- `gains=[2,1]`, `budget=5`, no caps -> allocation skewed toward activity 0 in
  the analytic `gains**2` proportion, summing to 5.
- `gains=[1,1,1]`, `budget=9`, `caps=[2, 100, 100]` -> activity 0 pinned at `2`,
  the rest split optimally; total still `9`.

## Acceptance Criteria

- A new module `scipy/optimize/_allocate.py` exists and exposes `allocate_budget`
  with the signature and return contract above.
- `scipy/optimize/tests/test_allocate.py` exists with at least 10 test cases
  that, using `numpy.testing.assert_allclose` / inequality assertions, verify:
  the allocation sums to `budget` and is non-negative; the uncapped optimum
  matches the analytic `gains**2` proportion; the achieved `"payoff"` beats an
  equal-split baseline; binding caps are saturated exactly with correct
  redistribution; `"success"` is True on solvable problems; inputs are not
  mutated; and each invalid-input case raises `ValueError`.
- A naive or hardcoded implementation (e.g. an even split regardless of `gains`,
  or ignoring `caps`) must fail these tests.
- The following command passes from the repository root after building SciPy:

  ```
  python -m pytest scipy/optimize/tests/test_allocate.py -v
  ```
