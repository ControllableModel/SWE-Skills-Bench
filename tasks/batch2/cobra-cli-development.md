# Task: Add a `gh units` offline unit-conversion command group

## Background

The GitHub CLI (`github.com/cli/cli/v2`) has no built-in helper for converting between the byte/duration units that pepper its own output. This task adds a brand-new, fully offline `units` command group that performs deterministic conversions from a static in-process table — no network, no auth, no GitHub API.

## Files to Create/Modify

- `pkg/cmd/units/units.go` (new) — the parent command and the static conversion table.
- `pkg/cmd/units/convert.go` (new) — the `convert <amount> <from> <to>` subcommand.
- `pkg/cmd/units/units_test.go` (new) — table-driven in-process tests driven by `SetArgs` with redirected streams.
- `pkg/cmd/root/root.go` (modify) — register the new group on the root command (`gh`).

All command handlers must write through the streams owned by the injected `*cmdutil.Factory` (`f.IOStreams`), following the construction style of existing leaf commands under `pkg/cmd/` (e.g. `pkg/cmd/label/list.go`).

## Requirements

### Command surface

- `gh units` is a parent command that, when invoked with no subcommand, prints its own help and exits without error. It must accept no positional arguments of its own.
- Construct it via `NewCmdUnits(f *cmdutil.Factory) *cobra.Command` and register it on the root command in `pkg/cmd/root/root.go`.
- The group must require no authentication and perform no network access; it must work when logged out.

### The static unit table

- Define inside the `units` package a fixed table mapping each known unit name to a multiplier relative to a base unit, grouped into two families: a byte family (`b`, `kb`, `mb`, `gb` as powers of 1024) and a duration family (`s`, `m`, `h`, `d`). Unit names are lowercase and unique.
- The table is hard-coded data — it must not read files, environment, or the network.

### `gh units convert <amount> <from> <to>`

- Requires **exactly three** positional arguments. Supplying any other count must fail with cobra's standard argument-count error message; do not hand-roll a `len(args)` count check inside the handler.
- Beyond the count check, validate the *content* of the arguments with a single custom positional-args validator (a `func(cmd *cobra.Command, args []string) error`) composed onto the command so that it runs before the handler: the first argument must parse as a non-negative number, and the `<from>` and `<to>` units must both exist in the table **and belong to the same family**. A cross-family conversion (e.g. `mb` to `h`) must fail with a clear error naming both units, before any conversion output is produced.
- On valid input, compute `amount * (from_multiplier / to_multiplier)` and print the numeric result on a single line to standard out, formatted deterministically (trailing zeros trimmed so `1024 b kb` prints `1`). Nothing is written to standard error on success.
- Unit matching is case-insensitive.

### Constraints

- Every command handler must be able to return an error (no handler may rely on `os.Exit` or panic to signal failure).
- No handler may write to `os.Stdout`/`os.Stderr` directly; all output must be capturable by an in-process test that redirects the command's streams.
- Building a fresh command tree per invocation must yield identical results regardless of prior invocations (no leaked flag/arg state between executions).

### Expected Functionality

- `gh units` (no args) -> prints help, success, no error.
- `gh units convert 1024 b kb` -> `1`.
- `gh units convert 2 h m` -> `120`.
- `gh units convert 1 MB KB` (mixed case) -> `1024`.
- `gh units convert 5 mb h` -> error naming both units (cross-family), no stdout.
- `gh units convert -3 s m` -> error (negative amount), no stdout.
- `gh units convert 1 b` / `gh units convert 1 b kb extra` -> cobra argument-count error.

## Acceptance Criteria

- `pkg/cmd/units/units.go`, `convert.go`, and `units_test.go` exist and compile.
- `pkg/cmd/root/root.go` registers the new group; `gh units --help` lists `convert`.
- The tests build a fresh command tree per case, drive it with `SetArgs`, capture output via redirected streams (e.g. `iostreams.Test()` plus `cmd.SetOut`/`cmd.SetErr`), and cover at minimum: no-arg parent help, a byte conversion, a duration conversion, a case-insensitive conversion, a cross-family rejection (with no stdout), a negative-amount rejection, and both argument-count failures — at least 10 distinct test cases total.
- The package builds: `go build ./pkg/cmd/units/... ./pkg/cmd/root/...`
- The following command passes from the repo root:

  ```
  go test ./pkg/cmd/units/...
  ```
