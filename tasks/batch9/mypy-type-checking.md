# Task: Add an Include/Exclude Path Filter

## Background

Black decides which files to format by matching candidate paths against
include and exclude glob/regex patterns. This task adds a self-contained path
filter to the `black` package that composes a set of include and exclude
predicates into a single decision over POSIX-style relative paths, independent of
`black.files`.

## Files to Create/Modify

- `src/black/path_filter.py` (new) — the filter module described below.
- `tests/test_path_filter.py` (new) — the deterministic unit tests for it.

The new module must live in the `black` package and import only from the Python
standard library (you may use `fnmatch` and/or `re`).

## Requirements

### Public surface

`from black.path_filter import PathFilter, FilterError` must succeed. The module
exposes exactly the class `PathFilter` and the exception `FilterError` (a subclass
of `ValueError`). Private helpers may begin with `_`.

### `PathFilter`

- Constructed as `PathFilter(includes, excludes)` where `includes` and `excludes`
  are each a (possibly empty) sequence of glob patterns (`str`). A non-`str`
  pattern, or a pattern that is the empty string, raises `FilterError`.
- `is_included(path)` returns a `bool` for a POSIX-style relative path string,
  according to these rules:
  - A path is **included** iff it matches at least one include pattern (or the
    include list is empty, meaning "include everything by default") **and** it
    matches no exclude pattern.
  - Exclusion takes precedence: if a path matches any exclude pattern it is never
    included, even if it also matches an include pattern.
  - Matching uses shell-style globbing where `*` matches within a path segment and
    `**` matches across segments (so `**/*.py` matches `a/b/c.py`). A pattern
    without a slash matches against the final path segment only (so `*.py` matches
    `a/b/c.py` but `tests/*` does not match `a/b/c.py`).
  - A path that is not a `str`, or is an absolute path (begins with `/`), raises
    `FilterError`.
- `select(paths)` takes an iterable of path strings and returns a `list[str]` of
  exactly those paths for which `is_included` is `True`, preserving input order.

### Expected Functionality

- `PathFilter(["**/*.py"], []).is_included("src/black/x.py")` is `True`.
- `PathFilter(["**/*.py"], ["**/test_*.py"]).is_included("tests/test_x.py")` is `False`.
- `PathFilter([], ["**/*.pyi"]).is_included("a/b.py")` is `True` (empty includes ->
  include by default), while `.is_included("a/b.pyi")` is `False`.
- `PathFilter(["*.py"], []).is_included("a/b/c.py")` is `True` (segment match on
  the basename) but `.is_included("a/b/c.txt")` is `False`.
- `select` filters and preserves order.

### Edge cases

- Empty includes **and** empty excludes: every (valid) path is included.
- Exclude beats include for the same path.
- An empty-string pattern, a non-`str` pattern, an absolute path, and a non-`str`
  path each raise `FilterError`.

## Acceptance Criteria

- The module exposes `PathFilter` and `FilterError` with the behavior above.
- `tests/test_path_filter.py` contains at least 12 independent test cases
  (parametrized cases count individually) covering include-by-default, the
  exclude-precedence rule, `**` cross-segment vs. basename-only matching, `select`
  order preservation, and at least three distinct `FilterError`-raising inputs.
- A naive implementation that uses a plain `fnmatch` without distinguishing `**`
  from `*` and basename-only matching, or that lets include override exclude,
  fails the tests.
- The following command passes from the repository root:

  ```bash
  python -m pytest tests/test_path_filter.py -q
  ```

- Running the project's configured type checker over the new module reports no errors:

  ```bash
  mypy src/black/path_filter.py
  ```
