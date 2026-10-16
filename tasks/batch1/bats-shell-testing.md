# Task: Add a Version-Range Membership Helper

## Background

The `bats-core` runtime ships a small set of internal Bash helper functions in `lib/bats-core/common.bash` (for example `bats_version_lt` and `bats_require_minimum_version`), which are automatically sourced into every test file the runner executes. This task adds a new internal helper that decides whether a `<major>.<minor>.<patch>` version falls inside an inclusive lower / exclusive upper range, together with a thorough behavioral test suite for it.

## Files to Create/Modify

- `lib/bats-core/common.bash` (modify) — add the new `bats_version_in_range` helper function.
- `test/common.bats` (modify) — add one `@test` block named `bats_version_in_range` that exercises the new helper's full behavior.

## Requirements

### Function contract

Add a function `bats_version_in_range` to `lib/bats-core/common.bash` with this signature and meaning:

```
bats_version_in_range <version> <min-inclusive> <max-exclusive>
```

- All three arguments are version strings.
- The function returns success (exit status `0`) when `<version>` is greater than or equal to `<min-inclusive>` **and** strictly less than `<max-exclusive>`.
- The function returns a non-success status when `<version>` is outside that half-open interval `[min-inclusive, max-exclusive)`.

### Version format and validation

- A valid version string consists of exactly three dot-separated numeric components: `<major>.<minor>.<patch>` (for example `1.4.0`).
- If **any** of the three arguments is not a valid `<major>.<minor>.<patch>` version, the function must reject the call: it must write an error message to standard error that contains the offending string and explains that the expected format is `<major>.<minor>.<patch>`, and it must terminate the call unsuccessfully rather than producing a normal in-range / out-of-range answer.
- Argument count matters: the function must be invoked with exactly three arguments. A call made with fewer than three arguments must not silently succeed; it must fail.

### Comparison semantics

- Comparison is component-wise and numeric, most-significant component first: `2.0.0` is greater than `1.9.9`, and `1.2.10` is greater than `1.2.9`.
- The lower bound is inclusive: a version exactly equal to `<min-inclusive>` is in range.
- The upper bound is exclusive: a version exactly equal to `<max-exclusive>` is **not** in range.
- An empty interval (where `<min-inclusive>` is greater than or equal to `<max-exclusive>`) contains no version; every membership query against such an interval is out of range.

### Distinguishing the failure modes

The exit status must let a caller tell *why* a call did not succeed:

- A well-formed query whose version is simply outside the interval must use a different non-zero exit status than the status used to report an invalid/malformed argument or a wrong argument count. In other words, "validly out of range" and "bad input" must be distinguishable by exit code alone, not only by the presence of an error message.

### Constraints

- The helper must be a self-contained shell function added to `lib/bats-core/common.bash`; it must not invoke external programs to perform the comparison (no `sort -V`, `awk`, `python`, etc.) and must not depend on network, filesystem, or environment state.
- Do not weaken or alter the behavior of the existing functions already in `common.bash`; the existing `test/common.bats` cases must continue to pass.

### Expected Functionality

- `bats_version_in_range 1.5.0 1.0.0 2.0.0` -> in range (success).
- `bats_version_in_range 1.0.0 1.0.0 2.0.0` -> in range (lower bound inclusive).
- `bats_version_in_range 2.0.0 1.0.0 2.0.0` -> out of range (upper bound exclusive).
- `bats_version_in_range 0.9.0 1.0.0 2.0.0` -> out of range (below lower bound).
- `bats_version_in_range 1.2.10 1.2.9 1.3.0` -> in range (numeric, not lexical, component comparison).
- `bats_version_in_range 1.5.0 2.0.0 1.0.0` -> out of range (empty interval).
- `bats_version_in_range 1.0 1.0.0 2.0.0` -> rejected as invalid input, with an error message naming `1.0` and the expected format.
- `bats_version_in_range 1.0.0 1.0.0` -> rejected (too few arguments).

## Acceptance Criteria

- A new function `bats_version_in_range` exists in `lib/bats-core/common.bash`.
- `test/common.bats` contains a new `@test` block named `bats_version_in_range` that, at minimum, asserts: in-range success, lower-bound-inclusive success, upper-bound-exclusive rejection, below-range rejection, a numeric-component case such as `1.2.10` versus `1.2.9`, the empty-interval case, an invalid-version case checking both the non-success status and the error-message content, and a wrong-argument-count case — and that distinguishes the "out of range" exit status from the "bad input" exit status.
- The full existing suite for this file still passes together with the new test. The following command, run from the repository root, exits `0` and reports every test in the file (including the new one) as passing:

```
./bin/bats test/common.bats
```
