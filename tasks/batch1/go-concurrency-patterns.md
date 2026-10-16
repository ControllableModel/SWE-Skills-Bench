# Task: Add a Latest-Value Broadcaster to lib/channels

## Background

Consul's `lib/channels` package (`lib/channels/deliver_latest.go`) holds small,
generic helpers for moving values between goroutines, such as `DeliverLatest`,
which keeps a single-slot channel carrying only the freshest value. Several
internal components (e.g. `agent/proxycfg`, `agent/consul/xdscapacity`) need to
push the most recent snapshot of some state to *many* independent consumers at
once, where each consumer only ever cares about the newest value and slow
consumers must never stall the producer. This task adds a reusable fan-out
helper to that package.

## Files to Create/Modify

- `lib/channels/broadcaster.go` (new) — the new broadcaster type and its public API.
- `lib/channels/broadcaster_test.go` (new) — table/scenario tests that exercise the behavior and run clean under `go test -race`.

## Requirements

Add an exported generic type to package `channels` that lets one producer publish
values and lets any number of consumers each receive the latest published value.
Design the public API so the scenarios below are satisfiable; the exact method
names are up to you, but they must be exported and the type must be generic over
the value type (`[T any]`).

### Construction and publishing

- A constructor returns a ready-to-use broadcaster carrying values of type `T`.
- The producer can publish a value through a single call. Publishing must never
  block on the state of any consumer and must always return promptly, regardless
  of how many consumers exist or whether they are currently reading.
- Each published value supersedes any earlier value that a given consumer has not
  yet observed: a consumer that reads after several rapid publishes is guaranteed
  to be able to observe the most recently published value, not an arbitrarily
  stale one. Intermediate values may be skipped.

### Subscribing and receiving

- A consumer can obtain a subscription from the broadcaster. From a subscription
  the consumer can receive values; the receive operation must support being
  cancelled/abandoned by the caller so a consumer can stop waiting without leaving
  anything running in the background.
- A subscription created *before* a publish must be able to observe that publish.
- Multiple concurrent subscriptions are independent: a value published once must
  be observable by every active subscription, and one consumer reading or failing
  to read must not affect what another consumer can observe.
- A subscription that never reads, or reads slowly, must not cause the producer or
  other consumers to block or to accumulate unbounded memory: at most a bounded
  amount of state (the latest value) is retained per subscription.

### Lifecycle and cleanup

- A subscription can be released by its owner. After release, that subscription
  stops receiving further published values.
- The broadcaster can be shut down. After shutdown, every outstanding subscription
  is unblocked (any consumer waiting to receive returns rather than hanging), and
  publishing after shutdown must not panic.
- No goroutine started by the broadcaster or its subscriptions may remain running
  after the broadcaster is shut down and all subscriptions are released. The
  implementation must be free of data races under the race detector and must not
  leak goroutines across repeated create/use/shutdown cycles.

### Expected Functionality

- Publish `A`, then `B`, then a consumer reads -> consumer observes `B` (latest), not necessarily `A`.
- Subscribe, then publish `X` -> the subscription can receive `X`.
- Two subscriptions active, publish `X` once -> both subscriptions can receive `X` independently.
- A consumer abandons a pending receive (via its cancellation mechanism) -> the receive returns without the value and nothing keeps running for it.
- Producer publishes in a tight loop while one consumer is blocked/slow -> the producer calls all return promptly and the consumer can still later read the most recent value.
- Shut down the broadcaster while a consumer is blocked on receive -> that consumer's receive returns (does not hang).
- Publish after shutdown -> no panic.

## Acceptance Criteria

- A new file `lib/channels/broadcaster.go` exists in package `channels` exposing
  an exported generic broadcaster type with a constructor, a publish operation, a
  way to obtain a subscription, a per-subscription receive operation that supports
  caller cancellation, a per-subscription release operation, and a broadcaster
  shutdown operation.
- The package builds: `go build ./lib/channels/` succeeds.
- All scenarios in the Requirements/Expected Functionality sections are covered by
  deterministic tests in `lib/channels/broadcaster_test.go`, including: latest-wins
  coalescing under rapid publishes, fan-out to multiple independent subscriptions,
  non-blocking publish while a consumer is slow/blocked, caller-cancelled receive,
  receive unblocking on shutdown, and publish-after-shutdown not panicking.
- The following command passes with no failures and no race-detector or
  goroutine-leak reports:

  ```
  go test -race -run 'Broadcaster' ./lib/channels/
  ```

- Tests must not rely on `time.Sleep` as a synchronization mechanism for asserting
  ordering or completion; they must complete deterministically and finish well
  within the package's default test timeout.
