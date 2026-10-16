# Task: Add a Periodic Task Runner to lib/routine

## Background

Consul's `lib/routine` package (`lib/routine/routine.go`) manages long-lived
background goroutines via a `Manager`. A recurring need is to run a callback on a
fixed interval and to stop it cleanly when shutting down. This task adds a
reusable periodic task runner to the same package.

## Files to Create/Modify

- `lib/routine/periodic.go` (new) — the periodic-runner type and its public API.
- `lib/routine/periodic_test.go` (new) — deterministic tests that run clean under `go test -race`.

## Requirements

Add an exported type to package `routine` that invokes a supplied callback
repeatedly on a configured interval inside a single dedicated goroutine, and that
can be started and stopped. The exact method/field names are up to you, but the
public surface must support the scenarios below.

### Construction and running

- A constructor accepts an interval duration and a callback of the form
  `func(context.Context) error`.
- A start operation begins the periodic loop in the background and returns
  promptly (it does not block the caller for the lifetime of the runner).
- The callback is invoked once per interval. Each invocation receives a context
  derived from the runner's lifetime so the callback can observe shutdown.
- A new invocation must not start while the previous invocation of the callback is
  still running; ticks that occur while a callback is in progress must not cause
  overlapping concurrent invocations.

### Stopping

- A stop operation cancels the runner's context and waits for any in-progress
  callback to return before it itself returns, so that after stop returns no
  callback is executing and no further invocations will occur.
- Calling stop more than once must be safe and must not panic.
- A callback that is blocked observes context cancellation when stop is called, so
  a cooperative callback can return promptly.

### Concurrency and safety

- Starting and stopping from different goroutines must be coordinated safely.
- No goroutine started by the runner may remain running after stop returns. The
  implementation must be free of data races under the race detector and must not
  leak goroutines across repeated start/stop cycles.

### Expected Functionality

- Start a runner whose callback increments a counter, let several intervals elapse, then stop -> the counter advanced by roughly the number of elapsed intervals and stopped advancing after stop.
- Use a callback that signals when it has started and then blocks -> stop cancels its context, the callback returns, and stop returns only after it does.
- Use a callback that takes longer than the interval -> invocations never overlap (the runner never has two callback bodies executing at once).
- Call stop twice -> no panic.

## Acceptance Criteria

- A new file `lib/routine/periodic.go` exists in package `routine` exposing an
  exported periodic-runner type with a constructor taking an interval and a
  `func(context.Context) error` callback, a non-blocking start operation, and a
  stop operation that waits for the in-progress callback to finish.
- The package builds: `go build ./lib/routine/` succeeds.
- All scenarios above are covered by deterministic tests in
  `lib/routine/periodic_test.go`, including: periodic invocation and cessation
  after stop, callback observing cancellation on stop with stop awaiting it,
  no overlapping invocations for a slow callback, and idempotent stop.
- The following command passes with no failures and no race-detector or
  goroutine-leak reports:

  ```
  go test -race -run 'Periodic' ./lib/routine/
  ```

- Tests must coordinate via channels or other synchronization primitives rather
  than asserting timing with `time.Sleep`, and must finish deterministically
  within the package's default test timeout (use a small interval).
