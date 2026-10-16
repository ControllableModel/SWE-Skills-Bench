# Task: Add a distribution fit-and-goodness reporter to scipy.stats

## Background

The SciPy repository (`scipy/stats`) exposes many continuous distributions and a
generic fitting interface, but has no single helper that fits a named
distribution to a sample, returns its estimated parameters, and quantifies how
well the fit describes the data. This task adds such a helper as a new private
module inside `scipy/stats`, with its own test suite.

## Files to Create/Modify

- `scipy/stats/_distfit_report.py` (new) — implementation of the reporter.
- `scipy/stats/meson.build` (modify) — add `_distfit_report.py` to a
  `py3.install_sources([...])` list whose `subdir` is `'scipy/stats'`.
- `scipy/stats/tests/test_distfit_report.py` (new) — deterministic unit tests.
- `scipy/stats/tests/meson.build` (modify) — add `test_distfit_report.py` to the
  `py3.install_sources([...])` list whose `subdir` is `'scipy/stats/tests'`.

(The test file imports the implementation directly, e.g.
`from scipy.stats._distfit_report import fit_and_assess`. No change to the public
`scipy/stats/__init__.py` API surface is required.)

## Requirements

### Public function

Implement a single function in `scipy/stats/_distfit_report.py`:

```
fit_and_assess(data, dist, *, alpha=0.05)
```

with the following contract.

- `data` is a 1-D, real-valued, finite array-like sample.
- `dist` is the name of a continuous distribution as a string (e.g. `"norm"`,
  `"expon"`, `"gamma"`); it must name a real continuous distribution available in
  the library.
- `alpha` is the significance level used to decide the `"reject"` flag of a
  goodness-of-fit test.

The function returns a dictionary with exactly these keys:

- `"params"` — a tuple of floats: the maximum-likelihood parameters of `dist`
  fitted to `data` (shape parameters first, then location and scale).
- `"ks_statistic"` — a float: the Kolmogorov-Smirnov distance between the
  empirical distribution of `data` and the fitted distribution.
- `"pvalue"` — a float in `[0, 1]`: the p-value of the goodness-of-fit test
  against the fitted distribution.
- `"reject"` — a bool: `True` iff `"pvalue" < alpha` (the data are unlikely to
  come from the fitted distribution).
- `"loglik"` — a float: the total log-likelihood of `data` under the fitted
  parameters.

### Behavioral constraints

- The MLE `"params"` must match an independent direct fit of the same named
  distribution to the same data.
- When `data` is genuinely drawn from `dist`, the goodness-of-fit test must
  usually NOT reject (`"reject"` False, large `"pvalue"`); when `data` is clearly
  from a different family, the test must reject (`"reject"` True, small
  `"pvalue"`).
- `"loglik"` must equal the sum of the fitted log-density over `data` at the
  returned `"params"` (self-consistency).
- Results must be deterministic for fixed inputs (no random p-value estimation
  that changes between calls).
- The function must not mutate `data`.

### Input validation (edge cases)

Raise `ValueError` with an informative message when:

- `data` is not 1-D, contains non-finite values, or has fewer than 5 samples.
- `dist` is not the name of an available continuous distribution.
- `alpha` is not in the open interval `(0, 1)`.

### Expected Functionality

- A normal sample fit with `dist="norm"` -> `"params"` ≈ the sample mean and
  standard deviation; `"reject"` False; `"loglik"` matching the recomputed sum.
- A clearly skewed exponential sample fit with `dist="norm"` -> `"reject"` True
  with a small `"pvalue"`.
- An exponential sample fit with `dist="expon"` -> `"reject"` False; `"params"`
  matching the analytic scale.
- Passing an unknown distribution name -> `ValueError`.

## Acceptance Criteria

- A new module `scipy/stats/_distfit_report.py` exists and exposes
  `fit_and_assess` with the signature and return contract above.
- `scipy/stats/tests/test_distfit_report.py` exists with at least 10 test cases
  that, using `numpy.testing.assert_allclose` / exact assertions, verify:
  recovered `"params"` match a direct independent fit; matched-family data are not
  rejected and mismatched-family data are rejected; `"loglik"` equals the
  recomputed log-density sum; `"reject"` is consistent with `"pvalue"` and
  `alpha`; results are deterministic across repeated calls; inputs are not
  mutated; and each invalid-input case raises `ValueError`.
- A naive or hardcoded implementation (e.g. always returning sample mean/std,
  never rejecting, or a fixed p-value) must fail these tests.
- The following command passes from the repository root after building SciPy:

  ```
  python -m pytest scipy/stats/tests/test_distfit_report.py -v
  ```
