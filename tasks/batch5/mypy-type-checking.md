# Task: Add a Target-Version Range Resolver

## Background

Black lets users select one or more target Python versions (e.g. PY38..PY313) and
must reason about contiguous version ranges — the minimum, the maximum, and
whether a given version is covered. This task adds a self-contained range
resolver to the `black` package that operates over an ordered set of named
Python versions, independent of `black.mode`.

## Files to Create/Modify

- `src/black/version_range.py` (new) — the range-resolver module described below.
- `tests/test_version_range.py` (new) — the deterministic unit tests for it.

The new module must live in the `black` package and import only from the Python
standard library.

## Requirements

### Public surface

`from black.version_range import PyVersion, VersionRange, RangeError` must succeed.
The module exposes exactly an `enum.Enum` named `PyVersion`, a class
`VersionRange`, and an exception `RangeError` (a subclass of `ValueError`).

### `PyVersion`

An ordered `Enum` whose members are `PY36`, `PY37`, `PY38`, `PY39`, `PY310`,
`PY311`, `PY312`, `PY313`, with integer values `6, 7, 8, 9, 10, 11, 12, 13`
respectively (so ordering by value matches release order). It must expose a
`parse(name)` classmethod that maps a string like `"py311"` or `"PY311"`
(case-insensitive) to the corresponding member and raises `RangeError` for any
unknown name.

### `VersionRange`

- Constructed as `VersionRange(versions)` from any non-empty iterable of
  `PyVersion` members. An empty iterable raises `RangeError`. A non-`PyVersion`
  element raises `RangeError`.
- `minimum` and `maximum` properties return the lowest and highest `PyVersion`.
- `covers(version)` returns a `bool`: `True` iff `minimum <= version <= maximum`
  by version value, regardless of whether `version` was in the original iterable
  (the range is contiguous/inclusive).
- `is_contiguous` returns a `bool`: `True` iff every version between `minimum`
  and `maximum` (inclusive, by value) was present in the original set.
- `as_sorted()` returns a `list[PyVersion]` of the distinct supplied versions in
  ascending value order (duplicates collapsed).

### Expected Functionality

- `VersionRange([PY38, PY310, PY39]).minimum is PY38` and `.maximum is PY310`.
- That range `.covers(PY39)` is `True`, `.covers(PY311)` is `False`, and
  `.is_contiguous` is `True`.
- `VersionRange([PY38, PY311]).is_contiguous` is `False` but `.covers(PY39)` is `True`.
- `PyVersion.parse("py312") is PY312`.

### Edge cases

- A single-element range: `minimum is maximum`, `is_contiguous` is `True`.
- Duplicates in the input do not affect `minimum`, `maximum`, or `is_contiguous`,
  and `as_sorted()` returns each version once.
- `PyVersion.parse("py999")` and `VersionRange([])` raise `RangeError`.

## Acceptance Criteria

- The module exposes `PyVersion`, `VersionRange`, and `RangeError` with the
  behavior above.
- `tests/test_version_range.py` contains at least 11 independent test cases
  covering min/max, the contiguous vs. gapped distinction, `covers` outside the
  supplied set, duplicate collapsing, `parse` round-trips, and at least three
  distinct `RangeError`-raising inputs.
- A naive implementation that treats the supplied set as the coverage set (rather
  than an inclusive contiguous range) or that ignores the contiguity gap fails the tests.
- The following command passes from the repository root:

  ```bash
  python -m pytest tests/test_version_range.py -q
  ```

- Running the project's configured type checker over the new module reports no errors:

  ```bash
  mypy src/black/version_range.py
  ```
