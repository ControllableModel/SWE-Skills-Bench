# Task: Add a `gh roster` command with composed positional-argument validation

## Background

The GitHub CLI (`github.com/cli/cli/v2`) has no offline command for assembling a small fixed roster from a closed set of role tokens. This task adds a new, fully offline `roster` command whose positional arguments must satisfy **two combined validation rules at once** — a closed value set and a custom uniqueness rule — before the handler runs. No network, no auth.

## Files to Create/Modify

- `pkg/cmd/roster/roster.go` (new) — the `roster` command and its composed args validation.
- `pkg/cmd/roster/roster_test.go` (new) — table-driven in-process tests with redirected streams.
- `pkg/cmd/root/root.go` (modify) — register the new command on the root command (`gh`).

The handler must write through `f.IOStreams`, following the construction style of existing leaf commands under `pkg/cmd/`.

## Requirements

### Command surface and combined args validation

- `gh roster` is a single command constructed via `NewCmdRoster(f *cmdutil.Factory) *cobra.Command`, registered on the root in `pkg/cmd/root/root.go`. Requires no auth, no network.
- The command declares a fixed, closed set of valid role tokens via cobra's `ValidArgs` (e.g. `lead`, `dev`, `qa`, `ops`).
- Positional arguments must satisfy **both** of the following, combined into the command's single args-validation slot (compose the two validators rather than putting either check inside the handler):
  1. Every positional argument must be one of the declared valid role tokens (use cobra's "only valid args" validation against `ValidArgs`); an unknown token must fail with cobra's standard invalid-argument error.
  2. A **custom** validator: at least one argument is required, and no role token may be repeated — a duplicate must fail with a clear error naming the repeated token.
- Both rules must take effect before the handler runs. Supplying zero arguments, an unknown token, or a duplicate token must all fail before any roster is printed.

### Handler output

- On valid input, the handler prints the roster: each accepted role token on its own line, in the order supplied, to standard out. Nothing to standard error on success. Output is deterministic.

### Constraints

- The handler and validators must return errors via `error` (no `os.Exit`/panic).
- No writes to `os.Stdout`/`os.Stderr` directly.
- A fresh command per invocation yields identical results.

### Expected Functionality

- `gh roster lead dev qa` -> three lines, in supplied order.
- `gh roster lead lead` -> duplicate error naming `lead`, no stdout.
- `gh roster lead boss` -> invalid-argument error for `boss` (not in valid set), no stdout.
- `gh roster` (no args) -> error (at least one role required), no stdout.
- Static completion of positional args -> exactly the valid role tokens.

## Acceptance Criteria

- `pkg/cmd/roster/roster.go` and `roster_test.go` exist and compile; `pkg/cmd/root/root.go` registers the command.
- A test proves the closed-set rejection (unknown token errors) and a separate test proves the custom duplicate-rejection rule — both before any stdout is produced — demonstrating the two validators are composed into one args slot.
- A test asserts the declared valid-token set (used both for validation and for completion) equals the intended role set.
- Tests build a fresh command per case, drive with `SetArgs`, capture via redirected streams, and total at least 10 distinct cases.
- The package builds: `go build ./pkg/cmd/roster/... ./pkg/cmd/root/...`
- The following command passes from the repo root:

  ```
  go test ./pkg/cmd/roster/...
  ```
