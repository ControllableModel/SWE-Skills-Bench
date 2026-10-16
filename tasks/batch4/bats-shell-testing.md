# Task: Add an Order-Preserving Array Deduplication Helper

## Background

The `bats-core` runtime keeps internal array utilities in `lib/bats-core/common.bash` (such as `bats_sort`, which orders values into a named result array). This task adds a new helper that removes duplicates while preserving first-seen order, together with a behavioral test suite for it.

## Files to Create/Modify

- `lib/bats-core/common.bash` (modify) — add the new `bats_array_unique` helper function.
- `test/common.bats` (modify) — add one `@test` block named `bats_array_unique` that exercises the helper's full behavior.

## Requirements

### Function contract

Add a function `bats_array_unique` to `lib/bats-core/common.bash` with this signature, mirroring the calling convention of `bats_sort`:

```
bats_array_unique <result-array-name> <values...>
```

- The function populates the array named by `<result-array-name>` with the input values with duplicates removed.
- **Order is preserved**: each distinct value appears at the position of its **first** occurrence in the input. (This must differ from sorting — the output order follows input order, not value order.)
- The result array must be fully reset on each call so that a prior value in that variable cannot leak into the result.

### Behavior and edge cases

- With no values supplied, the result array becomes empty (length `0`).
- Duplicate detection is exact string equality, not glob or numeric: `1` and `1.0` are distinct; `*` matches only another literal `*`.
- Values may contain spaces and shell-special characters; each element must be preserved verbatim as a single array element.
- A single empty-string value must be retained as one element; two empty-string values must collapse to one.
- The function must always return exit status `0`.

### Constraints

- The helper must be self-contained and pure: no external programs (no `sort`, `uniq`, `awk`), no network, no filesystem, no environment dependence.
- It must not reorder the surviving elements.
- Do not alter the behavior of any existing function in `common.bash`; the existing `test/common.bats` cases must still pass.

### Expected Functionality

- `bats_array_unique out a b a c b` -> `out` is `(a b c)`.
- `bats_array_unique out c b a` -> `out` is `(c b a)` (order preserved, NOT sorted).
- `bats_array_unique out` -> `out` is empty (length 0).
- `bats_array_unique out 1 1.0 1` -> `out` is `(1 1.0)` (distinct strings).
- `bats_array_unique out "a b" "a b" x` -> `out` is `("a b" x)` (space-containing element kept whole).
- `bats_array_unique out "" "" y` -> `out` is `("" y)`.

## Acceptance Criteria

- A new function `bats_array_unique` exists in `lib/bats-core/common.bash`.
- `test/common.bats` contains a new `@test` block named `bats_array_unique` that asserts: dedup with preserved first-seen order, a case proving the output is input-ordered rather than sorted, the empty-input case (length 0), a distinct-strings case such as `1` versus `1.0`, a space-containing-element case checking the element count and contents, an empty-string collapse case, and a case demonstrating the result array is reset rather than appended to across calls.
- The full existing suite for this file still passes together with the new test. The following command, run from the repository root, exits `0`:

```
./bin/bats test/common.bats
```
