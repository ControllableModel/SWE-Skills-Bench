# Task: Build a Structured Metadata Summary Extractor

## Background

The `pydicom` library (this repository) reads DICOM datasets whose contents are spread across many data elements. This task adds a self-contained utility to `src/pydicom/util/` that distils a `pydicom.dataset.Dataset` into a flat, predictable summary dictionary suitable for indexing or display.

## Files to Create/Modify

- `src/pydicom/util/summary.py` (new) — the metadata summary utility module.
- `tests/test_util_summary.py` (new) — the deterministic unit tests for the new module.

## Requirements

### Public API

Add `src/pydicom/util/summary.py` exposing a single public function with this exact signature:

```python
def summarize(ds, *, include_missing=False)
```

- `ds` is a `pydicom.dataset.Dataset`.
- The function returns a plain `dict` with string keys, and must **not** mutate `ds`.

### Output contract

The returned dict must contain exactly the following keys, derived from these DICOM elements:

- `"patient_name"` — string form of `PatientName`.
- `"patient_id"` — `PatientID`.
- `"modality"` — `Modality`.
- `"study_date"` — `StudyDate`.
- `"rows"` — `Rows` as a Python `int`.
- `"columns"` — `Columns` as a Python `int`.
- `"num_elements"` — the number of top-level data elements present in `ds` (file-meta elements are not counted), as an `int`.

### Behavior and edge cases

- For a missing element: when `include_missing=False` (default), the corresponding key must be **omitted** from the output dict entirely. When `include_missing=True`, the key must be present with value `None`.
- `"patient_name"` must be a `str` (not a `PersonName` object) so the result is JSON-serializable; e.g. a `PatientName` of `"Doe^John"` yields `"Doe^John"`.
- `"rows"`, `"columns"`, and `"num_elements"` must always be Python `int` when present (never a pydicom-specific numeric subclass instance that fails an `is`/`type` check against `int`).
- `"num_elements"` counts only the dataset's own elements, independent of `include_missing`.
- The function never raises on a dataset that is missing some or all of these elements.

### Expected Functionality

- A dataset with `PatientName="Doe^John"`, `PatientID="ID7"`, `Modality="MR"`, `Rows=64`, `Columns=64` and no `StudyDate` → with default flags, the result has keys `patient_name, patient_id, modality, rows, columns, num_elements` and no `study_date` key.
- The same dataset with `include_missing=True` → includes `"study_date": None`.
- `summarize` called twice on the same dataset returns equal dicts and leaves the dataset unchanged.

## Acceptance Criteria

- `src/pydicom/util/summary.py` exists and defines `summarize(ds, *, include_missing=False)` returning a `dict`.
- Missing-element handling for both `include_missing` modes is exactly as specified.
- `patient_name` is a `str`; `rows`/`columns`/`num_elements` are Python `int` with values matching the dataset; the dataset is not mutated.
- The new test file passes deterministically and covers present/missing elements under both flag values, type guarantees, the `num_elements` count, and non-mutation (≥10 test cases). A naive implementation that returns `PersonName`/non-`int` types, always includes missing keys, or omits `num_elements` must fail.

Run exactly:

```bash
python -m pytest tests/test_util_summary.py -q
```

This command must exit with all tests passing.
