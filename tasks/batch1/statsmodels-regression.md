# Task: Build a Linear Model Diagnostics Report Helper

## Background

The `statsmodels` library exposes many low-level estimation and testing
primitives, but users repeatedly stitch the same pieces together when they fit a
linear model to a continuous outcome and then want a single, structured summary
of how trustworthy that fit is. This task adds a small convenience helper inside
the `statsmodels.stats` subpackage that fits a linear model from raw arrays and
returns a structured, programmatically-consumable diagnostics report.

## Files to Create/Modify

- `statsmodels/stats/regression_report.py` (new) — implements the public helper described below.
- `statsmodels/stats/tests/test_regression_report.py` (new) — deterministic unit tests for the helper.

## Requirements

Implement a single public function in `statsmodels/stats/regression_report.py`
with this exact signature:

```python
def regression_diagnostics(endog, exog, add_intercept=True):
    ...
```

`endog` is a 1-D array-like of length `n` (the continuous outcome). `exog` is an
array-like of shape `(n, k)` (or a length-`n` 1-D array, treated as a single
column) of explanatory variables. The function fits an ordinary linear model of
`endog` on `exog` and returns a plain `dict` (not a custom object) with the keys
and semantics specified below.

### Intercept handling

- When `add_intercept=True` (the default), the model must include an intercept
  term in addition to the user-supplied columns of `exog`. The user must **not**
  be required to pre-add a column of ones themselves.
- When `add_intercept=False`, the model is fit using only the supplied columns of
  `exog`, with no intercept.
- If `add_intercept=True` but `exog` already contains a column that is constant
  across all rows, the function must **not** add a second redundant constant
  column (the result must not become rank-deficient because of duplicate
  constants).

### Returned report contents

The returned dict must contain at least the following keys:

- `"params"`: a 1-D `numpy.ndarray` of the fitted coefficients. When an intercept
  is present it must be the **first** element.
- `"nobs"`: the integer number of observations used in the fit.
- `"df_resid"`: the residual degrees of freedom (integer-valued).
- `"rsquared"`: the coefficient of determination of the fit (float).
- `"aic"` and `"bic"`: the model's information criteria (floats), suitable for
  comparing two competing specifications of the same outcome.
- `"resid"`: a 1-D `numpy.ndarray` of the model residuals, length `n`.
- `"het_pvalue"`: a float p-value from a test of whether the residual variance is
  constant with respect to the model's explanatory columns (i.e. a test for
  non-constant error variance). A small p-value signals non-constant variance.
- `"max_cooks_obs"`: the **integer row index** (0-based, into the original input)
  of the single observation with the largest influence on the fitted
  coefficients, as measured by the standard per-observation influence statistic.
- `"max_leverage_obs"`: the integer row index (0-based) of the observation with
  the largest leverage (diagonal of the hat/projection matrix).

### Constraints and edge cases

- The function must accept both plain Python lists and NumPy arrays for `endog`
  and `exog`, and must accept a 1-D `exog` as a single explanatory column.
- The values placed under `"rsquared"`, `"aic"`, `"bic"`, `"params"`, `"resid"`,
  `"het_pvalue"`, and the influence-based indices must be consistent with what
  `statsmodels`' own estimation and diagnostic machinery would produce for the
  equivalent model — a hand-rolled or hardcoded approximation will not satisfy
  the acceptance tests.
- `"max_cooks_obs"` and `"max_leverage_obs"` must be returned as Python `int`
  (or NumPy integer) values that can index back into the original `endog`.
- The function must not print anything or require any plotting backend.

### Expected Functionality

- Fitting `y` on a single near-perfectly-linear predictor with an intercept ->
  `"rsquared"` close to 1.0, `len(params) == 2`, and `params[0]` is the
  intercept.
- Fitting with `add_intercept=False` on a single predictor -> `len(params) == 1`
  and `"df_resid" == nobs - 1`.
- Passing an `exog` that already includes a constant column with
  `add_intercept=True` -> the fit succeeds and `len(params)` equals the number of
  supplied columns (no duplicate constant is added).
- Constructing data with one obviously extreme, off-trend observation ->
  `"max_cooks_obs"` equals the row index of that planted outlier.
- Constructing data with one observation whose predictor value is far from all
  others -> `"max_leverage_obs"` equals that observation's row index.

## Acceptance Criteria

- A new module `statsmodels/stats/regression_report.py` exists and exports a
  `regression_diagnostics` function with the signature above.
- For a dataset fit with an intercept, the returned `"params"`, `"rsquared"`,
  `"aic"`, `"bic"`, and `"resid"` match (to floating-point tolerance) the values
  obtained by fitting the same intercept-augmented linear model with
  `statsmodels`' ordinary-least-squares estimator directly.
- `"het_pvalue"` matches the p-value returned by the corresponding `statsmodels`
  heteroskedasticity diagnostic for the same residuals and design.
- `"max_cooks_obs"` and `"max_leverage_obs"` correctly identify the planted
  high-influence and high-leverage observations in constructed test data, and
  agree with the indices obtained from `statsmodels`' influence machinery
  (`OLSInfluence`) for the same fit.
- With `add_intercept=True`, supplying an `exog` that already contains a constant
  column does not add a duplicate constant, and the fit is full-rank.
- The following command passes:

```bash
pytest statsmodels/stats/tests/test_regression_report.py -q
```
