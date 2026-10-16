# Task: Add a Stable Exit-Code Mapper to ripgrep's Core

## Background

A well-behaved CLI maps distinct outcome categories to stable, documented process exit codes so that scripts can branch on them. This task adds a small, self-contained module to ripgrep's core that centralizes that mapping, decoupled from where errors are actually produced.

## Files to Create/Modify

- `crates/core/exit.rs` (new) — an enum of outcome categories and a function mapping each to a stable numeric exit code, plus its own `#[cfg(test)] mod tests`.
- `crates/core/main.rs` (modify) — add the `mod exit;` declaration so the new module is part of the binary crate (no behavioral wiring required).

## Requirements

### Outcome categories

- Define an enum with exactly these categories: a successful run with at least one match, a successful run with no matches, a usage/argument error, and an unexpected runtime error.
- Provide a function that converts a category into its exit code as an unsigned 8-bit integer.

### Code assignments

- "At least one match" maps to `0`.
- "No matches" maps to `1`.
- "Usage/argument error" maps to `2`.
- "Unexpected runtime error" maps to `2` as well (ripgrep collapses these onto the same non-search failure code), and the two error categories must remain distinct enum variants even though they share a code.

### Determinism

- The mapping must be a pure, total function: every variant returns a fixed code and the function never panics for any input.
- The "match found" success path must be the only category that yields `0`; "no matches" must never yield `0`.

### Expected Functionality

- match-found category -> `0`.
- no-match category -> `1`.
- usage-error category -> `2`.
- runtime-error category -> `2`.
- match-found is the unique category mapping to `0`.

## Acceptance Criteria

- A new `exit` module exists, is declared in `main.rs`, and compiles.
- The enum has four distinct variants and the mapper returns the exact codes specified, with `0` reserved solely for the match-found category.
- The module's own unit tests cover all scenarios above and pass via:

  ```
  cargo test --bin rg exit::
  ```
