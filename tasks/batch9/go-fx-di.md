# Task: Build a Worker-Pool Example with Reverse-Order Graceful Drain

## Background

The `docs/ex` directory of the `go.uber.org/fx` repository is a standalone Go module (`go.uber.org/fx/docs`, with `replace go.uber.org/fx => ../`) hosting small self-contained example applications, each in its own package with a co-located `_test.go`. This task adds a new example focused on the boot/shutdown contract of dependent components: a queue, a pool of workers that drain it, and a producer — where shutdown must release resources in the exact reverse of acquisition.

## Files to Create/Modify

- `docs/ex/workerpool/queue.go` (new) — a bounded in-memory work queue with start/stop coordination.
- `docs/ex/workerpool/worker.go` (new) — a worker pool that consumes the queue in the background once started.
- `docs/ex/workerpool/producer.go` (new) — a producer that enqueues a fixed batch of items at start.
- `docs/ex/workerpool/app.go` (new) — the composition root exposing a reusable `Module` and a shared `*Trace`.
- `docs/ex/workerpool/workerpool_test.go` (new) — the deterministic test described in Acceptance Criteria.

All files use package name `workerpool`. Reuse the existing `go.uber.org/fx/docs` module; do not create a new module or edit `go.mod`.

## Requirements

### Trace recorder

- Define an exported `Trace` struct, safe for concurrent use, with `Add(event string)` and `Events() []string` (returning a copy). It captures the ordered lifecycle events.

### Queue, workers, producer

- The queue, worker pool, and producer each register their own start and stop coordination with the application lifecycle. None may open resources or spawn goroutines from a constructor body.
- On start, components must come up in dependency order and append, in order: `"queue:start"`, `"workers:start"`, `"producer:start"`.
- The producer enqueues exactly `N` (N == 4) deterministic items at start. The worker pool drains the queue; once all `N` items have been processed, the trace must contain exactly `N` `"job:done"` events (the producer's start must block until enqueue completes, but processing happens in the background workers).
- On stop, components must shut down in the exact reverse of their start order, appending `"producer:stop"`, `"workers:stop"`, `"queue:stop"`. The drain on stop must be clean: no item may be lost and no goroutine may be leaked (all worker goroutines exit before `"queue:stop"` is recorded).

### Composition root

- Expose an exported `Module` (`fx.Option`) wiring queue, workers, and producer so that booting `Module` plus a supplied `*Trace` runs the full lifecycle.

### Edge cases & constraints

- Booting must not produce a missing-dependency or cycle error.
- The subsequence of start events and the subsequence of stop events must be exact reverses of each other.
- Exactly `N` `"job:done"` events must be present after a full start+stop cycle — no more, no fewer.
- Spawning the worker goroutines from a constructor (instead of at start) must be detectable: before start, no `"job:done"` may appear.

## Expected Functionality

- Scenario: full start then stop → outcome: start subsequence is `["queue:start","workers:start","producer:start"]` and stop subsequence is `["producer:stop","workers:stop","queue:stop"]`.
- Scenario: count `"job:done"` after the cycle → outcome: exactly 4.
- Scenario: inspect events before start → outcome: no `"job:done"` present.

## Acceptance Criteria

- A new package `workerpool` exists under `docs/ex/workerpool/` exposing `Trace` (with `Events()`) and `Module`.
- `docs/ex/workerpool/workerpool_test.go` boots via `fxtest.New(t, Module, fx.Supply(tr))` with a fresh `*Trace`, calls `RequireStart()`, waits deterministically until 4 `"job:done"` events are recorded (polling `tr.Events()` with a bounded timeout — no fixed sleep that races), then calls `RequireStop()`.
- The test asserts: the start-event subsequence equals `["queue:start","workers:start","producer:start"]`; the stop-event subsequence is its exact reverse; and exactly 4 `"job:done"` events are present.
- A naive implementation that does work in constructors fails because, before `RequireStart()`, no `"job:done"` event may exist.
- The following command, run from the `docs` directory, passes:

  ```bash
  cd docs && go test -race ./ex/workerpool/...
  ```
