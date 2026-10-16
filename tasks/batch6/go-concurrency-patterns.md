# Task: Add a Keyed Lock Manager to lib/mutex

## Background

Consul's `lib/mutex` package (`lib/mutex/mutex.go`) wraps
`golang.org/x/sync/semaphore` to provide a `Mutex` whose `TryLock` can be
cancelled by context. Several agent code paths need fine-grained locking keyed by
an identifier (e.g. per-service or per-session) so that operations on different
keys never contend while operations on the same key are serialized. This task
adds a reusable keyed-lock manager to the same package.

## Files to Create/Modify

- `lib/mutex/keyed.go` (new) — the keyed-lock-manager type and its public API.
- `lib/mutex/keyed_test.go` (new) — deterministic tests that run clean under `go test -race`.

## Requirements

Add an exported type to package `mutex` that hands out a logical lock per string
key. Locking one key must serialize only against other holders of the same key,
while different keys proceed in parallel. The exact method/field names are up to
you, but the public surface must support the scenarios below.

### Locking and unlocking

- A constructor returns a ready-to-use manager.
- A blocking lock operation acquires the lock for a given key, blocking until it
  is available, and a corresponding unlock operation releases it.
- A context-aware lock operation acquires the lock for a key but returns the
  context error if the context is cancelled before the lock is obtained; on that
  failure path the manager state for the key must be left consistent (no
  half-held lock).
- Two goroutines locking the same key are serialized: the second blocks until the
  first unlocks. Two goroutines locking different keys must both proceed without
  blocking each other.

### Resource hygiene

- The number of distinct keys ever used may be large; the manager must not retain
  per-key state forever for keys that are no longer held. Once a key has no
  holders and no waiters, its internal state may be reclaimed so that memory does
  not grow without bound as new keys are used over time.
- Reusing a key after it was reclaimed must behave identically to using it the
  first time.

### Concurrency and safety

- Concurrent lock/unlock calls across many keys from many goroutines must be safe.
- Mutual exclusion for a given key must hold under the race detector: a value
  guarded by a key's lock and mutated only while that key is held must never be
  observed in a torn state.
- The implementation must be free of data races and must not leak goroutines.

### Expected Functionality

- Spawn N goroutines that each lock the same key, increment a shared counter, and unlock -> the final counter equals N with no race report.
- Lock key "a" in one goroutine and key "b" in another concurrently -> both acquire without waiting on each other.
- Hold a key, then attempt a context-aware lock of the same key from another goroutine with a context that is cancelled -> that attempt returns the context error and does not corrupt the lock (the holder can still unlock and the key can be locked again afterward).
- Use many distinct keys sequentially, releasing each -> internal per-key state does not accumulate unboundedly (reusing a freed key works normally).

## Acceptance Criteria

- A new file `lib/mutex/keyed.go` exists in package `mutex` exposing an exported
  keyed-lock-manager type with a constructor, a blocking lock and unlock keyed by
  a string, and a context-aware lock keyed by a string that returns the context
  error on cancellation.
- The package builds: `go build ./lib/mutex/` succeeds.
- All scenarios above are covered by deterministic tests in
  `lib/mutex/keyed_test.go`, including: serialized same-key access with a correct
  final counter, parallel different-key access, context-cancelled acquire leaving
  consistent state, and freed-key reuse.
- The following command passes with no failures and no race-detector or
  goroutine-leak reports:

  ```
  go test -race -run 'Keyed' ./lib/mutex/
  ```

- Tests must use synchronization primitives rather than `time.Sleep` to coordinate
  goroutines and must finish deterministically within the package's default test
  timeout.
