# Task: Add a Bounded Page Window Manager for Infinite Queries

## Background

In the framework-agnostic core (`packages/query-core`), an infinite query can keep at most a bounded number of pages in memory; when a new page is fetched in a direction and the bound is exceeded, the oldest page from the opposite end is dropped so the window stays a fixed size. This task adds a self-contained public utility to `@tanstack/query-core` that maintains such a bounded page window in either fetch direction.

## Files to Create/Modify

- `packages/query-core/src/pageWindow.ts` (new) — implementation of the window manager and its exported types.
- `packages/query-core/src/index.ts` (modify) — re-export the new function and its types from the package entry point.
- `packages/query-core/src/__tests__/pageWindow.test.tsx` (new) — vitest suite covering the behavior described below.

## Requirements

Add a single exported function with the signature:

```ts
export type FetchDirection = 'forward' | 'backward'

export interface PageWindowInput<TItem> {
  items: ReadonlyArray<TItem>
  item: TItem
  direction: FetchDirection
  maxPages?: number
}

export function pushBounded<TItem>(input: PageWindowInput<TItem>): Array<TItem>
```

The function inserts `item` at the appropriate end of `items` and trims the window to `maxPages` if needed.

### Window semantics

- `direction: 'forward'` appends `item` to the END of `items`. If, after appending, the length exceeds `maxPages`, the FIRST element is dropped so the result length equals `maxPages`.
- `direction: 'backward'` prepends `item` to the START of `items`. If, after prepending, the length exceeds `maxPages`, the LAST element is dropped so the result length equals `maxPages`.
- `maxPages` of `0`, `undefined`, or any value `<= 0` means "no limit": the item is added (appended or prepended) and nothing is trimmed.
- The function MUST return a new array; it MUST NOT mutate `items`.

### Edge cases and constraints

- Adding to an empty list returns a one-element list regardless of `maxPages`.
- When the list is already at `maxPages`, a forward push drops exactly one element from the front and a backward push drops exactly one element from the back, keeping length at `maxPages`.
- When the list is below `maxPages`, no trimming occurs.
- The function MUST be pure and MUST NOT require a `QueryClient`, cache, timers, network, or framework.

### Expected Functionality

- `pushBounded({ items: [1, 2], item: 3, direction: 'forward' })` -> `[1, 2, 3]` (no limit)
- `pushBounded({ items: [1, 2, 3], item: 4, direction: 'forward', maxPages: 3 })` -> `[2, 3, 4]`
- `pushBounded({ items: [1, 2, 3], item: 0, direction: 'backward', maxPages: 3 })` -> `[0, 1, 2]`
- `pushBounded({ items: [], item: 9, direction: 'forward', maxPages: 3 })` -> `[9]`
- `pushBounded({ items: [1, 2], item: 3, direction: 'forward', maxPages: 0 })` -> `[1, 2, 3]`
- `pushBounded({ items: [1, 2], item: 3, direction: 'backward', maxPages: 5 })` -> `[3, 1, 2]` (below limit, no trim)

## Acceptance Criteria

- `pushBounded` and the `FetchDirection` type are exported from `@tanstack/query-core` via `packages/query-core/src/index.ts`.
- Forward/backward insertion, bounded trimming from the correct end, and the no-limit cases all behave as specified.
- The result is always a new array and `items` is never mutated.
- The test suite is deterministic and runs fully in-process (no network, no timers, no `QueryClient`).
- The following command passes (run from the repo root):

```bash
pnpm --filter @tanstack/query-core exec vitest run src/__tests__/pageWindow.test.tsx
```
