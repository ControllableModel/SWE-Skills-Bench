# Task: Add a Context-Aware Single-Flight Barrier to lib/semaphore

## Background

Consul's `lib/semaphore` package (`lib/semaphore/semaphore.go`) provides a
`Dynamic` semaphore whose capacity can change at runtime and whose `Acquire`
respects context cancellation. A related need is to deduplicate concurrent calls
for the same key so that an expensive operation runs only once while other
callers for that key wait for and share its result. This task adds a
context-aware single-flight helper to the same package.

## Files to Create/Modify

- `lib/semaphore/singleflight.go` (new) — the single-flight type and its public API.
- `lib/semaphore/singleflight_test.go` (new) — deterministic tests that run clean under `go test -race`.

## Requirements

Add an exported type to package `semaphore` that, given a string key and a
function producing a value, ensures that for any key only one execution of the
function is in flight at a time; concurrent callers for the same key share the
result of the single in-flight execution. The exact method/field names are up to
you, but the public surface must support the scenarios below.

### Execution and sharing

- The primary operation takes a `context.Context`, a key, and a function
  `func(context.Context) (interface{}, error)` (or a generic equivalent), and
  returns the produced value and error.
- When multiple goroutines call with the same key while a call is in flight, the
  function executes exactly once; all callers for that key receive the same
  returned value and error.
- Calls for different keys proceed independently and may run concurrently.
- After an in-flight call for a key completes, a subsequent call for that same
  key executes the function again (results are not cached beyond the in-flight
  window).

### Cancellation

- Each waiting caller's own `context.Context` must be honored: if a waiter's
  context is cancelled before the shared result is ready, that waiter returns
  with its context error and stops waiting, without affecting the in-flight
  execution or the other waiters.
- The function that performs the work receives a context; the design must ensure
  the work is not abandoned merely because one of several waiters cancelled.

### Concurrency and safety

- Concurrent calls across many keys from many goroutines must be safe.
- The implementation must be free of data races under the race detector and must
  not leak goroutines once all calls have returned.

### Expected Functionality

- Launch 50 goroutines calling with the same key while the function blocks on a signal, then release -> the function ran exactly once and all 50 callers receive the same value.
- Call with two different keys concurrently -> both functions run (deduplication is per-key, not global).
- One waiter cancels its context while a same-key call is in flight -> that waiter returns its context error; the remaining waiters still receive the shared result.
- Call a key, let it complete, then call the same key again -> the function runs a second time.

## Acceptance Criteria

- A new file `lib/semaphore/singleflight.go` exists in package `semaphore`
  exposing an exported single-flight type with a constructor and a call operation
  that takes a context, a key, and a work function and returns a shared
  value/error.
- The package builds: `go build ./lib/semaphore/` succeeds.
- All scenarios above are covered by deterministic tests in
  `lib/semaphore/singleflight_test.go`, including: exactly-once execution with
  shared result under many concurrent same-key callers, per-key independence,
  per-waiter context cancellation, and re-execution after completion.
- The following command passes with no failures and no race-detector or
  goroutine-leak reports:

  ```
  go test -race -run 'SingleFlight' ./lib/semaphore/
  ```

- Tests must use synchronization primitives (not `time.Sleep`) to coordinate the
  in-flight window and must finish deterministically within the package's default
  test timeout.
