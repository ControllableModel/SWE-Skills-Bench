# Task: Implement a Notification Queue Store Module

## Background

The `zustand` repository (pmndrs/zustand) exposes the framework-agnostic `createStore` factory from `zustand/vanilla` and the selector-aware subscription helper from `zustand/middleware`. This task adds a self-contained toast/notification-queue domain module on top of that public API, so its queueing and dismissal behavior can be driven and asserted entirely outside of React using the existing Vitest setup.

## Files to Create/Modify

- `examples/notifications-store/notificationsStore.ts` (new) — the notification-queue store factory and its public TypeScript types.
- `tests/notificationsStore.test.ts` (new) — the deterministic Vitest suite for the module.

(The repo aliases `zustand` / `zustand/*` imports to `src/*` via `vitest.config.mts`, and the Vitest `dir` is `tests`. Place the new module under `examples/notifications-store/` and import it from the test by relative path, e.g. `../examples/notifications-store/notificationsStore`.)

## Requirements

Implement a factory `createNotificationsStore(options?)` in `examples/notifications-store/notificationsStore.ts`. It must return a store object exposing the standard vanilla handles `getState`, `setState`, and `subscribe`, where `subscribe` additionally accepts a selector form `(selector, listener, options?)`.

### Notification items and state shape

- A notification has at least `{ id: string; message: string; level: 'info' | 'warning' | 'error' }`.
- The state exposes the queue as an ordered list `notifications` (oldest first, keyed by `id`, no duplicates) and these read-only derived fields, always consistent with the queue:
  - `count: number` — the number of notifications currently in the queue.
  - `hasErrors: boolean` — whether any notification has `level === 'error'`.
  - `visible: Notification[]` — the most recent `maxVisible` notifications (the tail of the queue), where `maxVisible` defaults to `3` and is configurable via `options.maxVisible`.

### Actions

- `push(notification)`: appends a notification with a unique `id` to the end of the queue. When adding it would exceed an optional `options.capacity` (a positive integer cap on the total queue length), the oldest notifications are evicted from the front so the queue length never exceeds `capacity`. When `options.capacity` is omitted, the queue is unbounded.
- `dismiss(id)`: removes the matching notification; an unknown `id` is a no-op.
- `dismissAll()`: empties the queue, returning `count` to `0`, `hasErrors` to `false`, and `visible` to an empty list.

### Derived consistency

`count`, `hasErrors`, and `visible` must always equal the values recomputed from the current queue (and `maxVisible`) after every action and must never drift.

### Selector-scoped subscriptions

Consumers must be able to subscribe to a single derived slice and be notified **only** when that slice changes:

- `subscribe(state => state.count, listener)` fires when (and only when) `count` changes.
- `subscribe(state => state.hasErrors, listener)` fires only when `hasErrors` flips value — e.g. pushing a second `'error'` notification (so `hasErrors` stays `true`) must NOT fire it, while pushing the first `'error'` (false → true) must.
- When `fireImmediately: true` is provided, the listener is called once synchronously at subscription time.

## Acceptance Criteria

- `examples/notifications-store/notificationsStore.ts` exports `createNotificationsStore` and the relevant TypeScript types; the module compiles under the repo's TypeScript config.
- A new Vitest suite `tests/notificationsStore.test.ts` contains at least 10 `it`/`test` cases covering: `push` appending in order, rejecting/handling duplicate ids, `dismiss` removing and being a no-op for an unknown id, `dismissAll` clearing, `count`/`hasErrors` correctness across a sequence of mutations, `visible` returning the tail of size `maxVisible`, the `capacity` eviction keeping the queue within the cap, a `count` selector subscription firing only on count change, a `hasErrors` subscription firing only on the boolean flip (not on a second error), and `fireImmediately`.
- All new tests pass deterministically with no reliance on network, timers, randomness, real `localStorage`, or a running server.
- The following command passes:

  ```
  pnpm vitest run tests/notificationsStore.test.ts
  ```
