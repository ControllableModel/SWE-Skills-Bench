# Task: Add a `--path-style` Enumerated-Choice Flag to ripgrep

## Background

Several ripgrep flags accept a small, fixed set of string values (an enumeration) rather than free-form text; the parser validates the value against that set and rejects anything else. Flags live in `crates/core/flags/defs.rs` and their parsed state lives on `LowArgs` in `crates/core/flags/lowargs.rs`. This task adds a new enumerated flag `--path-style` that selects how file paths are rendered.

## Files to Create/Modify

- `crates/core/flags/lowargs.rs` (modify) — add a small enum type for the path style and a field on `LowArgs` to hold it.
- `crates/core/flags/defs.rs` (modify) — implement the new flag, declare its allowed choices, register it in `FLAGS`, and add a `#[test]`.

## Requirements

### Choice set

- The flag's long name is `path-style` and it accepts a value named `STYLE`.
- The only accepted values are exactly: `absolute`, `relative`, and `basename`.
- The flag must advertise these three values as its documented choices (so generated help/completions can enumerate them).

### Parsing and validation

- A recognized value maps to a corresponding variant of the new enum type stored on `LowArgs`.
- Any value outside the accepted set (for example `full` or an empty string) must cause parsing to fail with an error message that mentions the offending value; it must not silently fall back to a default.
- Matching is case-sensitive: `Absolute` is not accepted.

### Default and override

- When the flag is never supplied, the stored value is the default variant `relative`.
- When the flag is supplied multiple times, the last valid occurrence wins.

### Registration

- The flag must be added to the global `FLAGS` slice so it is recognized by the CLI parser.

### Expected Functionality

- No flag -> stored style is the `relative` default.
- `--path-style absolute` -> stored style is the `absolute` variant.
- `--path-style=basename` -> stored style is the `basename` variant.
- `--path-style relative --path-style=absolute` -> stored style is `absolute`.
- `--path-style full` -> parsing returns an error mentioning `full`.

## Acceptance Criteria

- A new enum type and `LowArgs` field exist, defaulting to `relative`.
- Exactly the three documented choices are accepted; an unknown value errors out and names the bad value; matching is case-sensitive.
- The flag is registered in `FLAGS` and its choices are exposed for documentation.
- The added unit test covers all scenarios above and passes via:

  ```
  cargo test --bin rg flags::defs::test_path_style
  ```
