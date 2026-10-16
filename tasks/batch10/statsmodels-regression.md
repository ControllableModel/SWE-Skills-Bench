# Task: Build an Outlier-Robust Conditional-Quantile Fit Helper

## Background

The `statsmodels` regression subpackage offers both mean-based least squares and
conditional-quantile estimation, but users with outlier-contaminated data
repeatedly hand-wire the same comparison: fit the mean model, fit the median
(conditional-quantile) model, and contrast how sensitive each is to extreme
observations. This task adds a small convenience helper inside the
`statsmodels.regression` subpackage that fits both from raw arrays and returns a
structured comparison report.

## Files to Create/Modify

- `statsmodels/regression/quantile_compare.py` (new) — implements the public helper described below.
- `statsmodels/regression/tests/test_quantile_compare.py` (new) — deterministic unit tests for the helper.

## Requirements

Implement a single public function in
`statsmodels/regression/quantile_compare.py` with this exact signature:

```python
def compare_mean_vs_quantile(endog, exog, q=0.5, add_intercept=True):
    ...
```

`endog` is a 1-D array-like of length `n`. `exog` is an array-like of shape
`(n, k)` (or a length-`n` 1-D array, treated as a single column). `q` is the
conditional quantile to fit (0 < `q` < 1). The function fits both an ordinary
mean model and a conditional-quantile model of `endog` on `exog`, and returns a
plain `dict` (not a custom object).

### Intercept handling

- When `add_intercept=True` (default), both fits include an intercept in addition
  to the supplied columns; the user must not pre-add a column of ones.
- When `add_intercept=False`, both fits use only the supplied columns.
- If `exog` already contains a constant column, no second redundant constant may
  be added.

### Returned report contents

The returned dict must contain at least the following keys:

- `"ols_params"`: a 1-D `numpy.ndarray` of the mean-model coefficients (intercept
  first when present).
- `"quantile_params"`: a 1-D `numpy.ndarray` of the conditional-quantile model
  coefficients at quantile `q`, aligned column-for-column with `"ols_params"`.
- `"q"`: the float quantile that was fit.
- `"slope_diff"`: a 1-D `numpy.ndarray` equal to `quantile_params - ols_params`
  elementwise (so it has the same length as the parameter vectors).
- `"ols_resid"`: a 1-D `numpy.ndarray` of length `n` of the mean-model residuals.
- `"quantile_resid"`: a 1-D `numpy.ndarray` of length `n` of the
  conditional-quantile model residuals.
- `"quantile_below_fraction"`: a float, the fraction of observations whose
  `endog` lies strictly below its conditional-quantile fitted value; for a
  well-fit model this should be close to `q`.

### Constraints and edge cases

- The function must accept both plain Python lists and NumPy arrays, and a 1-D
  `exog`.
- A `q` outside the open interval `(0, 1)` must raise `ValueError`.
- `"ols_params"`, `"quantile_params"`, and the residual vectors must be
  consistent with what `statsmodels`' own mean and conditional-quantile
  estimators produce for the equivalent intercept-augmented designs; hardcoded
  approximations will not pass.
- The function must not print anything or require any plotting backend.

### Expected Functionality

- On clean, symmetric-error data with `q=0.5` -> `"slope_diff"` entries are small
  in magnitude (the median and mean fits nearly agree).
- On data with a few extreme outliers in `endog` and `q=0.5` -> the slope
  estimate(s) of the conditional-quantile fit are visibly less perturbed by the
  outliers than the mean-model slope(s) (so the corresponding `"slope_diff"`
  entry is non-negligible).
- `"quantile_below_fraction"` is approximately `q` for a reasonable fit.
- Passing `q=0` or `q=1.5` raises `ValueError`.

## Acceptance Criteria

- A new module `statsmodels/regression/quantile_compare.py` exists and exports
  `compare_mean_vs_quantile` with the signature above.
- `"ols_params"` matches the coefficients of the equivalent intercept-augmented
  ordinary least-squares fit with `statsmodels`.
- `"quantile_params"` matches the coefficients of the equivalent conditional-
  quantile fit at `q` with `statsmodels`, and `"slope_diff"` equals their
  elementwise difference.
- For constructed outlier-contaminated data, the conditional-quantile slope is
  closer to the clean-data slope than the mean-model slope is.
- Passing `q` outside `(0, 1)` raises `ValueError`.
- The following command passes:

```bash
pytest statsmodels/regression/tests/test_quantile_compare.py -q
```
