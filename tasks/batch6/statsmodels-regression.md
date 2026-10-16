# Task: Build a Heteroskedasticity-Aware Standard-Error Helper

## Background

The `statsmodels` regression subpackage estimates linear models with several
covariance options, but users repeatedly hand-wire the same decision: test the
fitted residuals for non-constant variance, and if present, re-report the
coefficient inference using a variance estimator that is valid under that
violation. This task adds a small convenience helper inside the
`statsmodels.regression` subpackage that fits a linear model from raw arrays and
returns coefficient inference appropriate to the detected error structure.

## Files to Create/Modify

- `statsmodels/regression/robust_se_helper.py` (new) — implements the public helper described below.
- `statsmodels/regression/tests/test_robust_se_helper.py` (new) — deterministic unit tests for the helper.

## Requirements

Implement a single public function in
`statsmodels/regression/robust_se_helper.py` with this exact signature:

```python
def fit_with_appropriate_se(endog, exog, add_intercept=True, alpha=0.05):
    ...
```

`endog` is a 1-D array-like of length `n`. `exog` is an array-like of shape
`(n, k)` (or a length-`n` 1-D array, treated as a single column). The function
fits an ordinary linear model, tests whether the error variance is constant, and
returns a plain `dict` (not a custom object).

### Intercept handling

- When `add_intercept=True` (default), include an intercept in addition to the
  supplied columns; the user must not pre-add a column of ones.
- When `add_intercept=False`, use only the supplied columns.
- If `exog` already contains a constant column, no second redundant constant may
  be added.

### Returned report contents

The returned dict must contain at least the following keys:

- `"params"`: a 1-D `numpy.ndarray` of the fitted coefficients (intercept first
  when present).
- `"het_pvalue"`: a float p-value from a test of non-constant error variance with
  respect to the model's explanatory columns. A small value signals
  heteroskedasticity.
- `"heteroskedastic"`: a `bool` that is `True` exactly when `"het_pvalue"` is
  below `alpha`.
- `"cov_type"`: the string `"nonrobust"` when `"heteroskedastic"` is `False`, and
  a heteroskedasticity-consistent identifier when it is `True`.
- `"bse"`: a 1-D `numpy.ndarray` of coefficient standard errors. These must be the
  **classical** standard errors when no heteroskedasticity is detected, and the
  **heteroskedasticity-consistent** standard errors (matching `"cov_type"`) when
  it is.
- `"pvalues"`: a 1-D `numpy.ndarray` of coefficient p-values computed from
  `"params"` and `"bse"` (so they change when robust standard errors are used).
- `"nobs"`: the integer number of observations used.

### Constraints and edge cases

- The function must accept both plain Python lists and NumPy arrays, and a 1-D
  `exog`.
- `"params"` does not depend on the covariance choice, but `"bse"` and
  `"pvalues"` must reflect the selected covariance type and must match what
  `statsmodels` produces when fitting the same model with the corresponding
  covariance option; hardcoded numbers will not pass.
- The function must not print anything or require any plotting backend.

### Expected Functionality

- On data with constant-variance errors -> `"heteroskedastic" == False`,
  `"cov_type" == "nonrobust"`, and `"bse"` equals the classical standard errors.
- On data whose error spread grows with a predictor -> `"heteroskedastic" ==
  True`, `"cov_type"` is the robust identifier, and `"bse"` differs from the
  classical standard errors.
- `"params"` is identical whether or not robust standard errors are selected.

## Acceptance Criteria

- A new module `statsmodels/regression/robust_se_helper.py` exists and exports
  `fit_with_appropriate_se` with the signature above.
- `"params"` matches the coefficients from the equivalent intercept-augmented OLS
  fit with `statsmodels`.
- When heteroskedasticity is detected, `"bse"` matches the
  heteroskedasticity-consistent standard errors produced by `statsmodels` for the
  same fit and `"cov_type"`; otherwise `"bse"` matches the classical errors.
- `"het_pvalue"` matches the corresponding `statsmodels` heteroskedasticity test.
- The following command passes:

```bash
pytest statsmodels/regression/tests/test_robust_se_helper.py -q
```
