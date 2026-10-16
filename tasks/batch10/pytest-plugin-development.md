# Task: Add a unified-diff line renderer utility with an exhaustive test suite

## Background

The pytest codebase (`pytest-dev/pytest`) renders rich assertion failure output,
including line-by-line diffs of expected vs actual values. This task adds a
small, self-contained module under `src/_pytest/` that turns two sequences of
lines into a compact prefixed diff, plus a thorough test module under `testing/`.

## Files to Create/Modify

- `src/_pytest/_linediff.py` (new) — the utility module described below.
- `testing/test_linediff_util.py` (new) — the test module for the utility.

## Requirements

Implement `src/_pytest/_linediff.py` as a pure module that may import only the
Python standard library (`difflib` is permitted) and use
`from __future__ import annotations` — no imports from other `_pytest` modules.
It MUST export exactly the following with the listed behavior. The test module
`testing/test_linediff_util.py` MUST verify every behavior, constraint, and edge
case enumerated here, including each distinct failure mode.

### `diff_lines(expected: list[str], actual: list[str]) -> list[str]`

Returns a list of prefixed lines describing how to turn `expected` into `actual`.

- Unchanged lines are prefixed with two spaces `"  "`.
- Lines present only in `expected` (removed) are prefixed with `"- "`.
- Lines present only in `actual` (added) are prefixed with `"+ "`.
- The prefixes preserve the original line text exactly (including any trailing
  whitespace inside the line).
- When `expected == actual`, every output line is an unchanged (`"  "`) line and
  the count equals the number of input lines.
- When both inputs are empty, returns `[]`.
- Input lines MUST NOT contain a `"\n"`; if any does, raise `ValueError`
  containing the offending line.

### `count_changes(diff: list[str]) -> tuple[int, int]`

Given the output of `diff_lines`, returns `(removed, added)` — the number of
`"- "` and `"+ "` lines respectively. Unchanged lines are ignored.

### `is_equal(expected: list[str], actual: list[str]) -> bool`

Returns `True` iff `diff_lines(expected, actual)` contains no `"+ "` or `"- "`
line. Equivalent to `expected == actual` but computed from the diff.

### Expected Functionality

- For `expected=["a","b","c"]` and `actual=["a","x","c"]`, the diff contains
  exactly one removed (`"- b"`) and one added (`"+ x"`) line, and two unchanged
  lines; `count_changes` returns `(1, 1)`; `is_equal` returns `False`.
- For identical inputs, `count_changes` returns `(0, 0)` and `is_equal` returns
  `True`.
- A pure-append case (`expected=["a"]`, `actual=["a","b"]`) yields exactly one
  added line and zero removed lines.

### Constraints

- All functions are pure (no I/O, no global mutable state, deterministic).
- No third-party packages and no other `_pytest` imports.
- The embedded-newline `ValueError` message MUST include the offending line.

## Acceptance Criteria

- `src/_pytest/_linediff.py` exists and exports `diff_lines`, `count_changes`,
  and `is_equal` with the behavior specified above.
- `testing/test_linediff_util.py` contains test functions asserting: the three
  prefix kinds and exact text preservation, the all-unchanged equal case, the
  both-empty case, the embedded-newline `ValueError`, the substitution example
  with its `count_changes`/`is_equal` results, the identical-inputs counts, and
  the pure-append case.
- The following command passes with every test collected and no failures:

  ```
  python -m pytest testing/test_linediff_util.py -p no:cacheprovider -q
  ```

- A partial or hardcoded implementation that does not handle each enumerated edge
  case MUST cause at least one assertion in `testing/test_linediff_util.py` to
  fail.
