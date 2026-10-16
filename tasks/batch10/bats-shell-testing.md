# Task: Add a Duration-To-Seconds Parsing Helper

## Background

The `bats-core` runtime deals with timeouts and durations in its test runner and ships small parsing/validation helpers in `lib/bats-core/common.bash`. This task adds a new helper that converts a compact human-readable duration string into a total number of seconds, together with a behavioral test suite for it.

## Files to Create/Modify

- `lib/bats-core/common.bash` (modify) — add the new `bats_duration_to_seconds` helper function.
- `test/common.bats` (modify) — add one `@test` block named `bats_duration_to_seconds` that exercises the helper's full behavior.

## Requirements

### Function contract

Add a function `bats_duration_to_seconds` to `lib/bats-core/common.bash` with this signature:

```
bats_duration_to_seconds <output-variable> <duration>
```

- `<duration>` is a compact string composed of one or more `<number><unit>` segments concatenated, where each unit is one of `h` (hours = 3600 s), `m` (minutes = 60 s), or `s` (seconds = 1 s). Example: `1h30m` = `5400`, `2m15s` = `135`, `45s` = `45`.
- On success the function writes the total number of seconds (a decimal integer) into the variable named by `<output-variable>` and returns exit status `0`.

### Parsing and validation rules

- Each segment is a run of decimal digits immediately followed by exactly one unit letter from `h`, `m`, `s`.
- A bare integer with no unit (for example `90`) must be rejected; every numeric run must carry a unit.
- An empty input string must be rejected.
- An unknown unit (for example `5d`), a unit with no preceding number (for example `m30s`), or any trailing/garbage characters must be rejected.
- The same unit may appear more than once and the segments are summed in order (for example `1m1m` = `120`); units need not be ordered or unique.
- On any rejection the function must write an error message to standard error that contains the offending input, must not assign to the output variable, and must return a non-zero status.
- The function must be called with exactly two arguments; any other count must fail.

### Constraints

- The helper must be self-contained and pure: no external programs (no `date`, `awk`, `sed`, `python`), no network, no filesystem, no environment dependence. Bash string processing and arithmetic are sufficient.
- It must write the result through the caller-supplied variable name rather than printing to standard output.
- Do not alter the behavior of any existing function in `common.bash`; the existing `test/common.bats` cases must still pass.

### Expected Functionality

- `bats_duration_to_seconds out 1h30m` -> `out` is `5400`, success.
- `bats_duration_to_seconds out 2m15s` -> `out` is `135`, success.
- `bats_duration_to_seconds out 45s` -> `out` is `45`, success.
- `bats_duration_to_seconds out 1h1m1s` -> `out` is `3661`, success.
- `bats_duration_to_seconds out 1m1m` -> `out` is `120` (repeated unit summed).
- `bats_duration_to_seconds out 90` -> rejected (no unit), error names `90`.
- `bats_duration_to_seconds out 5d` -> rejected (unknown unit).
- `bats_duration_to_seconds out ""` -> rejected (empty input).
- `bats_duration_to_seconds out 1h` -> rejected (wrong argument count) when called with only one argument after the output var name is omitted.

## Acceptance Criteria

- A new function `bats_duration_to_seconds` exists in `lib/bats-core/common.bash`.
- `test/common.bats` contains a new `@test` block named `bats_duration_to_seconds` that asserts: a multi-segment conversion (`1h30m`), a minutes-plus-seconds conversion, a single-segment seconds case, a full `h`/`m`/`s` combination, a repeated-unit summation, a missing-unit rejection whose error message names the input, an unknown-unit rejection, an empty-input rejection, and a wrong-argument-count rejection. Rejection cases must confirm the output variable was not assigned.
- The full existing suite for this file still passes together with the new test. The following command, run from the repository root, exits `0`:

```
./bin/bats test/common.bats
```
