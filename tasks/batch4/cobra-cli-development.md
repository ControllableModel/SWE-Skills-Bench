# Task: Add a `gh palette` command group with labelled help sections

## Background

The GitHub CLI (`github.com/cli/cli/v2`) groups related subcommands under titled sections in its help output. This task adds a new, fully offline `palette` command group that demonstrates the same titled-section help organization while serving a static in-process color catalog — no network, no auth.

## Files to Create/Modify

- `pkg/cmd/palette/palette.go` (new) — the parent command, the static color catalog, and the titled help sections.
- `pkg/cmd/palette/name.go` (new) — the `name <color>` lookup subcommand (a "query" section command).
- `pkg/cmd/palette/list.go` (new) — the `list` subcommand (a "query" section command).
- `pkg/cmd/palette/random.go` (new) — the `pick <index>` subcommand (a "select" section command).
- `pkg/cmd/palette/palette_test.go` (new) — table-driven in-process tests with redirected streams.
- `pkg/cmd/root/root.go` (modify) — register the new group on the root command (`gh`).

All command handlers must write through `f.IOStreams`, following the construction style of existing leaf commands under `pkg/cmd/`.

## Requirements

### Command surface and grouped help

- `gh palette` is a parent command constructed via `NewCmdPalette(f *cmdutil.Factory) *cobra.Command`, registered on the root in `pkg/cmd/root/root.go`. With no subcommand it prints help and exits without error, accepting no positional args of its own.
- The three subcommands must appear under **two distinct titled sections** in `gh palette --help`: `name` and `list` under one titled section ("Query commands:") and `pick` under another ("Select commands:"). The section titles must be registered such that each subcommand is assigned to its section and the titles render in help output. (Group declarations must exist before the subcommands are attached, or the assignment will not take effect.)

### The static catalog

- Define inside the package a fixed, ordered catalog of at least four colors. Each entry has a unique lowercase `name` (e.g. `red`, `green`, `blue`, `amber`) and a stable `hex` string. Hard-coded data only — no files/env/network.

### `gh palette list`

- No positional arguments. Prints every color, one per line, `name` then `hex`, in catalog order. Nothing to standard error on success.

### `gh palette name <color>`

- Requires exactly one positional argument (cobra standard args validation).
- Case-insensitive match against catalog names; on a hit prints the matching `hex`. On a miss returns a non-nil error naming the unknown color and prints nothing to standard out.
- Offers static completion of `<color>` from the catalog names via cobra's `ValidArgs`, so shell completion suggests exactly the catalog names.

### `gh palette pick <index>`

- Requires exactly one positional argument, a zero-based integer index. An out-of-range index returns a non-nil error and prints nothing to standard out; an in-range index prints that catalog entry's `name` and `hex`.

### Constraints

- Every handler must return errors via `error` (no `os.Exit`/panic).
- No handler may write to `os.Stdout`/`os.Stderr` directly.
- A fresh command tree per invocation yields identical results.

### Expected Functionality

- `gh palette --help` -> help text contains both titled section headers and lists `name`, `list`, `pick`.
- `gh palette list` -> all entries in catalog order.
- `gh palette name BLUE` -> the blue hex (case-insensitive).
- `gh palette name nope` -> error naming `nope`, no stdout.
- `gh palette pick 0` -> first catalog entry; `gh palette pick 99` -> range error, no stdout.
- `gh palette name` / `gh palette name a b` -> cobra argument-count error.

## Acceptance Criteria

- All new files exist and compile; `pkg/cmd/root/root.go` registers the group.
- `gh palette --help` output contains both section titles ("Query commands:" and "Select commands:") and assigns each subcommand to the correct section — assert on the captured help string.
- The static `ValidArgs` completion list for `name` equals the catalog names (assertable from the constructed command).
- Tests build a fresh tree per case, drive with `SetArgs`, capture via redirected streams, and total at least 10 distinct cases.
- The package builds: `go build ./pkg/cmd/palette/... ./pkg/cmd/root/...`
- The following command passes from the repo root:

  ```
  go test ./pkg/cmd/palette/...
  ```
