# Task: Add a Coalescing Event Debouncer to lib/channels

## Background

Consul's `lib/channels` package holds small, generic helpers for moving values
between goroutines (e.g. `DeliverLatest` in `lib/channels/deliver_latest.go`).
Several agent subsystems receive bursts of change notifications and only want to
react once per quiet window instead of once per event. This task adds a reusable
debouncer that collapses a burst of rapid signals into a single downstream
notification.

## Files to Create/Modify

- `lib/channels/debounce.go` (new) — the debouncer type and its public API.
- `lib/channels/debounce_test.go` (new) — deterministic tests that run clean under `go test -race`.

## Requirements

Add an exported type to package `channels` that turns a stream of incoming
trigger signals into a stream of debounced output signals. A burst of triggers
that arrive close together must produce exactly one output signal once the burst
settles. The exact method/field names are up to you, but the public surface must
let the scenarios below be satisfied, and the receive side must support being
abandoned by the caller.

### Construction and configuration

- A constructor accepts a quiet-window duration (the minimum idle gap that must
  elapse after the last trigger before an output is emitted) and returns a
  ready-to-use debouncer.
- The debouncer must not require an external clock argument to function, but the
  quiet window must be honored: an output is emitted only after the configured
  duration has passed since the most recent trigger.

### Triggering and output

- A caller can submit a trigger through a single non-blocking call; submitting a
  trigger must never block the caller regardless of whether an output is pending
  or being consumed.
- After one or more triggers, exactly one output signal becomes available once
  the quiet window elapses with no further triggers. A continuous stream of
  triggers spaced closer than the quiet window must not emit any output until the
  stream pauses.
- The output is delivered over a receive operation the caller can wait on; that
  operation must support cancellation via a caller-supplied `context.Context`, so
  a consumer can stop waiting without leaving anything running.

### Lifecycle and cleanup

- The debouncer can be closed by its owner. After close, any consumer waiting to
  receive an output is unblocked rather than left hanging, and submitting a
  trigger after close must not panic.
- No goroutine started by the debouncer may remain running after it is closed.
  The implementation must be free of data races under the race detector and must
  not leak goroutines across repeated create/use/close cycles.

### Expected Functionality

- Submit 5 triggers in rapid succession (all within one quiet window), then wait -> exactly one output is received.
- Submit a trigger, wait past the quiet window to consume the output, then submit another trigger -> a second output is received.
- Wait for an output with a context that is cancelled before any trigger -> the receive returns due to context cancellation, not a phantom output.
- Close the debouncer while a consumer is blocked on receive -> the receive returns (does not hang).
- Submit a trigger after close -> no panic.

## Acceptance Criteria

- A new file `lib/channels/debounce.go` exists in package `channels` exposing an
  exported debouncer type with a constructor taking a quiet-window duration, a
  non-blocking trigger-submission operation, a context-cancellable receive
  operation for the debounced output, and a close operation.
- The package builds: `go build ./lib/channels/` succeeds.
- All scenarios above are covered by deterministic tests in
  `lib/channels/debounce_test.go`, including: burst coalescing into a single
  output, a second independent debounce cycle, context-cancelled receive,
  receive unblocking on close, and trigger-after-close not panicking.
- The following command passes with no failures and no race-detector or
  goroutine-leak reports:

  ```
  go test -race -run 'Debounce' ./lib/channels/
  ```

- Tests must complete deterministically and finish well within the package's
  default test timeout; choose quiet-window durations small enough that the test
  runs quickly but must still assert that no output appears before the window
  elapses.
