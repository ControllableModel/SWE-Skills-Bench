# Task: Add a monotone resampling interpolator to scipy.interpolate

## Background

The SciPy repository (`scipy/interpolate`) provides spline and grid
interpolators, but has no single helper that resamples a strictly-increasing
function onto a new abscissa while preserving monotonicity and reporting whether
the request stayed inside the data range. This task adds such a helper as a new
private module inside `scipy/interpolate`, with its own test suite.

## Files to Create/Modify

- `scipy/interpolate/_monoresample.py` (new) — implementation of the resampler.
- `scipy/interpolate/meson.build` (modify) — add `_monoresample.py` to a
  `py3.install_sources([...])` list whose `subdir` is `'scipy/interpolate'`.
- `scipy/interpolate/tests/test_monoresample.py` (new) — deterministic unit tests.
- `scipy/interpolate/tests/meson.build` (modify) — add `test_monoresample.py` to
  the `py3.install_sources([...])` list whose `subdir` is
  `'scipy/interpolate/tests'`.

(The test file imports the implementation directly, e.g.
`from scipy.interpolate._monoresample import resample_monotone`. No change to the
public `scipy/interpolate/__init__.py` API surface is required.)

## Requirements

### Public function

Implement a single function in `scipy/interpolate/_monoresample.py`:

```
resample_monotone(x, y, x_new, *, extrapolate=False)
```

with the following contract.

- `x` is a 1-D, strictly increasing array-like of sample abscissae.
- `y` is a 1-D array-like the same length as `x` of monotonically non-decreasing
  sample values (a calibration curve).
- `x_new` is a 1-D array-like of query abscissae.
- `extrapolate` controls whether queries outside `[x[0], x[-1]]` are allowed.

The function returns a dictionary with exactly these keys:

- `"y_new"` — a 1-D float array, the interpolated values at `x_new`, preserving
  the monotonic (non-decreasing) ordering of the source data: if `x_new` is
  sorted ascending then `"y_new"` must be non-decreasing.
- `"in_range"` — a 1-D boolean array, the same length as `x_new`, marking which
  queries fell within `[x[0], x[-1]]`.
- `"n_extrapolated"` — an int: the count of queries that fell outside the data
  range.

### Behavioral constraints

- The interpolant must reproduce the source samples exactly at the original `x`
  (interpolation, not smoothing): querying `x` returns `y`.
- For monotone source data and a sorted query grid, `"y_new"` must contain no
  overshoot below the local minimum or above the local maximum of the bracketing
  samples and must stay non-decreasing.
- When `extrapolate` is `False`, any out-of-range query must raise; when `True`,
  out-of-range queries are filled by continuing the interpolant and counted in
  `"n_extrapolated"`, with `"in_range"` `False` for those entries.
- The function must not mutate `x`, `y`, or `x_new`.

### Input validation (edge cases)

Raise `ValueError` with an informative message when:

- `x` and `y` differ in length, or have fewer than 2 samples.
- `x` is not strictly increasing.
- `y` is not monotonically non-decreasing.
- `extrapolate` is `False` and any element of `x_new` lies outside
  `[x[0], x[-1]]`.

### Expected Functionality

- Querying the original `x` returns the original `y` exactly.
- A linear calibration `y = 2x + 1` sampled coarsely and queried densely ->
  `"y_new"` ≈ `2*x_new + 1`, all `"in_range"` True, `"n_extrapolated"` == 0.
- A sorted dense query on a non-decreasing curve -> `"y_new"` is non-decreasing
  (no oscillation).
- With `extrapolate=True` and queries past both ends -> those entries are
  `"in_range"` False and `"n_extrapolated"` counts them.

## Acceptance Criteria

- A new module `scipy/interpolate/_monoresample.py` exists and exposes
  `resample_monotone` with the signature and return contract above.
- `scipy/interpolate/tests/test_monoresample.py` exists with at least 10 test
  cases that, using `numpy.testing.assert_allclose` / boolean assertions, verify:
  exact reproduction at source nodes; correct linear-calibration values;
  monotonicity of `"y_new"` on sorted queries with no overshoot; `"in_range"` and
  `"n_extrapolated"` are correct for mixed in/out queries; out-of-range raises
  when `extrapolate` is False; inputs are not mutated; and each invalid-input case
  raises `ValueError`.
- A naive or hardcoded implementation (e.g. nearest-neighbor lookup, or an
  unconstrained high-order interpolant that overshoots, or ignoring the range
  check) must fail these tests.
- The following command passes from the repository root after building SciPy:

  ```
  python -m pytest scipy/interpolate/tests/test_monoresample.py -v
  ```
