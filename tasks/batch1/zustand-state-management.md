# Task: Implement a Shopping-Cart Store Module

## Background

The `zustand` repository (pmndrs/zustand) ships the framework-agnostic `createStore` API from `zustand/vanilla` plus middleware exported from `zustand/middleware`. This task adds a small, self-contained domain module on top of that public API that models a shopping cart, so it can be driven and asserted entirely outside of React using the existing Vitest setup.

## Files to Create/Modify

- `examples/cart-store/cartStore.ts` (new) — the cart store factory and its public types.
- `tests/cartStore.test.ts` (new) — the deterministic test suite for the module.

(The repo already aliases `zustand` / `zustand/*` imports to `src/*` via `vitest.config.mts`, and the Vitest `dir` is `tests`. Place the new module under `examples/cart-store/` and import it from the test by relative path, e.g. `../examples/cart-store/cartStore`.)

## Requirements

Implement a factory `createCartStore(options?)` in `examples/cart-store/cartStore.ts`. It must return a store object that exposes (at minimum) the standard vanilla store handles `getState`, `setState`, and `subscribe`, where `subscribe` additionally accepts a selector form (a selector function, a listener, and an `options` object). The store's state must hold cart line items, the derived totals described below, an async-operation status, and the actions listed below.

### Line items and state shape

- A line item has at least `{ id: string; name: string; unitPrice: number; quantity: number }`.
- The state must expose the current items as a list keyed by `id` (no duplicate ids may coexist), plus these read-only derived fields: `itemCount` (sum of all quantities) and `subtotal` (sum of `unitPrice * quantity` across all items).
- The state must also expose `status: 'idle' | 'loading' | 'success' | 'error'` and `errorMessage: string | null` describing the most recent async operation.

### Synchronous actions

- `addItem(item)`: adds a new line item. If an item with the same `id` already exists, its quantity is increased by the incoming `quantity` instead of creating a duplicate. The derived `itemCount` and `subtotal` must reflect the change.
- `setQuantity(id, quantity)`: sets the quantity of an existing item. A `quantity <= 0` removes the item entirely. A call for an unknown `id` is a no-op (no state change, no error).
- `removeItem(id)`: removes the item with the given `id`; unknown ids are a no-op.
- `clear()`: empties the cart and resets the derived totals to `0`.

### Derived totals must stay consistent

`itemCount` and `subtotal` must always equal the values computed from the current items after every action — they may never drift from the underlying items. A test that mutates the cart through several actions and recomputes the totals independently must always agree with the stored derived fields.

### Selector-scoped subscriptions

Consumers must be able to subscribe to a single derived slice and be notified **only** when that slice changes:

- `subscribe(state => state.subtotal, listener)` must invoke `listener` when (and only when) `subtotal` changes value; it must NOT fire when an unrelated field changes (e.g. `status`) while `subtotal` stays the same.
- The same must hold for an `itemCount` subscription.
- When the selector option `fireImmediately: true` is provided, the listener is called once synchronously at subscription time with the current slice.
- The listener receives `(currentSlice, previousSlice)`.

### Async load action with explicit status/error states

- `loadItems(fetcher)`: accepts a function returning a `Promise` of an items array. Before awaiting, `status` becomes `'loading'` and `errorMessage` becomes `null`. On success, the resolved items replace the cart contents and `status` becomes `'success'`. If the promise rejects (or the fetcher throws synchronously), the cart contents are left unchanged, `status` becomes `'error'`, and `errorMessage` is set to a non-empty message derived from the failure. `loadItems` must not throw to its caller in the rejection case — the error must be captured into store state instead.
- A guard must reject obviously invalid loads early: if `fetcher` is not a function, the action sets `status: 'error'` with a meaningful `errorMessage` and performs no async work.

### Optional persistence hook

`createCartStore` must accept an optional `options.storage` object implementing a minimal key/value contract (`getItem(name)`, `setItem(name, value)`, `removeItem(name)`; values are strings). When `storage` is supplied, the cart items must be serialized to it under a stable key after mutating actions, and a freshly created store given the same populated `storage` must rehydrate the previously saved items (and recompute the derived totals from them). When `options.storage` is omitted, the store must work normally with no persistence side effects. The storage contract must be satisfiable by a plain in-memory object in tests (no `window`, no real `localStorage`, no network).

## Acceptance Criteria

- `examples/cart-store/cartStore.ts` exports `createCartStore` and the relevant TypeScript types; the module compiles under the repo's TypeScript config.
- A new Vitest suite `tests/cartStore.test.ts` contains at least 10 `it`/`test` cases covering: adding items, merging quantities for a duplicate id, `setQuantity` removal at `<= 0`, no-ops for unknown ids, derived `itemCount`/`subtotal` correctness across a sequence of mutations, selector subscriptions firing only on the relevant slice change, `fireImmediately`, the async success path leaving `status: 'success'`, the async rejection path leaving `status: 'error'` with a non-empty `errorMessage` and unchanged items without throwing, the invalid-`fetcher` guard, and rehydration from an in-memory storage object.
- The async-failure tests assert that `loadItems` resolves (does not reject) and that state reflects the error.
- All new tests pass deterministically with no reliance on network, timers, randomness, real `localStorage`, or a running server.
- The following command passes:

  ```
  pnpm vitest run tests/cartStore.test.ts
  ```
