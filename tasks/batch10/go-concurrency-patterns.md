# Task: Add a One-Shot Future to lib/channels

## Background

Consul's `lib/channels` package holds small, generic helpers for moving values
between goroutines (e.g. `DeliverLatest` in `lib/channels/deliver_latest.go`).
Many agent code paths start an asynchronous operation and later need to retrieve
its single eventual result with cancellation support. This task adds a reusable
one-shot future (promise) helper to that package.

## Files to Create/Modify

- `lib/channels/future.go` (new) — the future/promise type and its public API.
- `lib/channels/future_test.go` (new) — deterministic tests that run clean under `go test -race`.

## Requirements

Add an exported generic type to package `channels` representing a value of type
`T` that will be produced exactly once at some point in the future, plus an error.
Producers complete the future once; consumers retrieve the result, optionally
waiting with cancellation. The exact method/field names are up to you, but the
public surface must support the scenarios below.

### Completion

- A constructor returns an uncompleted future carrying type `T`.
- A single "complete" operation sets the future's value and error. The first
  completion wins; subsequent completion attempts must not overwrite the result
  and must not panic (they are no-ops, or report that the future was already
  completed in a way the caller can detect).

### Retrieval

- A blocking get operation takes a `context.Context` and returns the completed
  value and error once available, or the context error if the context is
  cancelled first.
- A non-blocking poll operation reports whether the future is completed and, if so,
  returns its value and error without blocking.
- Multiple goroutines may get/poll the same future concurrently; every getter
  observes the same completed value and error once completion occurs. A getter
  that started waiting before completion is released when completion happens.
- A get on an already-completed future returns immediately.

### Concurrency and safety

- Concurrent complete/get/poll calls from many goroutines must be safe; the
  result observed by every consumer must be consistent (no torn or partial value).
- No goroutine internal to the future may remain running after the future is
  completed and all getters have returned. The implementation must be free of data
  races under the race detector and must not leak goroutines.

### Expected Functionality

- Start several getters that block, then complete the future once -> every getter is released and observes the same value and error.
- Complete the future, then get it -> returns immediately with the completed result.
- Get with a context that is cancelled before completion -> returns the context error; a later completion still works for other consumers.
- Complete twice -> the first completion wins, the second is a no-op (no panic), and pollers/getters see the first result.
- Poll before completion -> reports not-completed; poll after -> reports completed with the value.

## Acceptance Criteria

- A new file `lib/channels/future.go` exists in package `channels` exposing an
  exported generic future type with a constructor, a single completion operation,
  a context-aware blocking get, and a non-blocking poll.
- The package builds: `go build ./lib/channels/` succeeds.
- All scenarios above are covered by deterministic tests in
  `lib/channels/future_test.go`, including: many blocked getters released on
  completion observing the same result, immediate get after completion,
  context-cancelled get, first-completion-wins on double completion without panic,
  and poll before/after completion.
- The following command passes with no failures and no race-detector or
  goroutine-leak reports:

  ```
  go test -race -run 'Future' ./lib/channels/
  ```

- Tests must coordinate via channels or other synchronization primitives rather
  than `time.Sleep` and must finish deterministically within the package's default
  test timeout.
