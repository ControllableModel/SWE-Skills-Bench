# Task: Add a `--max-matches-per-line` Numeric Flag to ripgrep

## Background

ripgrep defines every command-line flag as a unit struct implementing the `Flag` trait in `crates/core/flags/defs.rs`, and stores parsed values on the `LowArgs` struct in `crates/core/flags/lowargs.rs`. This task adds a brand-new value-taking flag, `--max-matches-per-line`, that caps how many matches are reported on any single line.

## Files to Create/Modify

- `crates/core/flags/lowargs.rs` (modify) — add a field to hold the parsed value of the new flag.
- `crates/core/flags/defs.rs` (modify) — implement the new flag struct, register it in the `FLAGS` slice, and add a `#[test]` covering it.

## Requirements

### Flag surface

- The flag's long name is `max-matches-per-line` and it accepts a single value named `NUM`.
- It has no short name and no negated form.
- Its parsed value is stored on `LowArgs` as an `Option` of an unsigned 64-bit integer, defaulting to "absent" when the flag is never supplied.

### Value parsing and validation

- The supplied value must be parsed as a non-negative base-10 integer. A value that is not a valid number (for example `abc` or `1.5` or an empty string) must cause parsing to fail with an error rather than silently defaulting.
- A literal `0` is a legal value and must be stored as such (it is not treated as "absent").

### Override semantics

- When the flag is supplied more than once, the last occurrence wins (consistent with how other single-value ripgrep flags behave).

### Registration

- The flag must be discoverable by the normal CLI parser, i.e. it must be added to the global `FLAGS` slice so that `--max-matches-per-line` is recognized rather than rejected as an unknown flag.

### Expected Functionality

- No flag given -> stored value is the "absent" variant.
- `--max-matches-per-line 3` -> stored value is `Some(3)`.
- `--max-matches-per-line=0` -> stored value is `Some(0)`.
- `--max-matches-per-line 2 --max-matches-per-line=9` -> stored value is `Some(9)`.
- `--max-matches-per-line foo` -> parsing returns an error.

## Acceptance Criteria

- A new field exists on `LowArgs` for this flag and defaults to the absent variant.
- The flag is registered in `FLAGS` and parsed via the standard parser path.
- Numeric validation rejects non-numeric input with an error; `0` is accepted as a real value; the last value wins on repetition.
- The added unit test asserts every scenario above and passes via:

  ```
  cargo test --bin rg flags::defs::test_max_matches_per_line
  ```
