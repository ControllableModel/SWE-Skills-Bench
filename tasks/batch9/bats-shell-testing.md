# Task: Add a Pure-String Subpath Containment Helper

## Background

The `bats-core` runtime manipulates and compares filesystem paths as strings in helpers such as `bats_approx_realpath` in `lib/bats-core/common.bash`. This task adds a new helper that decides, purely by string analysis, whether one path lies inside another, together with a behavioral test suite for it.

## Files to Create/Modify

- `lib/bats-core/common.bash` (modify) — add the new `bats_path_is_inside` helper function.
- `test/common.bats` (modify) — add one `@test` block named `bats_path_is_inside` that exercises the helper's full behavior.

## Requirements

### Function contract

Add a function `bats_path_is_inside` to `lib/bats-core/common.bash` with this signature:

```
bats_path_is_inside <candidate-path> <base-path>
```

- The function returns exit status `0` when `<candidate-path>` is the same as `<base-path>` or is located beneath it in the path hierarchy, and a non-zero status otherwise.
- The decision is made purely from the string values; the function must not touch the filesystem (paths need not exist).

### Path-segment rules

- Containment is by whole path **segments**, not by raw string prefix. `/foo/bar` is inside `/foo`, but `/foobar` is **not** inside `/foo` (the prefix must end on a `/` boundary).
- A path is considered inside itself: `/foo` is inside `/foo` (success).
- A trailing slash on either argument must not change the answer: `/foo/` and `/foo` behave identically as the base, and `/foo/bar/` is inside `/foo`.
- The root `/` contains every absolute path.
- Comparison is literal segment text; this helper does not resolve `.` or `..` components, and a candidate that is a strict parent of the base (for example `/foo` against base `/foo/bar`) is **not** inside the base.

### Constraints

- The helper must be self-contained and pure: no external programs (no `realpath`, `readlink`, `dirname`, `python`), no actual filesystem access, no network, no environment dependence.
- It must signal its yes/no answer through the exit status rather than printing it.
- Do not alter the behavior of any existing function in `common.bash`; the existing `test/common.bats` cases must still pass.

### Expected Functionality

- `bats_path_is_inside /foo/bar /foo` -> inside (success).
- `bats_path_is_inside /foo /foo` -> inside (a path contains itself).
- `bats_path_is_inside /foobar /foo` -> not inside (segment boundary, not raw prefix).
- `bats_path_is_inside /foo/bar/ /foo` -> inside (trailing slash ignored).
- `bats_path_is_inside /foo/bar /foo/` -> inside (trailing slash on base ignored).
- `bats_path_is_inside /a/b/c / ` -> inside (root contains everything) — `/a/b/c` against base `/`.
- `bats_path_is_inside /foo /foo/bar` -> not inside (candidate is a parent of base).

## Acceptance Criteria

- A new function `bats_path_is_inside` exists in `lib/bats-core/common.bash`.
- `test/common.bats` contains a new `@test` block named `bats_path_is_inside` that asserts: a straightforward nested-inside case, the same-path-is-inside case, the segment-boundary case distinguishing `/foobar` from being inside `/foo`, a trailing-slash-on-candidate case, a trailing-slash-on-base case, a root-base case, and a candidate-is-parent (not inside) case.
- The full existing suite for this file still passes together with the new test. The following command, run from the repository root, exits `0`:

```
./bin/bats test/common.bats
```
