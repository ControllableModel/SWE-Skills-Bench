# Task: Add a `gh digest` command with mutually-exclusive and required flags

## Background

The GitHub CLI (`github.com/cli/cli/v2`) has no offline command for computing a stable digest of a literal string in a chosen encoding. This task adds a new, fully offline `digest` command whose flag surface enforces a precise, deterministic combination of options — no network, no auth.

## Files to Create/Modify

- `pkg/cmd/digest/digest.go` (new) — the `digest` command and its flag wiring.
- `pkg/cmd/digest/digest_test.go` (new) — table-driven in-process tests with redirected streams.
- `pkg/cmd/root/root.go` (modify) — register the new command on the root command (`gh`).

The handler must write through `f.IOStreams`, following the construction style of existing leaf commands under `pkg/cmd/`.

## Requirements

### Command surface

- `gh digest` is a single command (no subcommands) constructed via `NewCmdDigest(f *cmdutil.Factory) *cobra.Command`, registered on the root in `pkg/cmd/root/root.go`. It requires no auth and no network.
- It accepts exactly one positional argument: the literal input string (cobra standard args validation). Wrong arg counts must produce cobra's standard argument-count error, not a hand-rolled check.

### Flags and their interlocks

- `--encoding` / `-e` (string, **required**): selects the output encoding, one of `hex` or `base64`. The command must not run without this flag set; omitting it must fail before the handler with cobra's required-flag error.
- `--upper` (bool, default off): when set with `hex`, the hex output must be uppercase.
- `--lower` (bool, default off): when set with `hex`, the hex output must be lowercase.
- `--upper` and `--lower` are **mutually exclusive** — supplying both must fail with cobra's standard mutually-exclusive error, before the handler runs.

### Deterministic output

- Compute a CRC32 (IEEE) checksum of the input bytes and render it in the chosen encoding:
  - `hex` -> the 4-byte checksum as 8 lowercase hex characters by default, uppercased when `--upper`, lowercased when `--lower`.
  - `base64` -> standard base64 of the 4 big-endian checksum bytes. With `base64`, `--upper`/`--lower` have no casing effect (but `--upper` + `--lower` together is still rejected).
- The result is printed on a single line to standard out; nothing to standard error on success. The output for a given input + flags must be identical across runs.

### Constraints

- The handler must return errors via `error` (no `os.Exit`/panic).
- No writes to `os.Stdout`/`os.Stderr` directly.
- A fresh command per invocation yields identical results (no leaked flag state).

### Expected Functionality

- `gh digest hello -e hex` -> lowercase 8-char hex of CRC32("hello").
- `gh digest hello -e hex --upper` -> same value, uppercased.
- `gh digest hello -e base64` -> base64 of the 4 checksum bytes.
- `gh digest hello` (no `--encoding`) -> required-flag error, no stdout.
- `gh digest hello -e hex --upper --lower` -> mutually-exclusive error, no stdout.
- `gh digest -e hex` / `gh digest a b -e hex` -> cobra argument-count error.

## Acceptance Criteria

- `pkg/cmd/digest/digest.go` and `digest_test.go` exist and compile; `pkg/cmd/root/root.go` registers the command.
- A test proves the missing-required-flag rejection and a separate test proves the `--upper`/`--lower` mutual-exclusion rejection, each with no stdout produced.
- The same input + flag combination produces byte-identical output across two separate invocations (assert determinism).
- Tests build a fresh command per case, drive with `SetArgs`, capture via redirected streams, and total at least 10 distinct cases.
- The package builds: `go build ./pkg/cmd/digest/... ./pkg/cmd/root/...`
- The following command passes from the repo root:

  ```
  go test ./pkg/cmd/digest/...
  ```
