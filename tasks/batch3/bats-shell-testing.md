# Task: Add an Array Index-Of Helper

## Background

The `bats-core` runtime provides internal array utilities in `lib/bats-core/common.bash` (such as `bats_linear_reverse_search` and `bats_binary_search`) that take an array by name. This task adds a new helper that reports the position of the first matching element, together with a behavioral test suite for it.

## Files to Create/Modify

- `lib/bats-core/common.bash` (modify) — add the new `bats_array_index_of` helper function.
- `test/common.bats` (modify) — add one `@test` block named `bats_array_index_of` that exercises the helper's full behavior.

## Requirements

### Function contract

Add a function `bats_array_index_of` to `lib/bats-core/common.bash` with this signature:

```
bats_array_index_of <output-variable> <search-value> <array-name>
```

- `<array-name>` is the name of an existing Bash array (passed by name, not by value), matching the convention used by the other search helpers in this file.
- The function scans the array from the lowest index upward.
- On a match it writes the zero-based index of the **first** element equal to `<search-value>` into the variable named by `<output-variable>` and returns exit status `0`.
- When no element equals `<search-value>`, the function returns a non-zero status and does **not** modify the output variable.

### Behavior and edge cases

- Matching is exact string equality, not a substring or glob match: searching for `a` in an array containing only `ab` is a miss.
- If the value appears multiple times, the **lowest** index is reported.
- An empty array always yields a miss.
- The search value may be the empty string, and an element that is the empty string is a valid match.
- The search value may contain shell-special characters (spaces, `*`, `]`, `$`); these must be compared literally with no globbing or word-splitting.

### Constraints

- The helper must be self-contained and pure: no external programs, no network, no filesystem, no dependence on environment state.
- It must not require the array to be sorted.
- It must reference the array by the supplied name rather than expanding it at the call site.
- Do not alter the behavior of any existing function in `common.bash`; the existing `test/common.bats` cases must still pass.

### Expected Functionality

- Array `(a b c)`, search `b` -> index `1`, success.
- Array `(x y x z)`, search `x` -> index `0` (first occurrence), success.
- Array `(a b c)`, search `d` -> miss (non-zero), output variable untouched.
- Empty array, any search -> miss.
- Array `("" b)`, search `""` -> index `0`, success.
- Array `("a b" c)`, search `a b` -> index `0` (literal match including the space).
- Array `(ab cd)`, search `a` -> miss (no substring matching).

## Acceptance Criteria

- A new function `bats_array_index_of` exists in `lib/bats-core/common.bash`.
- `test/common.bats` contains a new `@test` block named `bats_array_index_of` that asserts: a found-in-the-middle case, a first-of-duplicates case, a not-found case that also confirms the output variable was left unchanged, an empty-array miss, an empty-string match, a literal-match case with a space-containing value, and a no-substring-matching case.
- The full existing suite for this file still passes together with the new test. The following command, run from the repository root, exits `0`:

```
./bin/bats test/common.bats
```
