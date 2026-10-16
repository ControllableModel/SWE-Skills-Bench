# Task: Add a terminal-width text truncation utility with an exhaustive test suite

## Background

The pytest codebase (`pytest-dev/pytest`) writes wrapped, width-aware output to
the terminal (see `src/_pytest/_io/`). This task adds a small, self-contained
module under `src/_pytest/_io/` that truncates and pads display strings to a
target column width, plus a thorough test module under `testing/`.

## Files to Create/Modify

- `src/_pytest/_io/_truncate.py` (new) — the utility module described below.
- `testing/io/test_truncate_util.py` (new) — the test module for the utility.

## Requirements

Implement `src/_pytest/_io/_truncate.py` as a pure, dependency-free module (only
the Python standard library and `from __future__ import annotations` are allowed
— no imports from other `_pytest` modules). It MUST export exactly the following
public callables with the listed behavior. The test module
`testing/io/test_truncate_util.py` MUST verify every behavior, constraint, and
edge case enumerated here, including each distinct failure mode.

### `ellipsize(text: str, width: int, *, marker: str = "...") -> str`

Returns `text` shortened so its character length does not exceed `width`,
appending `marker` when truncation happens.

- When `len(text) <= width`, returns `text` unchanged (no marker added).
- When truncation is needed, the result length is exactly `width` and ends with
  `marker`: `ellipsize("abcdef", 5)` returns `"ab..."`.
- A custom marker is honored: `ellipsize("abcdef", 4, marker="…")` returns
  `"abc…"` (single-character marker).
- If `width` is less than `len(marker)`, the result is `marker` truncated to
  `width` characters (e.g. `ellipsize("abcdef", 2)` returns `".."`).
- A `width` of `0` returns the empty string `""`.
- A negative `width` MUST raise `ValueError` whose message contains the value.

### `pad(text: str, width: int, *, align: str = "left", fill: str = " ") -> str`

Pads `text` with `fill` to reach `width` columns.

- `align` is one of `"left"`, `"right"`, `"center"`; any other value MUST raise
  `ValueError`.
- `pad("ab", 5)` returns `"ab   "`, `pad("ab", 5, align="right")` returns
  `"   ab"`, `pad("ab", 5, align="center")` returns `" ab  "` (extra fill goes to
  the right for odd remainders).
- When `len(text) >= width`, returns `text` unchanged (never truncates).
- `fill` MUST be exactly one character; otherwise raise `ValueError`.
- A negative `width` MUST raise `ValueError`.

### Expected Functionality

- For any `text` and any `width >= 0`, `len(ellipsize(text, width)) <= width`.
- For any `text` and `width`, `len(pad(text, width)) == max(len(text), width)`.
- `center` padding splits remainder so the right side never has fewer fill chars
  than the left.

### Constraints

- Both functions are pure (no I/O, no global mutable state, deterministic).
- No third-party packages and no other `_pytest` imports.
- Every `ValueError` message MUST include the offending argument value.

## Acceptance Criteria

- `src/_pytest/_io/_truncate.py` exists and exports `ellipsize` and `pad` with
  the behavior specified above.
- `testing/io/test_truncate_util.py` contains test functions asserting every
  behavior and failure mode: no-truncation passthrough, exact-width truncation,
  custom marker, marker-wider-than-width, zero width, negative-width error; all
  three alignments, the odd-remainder center rule, no-truncation-when-too-long,
  bad-align error, and multi-character/empty `fill` error.
- The following command passes with every test collected and no failures:

  ```
  python -m pytest testing/io/test_truncate_util.py -p no:cacheprovider -q
  ```

- A partial or hardcoded implementation that does not handle each enumerated edge
  case MUST cause at least one assertion in `testing/io/test_truncate_util.py` to
  fail.
