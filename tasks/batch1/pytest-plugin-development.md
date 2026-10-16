# Task: Add a node-id segment parser utility with an exhaustive test suite

## Background

The pytest codebase (`pytest-dev/pytest`) represents collected items with
"node ids" such as `tests/test_app.py::TestClass::test_method[param-1]`. This
task adds a small, self-contained utility module under `src/_pytest/` that
parses and normalizes these node ids, plus a thorough test module under
`testing/` that exercises every behavior the utility exposes.

## Files to Create/Modify

- `src/_pytest/_nodeid.py` (new) — the utility module described below.
- `testing/test_nodeid_util.py` (new) — the test module for the utility.

## Requirements

Implement `src/_pytest/_nodeid.py` as a pure, dependency-free module (only the
Python standard library and `from __future__ import annotations` are allowed —
no imports from other `_pytest` modules). It MUST export exactly the following
public callables and the listed behavior. The test module
`testing/test_nodeid_util.py` MUST verify every behavior, constraint, and edge
case enumerated here, including each distinct failure mode.

### `split_nodeid(nodeid: str) -> tuple[str, list[str]]`

Splits a node id into its file path and the list of `::`-separated name
segments after the path.

- For `"tests/test_app.py::TestClass::test_method"` returns
  `("tests/test_app.py", ["TestClass", "test_method"])`.
- For a node id with no `::` (e.g. `"tests/test_app.py"`) returns
  `("tests/test_app.py", [])`.
- A trailing or leading empty segment (e.g. `"a.py::"` or `"a.py::::b"`) MUST
  cause a `ValueError` whose message contains the offending node id.
- An empty string MUST raise `ValueError`.
- Whitespace inside a segment is preserved (segments are not stripped).

### `parametrize_id(segment: str) -> str | None`

Given a single name segment, returns the parametrization id inside the trailing
`[...]`, or `None` when the segment is not parametrized.

- `"test_method[param-1]"` returns `"param-1"`.
- `"test_method"` returns `None`.
- A segment whose bracket content is empty, e.g. `"test_method[]"`, returns the
  empty string `""` (which is distinct from `None`).
- Only a `[` matched by a `]` at the very end of the segment counts; a `[`
  without a closing `]` at the end (e.g. `"test_method[oops"`) returns `None`.
- Nested brackets keep the outermost pair: `"t[a[b]c]"` returns `"a[b]c"`.

### `base_name(segment: str) -> str`

Returns the segment with any trailing parametrization (`[...]`) removed.

- `"test_method[param-1]"` returns `"test_method"`.
- `"test_method"` returns `"test_method"` unchanged.
- `"test_method[]"` returns `"test_method"`.
- If the segment is itself a bare parametrization with no base name (e.g.
  `"[x]"`) the result is the empty string `""`.

### `normalize_nodeid(nodeid: str, *, sep: str = "/") -> str`

Returns a normalized node id whose path component uses `sep` as the path
separator and has redundant `.` path components and duplicate separators
removed; name segments are left untouched.

- Backslashes in the path component are treated as separators and converted to
  `sep` (so `"a\\b.py::t"` with default `sep` yields `"a/b.py::t"`).
- Redundant components are collapsed: `"a/./b//c.py::t"` yields `"a/b/c.py::t"`.
- A `..` component is NOT collapsed away (it is kept verbatim) — do not resolve
  parent directories.
- When `sep` is not `"/"`, both `/` and `\` in the input path are replaced by
  `sep`.
- Normalization MUST NOT alter the name segments, even if they contain `/`,
  `\`, or `.` characters.

### Expected Functionality

- `split_nodeid` round-trips with `normalize_nodeid` for already-normalized ids:
  normalizing an already-clean node id returns it unchanged.
- `base_name(seg)` combined with `parametrize_id(seg)` fully reconstructs `seg`
  for any parametrized segment: when `parametrize_id(seg)` is not `None`, then
  `seg == base_name(seg) + "[" + parametrize_id(seg) + "]"`.

### Constraints

- All four functions are pure (no I/O, no global mutable state, deterministic).
- No third-party packages and no other `_pytest` imports.
- Error messages for `ValueError` cases MUST include the offending input string.

## Acceptance Criteria

- `src/_pytest/_nodeid.py` exists and exports `split_nodeid`, `parametrize_id`,
  `base_name`, and `normalize_nodeid` with the behavior specified above.
- `testing/test_nodeid_util.py` exists and contains test functions that assert
  every behavior and every distinct failure mode listed in Requirements,
  including: the empty-segment and empty-string `ValueError` cases for
  `split_nodeid`; the `None` vs `""` distinction in `parametrize_id`; the
  unmatched-bracket and nested-bracket cases; the bare-parametrization case for
  `base_name`; and the backslash, `.`-collapse, `..`-preserved, duplicate-sep,
  custom-`sep`, and name-segment-untouched cases for `normalize_nodeid`.
- The following command passes with every test collected and no failures:

  ```
  python -m pytest testing/test_nodeid_util.py -p no:cacheprovider -q
  ```

- A partial or hardcoded implementation that does not handle each enumerated
  edge case (empty-segment rejection, `None` vs `""`, unmatched/nested brackets,
  `..` preservation, custom separators, untouched name segments) MUST cause at
  least one assertion in `testing/test_nodeid_util.py` to fail.
