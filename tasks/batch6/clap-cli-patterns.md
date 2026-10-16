# Task: Add a Layered Config-Precedence Resolver to ripgrep's Flag Module

## Background

ripgrep already reads extra arguments from a config rc file (see `crates/core/flags/config.rs`) and prepends them before the real command-line arguments so that the command line can override the file. This task introduces a small, self-contained helper that makes the precedence between three sources explicit and reusable for a single setting, without touching the existing parser flow.

## Files to Create/Modify

- `crates/core/flags/precedence.rs` (new) — a small module that resolves one setting from three layered sources with a fixed precedence, plus its own `#[cfg(test)] mod tests`.
- `crates/core/flags/mod.rs` (modify) — declare the new `precedence` module so it compiles as part of the crate.

## Requirements

### Resolver contract

- Provide a function that takes three optional inputs for a single string-valued setting — one from the command line, one from an environment-style source, and one from a config-file source — plus a default value, and returns the single effective value.
- The precedence, from highest to lowest, is: command-line input, then environment-style input, then config-file input, then the default.
- "Absent" must be represented by the `None` variant; only a present (`Some`) value at a given layer is allowed to win.

### Edge cases

- A present value at a higher-precedence layer must override any present value at every lower layer.
- An absent higher layer must fall through to the next present layer.
- If all three layered inputs are absent, the provided default is returned.
- A present value that is the empty string is still a present value (it wins over lower layers); it must not be treated as absent.

### Isolation

- The resolver must be a pure function of its inputs: it must not read process environment variables, files, or any global state itself. Callers are responsible for supplying the three inputs.

### Expected Functionality

- cli=`Some("a")`, env=`Some("b")`, file=`Some("c")`, default=`"d"` -> `"a"`.
- cli=`None`, env=`Some("b")`, file=`Some("c")`, default=`"d"` -> `"b"`.
- cli=`None`, env=`None`, file=`Some("c")`, default=`"d"` -> `"c"`.
- cli=`None`, env=`None`, file=`None`, default=`"d"` -> `"d"`.
- cli=`Some("")`, env=`Some("b")`, file=`None`, default=`"d"` -> `""`.

## Acceptance Criteria

- A new `precedence` module is declared in `mod.rs` and compiles.
- The resolver applies the fixed precedence cli > env > file > default, treats only `None` as absent (empty string is present), and reads no external state.
- The module's own unit tests cover all scenarios above and pass via:

  ```
  cargo test --bin rg flags::precedence::
  ```
