# Task: Implement a Tag and Keyword Resolver

## Background

The `pydicom` library (this repository) identifies every data element by a numeric `(group, element)` tag, while users typically refer to elements by their human-readable keyword (e.g. `PatientName`). This task adds a self-contained utility to `src/pydicom/util/` that translates between the two forms and describes a tag.

## Files to Create/Modify

- `src/pydicom/util/tagref.py` (new) — the tag/keyword resolver module.
- `tests/test_util_tagref.py` (new) — the deterministic unit tests for the new module.

## Requirements

### Public API

Add `src/pydicom/util/tagref.py` exposing exactly these two public functions:

```python
def resolve(name_or_tag)
def describe(name_or_tag)
```

- `name_or_tag` may be a keyword `str` (e.g. `"PatientName"`), a `(group, element)` tuple of ints, or an `int`/tag value.
- `resolve` returns a normalized tag as an `int` (the 32-bit combined group/element value).
- `describe` returns a `dict` describing the element.

### `resolve` contract

- Given a known keyword string, return its tag as an `int`.
- Given a `(group, element)` tuple or an `int`, return the equivalent combined `int` tag.
- Given an unknown keyword string, raise `ValueError`.

### `describe` contract

`describe(name_or_tag)` returns a `dict` with:

- `"tag"` — the combined tag as an `int`.
- `"group"` — the group number as an `int`.
- `"element"` — the element number as an `int`.
- `"keyword"` — the element's keyword `str` (empty string if the tag is not in the dictionary).
- `"vr"` — the Value Representation `str` from the data dictionary.
- `"name"` — the element's descriptive name `str`.

### Behavior and edge cases

- `resolve("PatientName")` and `resolve((0x0010, 0x0010))` and `resolve(0x00100010)` must all return the same `int`.
- `"group"` and `"element"` in `describe` must be consistent with `"tag"` (i.e. `tag == group << 16 | element`).
- For a tag not present in the data dictionary, `describe` must not raise: `"keyword"` is `""` and `"name"`/`"vr"` reflect the unknown/UN handling from the dictionary lookup.
- `resolve` on an unknown keyword raises `ValueError`; `describe` on an unknown *keyword string* likewise raises `ValueError` (only numeric/tuple unknown tags are tolerated).

### Expected Functionality

- `resolve("Modality")` equals `resolve((0x0008, 0x0060))`.
- `describe("PatientName")` → `{"tag": 0x00100010, "group": 0x0010, "element": 0x0010, "keyword": "PatientName", "vr": "PN", "name": ...}`.
- `describe((0x0011, 0x0011))` (a private/unknown tag) → does not raise; `"keyword"` is `""`.
- `resolve("NotAKeyword")` raises `ValueError`.

## Acceptance Criteria

- `src/pydicom/util/tagref.py` exists and defines `resolve` and `describe` as specified.
- All three input forms resolve to the same `int` tag; the `tag`/`group`/`element` consistency holds; VR/keyword/name are read from the data dictionary.
- Unknown keyword strings raise `ValueError`; unknown numeric/tuple tags are described without raising.
- The new test file passes deterministically and covers keyword/tuple/int equivalence, full `describe` output for a known tag, the unknown-numeric-tag tolerance, and the unknown-keyword `ValueError` (≥10 test cases). A naive implementation that hardcodes one tag or fails the cross-form equivalence must fail.

Run exactly:

```bash
python -m pytest tests/test_util_tagref.py -q
```

This command must exit with all tests passing.
