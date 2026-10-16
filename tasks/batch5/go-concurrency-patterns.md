# Task: Add a Fan-In Channel Merger to lib/channels

## Background

Consul's `lib/channels` package holds small, generic helpers for moving values
between goroutines (e.g. `DeliverLatest` in `lib/channels/deliver_latest.go`).
Agent components frequently watch several independent event sources and want to
process their outputs through a single loop. This task adds a reusable fan-in
helper that merges many input channels into one.

## Files to Create/Modify

- `lib/channels/merge.go` (new) — the fan-in merge function and any supporting type.
- `lib/channels/merge_test.go` (new) — deterministic tests that run clean under `go test -race`.

## Requirements

Add an exported generic function (or constructor) to package `channels` that
takes any number of input channels of type `<-chan T` plus a
`context.Context`, and returns a single output channel that carries every value
sent on any of the inputs. The exact signature is up to you, but it must satisfy
the scenarios below.

### Merging behavior

- Every value sent on any input channel must eventually appear on the single
  output channel. No input's values may be dropped while the merger is active.
- The relative order of values from any single input is preserved on the output;
  values from different inputs may be interleaved in any order.
- The function must work for zero inputs (the output simply completes) and for an
  arbitrary positive number of inputs.

### Completion and cancellation

- When all input channels are closed, the merger drains any remaining buffered
  values and then closes the output channel.
- When the supplied context is cancelled, the merger stops forwarding and closes
  the output channel promptly, even if some inputs are never closed.
- After the output channel is closed, ranging over it terminates cleanly.

### Concurrency and safety

- The merger must safely read from all inputs concurrently.
- No goroutine started by the merger may remain running after the output channel
  is closed (whether closure was caused by all inputs closing or by context
  cancellation). The implementation must be free of data races under the race
  detector and must not leak goroutines across repeated create/use cycles.

### Expected Functionality

- Merge three inputs each carrying distinct values, then close all three -> the output yields every value exactly once and then closes.
- Merge inputs and range over the output in a loop -> the loop terminates after all inputs close.
- Merge inputs that never close, then cancel the context -> the output closes promptly and no goroutine is left running.
- Merge zero inputs -> the output channel is closed immediately and ranging over it does nothing.

## Acceptance Criteria

- A new file `lib/channels/merge.go` exists in package `channels` exposing an
  exported generic fan-in function that takes a context and a variadic set of
  receive-only input channels and returns a single receive-only output channel.
- The package builds: `go build ./lib/channels/` succeeds.
- All scenarios above are covered by deterministic tests in
  `lib/channels/merge_test.go`, including: all values forwarded exactly once,
  output closing after all inputs close, output closing on context cancellation
  with no goroutine leak, and the zero-input case.
- The following command passes with no failures and no race-detector or
  goroutine-leak reports:

  ```
  go test -race -run 'Merge' ./lib/channels/
  ```

- Tests must not use `time.Sleep` to assert completion or ordering; they must
  finish deterministically within the package's default test timeout.
