# Task: Implement a Nested Sequence Flattener

## Background

The `pydicom` library (this repository) represents complex structured data (such as referenced studies or structured-report content) as **sequences** of nested datasets, sometimes many levels deep. This task adds a self-contained utility to `src/pydicom/util/` that walks a dataset and yields a flat, path-addressed view of every element including those inside sequences.

## Files to Create/Modify

- `src/pydicom/util/flatten.py` (new) — the sequence-flattening utility module.
- `tests/test_util_flatten.py` (new) — the deterministic unit tests for the new module.

## Requirements

### Public API

Add `src/pydicom/util/flatten.py` exposing a single public function with this exact signature:

```python
def flatten(ds)
```

- `ds` is a `pydicom.dataset.Dataset`.
- The function returns a `dict` mapping a string **path** to the element's value, and must not mutate `ds`.

### Path contract

- A top-level non-sequence element is keyed by its keyword, e.g. `"PatientName"`.
- An element inside a sequence is keyed by joining with `.` and indexing each sequence item, e.g. an element `ReferencedSOPInstanceUID` inside item `0` of `ReferencedStudySequence` is keyed `"ReferencedStudySequence.0.ReferencedSOPInstanceUID"`.
- Nesting continues to arbitrary depth, prefixing each level's keyword and item index.
- Sequence elements themselves do **not** appear as their own keys; only their leaf (non-sequence) descendants do.

### Value contract

- The mapped value is the element's `.value`. For `PersonName` values, store the `str` form so the result is comparable/serializable.
- Elements with an empty value (e.g. a zero-length string) are still included.

### Behavior and edge cases

- An empty sequence contributes no keys.
- Two items in the same sequence produce distinct keys via their differing indices (`...0...` vs `...1...`).
- The order of insertion follows the dataset's element order and the items' order (the returned dict's iteration order reflects a depth-first traversal), but tests may compare as an unordered mapping.
- The function does not raise on a dataset containing only top-level elements (no sequences).

### Expected Functionality

- A dataset with `PatientName="Doe^John"`, `Modality="CT"` and no sequences → `{"PatientName": "Doe^John", "Modality": "CT"}`.
- A dataset with `ReferencedStudySequence` having one item whose `ReferencedSOPInstanceUID="1.2.3"` → result contains `"ReferencedStudySequence.0.ReferencedSOPInstanceUID": "1.2.3"`.
- A two-level nested sequence yields a key with two `.<index>.` segments.

## Acceptance Criteria

- `src/pydicom/util/flatten.py` exists and defines `flatten(ds)` returning a `dict`.
- Top-level and arbitrarily nested sequence elements are flattened into dotted, index-bearing keys exactly as specified; sequence containers are not themselves keyed.
- `PersonName` values are stored as `str`; empty values are included; empty sequences contribute nothing; `ds` is not mutated.
- The new test file passes deterministically and covers top-level only, single-level sequence, multi-item sequence (distinct keys), two-level nesting, empty sequence, `PersonName` stringification, and non-mutation (≥10 test cases). A naive implementation that only handles top-level elements or omits item indices must fail.

Run exactly:

```bash
python -m pytest tests/test_util_flatten.py -q
```

This command must exit with all tests passing.
