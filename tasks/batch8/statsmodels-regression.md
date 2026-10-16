# Task: Build a Multicollinearity Diagnostics Helper

## Background

The `statsmodels` library provides influence and design diagnostics under
`statsmodels.stats`, but users who fit a linear model with several correlated
predictors repeatedly re-derive the same collinearity checks by hand to decide
whether the design matrix is numerically well behaved. This task adds a small
convenience helper inside the `statsmodels.stats` subpackage that takes a design
matrix and returns a structured multicollinearity report.

## Files to Create/Modify

- `statsmodels/stats/collinearity.py` (new) — implements the public helper described below.
- `statsmodels/stats/tests/test_collinearity.py` (new) — deterministic unit tests for the helper.

## Requirements

Implement a single public function in `statsmodels/stats/collinearity.py` with
this exact signature:

```python
def collinearity_report(exog, add_intercept=True, vif_threshold=10.0):
    ...
```

`exog` is an array-like of shape `(n, k)` of explanatory variables (or a
length-`n` 1-D array, treated as a single column). The function returns a plain
`dict` (not a custom object).

### Intercept handling

- When `add_intercept=True` (default), the diagnostics must be computed for the
  design that includes an intercept column in addition to the supplied columns;
  the user must not pre-add a column of ones. The per-predictor inflation factors
  must be reported only for the **non-intercept** columns.
- When `add_intercept=False`, only the supplied columns form the design and every
  supplied column gets a reported factor.
- If `exog` already contains a constant column, no second redundant constant may
  be added.

### Returned report contents

The returned dict must contain at least the following keys:

- `"vif"`: a 1-D `numpy.ndarray` of variance-inflation factors, one per
  non-intercept predictor column, in the original column order. Each entry
  measures how much that predictor's variance is inflated by its linear
  dependence on the other predictors.
- `"max_vif"`: the float maximum of `"vif"`.
- `"high_vif_columns"`: a list of integer 0-based column indices (into the
  supplied `exog`) whose inflation factor exceeds `vif_threshold`.
- `"condition_number"`: a float condition number of the (intercept-augmented when
  requested) design, summarizing overall ill-conditioning.
- `"multicollinear"`: a `bool` that is `True` exactly when `"max_vif"` exceeds
  `vif_threshold`.

### Constraints and edge cases

- The function must accept both plain Python lists and NumPy arrays, and a 1-D
  `exog`.
- `len(vif)` must equal the number of supplied (non-intercept) predictor columns.
- The `"vif"` and `"condition_number"` values must be consistent with what
  `statsmodels`' own collinearity / design-diagnostic machinery produces for the
  equivalent design; hardcoded approximations will not pass.
- The function must not print anything or require any plotting backend.

### Expected Functionality

- On nearly-orthogonal predictor columns -> all `"vif"` entries near 1.0,
  `"multicollinear" == False`, and `"high_vif_columns"` empty.
- On a design where one column is nearly a linear combination of the others ->
  that column's `"vif"` entry is very large, it appears in `"high_vif_columns"`,
  and `"multicollinear" == True`.
- `"condition_number"` is markedly larger for the ill-conditioned design than for
  the orthogonal one.

## Acceptance Criteria

- A new module `statsmodels/stats/collinearity.py` exists and exports
  `collinearity_report` with the signature above.
- Each `"vif"` entry matches (to floating-point tolerance) the
  variance-inflation factor produced by `statsmodels` for the corresponding
  column of the same design.
- `"high_vif_columns"` and `"multicollinear"` are consistent with `"vif"` and
  `vif_threshold`.
- For constructed orthogonal vs near-collinear designs, the boolean and
  index outcomes match the described behavior.
- The following command passes:

```bash
pytest statsmodels/stats/tests/test_collinearity.py -q
```
