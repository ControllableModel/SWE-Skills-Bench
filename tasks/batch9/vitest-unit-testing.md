# Task: Add a minimal typed event emitter

## Background

Vite's dev server and HMR layers pass events between components. A small, dependency-free typed event emitter is a reusable primitive for such notification points. This task adds an `EventEmitter` to the node utilities, with `on`/`once`/`off`/`emit`, plus a test suite that verifies listener invocation precisely.

## Files to Create/Modify

- `packages/vite/src/node/eventEmitter.ts` (new) — the `EventEmitter` implementation.
- `packages/vite/src/node/__tests__/eventEmitter.spec.ts` (new) — a dedicated test file exercising listener semantics.

## Requirements

### Class shape

Export a class from `packages/vite/src/node/eventEmitter.ts`:

```ts
export class EventEmitter<Events extends Record<string, unknown>> {
  on<E extends keyof Events>(event: E, listener: (payload: Events[E]) => void): () => void
  once<E extends keyof Events>(event: E, listener: (payload: Events[E]) => void): () => void
  off<E extends keyof Events>(event: E, listener: (payload: Events[E]) => void): void
  emit<E extends keyof Events>(event: E, payload: Events[E]): void
  listenerCount<E extends keyof Events>(event: E): number
}
```

### Behavior

- `on` registers a listener and returns an unsubscribe function; calling that function removes exactly that listener.
- `emit` calls every listener currently registered for the event, in registration order, each with the single `payload` argument.
- `once` registers a listener that is invoked at most once and then automatically removed before/at the time it would be eligible for a second call.
- `off` removes a specific listener for an event; removing a listener that is not registered is a no-op.
- The same listener function registered twice for the same event is invoked twice per `emit`; `off` removes one registration at a time.
- Emitting an event with no listeners is a no-op and must not throw.
- `listenerCount` returns the number of currently-registered listeners for the event (a `once` listener counts until it has fired).
- Adding or removing listeners from inside a listener during an `emit` must not affect the set of listeners already being notified by that same `emit` (the dispatch iterates over a snapshot).

### Edge cases

- After a `once` listener fires, `listenerCount` for that event drops accordingly.
- Calling the unsubscribe function returned by `on` twice is safe (second call is a no-op).
- Listeners for different events are isolated; emitting event `a` must never call event `b`'s listeners.

### Expected Functionality

| Scenario | Outcome |
|----------|---------|
| two `on` listeners, then `emit` | both called once, in registration order, with the payload |
| `once` listener, then `emit` twice | called exactly once total |
| `on` listener then call its unsubscribe, then `emit` | not called |
| listener added during `emit` | not called by that same `emit` |

## Acceptance Criteria

- `EventEmitter` is exported from `packages/vite/src/node/eventEmitter.ts` with the shape above.
- The new test file imports `EventEmitter` from `../eventEmitter`, uses mock listener functions to assert exact call counts, call arguments, and invocation order, and creates a fresh emitter per test.
- The file contains at least 12 assertions and covers all four scenarios above plus event isolation and double-unsubscribe safety.
- Every test passes when run from the repo root:

```
pnpm exec vitest run packages/vite/src/node/__tests__/eventEmitter.spec.ts
```

- A naive implementation (mutating the live listener array during dispatch, `once` firing twice, or unsubscribe affecting the wrong listener) must fail at least one assertion.
