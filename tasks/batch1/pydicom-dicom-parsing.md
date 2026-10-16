# Task: Implement a Recursive Dataset De-Identification Utility

## Background

The `pydicom` library (this repository) reads and edits DICOM datasets, which frequently carry patient-identifying information that must be stripped before the data can be shared for research. This task adds a small, self-contained utility to `src/pydicom/util/` that produces a de-identified copy of a `pydicom.dataset.Dataset`.

## Files to Create/Modify

- `src/pydicom/util/deident.py` (new) — the de-identification utility module.
- `tests/test_util_deident.py` (new) — the deterministic unit tests for the new module.

## Requirements

### Public API

Add a module `src/pydicom/util/deident.py` exposing a single public function with this exact signature:

```python
def deidentify(ds, *, in_place=False)
```

- `ds` is a `pydicom.dataset.Dataset`.
- When `in_place=False` (default), the input dataset must **not** be mutated; the function returns a new, independent `Dataset` with the de-identification applied. When `in_place=True`, the function modifies `ds` and returns the same object.
- The function returns a `Dataset`.

### Which elements are affected

The function operates on a fixed policy keyed by DICOM **keyword**. Two disjoint groups of identifying elements must be handled:

- **Replaced** (kept in the dataset but given a fixed placeholder value): `PatientName` → `"ANONYMOUS"`, `PatientID` → `"ANONYMOUS"`, `PatientBirthDate` → `"19000101"`.
- **Removed** (the element is deleted entirely if present): `PatientAddress`, `PatientTelephoneNumbers`, `InstitutionName`, `InstitutionAddress`, `ReferringPhysicianName`, `PerformingPhysicianName`, `OperatorsName`.

All other elements (including pixel data and image geometry such as `Rows`, `Columns`, `PixelData`, `PixelSpacing`, `Modality`, `StudyInstanceUID`) must be left exactly as they were.

### Behavior and edge cases

- **Idempotent absence handling**: if a "replaced" keyword is absent from the dataset, it must **not** be added — only existing elements are replaced. Removing an absent element is a no-op.
- **Nested sequences**: the policy must be applied at every nesting depth. If an identifying element appears inside an item of a sequence (for example an item of `OtherPatientIDsSequence` containing a `PatientID`, or any nested `Dataset`), it must be replaced/removed there too, at arbitrary depth.
- **Non-mutation guarantee**: with `in_place=False`, after the call the original `ds` and every nested dataset inside it must still hold their original values; mutating the returned dataset (including its nested sequence items) must not affect the input.
- **Idempotence**: calling `deidentify` on an already de-identified dataset must yield an equivalent result (the replaced values stay at their placeholders and the removed elements stay absent).
- **Return contract**: the returned object must be a `Dataset` for which the affected keywords reflect the policy above and all unaffected elements compare equal to the input's.

### Expected Functionality

- A dataset with `PatientName="Doe^John"`, `PatientID="ID-42"`, `PatientBirthDate="19850102"`, `InstitutionName="General Hospital"`, `Modality="CT"`, `Rows=4` → after de-identification: `PatientName=="ANONYMOUS"`, `PatientID=="ANONYMOUS"`, `PatientBirthDate=="19000101"`, `InstitutionName` absent, and `Modality`/`Rows` unchanged.
- A dataset whose `OtherPatientIDsSequence[0]` item has `PatientID="NESTED"` and `InstitutionAddress="..."` → after de-identification the nested item's `PatientID=="ANONYMOUS"` and its `InstitutionAddress` is absent.
- Calling with `in_place=False` then mutating the result leaves the source dataset's values intact.

## Acceptance Criteria

- A new module `src/pydicom/util/deident.py` exists and defines `deidentify(ds, *, in_place=False)`.
- The replacement and removal policy is applied exactly as specified, at top level and within nested sequence items at any depth, with absent elements neither added nor erroring.
- Unaffected elements (pixel data, geometry, UIDs, modality, etc.) are byte-for-value identical before and after.
- The non-mutation contract for `in_place=False` and the in-place contract for `in_place=True` both hold.
- The new test file passes deterministically and exercises at least the top-level replace, top-level remove, nested-sequence, absent-element, non-mutation, and idempotence cases (≥10 test cases). A naive implementation that ignores nested sequences, mutates the input, or adds absent elements must fail.

Run exactly:

```bash
python -m pytest tests/test_util_deident.py -q
```

This command must exit with all tests passing.
