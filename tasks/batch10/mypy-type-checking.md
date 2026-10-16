# Task: Add a Changed-Line-Range Merger

## Background

Black's `--line-ranges` feature lets users limit formatting to specific 1-based,
inclusive line spans, which then must be normalized into a minimal, sorted,
non-overlapping set. This task adds a self-contained line-range merger to the
`black` package that validates and merges such spans, independent of
`black.ranges`.

## Files to Create/Modify

- `src/black/range_merge.py` (new) — the merger module described below.
- `tests/test_range_merge.py` (new) — the deterministic unit tests for it.

The new module must live in the `black` package and import only from the Python
standard library.

## Requirements

### Public surface

`from black.range_merge import LineRange, merge_ranges, RangeMergeError` must
succeed. The module exposes exactly a `LineRange` type, a function `merge_ranges`,
and an exception `RangeMergeError` (a subclass of `ValueError`). Private helpers
may begin with `_`.

### `LineRange`

`LineRange` represents one inclusive 1-based span and carries a `start` (`int`)
and an `end` (`int`). It may be a `dataclass` or `NamedTuple`. It must validate on
construction (or via a `LineRange.of(start, end)` classmethod) that `start >= 1`
and `end >= start`; otherwise raise `RangeMergeError`.

### `merge_ranges(ranges)`

Takes an iterable of `LineRange` values and returns a `list[LineRange]` that is:

- **Sorted** ascending by `start`.
- **Merged**: two ranges that overlap **or are adjacent** (i.e. the next range's
  `start <= current.end + 1`) are combined into a single range spanning both.
- **Minimal**: the returned list contains no overlapping or adjacent ranges and is
  the smallest such set covering exactly the same lines as the input.

The input may be empty (returns `[]`). Any non-`LineRange` element raises
`RangeMergeError`.

### Expected Functionality

| Input spans | Result spans |
|-------------|--------------|
| `[(1,3), (2,5)]` | `[(1,5)]` (overlap) |
| `[(1,3), (4,6)]` | `[(1,6)]` (adjacent: 4 == 3+1) |
| `[(1,3), (5,6)]` | `[(1,3), (5,6)]` (gap at line 4) |
| `[(10,12), (1,2)]` | `[(1,2), (10,12)]` (sorted) |
| `[(1,10), (3,4)]` | `[(1,10)]` (contained) |
| `[]` | `[]` |

### Edge cases

- A single range is returned unchanged (but as a new list).
- Three ranges that chain (`[(1,2), (3,4), (5,6)]`) all merge into `[(1,6)]`.
- Constructing `LineRange` with `start=0`, or with `end < start` (e.g.
  `start=5, end=3`), raises `RangeMergeError`.
- Passing a non-`LineRange` element to `merge_ranges` raises `RangeMergeError`.

## Acceptance Criteria

- The module exposes `LineRange`, `merge_ranges`, and `RangeMergeError` with the
  behavior above.
- `tests/test_range_merge.py` contains at least 12 independent test cases
  (parametrized cases count individually) covering overlap, adjacency-merge, a real
  gap that is preserved, sorting of out-of-order input, full containment, the
  empty input, and at least three distinct `RangeMergeError`-raising inputs.
- A naive implementation that only sorts without merging, or that merges only true
  overlaps but not adjacency (off-by-one), fails the tests.
- The following command passes from the repository root:

  ```bash
  python -m pytest tests/test_range_merge.py -q
  ```

- Running the project's configured type checker over the new module reports no errors:

  ```bash
  mypy src/black/range_merge.py
  ```
