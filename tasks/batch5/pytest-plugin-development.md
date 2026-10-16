# Task: Add an INI-style option value coercion utility with an exhaustive test suite

## Background

The pytest codebase (`pytest-dev/pytest`) reads configuration values that arrive
as raw strings and must be coerced to typed values (bool / int / list / path
lists). This task adds a small, self-contained module under `src/_pytest/` that
performs these coercions, plus a thorough test module under `testing/`.

## Files to Create/Modify

- `src/_pytest/_inivalue.py` (new) — the utility module described below.
- `testing/test_inivalue_util.py` (new) — the test module for the utility.

## Requirements

Implement `src/_pytest/_inivalue.py` as a pure, dependency-free module (only the
Python standard library and `from __future__ import annotations` are allowed — no
imports from other `_pytest` modules). It MUST export exactly the following
public callables with the listed behavior. The test module
`testing/test_inivalue_util.py` MUST verify every behavior, constraint, and edge
case enumerated here, including each distinct failure mode.

### `to_bool(text: str) -> bool`

- The strings `"1"`, `"true"`, `"yes"`, `"on"` (case-insensitive, surrounding
  whitespace ignored) return `True`.
- The strings `"0"`, `"false"`, `"no"`, `"off"` return `False`.
- Any other value MUST raise `ValueError` whose message contains the input.

### `to_int(text: str, *, default: int | None = None) -> int`

- Parses a base-10 integer, ignoring surrounding whitespace; `"  42 "` returns
  `42`; a leading `+`/`-` sign is honored.
- An empty/whitespace-only string returns `default` when `default` is not
  `None`, otherwise raises `ValueError`.
- A non-integer value (e.g. `"4.5"`, `"abc"`) MUST raise `ValueError` containing
  the input, even when a `default` is supplied (a malformed non-empty value is
  never silently defaulted).

### `to_list(text: str, *, sep: str | None = None) -> list[str]`

- With `sep=None`, splits on any run of whitespace AND on newlines, dropping
  empty items: `"a b\n c"` returns `["a", "b", "c"]`.
- With an explicit `sep` (e.g. `","`), splits on that separator and strips each
  item, dropping empties: `"a, ,b ,"` with `sep=","` returns `["a", "b"]`.
- An empty/whitespace-only input returns `[]` for both modes.

### `to_path_list(text: str, *, base: str) -> list[str]`

- Splits like `to_list` with `sep=None`, then joins each relative entry onto
  `base` using POSIX `/` join semantics; entries that are already absolute
  (start with `/`) are kept as-is.
- Duplicate resulting paths are removed while preserving first-seen order.
- Redundant `.` components and duplicate `/` in each result are collapsed (but a
  `..` component is preserved verbatim, not resolved).

### Expected Functionality

- `to_bool` is exhaustive over its truthy/falsey vocabularies and rejects
  everything else.
- `to_int` distinguishes "empty -> default" from "malformed -> error".
- `to_list` and `to_path_list` never include empty-string items in their output.

### Constraints

- All functions are pure (no I/O, no filesystem access, deterministic).
- No third-party packages and no other `_pytest` imports.
- Every `ValueError` message MUST include the offending input string.

## Acceptance Criteria

- `src/_pytest/_inivalue.py` exists and exports `to_bool`, `to_int`, `to_list`,
  and `to_path_list` with the behavior specified above.
- `testing/test_inivalue_util.py` contains test functions asserting every truthy
  and falsey token for `to_bool` plus its error case; the empty-default,
  malformed-error-even-with-default, sign, and whitespace cases for `to_int`;
  both split modes, empty-item dropping, and empty-input cases for `to_list`;
  and the absolute-passthrough, dedup-order-preserving, `.`-collapse, and
  `..`-preserved cases for `to_path_list`.
- The following command passes with every test collected and no failures:

  ```
  python -m pytest testing/test_inivalue_util.py -p no:cacheprovider -q
  ```

- A partial or hardcoded implementation that does not handle each enumerated edge
  case MUST cause at least one assertion in `testing/test_inivalue_util.py` to
  fail.
