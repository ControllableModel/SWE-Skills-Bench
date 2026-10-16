# Task: Implement a Modality LUT Rescale Applier

## Background

The `pydicom` library (this repository) stores raw stored pixel values that must be converted to meaningful output units (e.g. CT Hounsfield units) using a linear *Rescale Slope* and *Rescale Intercept* before any further analysis. This task adds a self-contained utility to `src/pydicom/util/` that applies this modality rescale to a pixel array.

## Files to Create/Modify

- `src/pydicom/util/rescale.py` (new) — the modality rescale utility module.
- `tests/test_util_rescale.py` (new) — the deterministic unit tests for the new module.

## Requirements

### Public API

Add `src/pydicom/util/rescale.py` exposing a single public function with this exact signature:

```python
def apply_rescale(arr, ds)
```

- `arr` is a `numpy.ndarray` of stored pixel values.
- `ds` is a `pydicom.dataset.Dataset` that may carry `RescaleSlope` and `RescaleIntercept`.
- The function returns a new `numpy.ndarray` and must not mutate `arr`.

### Mapping contract

- When both `RescaleSlope` (`m`) and `RescaleIntercept` (`b`) are present, return `arr * m + b` computed as floating-point (`numpy.float64`).
- When only one of the two is present, treat the missing one with its identity default: missing slope → `1`, missing intercept → `0`.
- When neither is present, return `arr` unchanged in value (a copy is acceptable, but the returned values must equal the input values).

### Behavior and edge cases

- `RescaleSlope`/`RescaleIntercept` are DICOM **DS** (decimal string) values; they must be interpreted numerically (e.g. a slope of `"1"` and intercept of `"-1024"`).
- When a rescale is applied, the output dtype must be a floating type (`numpy.float64`), regardless of the input integer dtype.
- The input array must not be mutated.
- A slope that is not exactly `1` (e.g. `0.5`) must scale values accordingly.

### Expected Functionality

- `arr = [[0, 1000, 2000]]`, `RescaleSlope="1"`, `RescaleIntercept="-1024"` → `[[-1024.0, -24.0, 976.0]]`.
- `arr = [[10, 20]]`, `RescaleSlope="0.5"`, no intercept → `[[5.0, 10.0]]`.
- `arr` with no rescale elements → values returned unchanged.

## Acceptance Criteria

- `src/pydicom/util/rescale.py` exists and defines `apply_rescale(arr, ds)` returning a `numpy.ndarray`.
- The linear rescale, identity defaults for a single missing element, and the no-rescale passthrough all behave exactly as specified, parsing DS values numerically.
- When rescaling, the output is `numpy.float64`; the input array is never mutated.
- The new test file passes deterministically and covers full slope+intercept, slope-only, intercept-only, no-rescale passthrough, the float-output dtype, fractional slope, and non-mutation (≥10 test cases). A naive implementation that ignores the intercept, leaves integer dtype, or mutates the input must fail.

Run exactly:

```bash
python -m pytest tests/test_util_rescale.py -q
```

This command must exit with all tests passing.
