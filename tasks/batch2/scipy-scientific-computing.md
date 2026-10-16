# Task: Add a robust nonlinear decay-curve fitter to scipy.optimize

## Background

The SciPy repository (`scipy/optimize`) ships general curve-fitting machinery
but has no single helper that fits a fixed exponential-decay-plus-offset model
to noisy measurements and reports both the recovered parameters and quantitative
fit-quality diagnostics. This task adds such a helper as a new private module
inside `scipy/optimize`, with its own test suite.

## Files to Create/Modify

- `scipy/optimize/_decayfit.py` (new) — implementation of the fitter.
- `scipy/optimize/meson.build` (modify) — add `_decayfit.py` to a
  `py3.install_sources([...])` list whose `subdir` is `'scipy/optimize'` so the
  new module is installed/importable.
- `scipy/optimize/tests/test_decayfit.py` (new) — deterministic unit tests.
- `scipy/optimize/tests/meson.build` (modify) — add `test_decayfit.py` to the
  `py3.install_sources([...])` list whose `subdir` is `'scipy/optimize/tests'`.

(The test file imports the implementation directly, e.g.
`from scipy.optimize._decayfit import fit_decay`. No change to the public
`scipy/optimize/__init__.py` API surface is required.)

## Requirements

### Public function

Implement a single function in `scipy/optimize/_decayfit.py`:

```
fit_decay(t, y, *, p0=None, bounds=None)
```

with the following contract.

- `t` is a 1-D, real-valued, strictly increasing array-like of sample times.
- `y` is a 1-D array-like of the same length as `t` holding the measured values.
- The fixed model is `f(t) = a * exp(-b * t) + c`, with `a`, `b`, `c` the three
  parameters to recover and `b > 0`.
- `p0` is an optional initial guess `(a, b, c)`; when `None`, a sensible
  data-derived guess must be formed automatically so the fit converges without
  the caller supplying one.
- `bounds`, when given, is a pair of `(lower, upper)` 3-vectors constraining
  `(a, b, c)`; the returned parameters must respect these bounds.

The function returns a dictionary with exactly these keys:

- `"params"` — a length-3 float array `(a, b, c)` of the fitted parameters.
- `"residual_rms"` — a non-negative float: the root-mean-square of
  `y - f(t; params)`.
- `"r_squared"` — the coefficient of determination of the fit, a float in
  `(-inf, 1]` where `1.0` denotes a perfect fit.

### Behavioral constraints

- Given data generated from the model with known `(a, b, c)` and small additive
  noise, the recovered `"params"` must match the ground truth within a tight
  tolerance and `"r_squared"` must be very close to `1.0`.
- `"residual_rms"` must equal the RMS of the actual residuals for the returned
  parameters (self-consistency).
- The fit must converge starting from the automatic `p0` for at least one
  well-conditioned data set without the caller providing `p0`.
- When `bounds` are supplied, every returned parameter must lie within
  `[lower, upper]`.
- The function must not mutate the caller's `t` or `y` arrays.

### Input validation (edge cases)

Raise `ValueError` with an informative message when:

- `t` and `y` have different lengths, or fewer than 4 samples (3 parameters need
  at least 4 points for an over-determined fit).
- `t` is not strictly increasing.
- `bounds` is provided but is not a pair of length-3 vectors with
  `lower <= upper` elementwise.

If the underlying optimization fails to converge, raise `RuntimeError` with a
message that mentions non-convergence rather than returning a bogus result.

### Expected Functionality

- Data from `a=3.0, b=0.5, c=1.0` over `t in [0, 10]` with tiny noise ->
  `"params"` ≈ `[3.0, 0.5, 1.0]` and `"r_squared"` ≈ `1.0`.
- A flat constant signal `y = c` -> `b` recovered near `0` (or the offset `c`
  dominating), `"residual_rms"` ≈ `0`.
- Passing `bounds=([0,0,0],[10,1,5])` clamps each returned parameter into range.

## Acceptance Criteria

- A new module `scipy/optimize/_decayfit.py` exists and exposes `fit_decay` with
  the signature and return contract above.
- `scipy/optimize/tests/test_decayfit.py` exists with at least 10 test cases that,
  using `numpy.testing.assert_allclose` with appropriate tolerances, verify:
  parameters are recovered from synthetic clean data; `"r_squared"` ≈ 1 on a good
  fit and lower on a poor fit; `"residual_rms"` matches recomputed residuals;
  automatic `p0` produces convergence without a user guess; bounds are respected;
  inputs are not mutated; and each invalid-input case raises the documented
  exception.
- A naive or hardcoded implementation (e.g. always returning `p0`, or fitting a
  straight line, or ignoring `bounds`) must fail these tests.
- The following command passes from the repository root after building SciPy:

  ```
  python -m pytest scipy/optimize/tests/test_decayfit.py -v
  ```
