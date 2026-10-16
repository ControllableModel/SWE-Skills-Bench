# Task: Build a Residual Autocorrelation Diagnostics Helper

## Background

The `statsmodels` time-series subpackage offers several tools for inspecting
whether a fitted model has captured the serial dependence in its data, but users
repeatedly stitch the same checks together to decide whether residuals still
carry autocorrelation. This task adds a small convenience helper inside the
`statsmodels.tsa` subpackage that takes a residual series and returns a
structured autocorrelation-diagnostics report.

## Files to Create/Modify

- `statsmodels/tsa/resid_autocorr.py` (new) — implements the public helper described below.
- `statsmodels/tsa/tests/test_resid_autocorr.py` (new) — deterministic unit tests for the helper.

## Requirements

Implement a single public function in `statsmodels/tsa/resid_autocorr.py` with
this exact signature:

```python
def autocorrelation_report(resid, lags=10, alpha=0.05, model_df=0):
    ...
```

`resid` is a 1-D array-like (list, NumPy array, or pandas Series) of model
residuals of length `n`. The function returns a plain `dict` (not a custom
object).

### Returned report contents

The returned dict must contain at least the following keys:

- `"acf"`: a 1-D `numpy.ndarray` of autocorrelation values for lags `0` through
  `lags` inclusive (so length `lags + 1`), with the lag-0 entry equal to 1.0.
- `"durbin_watson"`: a float Durbin-Watson statistic for first-order
  autocorrelation, lying in the closed interval `[0, 4]`; values near 2 indicate
  no first-order autocorrelation.
- `"ljungbox_stat"`: the portmanteau test statistic at lag `lags` (float),
  adjusted for `model_df` consumed degrees of freedom.
- `"ljungbox_pvalue"`: the float p-value of that portmanteau test at lag `lags`.
- `"autocorrelated"`: a `bool` that is `True` exactly when `"ljungbox_pvalue"` is
  below `alpha` (i.e. residuals show significant remaining autocorrelation).
- `"first_significant_lag"`: the integer lag (>= 1) of the first individual
  autocorrelation whose absolute value exceeds the approximate white-noise
  significance band `1.96 / sqrt(n)`, or `None` if no lag in `1..lags` exceeds it.

### Constraints and edge cases

- The function must accept lists, NumPy arrays, and pandas Series.
- `"acf"`, `"durbin_watson"`, `"ljungbox_stat"`, and `"ljungbox_pvalue"` must be
  consistent with what `statsmodels`' own autocorrelation and portmanteau
  machinery produces for the same residual series and lag count; hardcoded
  approximations will not pass.
- `model_df` must be passed through to the portmanteau computation so that the
  reference degrees of freedom are reduced accordingly.
- The function must not print anything or require any plotting backend.

### Expected Functionality

- On white-noise-like residuals -> `"durbin_watson"` near 2,
  `"ljungbox_pvalue"` large, `"autocorrelated" == False`, and
  `"first_significant_lag"` is `None`.
- On strongly positively-autocorrelated residuals -> `"durbin_watson"` well below
  2, `"ljungbox_pvalue"` small, `"autocorrelated" == True`, and
  `"first_significant_lag"` is a small integer (typically 1).
- `len(acf) == lags + 1` and `acf[0] == 1.0`.

## Acceptance Criteria

- A new module `statsmodels/tsa/resid_autocorr.py` exists and exports
  `autocorrelation_report` with the signature above.
- `"acf"`, `"durbin_watson"`, `"ljungbox_stat"`, and `"ljungbox_pvalue"` match (to
  floating-point tolerance) the values produced by the corresponding
  `statsmodels` functions for the same residual series, `lags`, and `model_df`.
- For constructed white-noise and autocorrelated residuals, the boolean and
  first-significant-lag outcomes match the described behavior.
- The following command passes:

```bash
pytest statsmodels/tsa/tests/test_resid_autocorr.py -q
```
