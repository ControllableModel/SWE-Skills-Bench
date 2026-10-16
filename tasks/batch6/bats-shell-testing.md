# Task: Add an Array Join-By-Delimiter Helper

## Background

The `bats-core` runtime assembles formatted strings from arrays in several internal helpers (for example `bats_append_arrays_as_args` in `lib/bats-core/common.bash`). This task adds a new helper that joins array elements with an arbitrary delimiter into a single string, together with a behavioral test suite for it.

## Files to Create/Modify

- `lib/bats-core/common.bash` (modify) — add the new `bats_join_by` helper function.
- `test/common.bats` (modify) — add one `@test` block named `bats_join_by` that exercises the helper's full behavior.

## Requirements

### Function contract

Add a function `bats_join_by` to `lib/bats-core/common.bash` with this signature:

```
bats_join_by <output-variable> <delimiter> <elements...>
```

- The function concatenates the elements into one string, placing exactly one copy of `<delimiter>` **between** consecutive elements (never before the first or after the last), and writes the result into the variable named by `<output-variable>`.
- It returns exit status `0`.

### Behavior and edge cases

- With a single element, the result is that element with no delimiter added.
- With no elements, the result is the empty string.
- The delimiter is placed only between elements: there are exactly `n - 1` delimiters for `n` elements.
- The delimiter may be multiple characters (for example `, ` or `->`), the empty string (elements are concatenated with nothing between them), or a single character such as `:`.
- Empty-string elements are honored: joining `("" a "")` with `:` yields `:a:` (an empty leading and trailing field around the delimiters).
- Elements may contain the delimiter or other special characters; they must be copied verbatim with no further splitting.

### Constraints

- The helper must be self-contained and pure: no external programs (no `paste`, `sed`, `tr`, `IFS`-based subshell `echo` tricks that fork), no network, no filesystem, no environment dependence.
- It must write the result through the caller-supplied variable name rather than printing to standard output.
- Do not alter the behavior of any existing function in `common.bash`; the existing `test/common.bats` cases must still pass.

### Expected Functionality

- `bats_join_by out , a b c` -> `out` is `a,b,c`.
- `bats_join_by out " -> " x y` -> `out` is `x -> y` (multi-character delimiter).
- `bats_join_by out , solo` -> `out` is `solo` (single element, no delimiter).
- `bats_join_by out ,` -> `out` is `` (no elements).
- `bats_join_by out "" a b c` -> `out` is `abc` (empty delimiter).
- `bats_join_by out : "" a ""` -> `out` is `:a:` (empty elements honored).
- `bats_join_by out , "a,b" c` -> `out` is `a,b,c` (an element containing the delimiter is preserved).

## Acceptance Criteria

- A new function `bats_join_by` exists in `lib/bats-core/common.bash`.
- `test/common.bats` contains a new `@test` block named `bats_join_by` that asserts: a basic single-character-delimiter join, a multi-character-delimiter join, the single-element case, the no-elements (empty result) case, an empty-delimiter case, an empty-elements case yielding leading/trailing empty fields, and a case where an element itself contains the delimiter character. At least one case must confirm the result is delivered via the caller's variable.
- The full existing suite for this file still passes together with the new test. The following command, run from the repository root, exits `0`:

```
./bin/bats test/common.bats
```
