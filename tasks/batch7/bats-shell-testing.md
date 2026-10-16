# Task: Add a Sorted-Array Occurrence Counter Helper

## Background

The `bats-core` runtime ships internal utilities that operate over sorted arrays in `lib/bats-core/common.bash` (such as `bats_binary_search`, `bats_all_in`, and `bats_any_in`). This task adds a new helper that counts how many times a value occurs in a sorted array, together with a behavioral test suite for it.

## Files to Create/Modify

- `lib/bats-core/common.bash` (modify) — add the new `bats_count_in_sorted` helper function.
- `test/common.bats` (modify) — add one `@test` block named `bats_count_in_sorted` that exercises the helper's full behavior.

## Requirements

### Function contract

Add a function `bats_count_in_sorted` to `lib/bats-core/common.bash` with this signature:

```
bats_count_in_sorted <output-variable> <search-value> <sorted-array-name>
```

- `<sorted-array-name>` names an existing array whose elements are already in ascending string order (the same precondition the other sorted-array helpers in this file rely on).
- The function writes the number of elements equal to `<search-value>` into the variable named by `<output-variable>`.
- The exit status reflects presence: `0` when the count is one or more, non-zero when the count is `0` (value absent). The output variable is still set to `0` on the absent case.

### Behavior and edge cases

- Equality is exact string comparison, consistent with the existing sorted-array helpers.
- The count must include all consecutive equal elements (for example `(a b b b c)` searched for `b` yields `3`).
- A value smaller than every element, larger than every element, or falling in a gap yields count `0` and a non-zero status.
- An empty array yields count `0` and a non-zero status.
- The search value may be the empty string.

### Constraints

- The helper must be self-contained and pure: no external programs (no `grep -c`, `wc`, `awk`), no network, no filesystem, no environment dependence.
- It must reference the array by the supplied name rather than expanding it at the call site.
- It must not require the search value to exist; the absent case is a normal, non-erroring outcome distinguished by exit status and a count of `0`.
- Do not alter the behavior of any existing function in `common.bash`; the existing `test/common.bats` cases must still pass.

### Expected Functionality

- Sorted array `(a b b b c)`, search `b` -> count `3`, success.
- Sorted array `(a b c)`, search `a` -> count `1`, success (boundary element).
- Sorted array `(a b c)`, search `c` -> count `1`, success (last element).
- Sorted array `(a c e)`, search `b` -> count `0`, non-zero status (gap).
- Sorted array `(b c d)`, search `a` -> count `0`, non-zero (below all).
- Empty array, search anything -> count `0`, non-zero.

## Acceptance Criteria

- A new function `bats_count_in_sorted` exists in `lib/bats-core/common.bash`.
- `test/common.bats` contains a new `@test` block named `bats_count_in_sorted` that asserts: a run-of-duplicates count, a single-occurrence count at the first element, a single-occurrence count at the last element, an absent-in-a-gap case checking both count `0` and the non-zero status, a below-all-elements absent case, and an empty-array case. Absent cases must verify the output variable equals `0`.
- The full existing suite for this file still passes together with the new test. The following command, run from the repository root, exits `0`:

```
./bin/bats test/common.bats
```
