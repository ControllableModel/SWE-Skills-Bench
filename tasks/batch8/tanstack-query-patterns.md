# Task: Add an Optimistic List Update and Rollback Helper

## Background

In the framework-agnostic core (`packages/query-core`), a consumer can update cached list data immediately when a change is initiated and then roll back to the prior snapshot if the change fails. This task adds a self-contained public utility to `@tanstack/query-core` that produces the optimistic next state of a keyed list together with the snapshot needed to undo it.

## Files to Create/Modify

- `packages/query-core/src/optimisticList.ts` (new) — implementation of the helper and its exported types.
- `packages/query-core/src/index.ts` (modify) — re-export the new function and its types from the package entry point.
- `packages/query-core/src/__tests__/optimisticList.test.tsx` (new) — vitest suite covering the behavior described below.

## Requirements

Add two exported functions with the signatures:

```ts
export interface OptimisticEdit<TItem> {
  type: 'add' | 'update' | 'remove'
  item: TItem
}

export interface OptimisticResult<TItem> {
  next: Array<TItem>
  snapshot: Array<TItem>
}

export function applyOptimistic<TItem extends { id: string | number }>(
  current: ReadonlyArray<TItem>,
  edit: OptimisticEdit<TItem>,
): OptimisticResult<TItem>

export function rollback<TItem>(
  result: OptimisticResult<TItem>,
): Array<TItem>
```

`applyOptimistic` computes the optimistic next list and captures a snapshot; `rollback` returns the captured snapshot so the prior state can be restored.

### Update semantics

Items are identified by their `id` property.

- `'add'`: append `edit.item` to the end of the list. If an item with the same `id` already exists, the list is returned unchanged (no duplicate `id`).
- `'update'`: replace the existing item that has the same `id` as `edit.item` with `edit.item`, preserving its position. If no item with that `id` exists, the list is returned unchanged.
- `'remove'`: drop the item whose `id` equals `edit.item.id`, preserving the order of the rest. If no such item exists, the list is returned unchanged.
- `snapshot` MUST be a shallow copy of `current` captured before the edit, suitable for restoring the prior state.
- `rollback(result)` MUST return `result.snapshot`.

### Edge cases and constraints

- `next` MUST be a new array (never the same reference as `current`); the function MUST NOT mutate `current` or any element.
- For a no-op edit (duplicate add, update/remove of a missing id), `next` MUST still be a new array equal in contents to `current`.
- Order is preserved for `update` and `remove`; `add` always appends at the end.
- The functions MUST be pure and MUST NOT require a `QueryClient`, cache, timers, network, or framework.

### Expected Functionality

- `applyOptimistic([{ id: 1, t: 'a' }], { type: 'add', item: { id: 2, t: 'b' } }).next` -> `[{ id: 1, t: 'a' }, { id: 2, t: 'b' }]`
- `applyOptimistic([{ id: 1, t: 'a' }], { type: 'add', item: { id: 1, t: 'dupe' } }).next` -> unchanged contents `[{ id: 1, t: 'a' }]`
- `applyOptimistic([{ id: 1, t: 'a' }, { id: 2, t: 'b' }], { type: 'update', item: { id: 2, t: 'B' } }).next` -> `[{ id: 1, t: 'a' }, { id: 2, t: 'B' }]`
- `applyOptimistic([{ id: 1 }, { id: 2 }], { type: 'remove', item: { id: 1 } }).next` -> `[{ id: 2 }]`
- `rollback(applyOptimistic(current, edit))` -> contents equal to the original `current` snapshot.

## Acceptance Criteria

- `applyOptimistic`, `rollback`, and the `OptimisticEdit` type are exported from `@tanstack/query-core` via `packages/query-core/src/index.ts`.
- Add/update/remove behave as specified, including the no-op cases and order preservation.
- `next` and `snapshot` are new arrays; `current` is never mutated.
- `rollback` restores the pre-edit snapshot.
- The test suite is deterministic and runs fully in-process (no network, no timers, no `QueryClient`).
- The following command passes (run from the repo root):

```bash
pnpm --filter @tanstack/query-core exec vitest run src/__tests__/optimisticList.test.tsx
```
