# Task: Add a `gh snippet` command group with dynamic argument completion

## Background

The GitHub CLI (`github.com/cli/cli/v2`) ships rich shell completion. This task adds a new, fully offline `snippet` command group serving a static in-process catalog of code snippets, exercising *dynamic* (computed-at-completion-time) suggestion of its positional argument — no network, no auth.

## Files to Create/Modify

- `pkg/cmd/snippet/snippet.go` (new) — the parent command and the static snippet catalog.
- `pkg/cmd/snippet/get.go` (new) — the `get <key>` subcommand with dynamic completion.
- `pkg/cmd/snippet/snippet_test.go` (new) — table-driven in-process tests, including completion tests.
- `pkg/cmd/root/root.go` (modify) — register the new group on the root command (`gh`).

All handlers must write through `f.IOStreams`, following the construction style of existing leaf commands under `pkg/cmd/`.

## Requirements

### Command surface

- `gh snippet` is a parent constructed via `NewCmdSnippet(f *cmdutil.Factory) *cobra.Command`, registered on the root in `pkg/cmd/root/root.go`. With no subcommand it prints help and exits without error, accepting no positional args of its own. Requires no auth, no network.

### The static catalog

- Define inside the package a fixed map/slice of snippets keyed by a unique lowercase `key` (e.g. `clone`, `commit`, `checkout`, `cherry-pick`), each mapping to a one-line `body`. Hard-coded data only — no files/env/network.

### `gh snippet get <key>`

- Requires exactly one positional argument (cobra standard args validation). Wrong counts -> cobra argument-count error (no hand-rolled check).
- On an exact key match prints the snippet `body` on one line to standard out. On a miss returns a non-nil error naming the unknown key and prints nothing to standard out.
- Provides **dynamic** completion of `<key>`: a completion function that, given the partially typed text, returns only the catalog keys that have that text as a prefix, and signals that shell file-name completion must **not** be offered as a fallback. Completion suggestions must be computed from the live catalog (not a hardcoded `ValidArgs` slice).

### Constraints

- Handlers must return errors via `error` (no `os.Exit`/panic).
- No writes to `os.Stdout`/`os.Stderr` directly.
- A fresh command tree per invocation yields identical results.

### Expected Functionality

- `gh snippet` -> help, success.
- `gh snippet get clone` -> the `clone` snippet body.
- `gh snippet get nope` -> error naming `nope`, no stdout.
- Completion for `gh snippet get che` -> suggestions limited to catalog keys starting with `che` (e.g. `checkout`, `cherry-pick`), with no file-completion fallback.
- Completion for `gh snippet get ` (empty prefix) -> all catalog keys, no file-completion fallback.
- `gh snippet get` / `gh snippet get a b` -> cobra argument-count error.

## Acceptance Criteria

- `pkg/cmd/snippet/snippet.go`, `get.go`, and `snippet_test.go` exist and compile; `pkg/cmd/root/root.go` registers the group.
- A test invokes the command's registered completion function (directly, or via the `__complete` mechanism using `SetArgs` with `cobra.ShellCompRequestCmd`) for at least one non-empty prefix and the empty prefix, asserting both the returned suggestion set **and** that the returned directive prevents file-name completion fallback.
- A test asserts the suggestion set is prefix-filtered (a typed prefix yields a strict subset of keys).
- Tests build a fresh tree per case, drive with `SetArgs`, capture via redirected streams, and total at least 10 distinct cases.
- The package builds: `go build ./pkg/cmd/snippet/... ./pkg/cmd/root/...`
- The following command passes from the repo root:

  ```
  go test ./pkg/cmd/snippet/...
  ```
