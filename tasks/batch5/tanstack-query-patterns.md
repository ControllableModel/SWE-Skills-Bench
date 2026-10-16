# Task: Add an Infinite-Query Page Accumulator

## Background

In the framework-agnostic core (`packages/query-core`), an infinite query keeps a list of fetched pages together with the page parameter used for each, and computes the parameter for the next page from the most recently fetched page. This task adds a self-contained public utility to `@tanstack/query-core` that appends a newly fetched page to an accumulated infinite-data structure and derives the next page parameter.

## Files to Create/Modify

- `packages/query-core/src/pageAccumulator.ts` (new) — implementation of the accumulator and its exported types.
- `packages/query-core/src/index.ts` (modify) — re-export the new function and its types from the package entry point.
- `packages/query-core/src/__tests__/pageAccumulator.test.tsx` (new) — vitest suite covering the behavior described below.

## Requirements

Add a single exported function with the signature:

```ts
export interface AccumulatedPages<TPage, TParam> {
  pages: Array<TPage>
  pageParams: Array<TParam>
}

export interface AppendPageInput<TPage, TParam> {
  current: AccumulatedPages<TPage, TParam>
  page: TPage
  param: TParam
  getNextPageParam: (
    lastPage: TPage,
    allPages: Array<TPage>,
    lastPageParam: TParam,
    allPageParams: Array<TParam>,
  ) => TParam | undefined | null
}

export function appendPage<TPage, TParam>(
  input: AppendPageInput<TPage, TParam>,
): {
  next: AccumulatedPages<TPage, TParam>
  nextPageParam: TParam | undefined
  hasNextPage: boolean
}
```

The function appends `page`/`param` to the accumulated data and computes the parameter for the following page.

### Accumulation semantics

- `next.pages` is `current.pages` with `page` appended at the end; `next.pageParams` is `current.pageParams` with `param` appended at the end, kept index-aligned.
- `nextPageParam` is the result of calling `getNextPageParam` with the newly appended page as `lastPage`, the full `next.pages` as `allPages`, `param` as `lastPageParam`, and the full `next.pageParams` as `allPageParams`.
- `hasNextPage` is `true` when `nextPageParam` is neither `null` nor `undefined`, and `false` otherwise.
- When `getNextPageParam` returns `null` or `undefined`, `nextPageParam` MUST be normalized to `undefined`.

### Edge cases and constraints

- Appending the first page to an empty accumulator (`{ pages: [], pageParams: [] }`) yields a one-page result and still computes `nextPageParam` from that page.
- The function MUST NOT mutate `current` or its arrays — it returns new arrays (the caller relies on referential change to detect updates).
- `getNextPageParam` is invoked exactly once per call.
- The function MUST be pure aside from the single `getNextPageParam` call, and MUST NOT require a `QueryClient`, cache, timers, network, or framework.

### Expected Functionality

- Appending `page` `{ items: ['a'], cursor: 2 }` with `param` `1` to an empty accumulator, where `getNextPageParam` returns `lastPage.cursor`, yields `pages: [{ items: ['a'], cursor: 2 }]`, `pageParams: [1]`, `nextPageParam: 2`, `hasNextPage: true`.
- When `getNextPageParam` returns `undefined`, `hasNextPage` is `false` and `nextPageParam` is `undefined`.
- When `getNextPageParam` returns `null`, the result normalizes `nextPageParam` to `undefined` and `hasNextPage` is `false`.
- `current` and its `pages`/`pageParams` arrays are not mutated (verified by identity/length checks after the call).

## Acceptance Criteria

- `appendPage` and the `AccumulatedPages` type are exported from `@tanstack/query-core` via `packages/query-core/src/index.ts`.
- The function correctly appends, index-aligns, computes `nextPageParam`, normalizes `null`/`undefined`, and sets `hasNextPage`.
- The original accumulator is never mutated.
- The test suite is deterministic and runs fully in-process (no network, no timers, no `QueryClient`).
- The following command passes (run from the repo root):

```bash
pnpm --filter @tanstack/query-core exec vitest run src/__tests__/pageAccumulator.test.tsx
```
