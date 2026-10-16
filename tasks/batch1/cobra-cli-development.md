# Task: Add a `gh reference` command group for offline CLI cheat-sheet lookup

## Background

The GitHub CLI (`github.com/cli/cli/v2`) ships many subcommands but has no built-in, offline "cheat sheet" that reminds users which flags and aliases a given topic exposes. This task adds a brand-new, fully self-contained `reference` command group that answers questions from a static in-process catalog — no network, no auth, no GitHub API calls.

## Files to Create/Modify

- `pkg/cmd/reference/reference.go` (new) — the parent command and the static catalog it serves.
- `pkg/cmd/reference/list.go` (new) — the `list` subcommand.
- `pkg/cmd/reference/show.go` (new) — the `show <topic>` subcommand.
- `pkg/cmd/reference/reference_test.go` (new) — table-driven tests that execute the command tree in-process and assert on captured output and errors.
- `pkg/cmd/root/root.go` (modify) — register the new command group on the root command (`gh`).

All command handlers must write through the streams owned by the injected `*cmdutil.Factory` (`f.IOStreams`), following the same construction style as the existing leaf commands under `pkg/cmd/` (e.g. `pkg/cmd/completion/completion.go`, `pkg/cmd/label/list.go`).

## Requirements

### Command surface

- `gh reference` is a parent command that, when invoked with no subcommand, prints its own help and exits without error. It must accept no positional arguments of its own.
- It must require no authentication and perform no network access. It must be usable when the user is logged out.
- Construct it via `NewCmdReference(f *cmdutil.Factory) *cobra.Command` and register it on the root command in `pkg/cmd/root/root.go`.

### The static catalog

Define, inside the `reference` package, a fixed in-process catalog of topics. Each topic has a stable lowercase `name` (e.g. `pr`, `issue`, `repo`), a one-line `summary`, and an ordered list of `aliases` (possibly empty). The catalog is hard-coded data — it must not read files, environment, or the network. The catalog must contain at least four topics, and topic names must be unique.

### `gh reference list`

- Takes no positional arguments.
- Prints every catalog topic, one per line, with the topic name followed by its summary, in a stable order (catalog order).
- Supports a `--limit`/`-L` integer flag (default `30`) that caps how many topics are printed; a value below `1` is rejected with a flag error before any output is produced.
- Output goes to standard out; nothing is written to standard error on success.

### `gh reference show <topic>`

- Requires exactly one positional argument: the topic name. Supplying zero or more than one argument must fail with cobra's standard argument-count error message (do not hand-roll an argument-count check inside the handler).
- Topic matching is case-insensitive against the catalog `name`.
- On a match, prints the topic's summary, then — if the topic has aliases — prints each alias. The exact line format is up to you but must be deterministic and asserted by your test.
- On no match, returns a non-nil error whose message names the unknown topic; nothing is written to standard out in that case.
- Provides dynamic completion of the positional `<topic>` argument from the catalog names, such that completion suggestions do not fall back to filename completion.

### Flag inheritance

- Add a single `--plain` boolean flag at the `reference` parent level that is visible to and usable from **both** `list` and `show` (i.e. it is declared once on the parent, not duplicated on each child). When set, `show` omits the alias lines and `list` omits summaries (names only). The flag must default to off.

### Constraints

- Every command handler must be able to return an error (no handler may rely on `os.Exit` or panic to signal failure).
- No handler may write to `os.Stdout` or `os.Stderr` directly; all output must be capturable by an in-process test that redirects the command's streams.
- Building a fresh command tree per test invocation must yield identical results regardless of prior invocations (no leaked flag state between executions).

### Expected Functionality

- `gh reference` (no args) -> prints help, exit code success, no error.
- `gh reference list` -> all topics, name + summary per line, catalog order.
- `gh reference list --limit 2` -> only the first two topics.
- `gh reference list --limit 0` -> flag error, no topic output.
- `gh reference list --plain` -> topic names only, no summaries.
- `gh reference show PR` (any casing) -> matching topic's summary and its aliases.
- `gh reference show pr --plain` -> summary only, no alias lines.
- `gh reference show nope` -> error mentioning `nope`, no stdout.
- `gh reference show` / `gh reference show a b` -> cobra argument-count error.

## Acceptance Criteria

- `pkg/cmd/reference/reference.go`, `list.go`, `show.go`, and `reference_test.go` exist and compile.
- `pkg/cmd/root/root.go` registers the new group; `gh reference --help` lists `list` and `show`.
- The new tests build a fresh command tree per case, drive it with `SetArgs`, capture output via redirected streams (e.g. `iostreams.Test()` plus `cmd.SetOut`/`cmd.SetErr`), and cover at minimum: no-arg parent help, `list` full output and ordering, `--limit` truncation, `--limit 0` flag rejection, case-insensitive `show` hit, `show` miss producing an error with no stdout, the `--plain` behavior on both subcommands, and both argument-count failure cases for `show` — at least 10 distinct test cases total.
- The package builds: `go build ./pkg/cmd/reference/... ./pkg/cmd/root/...`
- The following command passes from the repo root:

  ```
  go test ./pkg/cmd/reference/...
  ```
