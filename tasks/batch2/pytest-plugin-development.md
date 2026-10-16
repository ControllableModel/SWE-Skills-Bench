# Task: Add a duration-string parser and formatter utility with an exhaustive test suite

## Background

The pytest codebase (`pytest-dev/pytest`) reports test durations and accepts
human-readable time strings in several places. This task adds a small,
self-contained module under `src/_pytest/` that parses and formats durations,
plus a thorough test module under `testing/` exercising every behavior.

## Files to Create/Modify

- `src/_pytest/_duration.py` (new) — the utility module described below.
- `testing/test_duration_util.py` (new) — the test module for the utility.

## Requirements

Implement `src/_pytest/_duration.py` as a pure, dependency-free module (only the
Python standard library and `from __future__ import annotations` are allowed — no
imports from other `_pytest` modules). It MUST export exactly the following
public callables with the listed behavior. The test module
`testing/test_duration_util.py` MUST verify every behavior, constraint, and edge
case enumerated here, including each distinct failure mode.

### `parse_duration(text: str) -> float`

Parses a duration string into a number of seconds (a `float`).

- Accepts a bare number meaning seconds: `"5"` returns `5.0`, `"0.25"` returns
  `0.25`.
- Accepts unit-suffixed values: `"500ms"` returns `0.5`, `"2s"` returns `2.0`,
  `"3m"` returns `180.0`, `"1h"` returns `3600.0`.
- Accepts a multi-term expression separated by whitespace: `"1h 30m"` returns
  `5400.0`, `"1m 30s"` returns `90.0`.
- Leading and trailing whitespace is ignored; internal runs of whitespace
  collapse.
- The unit suffix is case-insensitive: `"2S"` equals `"2s"`.
- A negative value MUST raise `ValueError` whose message contains the input.
- An empty or whitespace-only string MUST raise `ValueError`.
- An unknown unit (e.g. `"5d"`) MUST raise `ValueError` whose message contains
  the offending unit and the input.
- A term with no numeric part (e.g. `"ms"`) MUST raise `ValueError`.

### `format_duration(seconds: float) -> str`

Formats a non-negative number of seconds into a compact human string.

- `0` returns `"0s"`.
- `90` returns `"1m30s"` (no spaces; omit zero-valued higher-or-lower units only
  when they are zero, but always include at least one unit).
- `3600` returns `"1h"`, `3661` returns `"1h1m1s"`.
- `0.5` returns `"500ms"`; sub-second values below `1` are rendered in `ms`.
- Milliseconds are rounded to the nearest whole millisecond.
- A negative input MUST raise `ValueError`.

### Expected Functionality

- Round-trip stability for whole-second values: for any non-negative integer
  number of seconds `n` that is representable, `parse_duration(format_duration(n))`
  equals `float(n)`.
- `format_duration` never emits a unit whose value is zero except for the lone
  `"0s"` result.

### Constraints

- Both functions are pure (no I/O, no global mutable state, deterministic).
- No third-party packages and no other `_pytest` imports.
- Every `ValueError` message MUST include the offending input string.

## Acceptance Criteria

- `src/_pytest/_duration.py` exists and exports `parse_duration` and
  `format_duration` with the behavior specified above.
- `testing/test_duration_util.py` contains test functions asserting every
  behavior and every distinct failure mode listed in Requirements, including:
  bare numbers, every unit, multi-term expressions, case-insensitivity, and each
  `ValueError` case (negative, empty, unknown unit, missing number); plus the
  `"0s"`, `"1m30s"`, `"1h1m1s"`, and `"500ms"` formatting cases and the
  round-trip property.
- The following command passes with every test collected and no failures:

  ```
  python -m pytest testing/test_duration_util.py -p no:cacheprovider -q
  ```

- A partial or hardcoded implementation that does not handle each enumerated edge
  case MUST cause at least one assertion in `testing/test_duration_util.py` to
  fail.
