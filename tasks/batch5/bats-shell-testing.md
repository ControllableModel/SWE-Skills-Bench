# Task: Add a Key/Value Pair Parsing Helper

## Background

The `bats-core` runtime parses structured option strings in several internal helpers under `lib/bats-core/`. This task adds a new helper to `lib/bats-core/common.bash` that splits a `key=value` token into its two parts, together with a behavioral test suite for it.

## Files to Create/Modify

- `lib/bats-core/common.bash` (modify) — add the new `bats_split_key_value` helper function.
- `test/common.bats` (modify) — add one `@test` block named `bats_split_key_value` that exercises the helper's full behavior.

## Requirements

### Function contract

Add a function `bats_split_key_value` to `lib/bats-core/common.bash` with this signature:

```
bats_split_key_value <key-output-variable> <value-output-variable> <token>
```

- `<token>` is expected to contain a key and a value separated by the **first** `=` character.
- On success the function writes everything before the first `=` into the key output variable, everything after the first `=` into the value output variable, and returns exit status `0`.

### Splitting and validation rules

- Only the **first** `=` is the separator. A token such as `a=b=c` yields key `a` and value `b=c`.
- The key must be non-empty. A token whose key portion is empty (for example a token beginning with `=`) must be rejected.
- The value portion **may** be empty: a token ending in `=` (such as `KEY=`) is valid and yields an empty value.
- A token that contains no `=` at all must be rejected.
- On any rejection the function must write an error message to standard error that contains the offending token, must not assign to either output variable, and must return a non-zero status.
- The function must be called with exactly three arguments; any other count must fail.

### Constraints

- The helper must be self-contained and pure: no external programs (no `cut`, `awk`, `sed`), no network, no filesystem, no environment dependence.
- Keys and values must be captured literally; glob characters and spaces in the value must be preserved verbatim.
- Do not alter the behavior of any existing function in `common.bash`; the existing `test/common.bats` cases must still pass.

### Expected Functionality

- `bats_split_key_value k v "FOO=bar"` -> `k`=`FOO`, `v`=`bar`, success.
- `bats_split_key_value k v "a=b=c"` -> `k`=`a`, `v`=`b=c` (only the first `=` splits).
- `bats_split_key_value k v "KEY="` -> `k`=`KEY`, `v`=`` (empty value allowed).
- `bats_split_key_value k v "=value"` -> rejected (empty key), error names the token.
- `bats_split_key_value k v "novalue"` -> rejected (no `=`).
- `bats_split_key_value k v "p=a b*c"` -> `k`=`p`, `v`=`a b*c` (value preserved verbatim).
- `bats_split_key_value k v "a=b" extra` -> rejected (wrong argument count).

## Acceptance Criteria

- A new function `bats_split_key_value` exists in `lib/bats-core/common.bash`.
- `test/common.bats` contains a new `@test` block named `bats_split_key_value` that asserts: a basic split, a multiple-`=` case splitting only on the first, an empty-value-allowed case, an empty-key rejection whose error message names the token, a no-separator rejection, a verbatim-value case with spaces and a glob character, and a wrong-argument-count rejection. Rejection cases must also confirm the output variables were not assigned.
- The full existing suite for this file still passes together with the new test. The following command, run from the repository root, exits `0`:

```
./bin/bats test/common.bats
```
