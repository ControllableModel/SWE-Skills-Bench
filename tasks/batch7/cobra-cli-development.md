# Task: Add a `gh stats` command with bounded args and flag-value completion

## Background

The GitHub CLI (`github.com/cli/cli/v2`) has no offline command for computing simple summary statistics over a list of literal numbers. This task adds a new, fully offline `stats` command that accepts a bounded number of positional values and offers completion for one of its flags' values — no network, no auth.

## Files to Create/Modify

- `pkg/cmd/stats/stats.go` (new) — the `stats` command, its flags, and flag-value completion registration.
- `pkg/cmd/stats/stats_test.go` (new) — table-driven in-process tests, including a flag-completion test.
- `pkg/cmd/root/root.go` (modify) — register the new command on the root command (`gh`).

The handler must write through `f.IOStreams`, following the construction style of existing leaf commands under `pkg/cmd/`.

## Requirements

### Command surface and bounded args

- `gh stats` is a single command constructed via `NewCmdStats(f *cmdutil.Factory) *cobra.Command`, registered on the root in `pkg/cmd/root/root.go`. Requires no auth, no network.
- It accepts between **1 and 8** positional numeric arguments, enforced with cobra's range argument validation (not a hand-rolled count check). Zero args, or more than 8, must fail with cobra's standard argument-count error before the handler runs.
- Each positional argument must parse as a number; a non-numeric argument causes the handler to return a non-nil error naming the bad value, with no statistic printed.

### The `--metric` flag and its completion

- `--metric` / `-m` (string, default `sum`): one of `sum`, `mean`, `min`, `max`. An unsupported value must fail with a clear error before computing anything.
- Register a flag-value completion function for `--metric` so that completing its value suggests exactly the four supported metric names (and no file-name fallback).

### Deterministic output

- The handler computes the requested metric over the parsed positional numbers and prints the result on a single line to standard out, formatted deterministically (trailing zeros trimmed; `mean` of `1 2` prints `1.5`). Nothing to standard error on success.

### Constraints

- The handler must return errors via `error` (no `os.Exit`/panic).
- No writes to `os.Stdout`/`os.Stderr` directly.
- A fresh command per invocation yields identical results (no leaked flag state).

### Expected Functionality

- `gh stats 1 2 3 4` -> `10` (default metric `sum`).
- `gh stats 1 2 -m mean` -> `1.5`.
- `gh stats 5 1 9 -m min` -> `1`; `-m max` -> `9`.
- `gh stats 1 2 -m median` -> unsupported-metric error, no stdout.
- `gh stats 1 x 3` -> non-numeric error naming `x`, no stdout.
- `gh stats` (no args) / nine args -> cobra argument-count error.
- Completing `--metric` value -> exactly `sum`, `mean`, `min`, `max`, no file-name fallback.

## Acceptance Criteria

- `pkg/cmd/stats/stats.go` and `stats_test.go` exist and compile; `pkg/cmd/root/root.go` registers the command.
- A test drives the flag-value completion (e.g. via `__complete` using `SetArgs` with `cobra.ShellCompRequestCmd` and `--metric ""`, or by invoking the registered function) and asserts the suggestion set equals the four metric names with no file-name fallback.
- Tests prove both bounds of the arg range: zero args rejected and nine args rejected, each with cobra's argument-count error.
- Tests build a fresh command per case, drive with `SetArgs`, capture via redirected streams, and total at least 10 distinct cases.
- The package builds: `go build ./pkg/cmd/stats/... ./pkg/cmd/root/...`
- The following command passes from the repo root:

  ```
  go test ./pkg/cmd/stats/...
  ```
