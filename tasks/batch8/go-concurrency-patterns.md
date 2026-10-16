# Task: Add a Concurrent Pipeline Stage to lib/channels

## Background

Consul's `lib/channels` package holds small, generic helpers for moving values
between goroutines (e.g. `DeliverLatest` in `lib/channels/deliver_latest.go`).
Processing streams of items through a transformation while preserving streaming
semantics (back-pressure, ordering of completion, cancellation) is a recurring
need. This task adds a reusable concurrent pipeline-stage helper.

## Files to Create/Modify

- `lib/channels/stage.go` (new) — the pipeline-stage function and any supporting type.
- `lib/channels/stage_test.go` (new) — deterministic tests that run clean under `go test -race`.

## Requirements

Add an exported generic function to package `channels` that reads input values
from a `<-chan IN`, applies a transform function to each, and emits results on a
returned `<-chan OUT`, using a configurable number of concurrent workers. The
exact signature is up to you, but it must satisfy the scenarios below.

### Stage behavior

- The function accepts a `context.Context`, an input channel `<-chan IN`, a
  worker count (positive integer), and a transform `func(context.Context, IN)
  (OUT, error)`, and returns an output channel of results.
- Every input value is processed by the transform exactly once. With a worker
  count greater than one, multiple inputs may be transformed concurrently, but at
  no instant may more than the configured number of transforms run simultaneously.
- Each emitted result must carry both the transformed value and any error the
  transform returned for that input (e.g. via a small result struct), so that the
  consumer can observe per-item failures without losing successful results.

### Completion and cancellation

- When the input channel is closed and all in-flight transforms finish, the output
  channel is closed. Ranging over the output then terminates cleanly.
- When the context is cancelled, the stage stops launching new transforms and
  closes the output channel promptly; cooperative transforms observe the
  cancellation through their context.
- A slow consumer must exert back-pressure: the stage must not buffer an unbounded
  number of results ahead of the consumer.

### Concurrency and safety

- No goroutine started by the stage may remain running after the output channel is
  closed (whether by input completion or context cancellation). The implementation
  must be free of data races under the race detector and must not leak goroutines
  across repeated runs.

### Expected Functionality

- Feed 100 inputs through a stage with 4 workers, each transform recording observed concurrency -> all 100 results are emitted and the observed concurrency never exceeds 4.
- Use a transform that returns an error for some inputs -> the corresponding results carry that error while other results carry successful values.
- Close the input after feeding values -> the output channel closes and a range loop over it terminates.
- Cancel the context mid-stream -> the output channel closes promptly and no goroutine leaks.

## Acceptance Criteria

- A new file `lib/channels/stage.go` exists in package `channels` exposing an
  exported generic pipeline-stage function that takes a context, an input channel,
  a worker count, and a transform function and returns a result output channel.
- The package builds: `go build ./lib/channels/` succeeds.
- All scenarios above are covered by deterministic tests in
  `lib/channels/stage_test.go`, including: bounded worker concurrency with all
  inputs processed, per-item error propagation, output closing after input
  completion, and output closing on context cancellation with no goroutine leak.
- The following command passes with no failures and no race-detector or
  goroutine-leak reports:

  ```
  go test -race -run 'Stage' ./lib/channels/
  ```

- Tests must not use `time.Sleep` to assert ordering or completion and must finish
  deterministically within the package's default test timeout.
