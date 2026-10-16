# Task: Add an Observable Value Store to the shared package

## Background
The `shared` package in this React monorepo holds small, dependency-free utility modules (for example `objectIs.js`, `shallowEqual.js`) consumed across renderers. This task adds a tiny observable value container that notifies subscribers when its value changes, skipping notifications when the new value is equivalent to the old one.

## Files to Create/Modify
- `packages/shared/createObservableValue.js` (new) — the observable value implementation.
- `packages/shared/__tests__/createObservableValue-test.js` (new) — the deterministic test suite for the store.

## Requirements

### Public API
`createObservableValue.js` must `export default` a factory function:

```
createObservableValue(initialValue)
```

It returns a store object exposing exactly these methods:
- `get() -> value`
- `set(nextValue) -> boolean`
- `subscribe(listener) -> unsubscribe`
- `subscriberCount() -> number`

The store must rely only on its arguments; it must never use timers, the network, globals, or any other module.

### Value semantics
- `get()` returns the current value (initially `initialValue`).
- `set(nextValue)` updates the current value and notifies every subscriber **only if** `nextValue` differs from the current value under `Object.is` semantics. It returns `true` when a change occurred (and notifications were sent) and `false` when the value was equivalent (no notification).
- Under `Object.is` semantics: setting `NaN` when the current value is already `NaN` is **not** a change; setting `-0` when the current value is `+0` **is** a change.
- When a change occurs, each subscriber is invoked once with `(nextValue, previousValue)` in subscription order.

### Subscriptions
- `subscribe(listener)` registers `listener` and returns an `unsubscribe` function; calling it removes that listener. Calling `unsubscribe` twice is a safe no-op.
- A listener registered after some `set` calls only receives notifications for subsequent changes.
- `subscriberCount()` returns the number of active subscribers.
- `listener` must be a function; otherwise `subscribe` throws a `TypeError`.

### Expected Functionality
- `set` to a new value -> all subscribers called once with `(next, prev)`; `set` returns `true`.
- `set` to the same value (e.g. `5` when already `5`) -> no subscriber called; `set` returns `false`.
- Current value `NaN`, `set(NaN)` -> returns `false`, no notification.
- Current value `+0`, `set(-0)` -> returns `true`, subscribers notified.
- After `unsubscribe`, that listener is no longer notified and `subscriberCount()` drops.

## Acceptance Criteria
- `packages/shared/createObservableValue.js` exists, exports the factory by default, and imports no other module.
- `packages/shared/__tests__/createObservableValue-test.js` exists and covers, with independent test cases, every behavior above (notification on change, suppression on equivalent value, `Object.is` semantics for `NaN` and signed zero, `(next, prev)` arguments, subscription ordering, unsubscribe idempotency, late-subscriber behavior, `subscriberCount`, and the `TypeError` for a non-function listener). The suite must register subscribers that are mock functions and assert how many times each was invoked and with which `(next, prev)` arguments. Tests must not depend on wall-clock timing, randomness, network, or a running server.
- The following command passes with all assertions green:

```
yarn test packages/shared/__tests__/createObservableValue-test.js
```
