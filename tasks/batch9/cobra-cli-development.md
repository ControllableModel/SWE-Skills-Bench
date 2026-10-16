# Task: Add a `gh ledger` command with a success-gated post-run finalizer

## Background

The GitHub CLI (`github.com/cli/cli/v2`) has no offline command for validating and committing entries to an in-memory ledger. This task adds a new, fully offline `ledger` command whose post-run finalization must execute **only** when the main work succeeds — exercising the ordering of cobra's run lifecycle. No network, no auth.

## Files to Create/Modify

- `pkg/cmd/ledger/ledger.go` (new) — the `ledger` command, its main run hook, and its post-run finalizer.
- `pkg/cmd/ledger/ledger_test.go` (new) — table-driven in-process tests with redirected streams.
- `pkg/cmd/root/root.go` (modify) — register the new command on the root command (`gh`).

The handler must write through `f.IOStreams`, following the construction style of existing leaf commands under `pkg/cmd/`.

## Requirements

### Command surface

- `gh ledger` is a single command constructed via `NewCmdLedger(f *cmdutil.Factory) *cobra.Command`, registered on the root in `pkg/cmd/root/root.go`. Requires no auth, no network.
- It accepts exactly two positional arguments: `<entry>` and `<amount>` (cobra standard args validation). Wrong counts -> cobra argument-count error (no hand-rolled check).

### Main work and the success-gated finalizer

- The main run step validates the input: `<amount>` must parse as a positive integer. On invalid amount it returns a non-nil error and prints nothing to standard out.
- On valid input, the main step prints a single deterministic "recorded" line to standard out naming the entry and amount.
- A **separate** post-run finalizer step prints a single deterministic "committed" line (e.g. a running total) to standard out. This finalizer must run **only** when the main step returned no error: on a failing run (invalid amount), the "committed" line must **not** appear.
- The finalizer must be wired as a distinct lifecycle step on the command (not merely called inline at the end of the main step), so that its success-gating is enforced by cobra's lifecycle ordering.

### Constraints

- Both the main step and the finalizer must be able to return an error (no `os.Exit`/panic).
- No writes to `os.Stdout`/`os.Stderr` directly.
- A fresh command per invocation yields identical results (no leaked state).

### Expected Functionality

- `gh ledger rent 100` -> standard out contains both a "recorded" line and a "committed" line, in that order.
- `gh ledger rent 0` -> invalid-amount error; standard out contains **neither** a "recorded" line for a committed entry nor any "committed" line.
- `gh ledger rent x` -> invalid-amount error; no "committed" line.
- `gh ledger rent` / `gh ledger rent 1 extra` -> cobra argument-count error; no "committed" line.

## Acceptance Criteria

- `pkg/cmd/ledger/ledger.go` and `ledger_test.go` exist and compile; `pkg/cmd/root/root.go` registers the command.
- A test on a **successful** run asserts both the "recorded" and "committed" lines are present and ordered.
- A separate test on a **failing** run (e.g. amount `0` or non-numeric) asserts the command returned an error **and** that the "committed" finalizer line is absent — proving the finalizer is gated on main-step success.
- Tests build a fresh command per case, drive with `SetArgs`, capture via redirected streams, and total at least 10 distinct cases.
- The package builds: `go build ./pkg/cmd/ledger/... ./pkg/cmd/root/...`
- The following command passes from the repo root:

  ```
  go test ./pkg/cmd/ledger/...
  ```
