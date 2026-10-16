# Task: Add a Resettable Countdown Barrier to lib/semaphore

## Background

Consul's `lib/semaphore` package (`lib/semaphore/semaphore.go`) provides a
`Dynamic` semaphore with context-aware `Acquire`. A complementary coordination
primitive is a countdown barrier: a counter that several goroutines decrement,
where waiters block until the counter reaches zero. This task adds a reusable
countdown barrier to the same package.

## Files to Create/Modify

- `lib/semaphore/barrier.go` (new) — the countdown-barrier type and its public API.
- `lib/semaphore/barrier_test.go` (new) — deterministic tests that run clean under `go test -race`.

## Requirements

Add an exported type to package `semaphore` that is initialized with a positive
count, lets goroutines mark units of work done (decrementing the count), and lets
other goroutines wait until the count reaches zero. The exact method/field names
are up to you, but the public surface must support the scenarios below.

### Construction and counting

- A constructor accepts an initial count (a positive integer) and returns a
  ready-to-use barrier.
- A "done" operation decrements the remaining count by one. When the count reaches
  zero, all current and future waiters for this generation are released.
- Decrementing below zero must be handled deterministically (either by panicking
  with a clear message or by being a safe no-op); the chosen behavior must be
  documented and covered by a test.

### Waiting and cancellation

- A wait operation takes a `context.Context` and blocks until either the count
  reaches zero (returning nil) or the context is cancelled (returning the context
  error). Many goroutines may wait concurrently; all are released together when
  the count hits zero.
- A wait that begins after the count has already reached zero returns immediately
  without blocking.

### Reset / reuse

- The barrier supports being reset to a new positive count for reuse. A reset
  starts a fresh generation: waiters that arrive after the reset block on the new
  count, and reaching zero in the new generation releases them. Reset while
  waiters from a previous, already-released generation exist must not corrupt
  state.

### Concurrency and safety

- Concurrent done/wait/reset calls from many goroutines must be safe.
- The implementation must be free of data races under the race detector and must
  not leak goroutines once all waiters have been released.

### Expected Functionality

- Initialize with count 5, start several waiters, call done 5 times from worker goroutines -> every waiter is released and returns nil.
- Wait with a context that is cancelled before the count reaches zero -> that wait returns the context error while other goroutines still counting down are unaffected.
- Wait after the count has already reached zero -> the wait returns immediately.
- Reach zero, reset to a new count, then run a fresh countdown -> new waiters block until the new count reaches zero, then are released.

## Acceptance Criteria

- A new file `lib/semaphore/barrier.go` exists in package `semaphore` exposing an
  exported countdown-barrier type with a constructor taking an initial count, a
  done/decrement operation, a context-aware wait operation, and a reset operation.
- The package builds: `go build ./lib/semaphore/` succeeds.
- All scenarios above are covered by deterministic tests in
  `lib/semaphore/barrier_test.go`, including: all waiters released on reaching
  zero, context-cancelled wait, immediate return when already zero, and a reset
  generation behaving correctly. The chosen under-zero behavior is also tested.
- The following command passes with no failures and no race-detector or
  goroutine-leak reports:

  ```
  go test -race -run 'Barrier' ./lib/semaphore/
  ```

- Tests must coordinate via channels or other synchronization primitives rather
  than `time.Sleep` and must finish deterministically within the package's default
  test timeout.
