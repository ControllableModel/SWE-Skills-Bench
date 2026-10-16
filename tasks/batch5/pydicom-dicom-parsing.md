# Task: Implement a Transfer Syntax Inspector

## Background

The `pydicom` library (this repository) stores each file's encoding choice in its File Meta Information as a *Transfer Syntax UID*, which determines byte order, VR encoding, and whether pixel data is compressed. This task adds a self-contained utility to `src/pydicom/util/` that reports the encoding properties of a dataset.

## Files to Create/Modify

- `src/pydicom/util/syntax.py` (new) — the transfer-syntax inspection module.
- `tests/test_util_syntax.py` (new) — the deterministic unit tests for the new module.

## Requirements

### Public API

Add `src/pydicom/util/syntax.py` exposing a single public function with this exact signature:

```python
def describe_transfer_syntax(ds)
```

- `ds` is a `pydicom.dataset.Dataset` that may have a `file_meta` carrying `TransferSyntaxUID`.
- The function returns a `dict` and must not mutate `ds`.

### Output contract

When a `TransferSyntaxUID` is present, the returned dict must contain:

- `"uid"` — the transfer syntax UID as a `str`.
- `"name"` — the human-readable name of the UID as a `str`.
- `"is_compressed"` — `True` if the syntax is an encapsulated/compressed transfer syntax, else `False`.
- `"is_little_endian"` — `True`/`False` byte ordering as defined by the UID.
- `"is_implicit_vr"` — `True`/`False` whether VR is implicit, as defined by the UID.

When `ds` has no `file_meta`, or `file_meta` has no `TransferSyntaxUID`, the function returns the dict `{"uid": None}` and nothing else.

### Behavior and edge cases

- The boolean properties must reflect the actual semantics of the UID (e.g. Explicit VR Little Endian is uncompressed, little-endian, explicit VR; RLE Lossless is compressed; Implicit VR Little Endian is implicit VR).
- `"name"` must be the registered name for known UIDs, not just the raw UID digits.
- The function must not raise when `file_meta` is absent or empty.

### Expected Functionality

- A dataset whose `file_meta.TransferSyntaxUID` is Explicit VR Little Endian → `is_compressed=False`, `is_little_endian=True`, `is_implicit_vr=False`, and `"name"` is non-empty.
- A dataset whose transfer syntax is RLE Lossless → `is_compressed=True`.
- A dataset with no `file_meta` → result is exactly `{"uid": None}`.

## Acceptance Criteria

- `src/pydicom/util/syntax.py` exists and defines `describe_transfer_syntax(ds)` returning a `dict`.
- All five fields are populated correctly for present transfer syntaxes (uncompressed vs compressed, endianness, implicit/explicit VR), with `"name"` being the registered name.
- The missing-`file_meta`/missing-UID case returns exactly `{"uid": None}` without raising; `ds` is not mutated.
- The new test file passes deterministically and covers an uncompressed explicit-VR syntax, a compressed syntax, an implicit-VR syntax, name resolution, and the absent-file-meta case (≥10 test cases). A naive implementation that hardcodes `is_compressed=False` or omits `"name"` resolution must fail.

Run exactly:

```bash
python -m pytest tests/test_util_syntax.py -q
```

This command must exit with all tests passing.
