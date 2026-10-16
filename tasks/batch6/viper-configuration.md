# Task: Add a Hot-Reloading Config Watcher for Hugo's Server

## Background

Hugo's `hugo server` already watches the site for changes and rebuilds (see `commands/server.go` and `watcher/`). This task adds a small, self-contained package that watches a single sidecar settings file and re-applies a subset of runtime settings whenever the file changes on disk, so an operator can adjust those settings without restarting the server.

## Files to Create/Modify

- `internal/configwatch/configwatch.go` (new) — the watching settings holder.
- `internal/configwatch/configwatch_test.go` (new) — deterministic unit tests.
- `internal/configwatch/testdata/` (new) — optional fixture config files (tests may also write temp files).
- `go.mod` (modify) — add the dependency required to implement the watcher.
- `go.sum` (modify) — the corresponding checksums.

## Requirements

### Settings shape

Define an exported struct `Settings` decoded from the watched file:

| Key               | Field         | Type     | Default |
| ----------------- | ------------- | -------- | ------- |
| `log_level`       | `LogLevel`    | `string` | `"info"`|
| `disable_fast_render` | `DisableFastRender` | `bool` | `false` |

The struct must be populated by decoding the file's configuration, with the underscore-named keys decoding into the matching fields.

### Watcher API

Provide an exported type `Watcher` with:

- A constructor `New(path string) (*Watcher, error)` that loads the file at `path` and returns a watcher whose current settings reflect that file.
- A method `Current() Settings` returning a snapshot of the currently-resolved settings; it must be safe to call concurrently with a reload.
- A method `Start() error` that begins watching the file for changes; whenever the file's contents change on disk, the watcher must reload it and update what `Current()` returns.
- A method `OnChange(fn func(Settings))` registering a callback invoked with the new settings after each successful reload.
- A method `Stop()` that stops watching and releases resources.

Each `Watcher` must own an isolated configuration instance; constructing multiple watchers (and the test cases) must not share or leak state.

### Reload behavior

- After `Start()`, appending a changed value to the watched file on disk must cause `Current()` to reflect the new value and must invoke each registered `OnChange` callback with the new settings.
- A reload that reads a malformed file must leave the previously-good `Current()` settings unchanged and must NOT invoke the change callback with corrupted data.

### Expected Functionality

- Scenario: file sets `log_level: debug` -> after `New`, `Current().LogLevel == "debug"`.
- Scenario: after `Start()`, the file is updated to `log_level: warn` (content change on disk) -> within a bounded wait, `Current().LogLevel == "warn"` and the `OnChange` callback fired with that value.
- Scenario: `disable_fast_render: true` written to the file -> `Current().DisableFastRender == true`.
- Scenario: the file is rewritten with invalid syntax -> `Current()` still returns the last valid settings.
- Scenario: after `Stop()`, further file changes do not change `Current()`.

Tests must drive reloads by changing the file's bytes on disk (e.g. truncating/rewriting or appending), not by simulating editor behavior, and must wait on `Current()`/callback state with a bounded poll/timeout rather than a fixed unconditional sleep.

## Acceptance Criteria

- Package `internal/configwatch` exports `Settings`, `Watcher`, `New`, and methods `Current`, `Start`, `OnChange`, `Stop`.
- Changing the watched file's bytes after `Start()` updates `Current()` and fires `OnChange`.
- A malformed reload preserves the last valid settings and does not deliver corrupted data to the callback.
- After `Stop()`, changes are ignored.
- `Current()` is safe to call while a reload is in progress.
- Each watcher owns isolated state; tests do not depend on execution order.
- The following command passes from the repository root:

  ```
  go test ./internal/configwatch/
  ```
