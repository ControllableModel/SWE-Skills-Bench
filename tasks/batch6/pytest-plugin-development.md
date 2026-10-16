# Task: Add a warning-filter spec parser utility with an exhaustive test suite

## Background

The pytest codebase (`pytest-dev/pytest`) accepts `-W` / `filterwarnings`
entries in Python's `action:message:category:module:lineno` form (see
`src/_pytest/warnings.py`). This task adds a small, self-contained module under
`src/_pytest/` that parses such a spec into a structured record, plus a thorough
test module under `testing/`.

## Files to Create/Modify

- `src/_pytest/_warnfilter.py` (new) — the utility module described below.
- `testing/test_warnfilter_util.py` (new) — the test module for the utility.

## Requirements

Implement `src/_pytest/_warnfilter.py` as a pure, dependency-free module (only
the Python standard library and `from __future__ import annotations` are allowed
— no imports from other `_pytest` modules). It MUST export exactly the following
with the listed behavior. The test module `testing/test_warnfilter_util.py` MUST
verify every behavior, constraint, and edge case enumerated here, including each
distinct failure mode.

### `FilterSpec` (data type)

An immutable record with five readable string/int fields: `action`, `message`,
`category`, `module`, and `lineno` (an `int`). Two records with identical fields
MUST compare equal.

### `parse_filter(spec: str) -> FilterSpec`

Parses a colon-separated warning filter spec.

- The fields are positional: `action:message:category:module:lineno`. Trailing
  fields may be omitted and default to: `message=""`, `category=""`,
  `module=""`, `lineno=0`.
- `action` is required and MUST be one of `"error"`, `"ignore"`, `"always"`,
  `"default"`, `"module"`, `"once"`. Any other action MUST raise `ValueError`
  containing the bad action and the input.
- A prefix is allowed: an `action` may be abbreviated to a unique prefix of a
  valid action (e.g. `"err"` -> `"error"`, `"i"` -> `"ignore"`); an ambiguous or
  non-matching prefix MUST raise `ValueError`. (`"o"` is ambiguous between
  `"once"` — and no other — so it resolves to `"once"`; verify a genuinely
  ambiguous case raises.)
- `lineno`, when present, MUST be a non-negative integer; a negative or
  non-integer lineno MUST raise `ValueError` containing the input.
- More than five colon-separated fields MUST raise `ValueError`.
- Surrounding whitespace around the whole spec is ignored, but whitespace inside
  the `message` field is preserved.

### Expected Functionality

- `parse_filter("error")` yields
  `FilterSpec("error", "", "", "", 0)`.
- `parse_filter("ignore::DeprecationWarning")` yields a record whose `message`
  is `""` and whose `category` is `"DeprecationWarning"`.
- `parse_filter("always:msg here:UserWarning:mymod:12")` preserves the inner
  space in `"msg here"` and parses `lineno == 12`.

### Constraints

- `parse_filter` is pure (no I/O, no global mutable state, deterministic).
- No third-party packages and no other `_pytest` imports.
- Every `ValueError` message MUST include the offending input string.

## Acceptance Criteria

- `src/_pytest/_warnfilter.py` exists and exports `FilterSpec` and
  `parse_filter` with the behavior specified above.
- `testing/test_warnfilter_util.py` contains test functions asserting: the
  five-field default-filling behavior, every valid action, prefix expansion
  including the ambiguous-prefix error, the empty-message-with-category case,
  message-whitespace preservation, the bad-action error, the negative /
  non-integer lineno errors, the too-many-fields error, and record equality.
- The following command passes with every test collected and no failures:

  ```
  python -m pytest testing/test_warnfilter_util.py -p no:cacheprovider -q
  ```

- A partial or hardcoded implementation that does not handle each enumerated edge
  case MUST cause at least one assertion in `testing/test_warnfilter_util.py` to
  fail.
