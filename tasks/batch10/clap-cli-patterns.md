# Task: Add a `complete-elvish` Target to ripgrep's `--generate` Flag

## Background

ripgrep's `--generate` flag selects a one-shot "generate something and exit" mode (man page or a shell-completion script) by mapping a `KIND` value onto a `GenerateMode` variant, which in turn sets the overall run mode on `LowArgs`. The flag is defined in `crates/core/flags/defs.rs` and the mode enum lives in `crates/core/flags/lowargs.rs`. This task adds a new generate target for the Elvish shell.

## Files to Create/Modify

- `crates/core/flags/lowargs.rs` (modify) — add a new variant to the `GenerateMode` enum representing Elvish completion generation.
- `crates/core/flags/defs.rs` (modify) — accept a new `complete-elvish` value for `--generate`, advertise it as a documented choice, and extend the existing `--generate` `#[test]`.

## Requirements

### New generate target

- The `--generate` flag must accept a new value `complete-elvish` that selects the new `GenerateMode` variant for Elvish completions.
- The new value must be added to the flag's documented choice list so it is enumerated for help/completion generation; its placement must keep the existing choices and their order intact (the new entry is appended).

### Mode selection semantics

- Supplying `--generate complete-elvish` must set the overall run mode to the "generate Elvish completions" mode.
- The pre-existing targets (`man`, `complete-bash`, `complete-zsh`, `complete-fish`, `complete-powershell`) must continue to map to their current modes unchanged.
- The mode-override behavior is preserved: a later `--generate` value replaces an earlier one, and a subsequent search-selecting flag still overrides a generate mode (the generate mode is not "sticky").

### Validation

- An unrecognized `KIND` (for example `complete-elv` or `complete-elvis`) must still produce an error; only the exact spelling `complete-elvish` selects the new target.

### Expected Functionality

- `--generate complete-elvish` -> run mode is the new generate-Elvish mode.
- `--generate complete-bash` -> run mode is still the generate-bash mode.
- `--generate complete-bash --generate=complete-elvish` -> run mode is the generate-Elvish mode (later wins).
- `--generate complete-elvis` -> parsing returns an error.
- The flag's documented choices include `complete-elvish` while still listing the original five in their original order.

## Acceptance Criteria

- A new `GenerateMode` variant exists and `--generate complete-elvish` selects it.
- The documented choices append `complete-elvish` without disturbing the existing entries; all prior targets still map correctly; an unknown kind errors out; later-wins and search-override semantics are preserved.
- The extended `--generate` unit test covers the scenarios above and passes via:

  ```
  cargo test --bin rg flags::defs::test_generate
  ```
