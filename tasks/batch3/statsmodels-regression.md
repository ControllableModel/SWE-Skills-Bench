# Task: Build a Binary-Outcome Model Report Helper

## Background

The `statsmodels` library exposes binary-outcome estimators under
`statsmodels.discrete`, but users who fit a model to a 0/1 outcome repeatedly
stitch together the same post-fit summary: interpretable effect sizes, fitted
probabilities, and a deterministic classification breakdown. This task adds a
small convenience helper inside the `statsmodels.discrete` subpackage that fits
a binary model from raw arrays and returns a structured report.

## Files to Create/Modify

- `statsmodels/discrete/binary_report.py` (new) — implements the public helper described below.
- `statsmodels/discrete/tests/test_binary_report.py` (new) — deterministic unit tests for the helper.

## Requirements

Implement a single public function in `statsmodels/discrete/binary_report.py`
with this exact signature:

```python
def binary_outcome_report(endog, exog, add_intercept=True, threshold=0.5):
    ...
```

`endog` is a 1-D array-like of length `n` containing only 0/1 values. `exog` is
an array-like of shape `(n, k)` (or a length-`n` 1-D array, treated as a single
column). The function fits a binary model of `endog` on `exog` and returns a
plain `dict` (not a custom object).

### Intercept handling

- When `add_intercept=True` (default), the model must include an intercept in
  addition to the supplied columns; the user must not pre-add a column of ones.
- When `add_intercept=False`, only the supplied columns are used.
- If `add_intercept=True` but `exog` already contains a constant column, no
  second redundant constant may be added.

### Returned report contents

The returned dict must contain at least the following keys:

- `"params"`: a 1-D `numpy.ndarray` of the fitted log-odds coefficients, with the
  intercept first when present.
- `"odds_ratios"`: a 1-D `numpy.ndarray`, one per coefficient, on the
  multiplicative odds scale (so a unit change in a predictor multiplies the odds
  of the positive outcome by the corresponding entry).
- `"fitted_prob"`: a 1-D `numpy.ndarray` of length `n` of in-sample predicted
  probabilities of the positive outcome, each strictly between 0 and 1.
- `"predicted_class"`: a 1-D integer `numpy.ndarray` of length `n` equal to 1
  where `"fitted_prob"` exceeds `threshold` and 0 otherwise.
- `"confusion"`: a 2x2 integer `numpy.ndarray` with rows indexed by the true
  class (0 then 1) and columns by the predicted class (0 then 1).
- `"accuracy"`: a float, the fraction of observations whose `"predicted_class"`
  equals the observed `endog`.
- `"llf"`: the maximized log-likelihood of the fit (float).
- `"nobs"`: the integer number of observations used.

### Constraints and edge cases

- The function must accept both plain Python lists and NumPy arrays, and a 1-D
  `exog` as a single column.
- `"params"`, `"odds_ratios"`, `"fitted_prob"`, and `"llf"` must be consistent
  with what `statsmodels`' own binary-outcome estimation machinery produces for
  the equivalent specification; hardcoded approximations will not pass.
- `"accuracy"` and `"confusion"` must be derived from `"predicted_class"` and
  `endog` only (no separate re-estimation).
- The function must not print anything or require any plotting backend.

### Expected Functionality

- On linearly separable-ish data with a strong positive predictor, that
  predictor's `"odds_ratios"` entry exceeds 1.0 and `"accuracy"` is high.
- Lowering `threshold` toward 0 increases the count of predicted-1 observations
  (the sum of `"predicted_class"` is monotone non-decreasing as `threshold`
  falls).
- The four entries of `"confusion"` always sum to `"nobs"`.

## Acceptance Criteria

- A new module `statsmodels/discrete/binary_report.py` exists and exports
  `binary_outcome_report` with the signature above.
- `"params"`, `"odds_ratios"`, `"fitted_prob"`, and `"llf"` match (to
  floating-point tolerance) the values obtained by fitting the equivalent
  intercept-augmented binary model with `statsmodels` directly.
- `"confusion"`, `"accuracy"`, and `"predicted_class"` are internally consistent
  with one another and with `endog` for constructed test data.
- The following command passes:

```bash
pytest statsmodels/discrete/tests/test_binary_report.py -q
```
