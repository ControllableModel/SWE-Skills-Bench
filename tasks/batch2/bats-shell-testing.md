# Task: Add a Version-String Normalizer Helper

## Background

The `bats-core` runtime keeps a collection of internal Bash helper functions in `lib/bats-core/common.bash` (such as `bats_version_lt` and `bats_check_valid_version`) that are sourced into the runner. This task adds a new internal helper that canonicalizes shorthand version strings into a strict three-component form, together with a behavioral test suite for it.

## Files to Create/Modify

- `lib/bats-core/common.bash` (modify) — add the new `bats_version_normalize` helper function.
- `test/common.bats` (modify) — add one `@test` block named `bats_version_normalize` that exercises the helper's full behavior.

## Requirements

### Function contract

Add a function `bats_version_normalize` to `lib/bats-core/common.bash` with this signature:

```
bats_version_normalize <output-variable> <version>
```

- `<version>` is a version string that may have one, two, or three dot-separated numeric components.
- On success the function writes the canonical `<major>.<minor>.<patch>` form into the variable whose name is `<output-variable>` and returns exit status `0`.
- Missing trailing components are filled with `0`: `1` becomes `1.0.0`, and `1.4` becomes `1.4.0`. A string that already has all three components is returned unchanged.

### Validation

- Each present component must be a non-empty run of decimal digits. A component containing any non-digit character, an empty component (for example from a leading, trailing, or doubled dot), or a string with more than three components must be rejected.
- On rejection the function must write an error message to standard error that contains the offending input string, must not assign to the output variable, and must return a non-zero status.
- The function must be called with exactly two arguments; any other argument count must fail.

### Constraints

- The helper must be self-contained: it must not invoke external programs (no `sed`, `awk`, `cut`, `python`, etc.) and must not depend on network, filesystem, or environment state.
- It must write its result via the caller-supplied variable name rather than printing the canonical value to standard output.
- Do not alter the behavior of any existing function in `common.bash`; the existing `test/common.bats` cases must still pass.

### Expected Functionality

- `bats_version_normalize out 1` -> `out` becomes `1.0.0`, success.
- `bats_version_normalize out 1.4` -> `out` becomes `1.4.0`, success.
- `bats_version_normalize out 2.10.3` -> `out` becomes `2.10.3`, success.
- `bats_version_normalize out 01.2.3` -> `out` becomes `01.2.3` (digits preserved verbatim, no numeric reduction), success.
- `bats_version_normalize out 1.2.3.4` -> rejected (too many components), error names `1.2.3.4`.
- `bats_version_normalize out 1..3` -> rejected (empty middle component).
- `bats_version_normalize out 1.x` -> rejected (non-digit component), error names `1.x`.
- `bats_version_normalize out` -> rejected (wrong argument count).

## Acceptance Criteria

- A new function `bats_version_normalize` exists in `lib/bats-core/common.bash`.
- `test/common.bats` contains a new `@test` block named `bats_version_normalize` that asserts: one-component padding, two-component padding, an unchanged three-component value, digit-preservation for a zero-padded component, a too-many-components rejection that also checks the error message names the input, an empty-component rejection, a non-digit rejection, and a wrong-argument-count rejection. At least one success case must verify the value landed in the caller's variable (not stdout).
- The full existing suite for this file still passes together with the new test. The following command, run from the repository root, exits `0`:

```
./bin/bats test/common.bats
```
