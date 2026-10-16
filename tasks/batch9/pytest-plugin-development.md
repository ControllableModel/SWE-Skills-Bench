# Task: Add a fixture-scope ordering and validation utility with an exhaustive test suite

## Background

The pytest codebase (`pytest-dev/pytest`) orders fixtures by scope —
`session` > `package` > `module` > `class` > `function` — and validates scope
names (see `src/_pytest/scope.py`). This task adds a small, self-contained module
under `src/_pytest/` that ranks and compares scopes, plus a thorough test module
under `testing/`.

## Files to Create/Modify

- `src/_pytest/_scoperank.py` (new) — the utility module described below.
- `testing/test_scoperank_util.py` (new) — the test module for the utility.

## Requirements

Implement `src/_pytest/_scoperank.py` as a pure, dependency-free module (only the
Python standard library and `from __future__ import annotations` are allowed — no
imports from other `_pytest` modules). It MUST export exactly the following with
the listed behavior. The test module `testing/test_scoperank_util.py` MUST verify
every behavior, constraint, and edge case enumerated here, including each
distinct failure mode.

### `SCOPES` (sequence)

A read-only ordered sequence of the five scope names, broadest first:
`("session", "package", "module", "class", "function")`.

### `rank(scope: str) -> int`

- Returns the 0-based index where `session` is `0` (broadest) and `function` is
  `4` (narrowest).
- An unknown scope MUST raise `ValueError` whose message contains the offending
  scope and lists the valid scopes.

### `is_broader(a: str, b: str) -> bool`

- Returns `True` when scope `a` is strictly broader than scope `b` (i.e. lives
  earlier in `SCOPES`); equal scopes return `False`.
- Either invalid scope name MUST raise `ValueError`.

### `narrowest(scopes: Iterable[str]) -> str`

- Returns the narrowest scope among a non-empty iterable.
- An empty iterable MUST raise `ValueError`.
- Any invalid member MUST raise `ValueError`.

### `sort_by_scope(items: Iterable[tuple[str, str]]) -> list[tuple[str, str]]`

- Each item is a `(name, scope)` pair. Returns the items ordered from broadest
  scope to narrowest scope.
- Items sharing the same scope MUST retain their original relative order (stable
  sort).
- Any item with an invalid scope MUST raise `ValueError`.

### Expected Functionality

- `rank("session") < rank("function")` and the full ranking is strictly
  increasing across `SCOPES`.
- `is_broader("module", "function")` is `True`; `is_broader("function",
  "module")` is `False`; `is_broader("class", "class")` is `False`.
- `narrowest(["session", "module", "class"])` returns `"class"`.
- `sort_by_scope([("a","function"),("b","session"),("c","function")])` returns
  `[("b","session"),("a","function"),("c","function")]` (stable within equal
  scopes).

### Constraints

- All functions are pure (no I/O, no global mutable state, deterministic).
- No third-party packages and no other `_pytest` imports.
- Every `ValueError` message MUST include the offending scope string.

## Acceptance Criteria

- `src/_pytest/_scoperank.py` exists and exports `SCOPES`, `rank`, `is_broader`,
  `narrowest`, and `sort_by_scope` with the behavior specified above.
- `testing/test_scoperank_util.py` contains test functions asserting: the exact
  `SCOPES` order, the full strictly-increasing ranking, the invalid-scope error
  for `rank`, the broader/narrower/equal cases and invalid-scope error for
  `is_broader`, the `narrowest` happy path plus empty-iterable and invalid-member
  errors, and the stable broadest-to-narrowest ordering plus invalid-scope error
  for `sort_by_scope`.
- The following command passes with every test collected and no failures:

  ```
  python -m pytest testing/test_scoperank_util.py -p no:cacheprovider -q
  ```

- A partial or hardcoded implementation that does not handle each enumerated edge
  case MUST cause at least one assertion in `testing/test_scoperank_util.py` to
  fail.
