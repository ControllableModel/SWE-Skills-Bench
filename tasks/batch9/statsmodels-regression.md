# Task: Build a Weighted Least-Squares Helper for Non-Constant Variance

## Background

The `statsmodels` regression subpackage supports both ordinary and weighted
least-squares estimation, but users facing errors whose spread varies across
observations repeatedly hand-wire the same two-step routine: fit ordinarily to
learn the variance pattern, then re-fit with weights that down-weight the
high-variance observations. This task adds a small convenience helper inside the
`statsmodels.regression` subpackage that performs that routine from raw arrays.

## Files to Create/Modify

- `statsmodels/regression/wls_helper.py` (new) — implements the public helper described below.
- `statsmodels/regression/tests/test_wls_helper.py` (new) — deterministic unit tests for the helper.

## Requirements

Implement a single public function in `statsmodels/regression/wls_helper.py`
with this exact signature:

```python
def weighted_fit(endog, exog, weights=None, add_intercept=True):
    ...
```

`endog` is a 1-D array-like of length `n`. `exog` is an array-like of shape
`(n, k)` (or a length-`n` 1-D array, treated as a single column). `weights` is
an optional 1-D array-like of length `n` of strictly positive observation
weights. The function returns a plain `dict` (not a custom object).

### Intercept handling

- When `add_intercept=True` (default), include an intercept in addition to the
  supplied columns; the user must not pre-add a column of ones.
- When `add_intercept=False`, use only the supplied columns.
- If `exog` already contains a constant column, no second redundant constant may
  be added.

### Weighting behavior

- When `weights` is provided, the model must be fit by weighted least squares
  using those weights (each observation's contribution scaled by its weight).
- When `weights` is `None`, the helper must derive weights automatically: fit the
  model ordinarily, then construct weights that are **inversely proportional to a
  fitted-value-driven estimate of each observation's error variance**, so that
  observations with larger estimated variance receive smaller weight. The fit
  reported must then be the weighted one using those derived weights.

### Returned report contents

The returned dict must contain at least the following keys:

- `"params"`: a 1-D `numpy.ndarray` of the weighted-fit coefficients (intercept
  first when present).
- `"bse"`: a 1-D `numpy.ndarray` of the weighted-fit coefficient standard errors.
- `"weights"`: a 1-D `numpy.ndarray` of length `n` of the weights actually used
  (the supplied ones, or the derived ones when `weights is None`); all strictly
  positive.
- `"rsquared"`: the weighted fit's coefficient of determination (float).
- `"derived_weights"`: a `bool`, `True` exactly when `weights` was `None` and the
  helper computed the weights itself.
- `"nobs"`: the integer number of observations used.

### Constraints and edge cases

- The function must accept both plain Python lists and NumPy arrays, and a 1-D
  `exog`.
- A non-positive entry in a supplied `weights` must raise `ValueError`.
- `"params"`, `"bse"`, and `"rsquared"` must be consistent with what
  `statsmodels`' own weighted least-squares estimator produces for the same
  design and weights; hardcoded approximations will not pass.
- The function must not print anything or require any plotting backend.

### Expected Functionality

- Supplying explicit `weights` -> `"derived_weights" == False`, `"weights"`
  equals the supplied array, and `"params"`/`"bse"` match a direct weighted fit
  with those weights.
- On data whose error spread grows with the fitted value and `weights=None` ->
  `"derived_weights" == True`, the high-variance observations receive smaller
  weights than the low-variance ones, and the reported fit is the weighted one.
- Supplying a `weights` array containing a zero or negative value raises
  `ValueError`.

## Acceptance Criteria

- A new module `statsmodels/regression/wls_helper.py` exists and exports
  `weighted_fit` with the signature above.
- With explicit weights, `"params"`, `"bse"`, and `"rsquared"` match (to
  floating-point tolerance) a direct `statsmodels` weighted least-squares fit on
  the same intercept-augmented design and weights.
- With `weights=None`, `"derived_weights"` is `True` and the derived weights are
  smaller for observations whose estimated error variance is larger.
- A non-positive supplied weight raises `ValueError`.
- The following command passes:

```bash
pytest statsmodels/regression/tests/test_wls_helper.py -q
```
