# Task: Add a `gh redact` command group distinguishing persistent and local flags

## Background

The GitHub CLI (`github.com/cli/cli/v2`) has no offline command for redacting secrets out of literal text. This task adds a new, fully offline `redact` command group whose flag surface deliberately separates a shared (inherited) option from per-subcommand (local) options — no network, no auth.

## Files to Create/Modify

- `pkg/cmd/redact/redact.go` (new) — the parent command and the shared persistent flag.
- `pkg/cmd/redact/mask.go` (new) — the `mask <text>` subcommand with its own local flag.
- `pkg/cmd/redact/scan.go` (new) — the `scan <text>` subcommand with its own local flag.
- `pkg/cmd/redact/redact_test.go` (new) — table-driven in-process tests with redirected streams.
- `pkg/cmd/root/root.go` (modify) — register the new group on the root command (`gh`).

All handlers must write through `f.IOStreams`, following the construction style of existing leaf commands under `pkg/cmd/`.

## Requirements

### Command surface and flag scoping

- `gh redact` is a parent constructed via `NewCmdRedact(f *cmdutil.Factory) *cobra.Command`, registered on the root in `pkg/cmd/root/root.go`. With no subcommand it prints help and exits without error, accepting no positional args of its own. Requires no auth, no network.
- The parent declares a single **persistent** string flag `--token` / `-t` (the secret token to act on; default empty) that is inherited by and usable from **both** `mask` and `scan`.
- `mask` declares a **local** string flag `--with` (default `*`) — the single character used as the mask. This flag must **not** be available on `scan`.
- `scan` declares a **local** boolean flag `--count` (default off) — print only the number of occurrences. This flag must **not** be available on `mask`.
- Supplying a subcommand's local flag on the *other* subcommand must fail with cobra's standard unknown-flag error.

### `gh redact mask <text>`

- Requires exactly one positional argument (cobra standard args validation).
- If `--token` is empty, returns a clear error before producing output (nothing to stdout).
- Replaces every occurrence of the `--token` value within `<text>` with a run of the `--with` character of equal length to the token, and prints the resulting string on one line to standard out. `--with` must be exactly one character, else a clear error and no stdout.

### `gh redact scan <text>`

- Requires exactly one positional argument.
- If `--token` is empty, returns a clear error before producing output.
- Prints the number of (non-overlapping) occurrences of `--token` in `<text>`. With `--count` off it prints a human line including the count; with `--count` on it prints the bare integer only. Output is deterministic.

### Constraints

- Handlers must return errors via `error` (no `os.Exit`/panic).
- No writes to `os.Stdout`/`os.Stderr` directly.
- A fresh command tree per invocation yields identical results.

### Expected Functionality

- `gh redact mask "abXYab" -t ab` -> `**XY**` (token `ab` masked with default `*`).
- `gh redact mask "abXYab" -t ab --with "#"` -> `##XY##`.
- `gh redact mask "x" --with ab -t z` -> error (mask char not single), no stdout.
- `gh redact mask "x"` (no `--token`) -> error, no stdout.
- `gh redact scan "ababab" -t ab` -> human line containing `3`.
- `gh redact scan "ababab" -t ab --count` -> bare `3`.
- `gh redact mask "x" -t z --count` -> unknown-flag error (`--count` is local to `scan`).
- `gh redact scan "x" -t z --with "#"` -> unknown-flag error (`--with` is local to `mask`).

## Acceptance Criteria

- All new files exist and compile; `pkg/cmd/root/root.go` registers the group.
- A test proves `--token` is usable on both subcommands (inherited), and two tests prove each local flag is rejected on the sibling subcommand (unknown-flag error).
- Tests build a fresh tree per case, drive with `SetArgs`, capture via redirected streams, and total at least 10 distinct cases.
- The package builds: `go build ./pkg/cmd/redact/... ./pkg/cmd/root/...`
- The following command passes from the repo root:

  ```
  go test ./pkg/cmd/redact/...
  ```
