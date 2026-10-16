# Task: Add a `gh budget` command group with an inherited pre-run validation chain

## Background

The GitHub CLI (`github.com/cli/cli/v2`) currently has no offline helper for tracking a notional "operation budget" across a small set of subcommands. This task adds a new, fully offline `budget` command group whose subcommands share a validated context established before each runs — entirely from in-process state, with no network or auth.

## Files to Create/Modify

- `pkg/cmd/budget/budget.go` (new) — the parent command and shared options struct.
- `pkg/cmd/budget/spend.go` (new) — the `spend <amount>` subcommand.
- `pkg/cmd/budget/report.go` (new) — the `report` subcommand.
- `pkg/cmd/budget/budget_test.go` (new) — table-driven in-process tests with redirected streams.
- `pkg/cmd/root/root.go` (modify) — register the new group on the root command (`gh`).

All command handlers must write through the streams owned by the injected `*cmdutil.Factory` (`f.IOStreams`), following the construction style of existing leaf commands under `pkg/cmd/`.

## Requirements

### Command surface and the pre-run chain

- `gh budget` is a parent command constructed via `NewCmdBudget(f *cmdutil.Factory) *cobra.Command`, registered on the root in `pkg/cmd/root/root.go`. With no subcommand it prints help and exits without error, accepting no positional args of its own.
- The parent declares a single persistent integer flag `--cap` (default `100`) that is inherited by **both** subcommands.
- Before either subcommand's main work runs, a parent-level pre-run hook must validate `--cap`: a value below `1` must abort with a clear error and prevent the subcommand's main work from executing.
- The `spend` subcommand needs its **own** pre-run step (validating its positional argument, below) **in addition to** the parent's cap validation. Both must take effect for `spend`: the parent's cap check must not be silently lost when the child installs its own pre-run hook. (Cobra does not chain a child's persistent pre-run with the parent's automatically.)

### `gh budget spend <amount>`

- Requires exactly one positional argument via cobra's standard args validation (not a hand-rolled count check).
- The child pre-run step parses `<amount>` as an integer and rejects a negative value with a clear error before the handler runs.
- On success the handler prints a single deterministic line reporting the spent amount and the remaining budget computed as `cap - amount` (e.g. for `--cap 100` spending `30`, remaining is `70`).
- If `amount` exceeds `cap`, the handler returns a non-nil error naming the overspend and prints nothing to standard out.

### `gh budget report`

- Takes no positional arguments.
- Prints a single deterministic line stating the current cap (the value resolved from `--cap`). Inherits the same `--cap` value the parent validated.

### Constraints

- Every handler and pre-run hook must be able to return an error (no `os.Exit`/panic to signal failure).
- No handler may write to `os.Stdout`/`os.Stderr` directly.
- A fresh command tree per invocation must yield identical results regardless of prior invocations.

### Expected Functionality

- `gh budget` -> help, success.
- `gh budget report --cap 250` -> line stating cap `250`.
- `gh budget spend 30` (default cap 100) -> line: spent 30, remaining 70.
- `gh budget spend 30 --cap 0` -> parent cap-validation error, no stdout.
- `gh budget spend -5` -> child negative-amount error, no stdout.
- `gh budget spend 150 --cap 100` -> overspend error, no stdout.
- `gh budget spend` / `gh budget spend 1 2` -> cobra argument-count error.

## Acceptance Criteria

- `pkg/cmd/budget/budget.go`, `spend.go`, `report.go`, and `budget_test.go` exist and compile.
- `pkg/cmd/root/root.go` registers the group; `gh budget --help` lists `spend` and `report`.
- A test case specifically proves the inherited cap validation still fires for `spend` (e.g. `gh budget spend 30 --cap 0` errors), distinct from the child's own amount validation (`gh budget spend -5` errors). Both `--cap 0` for `report` and for `spend` must be rejected.
- Tests build a fresh tree per case, drive with `SetArgs`, capture via redirected streams, and total at least 10 distinct cases.
- The package builds: `go build ./pkg/cmd/budget/... ./pkg/cmd/root/...`
- The following command passes from the repo root:

  ```
  go test ./pkg/cmd/budget/...
  ```
