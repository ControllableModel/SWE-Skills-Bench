# Task: Implement a Paginated Data-Table Store Module

## Background

The `zustand` repository (pmndrs/zustand) exposes the framework-agnostic `createStore` factory from `zustand/vanilla` and the selector-aware subscription helper from `zustand/middleware`. This task adds a self-contained paginated data-table domain module on top of that public API, so its paging, sorting, and async fetch behavior can be driven and asserted entirely outside of React using the existing Vitest setup.

## Files to Create/Modify

- `examples/table-store/tableStore.ts` (new) — the data-table store factory and its public TypeScript types.
- `tests/tableStore.test.ts` (new) — the deterministic Vitest suite for the module.

(The repo aliases `zustand` / `zustand/*` imports to `src/*` via `vitest.config.mts`, and the Vitest `dir` is `tests`. Place the new module under `examples/table-store/` and import it from the test by relative path, e.g. `../examples/table-store/tableStore`.)

## Requirements

Implement a factory `createTableStore(options?)` in `examples/table-store/tableStore.ts`. It must return a store object exposing the standard vanilla handles `getState`, `setState`, and `subscribe`, where `subscribe` additionally accepts a selector form `(selector, listener, options?)`.

### Row data and state shape

- A row has at least `{ id: string; name: string; score: number }`.
- The state exposes the full `rows` list (keyed by `id`, no duplicates), `pageSize: number` (default `10`, configurable via `options.pageSize`), `pageIndex: number` (zero-based), `sortKey: 'name' | 'score'`, and `sortDir: 'asc' | 'desc'`.
- The state exposes these read-only derived fields, always consistent with the data and paging:
  - `sortedRows` — all rows ordered by `sortKey`/`sortDir` (`score` numeric, `name` lexicographic).
  - `pageRows` — the slice of `sortedRows` for the current `pageIndex` and `pageSize`.
  - `pageCount` — `ceil(rows.length / pageSize)`, at least `1` even when there are zero rows.

### Actions

- `setRows(rows)`: replaces all rows (rejecting any input that contains duplicate ids — no state change in that case) and resets `pageIndex` to `0`.
- `setSort(key, dir)`: updates the sort key/direction and recomputes `sortedRows`/`pageRows`; resets `pageIndex` to `0`.
- `goToPage(index)`: sets `pageIndex`, clamped to `[0, pageCount - 1]`.
- `nextPage()` / `prevPage()`: move one page within the clamped range (no-op at the respective boundary).

### Derived consistency

`sortedRows`, `pageRows`, `pageCount`, and the clamped `pageIndex` must always equal the values recomputed from `rows`, `pageSize`, `sortKey`, and `sortDir` after every action and must never drift.

### Async fetch with status/error states

- The state also exposes `status: 'idle' | 'loading' | 'success' | 'error'` and `errorMessage: string | null`.
- `fetchRows(fetcher)`: accepts a function returning a `Promise` of a rows array. Before awaiting, `status` becomes `'loading'` and `errorMessage` becomes `null`. On success the resolved rows replace the data (via the same duplicate-id validation as `setRows`) and `status` becomes `'success'`. On rejection (or a synchronous throw) the rows are left unchanged, `status` becomes `'error'`, `errorMessage` is set to a non-empty message, and `fetchRows` must NOT throw to its caller. If `fetcher` is not a function, the action sets `status: 'error'` with a meaningful message and performs no async work.

### Selector-scoped subscriptions

- `subscribe(state => state.pageRows, listener)` fires when (and only when) the `pageRows` slice changes (compared with shallow/structural equality so that paging or sorting that changes the visible page fires, but an unrelated `status` change does not).
- When `fireImmediately: true` is provided, the listener is called once synchronously at subscription time.

## Acceptance Criteria

- `examples/table-store/tableStore.ts` exports `createTableStore` and the relevant TypeScript types; the module compiles under the repo's TypeScript config.
- A new Vitest suite `tests/tableStore.test.ts` contains at least 10 `it`/`test` cases covering: `setRows` with `pageCount`/`pageRows` correctness, rejecting duplicate ids, sorting by `score` and by `name` in both directions, `goToPage` clamping, `nextPage`/`prevPage` boundaries, derived consistency across a sequence of actions, the async success path leaving `status: 'success'`, the async rejection path leaving `status: 'error'` with a non-empty `errorMessage` and unchanged rows without throwing, the invalid-`fetcher` guard, and a `pageRows` selector subscription that fires on page change but not on an unrelated `status` change.
- All new tests pass deterministically with no reliance on network, timers, randomness, real `localStorage`, or a running server.
- The following command passes:

  ```
  pnpm vitest run tests/tableStore.test.ts
  ```
