# Task: Implement a DICOM Series Slice Sorter

## Background

The `pydicom` library (this repository) is commonly used to load a folder of single-slice DICOM files that together make up one 3-D acquisition. This task adds a self-contained utility to `src/pydicom/util/` that orders a list of in-memory datasets into correct spatial slice order.

## Files to Create/Modify

- `src/pydicom/util/series.py` (new) — the slice-sorting utility module.
- `tests/test_util_series.py` (new) — the deterministic unit tests for the new module.

## Requirements

### Public API

Add `src/pydicom/util/series.py` exposing a single public function with this exact signature:

```python
def sort_slices(datasets)
```

- `datasets` is an iterable of `pydicom.dataset.Dataset` objects.
- The function returns a **new** `list` of the same dataset objects in sorted order. It must not mutate the input iterable's underlying list ordering and must not mutate any dataset.

### Ordering contract

- Primary sort key: the third component of `ImagePositionPatient` (the patient z-coordinate), ascending, compared as `float`.
- For datasets that lack `ImagePositionPatient`, fall back to `InstanceNumber` (ascending, as `int`).
- If a dataset has neither element, it must be placed **after** all datasets that have at least one of the keys, preserving the original relative order among such elementless datasets.
- The sort must be **stable**: datasets comparing equal on the chosen key keep their original relative order.

### Behavior and edge cases

- `ImagePositionPatient` takes precedence over `InstanceNumber`: if one dataset has a position and another has only an instance number, the one with a position is ordered by its z-value and is considered to come *before* the position-less one only based on key availability rules above (position-bearing datasets are ordered among themselves by z; instance-only datasets are ordered among themselves by instance number; datasets with neither go last).
- The function returns a list of the *same* object references (identity preserved), not copies.
- Passing an empty iterable returns an empty list.
- The function must accept a generator as input.

### Expected Functionality

- Three datasets with `ImagePositionPatient` z = `[2.0, 0.0, 1.0]` → returned order has z `0.0, 1.0, 2.0`.
- Datasets lacking position but with `InstanceNumber = [3, 1, 2]` → returned order has instance numbers `1, 2, 3`.
- A dataset with neither element is placed last, after all keyed datasets.

## Acceptance Criteria

- `src/pydicom/util/series.py` exists and defines `sort_slices(datasets)` returning a new `list`.
- Position-based ordering, instance-number fallback, last-placement of elementless datasets, and stability all behave exactly as specified.
- Object identity is preserved; an empty input and a generator input are both handled; no dataset is mutated.
- The new test file passes deterministically and covers position sort, instance-number fallback, mixed/elementless placement, stability, identity preservation, empty input, and generator input (≥10 test cases). A naive implementation that crashes on missing elements or is unstable must fail.

Run exactly:

```bash
python -m pytest tests/test_util_series.py -q
```

This command must exit with all tests passing.
