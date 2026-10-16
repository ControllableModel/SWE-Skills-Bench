# Task: Build an ARIMA Forecast Helper with Stationarity Pre-Check

## Background

The `statsmodels` library provides time-series estimators under
`statsmodels.tsa`, but users who forecast a univariate series repeatedly hand-
write the same pre-flight: deciding whether the series must be differenced before
modelling, then fitting and producing an interval forecast. This task adds a
small convenience helper inside the `statsmodels.tsa` subpackage that performs
that pipeline from a raw series and returns a structured report.

## Files to Create/Modify

- `statsmodels/tsa/arima_forecast_helper.py` (new) — implements the public helper described below.
- `statsmodels/tsa/tests/test_arima_forecast_helper.py` (new) — deterministic unit tests for the helper.

## Requirements

Implement a single public function in
`statsmodels/tsa/arima_forecast_helper.py` with this exact signature:

```python
def forecast_series(y, steps=5, max_diff=1, alpha=0.05):
    ...
```

`y` is a 1-D array-like (list, NumPy array, or pandas Series) representing an
ordered univariate series of length `n`. The function decides an integration
order, fits an autoregressive-integrated model, and returns a plain `dict` (not
a custom object).

### Integration-order selection

- The function must run a unit-root / stationarity test on `y`. If the test
  indicates the level series is non-stationary, the series must be differenced
  before modelling; otherwise it must be modelled in levels.
- The chosen integration order must be reported and must never exceed `max_diff`.
- Differencing decisions must be driven by the test result, not hardcoded.

### Returned report contents

The returned dict must contain at least the following keys:

- `"d"`: the integer integration order actually used (0 <= d <= `max_diff`).
- `"adf_pvalue"`: the float p-value of the stationarity test applied to the
  original `y` (before any differencing). A small value indicates stationarity.
- `"forecast"`: a 1-D `numpy.ndarray` of length `steps` with the point forecasts
  on the **original** scale of `y` (i.e. integration is undone, not left in
  differenced space).
- `"lower"` and `"upper"`: 1-D `numpy.ndarray`s of length `steps` giving the
  lower and upper bounds of the `(1 - alpha)` forecast interval on the original
  scale, with `"lower"[i] <= forecast[i] <= upper[i]` for every `i`.
- `"aic"`: the AIC of the fitted model (float).
- `"resid_ljungbox_pvalue"`: a float p-value from a residual autocorrelation
  test on the fitted model's residuals (a small value signals leftover
  autocorrelation / model inadequacy).

### Constraints and edge cases

- The function must accept lists, NumPy arrays, and pandas Series.
- `"forecast"`, `"lower"`, `"upper"`, `"aic"`, and `"adf_pvalue"` must be
  consistent with what `statsmodels`' own time-series estimation and diagnostic
  machinery produces for the chosen specification; hardcoded numbers will not
  pass.
- The function must not print anything or require any plotting backend.

### Expected Functionality

- On a clearly trending (random-walk-like) series, `"adf_pvalue"` is large and
  `"d"` is 1 (when `max_diff >= 1`).
- On a stationary mean-reverting series, `"adf_pvalue"` is small and `"d"` is 0.
- `len(forecast) == len(lower) == len(upper) == steps`, and the interval brackets
  the point forecast at every horizon.

## Acceptance Criteria

- A new module `statsmodels/tsa/arima_forecast_helper.py` exists and exports
  `forecast_series` with the signature above.
- `"adf_pvalue"` matches the p-value of the corresponding `statsmodels`
  stationarity test on the raw series.
- For a constructed non-stationary series, `"d" == 1`; for a constructed
  stationary series, `"d" == 0`.
- `"forecast"`, `"lower"`, and `"upper"` have length `steps`, are on the original
  scale, and satisfy `lower <= forecast <= upper` elementwise.
- The following command passes:

```bash
pytest statsmodels/tsa/tests/test_arima_forecast_helper.py -q
```
