# Task: Emit Negation Completions in ripgrep's Fish Completion Output

## Background

ripgrep generates fish-shell completions from its live flag metadata in `crates/core/flags/complete/fish.rs`. Each flag is turned into a `complete -c rg ...` line, and flags that have a negated long form deserve their own completion entry so users can tab-complete things like `--no-...`. This task ensures the fish generator emits a completion line for every flag that declares a negated name.

## Files to Create/Modify

- `crates/core/flags/complete/fish.rs` (modify) — emit an additional completion line for each flag that has a negated long name; add a `#[cfg(test)] mod tests` (or extend it) verifying the generated text.

## Requirements

### Negation lines

- For every flag whose metadata declares a negated long name (the `name_negated` value), the generated fish output must contain a completion line that registers that negated long option for the `rg` command.
- The negated completion line must carry the same short description (`doc_short`) as the flag it negates.
- For example, the `--hidden` flag has the negation `--no-hidden`; the output must contain a `complete -c rg` line that registers the `no-hidden` long option.

### Non-regression for positive forms

- Every flag must still produce its primary positive completion line (long name, optional short name, description) exactly as before.
- Flags without a negated name must not gain a spurious negation line.

### Quoting and determinism

- Any single-quote characters appearing in a flag's description must remain escaped in the emitted line so the fish script stays syntactically valid.
- Generation must depend only on static flag metadata and produce identical output on every run.

### Expected Functionality

- Output contains a `complete -c rg` line registering the `no-hidden` long option with `--hidden`'s description.
- Output contains a `complete -c rg` line registering the `no-ignore-vcs` long option.
- Output still contains the primary positive line for `--hidden` (registering the `hidden` long option).
- A flag with no negation (for example `--max-count`) contributes no negation line.

## Acceptance Criteria

- The fish generator emits one negation completion line per flag that declares a negated name, carrying that flag's short description.
- Positive completion lines are unchanged and flags without negations get no negation line; descriptions with single quotes remain escaped.
- The added/updated unit test asserts the `no-hidden` and `no-ignore-vcs` negation lines and the retained positive `hidden` line, and passes via:

  ```
  cargo test --bin rg flags::complete::fish::
  ```
