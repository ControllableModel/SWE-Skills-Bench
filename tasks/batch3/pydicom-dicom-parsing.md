# Task: Implement a Grayscale Windowing Normalizer

## Background

The `pydicom` library (this repository) exposes pixel intensities from medical images that often span a wide dynamic range and require windowing before display. This task adds a self-contained utility to `src/pydicom/util/` that maps a raw intensity array to an 8-bit display range using a window centre/width taken from a dataset.

## Files to Create/Modify

- `src/pydicom/util/window.py` (new) — the windowing normalizer module.
- `tests/test_util_window.py` (new) — the deterministic unit tests for the new module.

## Requirements

### Public API

Add `src/pydicom/util/window.py` exposing a single public function with this exact signature:

```python
def window_to_uint8(arr, ds)
```

- `arr` is a 2-D `numpy.ndarray` of intensities.
- `ds` is a `pydicom.dataset.Dataset` that may contain `WindowCenter` and `WindowWidth`.
- The function returns a new `numpy.ndarray` of dtype `numpy.uint8` with the same shape as `arr`, and must not mutate `arr`.

### Mapping contract

When `ds` has both `WindowCenter` (`c`) and `WindowWidth` (`w`, with `w >= 1`):

- Values `<= c - 0.5 - (w - 1) / 2` map to `0`.
- Values `>  c - 0.5 + (w - 1) / 2` map to `255`.
- Values in between map linearly into `0..255` via `round(((v - (c - 0.5)) / (w - 1) + 0.5) * 255)`, then clipped to `[0, 255]`.

When `ds` lacks `WindowCenter` or `WindowWidth`, fall back to min-max scaling of `arr`: the minimum value maps to `0`, the maximum to `255`, linearly in between; if all values are equal, the result is an all-zero array.

### Behavior and edge cases

- `WindowCenter`/`WindowWidth` may be multi-valued (a list-like); in that case use the first value of each.
- The returned array dtype must be exactly `numpy.uint8`; output values are always within `0..255`.
- `arr` may contain negative values (e.g. CT Hounsfield units); the mapping must still hold.
- The input array must be left unchanged after the call.

### Expected Functionality

- `arr = [[0, 50, 100]]`, `WindowCenter=50`, `WindowWidth=100` → centre maps near `128`, low end toward `0`, high end toward `255`.
- A dataset with no window elements and `arr` ranging 100..900 → 100 maps to `0`, 900 maps to `255`.
- A constant array with no window elements → all zeros.

## Acceptance Criteria

- `src/pydicom/util/window.py` exists and defines `window_to_uint8(arr, ds)` returning a `numpy.uint8` array of the input shape.
- The windowing formula and the min-max fallback both behave exactly as specified, including multi-valued window elements and the constant-array case.
- The input array is not mutated and all outputs lie in `0..255`.
- The new test file passes deterministically and covers windowed mapping (low/centre/high), multi-valued window elements, the min-max fallback, the constant-array case, dtype, shape, and non-mutation (≥10 test cases). A naive implementation that ignores the window elements or returns a non-uint8 array must fail.

Run exactly:

```bash
python -m pytest tests/test_util_window.py -q
```

This command must exit with all tests passing.
