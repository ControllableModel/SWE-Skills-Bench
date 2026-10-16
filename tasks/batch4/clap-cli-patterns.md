# Task: Add a Negatable `--summary` Switch Flag to ripgrep

## Background

Many ripgrep flags are boolean switches that come in pairs: a positive form that turns a behavior on and a negated long form (for example `--foo` / `--no-foo`) that turns it back off, with later occurrences overriding earlier ones. Flags are defined in `crates/core/flags/defs.rs` and store their state on `LowArgs` in `crates/core/flags/lowargs.rs`. This task adds a new switch `--summary` with a matching `--no-summary` negation.

## Files to Create/Modify

- `crates/core/flags/lowargs.rs` (modify) — add a boolean field for the new switch.
- `crates/core/flags/defs.rs` (modify) — implement the switch flag with its negated long name, register it in `FLAGS`, and add a `#[test]`.

## Requirements

### Switch surface

- The flag's positive long name is `summary` and it is a pure on/off switch that takes no value.
- It exposes a negated long name `no-summary`.
- It has no short name.
- Its state is stored as a plain boolean on `LowArgs`, defaulting to `false` when neither form is supplied.

### Negation and override semantics

- Supplying `--summary` sets the state to `true`; supplying `--no-summary` sets it to `false`.
- The negated form must be treated as a switch even though it is the negation (it never consumes a following value).
- The last occurrence among the two forms wins regardless of order: `--summary --no-summary` ends as `false`, and `--no-summary --summary` ends as `true`.

### Registration

- The flag must be added to the global `FLAGS` slice so both `--summary` and `--no-summary` are recognized by the CLI parser.

### Expected Functionality

- No flag -> stored value `false`.
- `--summary` -> stored value `true`.
- `--no-summary` -> stored value `false`.
- `--summary --no-summary` -> stored value `false`.
- `--no-summary --summary` -> stored value `true`.

## Acceptance Criteria

- A new boolean field exists on `LowArgs`, defaulting to `false`.
- The flag is a switch with a negated long form, both registered in `FLAGS`.
- Positive and negated forms set the boolean appropriately, the negated form consumes no value, and the last occurrence wins.
- The added unit test covers all scenarios above and passes via:

  ```
  cargo test --bin rg flags::defs::test_summary
  ```
