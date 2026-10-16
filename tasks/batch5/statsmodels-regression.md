# Task: Build a Nested-Model Comparison Helper

## Background

The `statsmodels` library exposes estimation results carrying information
criteria and log-likelihoods, but users who compare two competing
specifications of the same outcome repeatedly re-derive the same comparison
logic by hand — both the information-criterion ranking and, when one model nests
the other, a formal significance test. This task adds a small convenience helper
inside the `statsmodels.stats` subpackage that compares two already-fitted linear
results objects and returns a structured report.

## Files to Create/Modify

- `statsmodels/stats/model_comparison.py` (new) — implements the public helper described below.
- `statsmodels/stats/tests/test_model_comparison.py` (new) — deterministic unit tests for the helper.

## Requirements

Implement a single public function in `statsmodels/stats/model_comparison.py`
with this exact signature:

```python
def compare_models(reduced_results, full_results, nested=True, alpha=0.05):
    ...
```

`reduced_results` and `full_results` are fitted linear results objects produced
by `statsmodels`' ordinary-least-squares estimator on the **same** outcome
vector, where `reduced_results` uses a subset of the explanatory columns used by
`full_results`. The function returns a plain `dict` (not a custom object).

### Returned report contents

The returned dict must contain at least the following keys:

- `"aic"`: a dict with keys `"reduced"` and `"full"` mapping to each model's AIC.
- `"bic"`: a dict with keys `"reduced"` and `"full"` mapping to each model's BIC.
- `"preferred_by_aic"`: the string `"reduced"` or `"full"`, naming the model with
  the **lower** AIC.
- `"preferred_by_bic"`: the string `"reduced"` or `"full"`, naming the model with
  the lower BIC.
- When `nested=True`, additionally:
  - `"lr_stat"`: the likelihood-ratio statistic comparing the two nested models
    (float, non-negative).
  - `"lr_df"`: the integer difference in number of estimated parameters between
    the full and reduced models.
  - `"lr_pvalue"`: the float p-value of the likelihood-ratio test under the
    appropriate reference distribution.
  - `"full_significant"`: a `bool` that is `True` exactly when `"lr_pvalue"` is
    below `alpha` (i.e. the extra parameters of the full model are jointly
    significant).
- When `nested=False`, the three `"lr_*"` keys and `"full_significant"` must be
  absent (the helper must not fabricate a likelihood-ratio test for non-nested
  models).

### Constraints and edge cases

- `"lr_df"` must equal the difference in fitted-parameter counts and must be a
  positive integer when the full model genuinely adds parameters.
- `"aic"`, `"bic"`, `"lr_stat"`, and `"lr_pvalue"` must be consistent with the
  values carried by / derivable from the supplied `statsmodels` results objects;
  hardcoded numbers will not pass.
- If the two results were not fit on the same number of observations, the
  function must raise `ValueError`.
- The function must not print anything or require any plotting backend.

### Expected Functionality

- Adding a genuinely predictive extra column to the full model -> `"lr_pvalue"`
  small, `"full_significant" == True`, and `"preferred_by_aic" == "full"`.
- Adding a pure-noise extra column -> `"lr_pvalue"` large and
  `"full_significant" == False`.
- Calling with `nested=False` returns only the AIC/BIC comparison keys.

## Acceptance Criteria

- A new module `statsmodels/stats/model_comparison.py` exists and exports
  `compare_models` with the signature above.
- `"aic"` and `"bic"` values equal the `.aic` / `.bic` attributes of the supplied
  results objects.
- `"lr_stat"`, `"lr_df"`, and `"lr_pvalue"` match a likelihood-ratio test
  computed directly from the two results' log-likelihoods and parameter counts.
- Passing results fit on differing sample sizes raises `ValueError`.
- The following command passes:

```bash
pytest statsmodels/stats/tests/test_model_comparison.py -q
```
