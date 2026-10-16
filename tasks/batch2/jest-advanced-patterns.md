# Task: Add a Synchronous Event Bus to the shared package

## Background
The `shared` package in this React monorepo collects small, dependency-free utility modules (for example `shallowEqual.js`, `objectIs.js`) consumed across renderers. This task adds a tiny synchronous publish/subscribe event bus that lets independent parts of a renderer broadcast named events to registered listeners.

## Files to Create/Modify
- `packages/shared/createEventBus.js` (new) — the event bus implementation.
- `packages/shared/__tests__/createEventBus-test.js` (new) — the deterministic test suite for the bus.

## Requirements

### Public API
`createEventBus.js` must `export default` a zero-argument factory function:

```
createEventBus()
```

It returns a bus object exposing exactly these methods:
- `on(eventName, listener) -> unsubscribe`
- `once(eventName, listener) -> unsubscribe`
- `emit(eventName, payload) -> number`
- `listenerCount(eventName) -> number`
- `removeAll(eventName?) -> void`

### on(eventName, listener)
- Registers `listener` for the given `eventName`. Returns an `unsubscribe` function; calling it removes that exact listener registration.
- The same listener function may be registered more than once for the same event; each registration is independent and each must be invoked on `emit`.
- Calling the returned `unsubscribe` more than once is a no-op after the first call (it must not remove an unrelated listener and must not throw).
- `listener` must be a function; otherwise `on` throws a `TypeError`.

### once(eventName, listener)
- Like `on`, but the listener is automatically removed immediately before or after its first invocation, so it fires at most once even if the event is emitted repeatedly.
- The returned `unsubscribe` must cancel the pending once-listener if called before the event ever fires.

### emit(eventName, payload)
- Invokes every currently registered listener for `eventName`, in registration order, each called with the single `payload` argument. Returns the number of listeners that were invoked.
- Emitting an event with no listeners returns `0` and does nothing.
- Mutating the listener set from inside a listener (e.g. a listener unsubscribing itself or another) must not skip or double-invoke any listener that was registered at the moment `emit` began.

### listenerCount / removeAll
- `listenerCount(eventName)` returns the number of active listeners for that event (`once` listeners count until they fire).
- `removeAll(eventName)` removes all listeners for that event; `removeAll()` with no argument removes listeners for every event.

### Expected Functionality
- Register two listeners on `'data'`, `emit('data', 5)` -> both called once with `5`; `emit` returns `2`.
- A `once('ping', fn)` listener -> after two `emit('ping')` calls, `fn` was called exactly once.
- `unsubscribe` from `on` -> that listener no longer fires on later emits; `listenerCount` drops accordingly.
- `emit` on an event with zero listeners -> returns `0`.
- A listener that unsubscribes a second listener during `emit` -> the second listener still runs for that in-progress emit but not for subsequent emits.

## Acceptance Criteria
- `packages/shared/createEventBus.js` exists, exports the factory by default, and imports no other module.
- `packages/shared/__tests__/createEventBus-test.js` exists and covers, with independent test cases, every behavior above (multi-listener emit ordering, `once`, unsubscribe idempotency, mid-emit mutation safety, `listenerCount`, `removeAll` with and without an argument, and the `TypeError` for a non-function listener). The suite must register listeners that are mock functions and assert how many times each was invoked and with which payloads. Tests must not depend on wall-clock timing, randomness, network, or a running server.
- The following command passes with all assertions green:

```
yarn test packages/shared/__tests__/createEventBus-test.js
```
