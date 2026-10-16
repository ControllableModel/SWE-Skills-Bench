# Task: Add an Integer Clamp Helper

## Background

The `bats-core` runtime contains small arithmetic and validation helpers in `lib/bats-core/common.bash`. This task adds a new helper that constrains an integer into an inclusive range, validating its inputs, together with a behavioral test suite for it.

## Files to Create/Modify

- `lib/bats-core/common.bash` (modify) — add the new `bats_clamp_int` helper function.
- `test/common.bats` (modify) — add one `@test` block named `bats_clamp_int` that exercises the helper's full behavior.

## Requirements

### Function contract

Add a function `bats_clamp_int` to `lib/bats-core/common.bash` with this signature:

```
bats_clamp_int <output-variable> <value> <min> <max>
```

- On success the function writes into the variable named by `<output-variable>` the value clamped to the inclusive range `[min, max]`: `min` if `<value>` is below `min`, `max` if `<value>` is above `max`, otherwise `<value>` unchanged. It returns exit status `0`.

### Validation rules

- All of `<value>`, `<min>`, and `<max>` must be integers, optionally with a leading `-` sign (for example `-5`, `0`, `42`). A non-integer argument (containing letters, a decimal point, internal spaces, or being empty) must be rejected.
- If `<min>` is greater than `<max>` the range is invalid and the call must be rejected.
- On any rejection the function must write an error message to standard error identifying the problem, must not assign to the output variable, and must return a non-zero status.
- The function must be called with exactly four arguments; any other count must fail.

### Behavior and edge cases

- A value below the minimum clamps up to `min`; a value above the maximum clamps down to `max`; a value inside the range is returned unchanged.
- A value exactly equal to `min` or to `max` is in range (bounds inclusive) and returned unchanged.
- Negative bounds and negative values must compare numerically (`-10` is less than `-2`), not lexically.

### Constraints

- The helper must be self-contained and pure: no external programs (no `expr`, `bc`, `awk`), no network, no filesystem, no environment dependence. Bash arithmetic is sufficient.
- It must write the result through the caller-supplied variable name rather than printing to standard output.
- Do not alter the behavior of any existing function in `common.bash`; the existing `test/common.bats` cases must still pass.

### Expected Functionality

- `bats_clamp_int out 5 0 10` -> `out` is `5` (in range).
- `bats_clamp_int out -3 0 10` -> `out` is `0` (clamped up to min).
- `bats_clamp_int out 99 0 10` -> `out` is `10` (clamped down to max).
- `bats_clamp_int out 0 0 10` -> `out` is `0` (lower bound inclusive).
- `bats_clamp_int out -5 -10 -2` -> `out` is `-5` (negative numeric comparison).
- `bats_clamp_int out 5 10 0` -> rejected (min greater than max).
- `bats_clamp_int out 1.5 0 10` -> rejected (non-integer value).
- `bats_clamp_int out 5 0` -> rejected (wrong argument count).

## Acceptance Criteria

- A new function `bats_clamp_int` exists in `lib/bats-core/common.bash`.
- `test/common.bats` contains a new `@test` block named `bats_clamp_int` that asserts: an in-range pass-through, a clamp-up-to-min, a clamp-down-to-max, a bound-inclusive case, a negative-range numeric case proving non-lexical comparison, a min-greater-than-max rejection, a non-integer rejection, and a wrong-argument-count rejection. Rejection cases must confirm the output variable was not assigned.
- The full existing suite for this file still passes together with the new test. The following command, run from the repository root, exits `0`:

```
./bin/bats test/common.bats
```
