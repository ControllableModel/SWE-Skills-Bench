# Task: Emit Choice Lists into ripgrep's Bash Completion Output

## Background

ripgrep generates its own shell-completion scripts from the live flag metadata. The bash generator lives in `crates/core/flags/complete/bash.rs` and builds a script from templates, including a per-flag `case` arm that decides what completions to offer after a given flag. This task makes the bash generator offer the fixed value list for flags that declare a small enumerated choice set.

## Files to Create/Modify

- `crates/core/flags/complete/bash.rs` (modify) — when generating the `case` arm for a flag, emit the flag's declared choices as completion words; add a `#[cfg(test)] mod tests` (or extend it) verifying the generated text.

## Requirements

### Choice-aware completion arms

- For any flag that declares a non-empty list of documented choices (the `doc_choices` metadata), the generated bash script must contain a `case` arm for that flag's long option whose completion words are exactly that flag's choices, space-separated, in declaration order.
- For example, the `--engine` flag declares the choices `default`, `pcre2`, `auto`; the generated script must contain an arm offering `default pcre2 auto` (in that order) after `--engine`.

### Non-regression for other flags

- Flags that take a filename-style value must continue to produce their existing file-completion arm and must not be turned into choice arms.
- Switch flags (which take no value) must not gain a value-completion arm.
- The overall script must remain syntactically a single `_rg()` bash function with the existing top-level structure (the `complete -F _rg ... rg` registration line must still be present).

### Determinism

- Generation must depend only on the static flag metadata, producing identical output on every run (no environment or filesystem access).

### Expected Functionality

- Generated script contains, for `--engine`, a completion arm offering exactly `default pcre2 auto`.
- Generated script contains, for `--sort`, a completion arm offering exactly `none path modified accessed created`.
- Generated script still contains the `complete -F _rg` registration line.
- A flag with no choices and no filename type does not get a choices arm offering an empty word list.

## Acceptance Criteria

- The bash generator emits, for every choice-bearing flag, a `case` arm with that flag's choices space-separated in declaration order.
- Filename and switch flags are unaffected, and the script keeps its `_rg()` structure and `complete -F _rg` line.
- The added/updated unit test asserts the `--engine` and `--sort` choice arms and the registration line, and passes via:

  ```
  cargo test --bin rg flags::complete::bash::
  ```
