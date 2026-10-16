# Task: Implement a Multi-Frame Frame Selector

## Background

The `pydicom` library (this repository) loads enhanced/cine DICOM objects whose pixel data holds many stacked frames. This task adds a self-contained utility to `src/pydicom/util/` that extracts a single 2-D frame (or a contiguous range) from a multi-frame pixel array described by a dataset.

## Files to Create/Modify

- `src/pydicom/util/frames.py` (new) — the frame-selection utility module.
- `tests/test_util_frames.py` (new) — the deterministic unit tests for the new module.

## Requirements

### Public API

Add `src/pydicom/util/frames.py` exposing a single public function with this exact signature:

```python
def get_frame(arr, ds, index)
```

- `arr` is a `numpy.ndarray` representing the dataset's pixel data.
- `ds` is a `pydicom.dataset.Dataset` that may define `NumberOfFrames`, `Rows`, and `Columns`.
- `index` is an `int` selecting which frame to return.
- The function returns a single 2-D `numpy.ndarray` of shape `(Rows, Columns)`. The returned array must share no memory side-effects that mutate `arr` (mutating the result must not alter `arr`).

### Selection contract

- When `ds` indicates a multi-frame object (`NumberOfFrames > 1`), `arr` has leading frame axis of length `NumberOfFrames`; `get_frame(arr, ds, index)` returns frame `index`.
- When `ds` indicates a single frame (`NumberOfFrames` absent or `== 1`), the only valid `index` is `0`, which returns the whole 2-D image.
- Negative indices count from the end (`-1` is the last frame), matching Python indexing.
- An out-of-range `index` (beyond the number of frames in either direction) must raise `IndexError`.

### Behavior and edge cases

- The number of available frames is determined from `ds.NumberOfFrames` (defaulting to `1` when absent), not merely from `arr.shape`.
- The returned frame's shape must equal `(ds.Rows, ds.Columns)` when those are present.
- Mutating the returned array must not change the original `arr`.

### Expected Functionality

- `arr` of shape `(5, 4, 4)` with `NumberOfFrames=5` and `index=2` → returns the 3rd frame, shape `(4, 4)`.
- `index=-1` on the same array → returns the 5th frame.
- `index=5` on the same array → raises `IndexError`.
- A single-frame `arr` of shape `(4, 4)` with `index=0` → returns the full image.

## Acceptance Criteria

- `src/pydicom/util/frames.py` exists and defines `get_frame(arr, ds, index)` returning a 2-D array.
- Multi-frame indexing (including negative indices), single-frame handling, frame-count derivation from `NumberOfFrames`, and `IndexError` on out-of-range all behave exactly as specified.
- The returned frame has shape `(Rows, Columns)` and mutating it does not affect `arr`.
- The new test file passes deterministically and covers positive/negative indexing, single-frame, the out-of-range `IndexError`, frame-count from metadata, shape, and result independence (≥10 test cases). A naive implementation that always indexes `arr` without consulting `NumberOfFrames` or that does not raise on out-of-range must fail.

Run exactly:

```bash
python -m pytest tests/test_util_frames.py -q
```

This command must exit with all tests passing.
