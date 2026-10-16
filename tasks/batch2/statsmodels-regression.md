# Task: Build a Count-Data Model Selector

## Background

The `statsmodels` library ships generalized-linear modelling tools under
`statsmodels.genmod`, but users who model non-negative integer outcomes
repeatedly re-implement the same decision logic by hand. This task adds a small
convenience helper inside the `statsmodels.genmod` subpackage that fits a count
model to raw arrays and returns a structured, programmatically-consumable report
describing the fit and whether the chosen distributional assumption is adequate.

## Files to Create/Modify

- `statsmodels/genmod/count_selector.py` (new) — implements the public helper described below.
- `statsmodels/genmod/tests/test_count_selector.py` (new) — deterministic unit tests for the helper.

## Requirements

Implement a single public function in `statsmodels/genmod/count_selector.py`
with this exact signature:

```python
def select_count_model(endog, exog, add_intercept=True, dispersion_threshold=1.5):
    ...
```

`endog` is a 1-D array-like of length `n` holding non-negative integer counts.
`exog` is an array-like of shape `(n, k)` (or a length-`n` 1-D array, treated as
a single column) of explanatory variables. The function fits a count model of
`endog` on `exog` and returns a plain `dict` (not a custom object).

### Intercept handling

- When `add_intercept=True` (the default), the model must include an intercept
  term in addition to the supplied columns of `exog`. The user must **not** be
  required to pre-add a column of ones.
- When `add_intercept=False`, the model is fit using only the supplied columns.
- If `add_intercept=True` but `exog` already contains a constant column, the
  function must **not** add a second redundant constant.

### Returned report contents

The returned dict must contain at least the following keys:

- `"params"`: a 1-D `numpy.ndarray` of the fitted log-link coefficients. When an
  intercept is present it must be the **first** element.
- `"rate_ratios"`: a 1-D `numpy.ndarray`, one per coefficient, on the
  multiplicative scale (so that a unit change in a predictor multiplies the
  expected count by the corresponding entry).
- `"dispersion"`: a float estimate of how far the conditional variance exceeds
  the conditional mean under the equidispersed count assumption. A value near
  1.0 indicates the simple count model is adequate; values well above 1.0
  indicate the variance grows faster than the mean.
- `"overdispersed"`: a `bool` that is `True` exactly when `"dispersion"` exceeds
  `dispersion_threshold`.
- `"recommended_model"`: the string `"poisson"` when `"overdispersed"` is
  `False`, and `"negativebinomial"` when it is `True`.
- `"aic"`: the AIC of the recommended model (float). When overdispersion is
  detected, this must be the AIC of the heavier-tailed alternative re-fit on the
  same design, not of the equidispersed model.
- `"nobs"`: the integer number of observations used.

### Constraints and edge cases

- The function must accept both plain Python lists and NumPy arrays, and a 1-D
  `exog` as a single column.
- The `"dispersion"`, `"params"`, `"rate_ratios"`, and `"aic"` values must be
  consistent with what `statsmodels`' own count-model estimation machinery would
  produce for the equivalent specification — a hardcoded or approximated value
  will not satisfy the acceptance tests.
- The function must not print anything or require any plotting backend.

### Expected Functionality

- Fitting equidispersed counts generated with variance approximately equal to
  the mean -> `"dispersion"` close to 1.0, `"overdispersed" == False`, and
  `"recommended_model" == "poisson"`.
- Fitting clearly overdispersed counts (variance far exceeding the mean) ->
  `"overdispersed" == True`, `"recommended_model" == "negativebinomial"`, and
  `"aic"` reflecting the heavier-tailed alternative.
- A predictor with a known positive effect -> its `"rate_ratios"` entry is
  greater than 1.0.

## Acceptance Criteria

- A new module `statsmodels/genmod/count_selector.py` exists and exports
  `select_count_model` with the signature above.
- For equidispersed test data, `"params"`, `"rate_ratios"`, and `"dispersion"`
  match (to floating-point tolerance) the values obtained by fitting the
  equivalent intercept-augmented count GLM with `statsmodels` directly.
- For overdispersed test data, `"overdispersed"` is `True`,
  `"recommended_model"` is `"negativebinomial"`, and `"aic"` matches the AIC of
  the heavier-tailed model fit on the same design.
- The following command passes:

```bash
pytest statsmodels/genmod/tests/test_count_selector.py -q
```
