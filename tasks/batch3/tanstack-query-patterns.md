# Task: Add a Freshness Classifier for Cached Entries

## Background

In the framework-agnostic core (`packages/query-core`), a cached entry is considered "fresh" for a configurable window after it was last updated, and "stale" thereafter; consumers use this to decide whether a background refetch is needed. This task adds a self-contained public utility to `@tanstack/query-core` that classifies the freshness of an entry given when it was last updated, the configured freshness window, and the current time.

## Files to Create/Modify

- `packages/query-core/src/freshness.ts` (new) — implementation of the classifier and its exported types.
- `packages/query-core/src/index.ts` (modify) — re-export the new function and its return type from the package entry point.
- `packages/query-core/src/__tests__/freshness.test.tsx` (new) — vitest suite covering the behavior described below.

## Requirements

Add a single exported function with the signature:

```ts
export type Freshness = 'fresh' | 'stale'

export interface FreshnessInput {
  updatedAt: number          // epoch ms the entry was last updated
  staleTime?: number         // ms the entry stays fresh after updatedAt
  now: number                // current epoch ms
}

export function classifyFreshness(input: FreshnessInput): {
  status: Freshness
  msUntilStale: number
}
```

The function reports whether the entry is currently fresh and how many milliseconds remain before it becomes stale.

### Classification semantics

- The entry is `'fresh'` while `now` is strictly before `updatedAt + staleTime`, and `'stale'` once `now` reaches or passes that boundary.
- `msUntilStale` is the non-negative number of milliseconds from `now` until the entry becomes stale; once stale it MUST be exactly `0` (never negative).
- A missing or `0` `staleTime` means the entry is stale immediately at or after `updatedAt` (the default "refetch on mount" behavior): with `staleTime` omitted, an entry is `'fresh'` only when `now < updatedAt`.
- A `staleTime` of `Infinity` means the entry is always `'fresh'`; in that case `msUntilStale` MUST be `Infinity`.

### Edge cases and constraints

- Exactly at the boundary (`now === updatedAt + staleTime`) the entry is `'stale'` and `msUntilStale` is `0`.
- A `now` earlier than `updatedAt` (clock skew) MUST still yield a non-negative `msUntilStale` consistent with the fresh window.
- A negative `staleTime` MUST be treated as `0` (no fresh window).
- The function MUST be pure: it MUST NOT read the real clock itself (it uses the provided `now`), MUST NOT mutate its input, and MUST NOT require a `QueryClient`, cache, timers, network, or framework.

### Expected Functionality

- `classifyFreshness({ updatedAt: 1000, staleTime: 5000, now: 3000 })` -> `{ status: 'fresh', msUntilStale: 3000 }`
- `classifyFreshness({ updatedAt: 1000, staleTime: 5000, now: 6000 })` -> `{ status: 'stale', msUntilStale: 0 }`
- `classifyFreshness({ updatedAt: 1000, staleTime: 5000, now: 6000 })` boundary is inclusive-stale.
- `classifyFreshness({ updatedAt: 1000, now: 500 })` -> `{ status: 'fresh', msUntilStale: 500 }` (no staleTime, now before updatedAt).
- `classifyFreshness({ updatedAt: 1000, staleTime: Infinity, now: 9_999_999 })` -> `{ status: 'fresh', msUntilStale: Infinity }`.

## Acceptance Criteria

- `classifyFreshness` and the `Freshness` type are exported from `@tanstack/query-core` via `packages/query-core/src/index.ts`.
- The function returns the correct status and `msUntilStale` for the fresh, stale, boundary, no-staleTime, infinite, and clock-skew cases.
- `msUntilStale` is never negative.
- Calling `classifyFreshness` does not mutate its input or read the real clock.
- The test suite is deterministic and runs fully in-process (no network, no timers, no `QueryClient`).
- The following command passes (run from the repo root):

```bash
pnpm --filter @tanstack/query-core exec vitest run src/__tests__/freshness.test.tsx
```
