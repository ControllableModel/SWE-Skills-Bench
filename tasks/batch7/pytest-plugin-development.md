# Task: Add a glob-style test file pattern matcher with an exhaustive test suite

## Background

The pytest codebase (`pytest-dev/pytest`) decides which files are test modules
using shell-style patterns such as `test_*.py` / `*_test.py`. This task adds a
small, self-contained module under `src/_pytest/` that compiles and matches such
patterns against path-like strings, plus a thorough test module under
`testing/`.

## Files to Create/Modify

- `src/_pytest/_globmatch.py` (new) — the utility module described below.
- `testing/test_globmatch_util.py` (new) — the test module for the utility.

## Requirements

Implement `src/_pytest/_globmatch.py` as a pure, dependency-free module (only the
Python standard library and `from __future__ import annotations` are allowed — no
imports from other `_pytest` modules). It MUST export exactly the following with
the listed behavior. The test module `testing/test_globmatch_util.py` MUST verify
every behavior, constraint, and edge case enumerated here, including each
distinct failure mode.

### `matches(name: str, pattern: str) -> bool`

Matches a single path component against a glob pattern.

- `*` matches any run of characters including the empty run, but NEVER matches a
  `/`: `matches("test_app.py", "test_*.py")` is `True`; `matches("a/b", "a*b")`
  is `False`.
- `?` matches exactly one character that is not `/`.
- A character class `[abc]` matches one of the listed characters; a negated
  class `[!abc]` matches one character not listed; `[a-z]` matches a range.
- Matching is case-sensitive.
- An unterminated character class (e.g. `"a[bc"`) MUST raise `ValueError`
  containing the pattern.
- An empty pattern matches only the empty string.

### `matches_any(name: str, patterns: list[str]) -> bool`

- Returns `True` when `name` matches at least one pattern in `patterns`.
- An empty `patterns` list returns `False`.

### `split_segments(path: str) -> list[str]`

Splits a `/`-style path into non-empty components.

- `"a//b/./c"` returns `["a", "b", ".", "c"]` — duplicate separators are
  collapsed but a `.` component is preserved as its own segment.
- A leading `/` does not create an empty first segment.
- The empty string returns `[]`.

### Expected Functionality

- `matches_any("foo_test.py", ["test_*.py", "*_test.py"])` is `True`; the same
  name against `["test_*.py"]` alone is `False`.
- The `*`-does-not-cross-`/` rule is observable: `matches("a/b.py", "*.py")` is
  `False` while `matches("b.py", "*.py")` is `True`.
- Negated and ranged character classes both work and are mutually distinct.

### Constraints

- All functions are pure (no I/O, no filesystem access, deterministic).
- No third-party packages and no other `_pytest` imports.
- The character-class `ValueError` message MUST include the offending pattern.

## Acceptance Criteria

- `src/_pytest/_globmatch.py` exists and exports `matches`, `matches_any`, and
  `split_segments` with the behavior specified above.
- `testing/test_globmatch_util.py` contains test functions asserting: `*` (empty
  and non-empty, plus the no-`/` rule), `?`, positive/negated/ranged character
  classes, case-sensitivity, the empty-pattern case, the unterminated-class
  error; `matches_any` true/false and the empty-list case; and the
  duplicate-separator-collapse, `.`-preserved, leading-`/`, and empty-string
  cases for `split_segments`.
- The following command passes with every test collected and no failures:

  ```
  python -m pytest testing/test_globmatch_util.py -p no:cacheprovider -q
  ```

- A partial or hardcoded implementation that does not handle each enumerated edge
  case MUST cause at least one assertion in `testing/test_globmatch_util.py` to
  fail.
