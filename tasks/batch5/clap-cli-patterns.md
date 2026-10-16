# Task: Add an Aliased `--threads-cap` Flag with Human-Readable Parsing

## Background

ripgrep flags can carry one or more aliases (alternate long spellings that resolve to the same logical flag) in addition to a short name, and some flags parse their value through helper converters in the `convert` module of `crates/core/flags/defs.rs`. State is stored on `LowArgs` in `crates/core/flags/lowargs.rs`. This task adds a new flag `--threads-cap` that bounds a worker count, accepts a short name and an alias, and parses sizes like `1K`.

## Files to Create/Modify

- `crates/core/flags/lowargs.rs` (modify) — add a field to hold the parsed cap.
- `crates/core/flags/defs.rs` (modify) — implement the flag with a short name and an alias, parse its value via the existing human-readable size converter, register it in `FLAGS`, and add a `#[test]`.

## Requirements

### Flag surface

- The flag's long name is `threads-cap`, with a single alias `thread-cap`, and a short name `J`.
- It accepts a value named `NUM` and stores the result on `LowArgs` as an `Option` of an unsigned integer, defaulting to absent.

### Value parsing

- The value is parsed using ripgrep's existing human-readable size parsing (the same helper used by size-style flags), so suffixes such as `K` and `M` are honored: `1K` parses to `1024`.
- A value that the human-readable parser rejects must cause parsing to fail with an error rather than defaulting.

### Aliases and short name

- All three spellings must resolve to the same logical flag and update the same field: `--threads-cap`, `--thread-cap`, and `-J`.
- The alias must not be treated as a separate flag with its own state.

### Override semantics

- When supplied more than once (across any spelling), the last occurrence wins.

### Registration

- The flag must be added to the global `FLAGS` slice so every spelling is recognized.

### Expected Functionality

- No flag -> stored value absent.
- `--threads-cap 4` -> stored value `Some(4)`.
- `--thread-cap=1K` -> stored value `Some(1024)`.
- `-J 8` -> stored value `Some(8)`.
- `--threads-cap 2 -J 5` -> stored value `Some(5)`.
- `--threads-cap nonsense` -> parsing returns an error.

## Acceptance Criteria

- A new `LowArgs` field exists and defaults to absent.
- The long name, alias, and short name all resolve to the same flag and field; human-readable suffixes are honored (`1K` -> `1024`); invalid input errors out; the last occurrence wins.
- The flag (with its alias and short name) is registered in `FLAGS`.
- The added unit test covers all scenarios above and passes via:

  ```
  cargo test --bin rg flags::defs::test_threads_cap
  ```
