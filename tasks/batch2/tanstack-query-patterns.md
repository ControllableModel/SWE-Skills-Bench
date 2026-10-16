# Task: Add a Prefix-Based Cache Key Selector

## Background

In the framework-agnostic core (`packages/query-core`), bulk cache operations select many cached entries at once by matching their array-shaped keys against a single filter key. This task adds a self-contained public utility to `@tanstack/query-core` that, given a filter key and a collection of candidate keys, returns the subset of candidates that the filter would select, in both broad (prefix) and strict (exact) modes.

## Files to Create/Modify

- `packages/query-core/src/selectKeys.ts` (new) — implementation of the new selector and its exported types.
- `packages/query-core/src/index.ts` (modify) — re-export the new function from the package entry point.
- `packages/query-core/src/__tests__/selectKeys.test.tsx` (new) — vitest suite covering the behavior described below.

## Requirements

Add a single exported function with the signature:

```ts
export interface SelectKeysOptions {
  exact?: boolean
}

export function selectKeys(
  filter: QueryKey,
  candidates: ReadonlyArray<QueryKey>,
  options?: SelectKeysOptions,
): Array<QueryKey>
```

`QueryKey` is the existing array key type already exported by the package. The function returns the subset of `candidates` (preserving their original order) that the `filter` selects.

### Selection semantics

- In the default (broad) mode, a candidate is selected when `filter` matches it as a leading-scope filter: every element of `filter` matches the corresponding leading element of the candidate, using the same structural partial-matching the cache uses for non-exact selection. A shorter filter therefore selects every candidate it is a prefix of. Example: filter `['todos']` selects `['todos']`, `['todos', 5]`, and `['todos', 5, 'comments']`.
- Object elements are matched structurally: every property listed in the filter element must be present and (recursively) match in the candidate element; extra properties on the candidate do not break the match, and property ordering is irrelevant. Example: filter `['todos', { status: 'done' }]` selects `['todos', { status: 'done', page: 2 }]` but not `['todos', { status: 'open' }]`.
- When `options.exact` is `true`, a candidate is selected only when it is equivalent to `filter` under the package's stable, order-independent key equivalence (so `['t', { a: 1, b: 2 }]` is selected by exact filter `['t', { b: 2, a: 1 }]`).

### Edge cases and constraints

- An empty filter `[]` in broad mode selects every candidate; in exact mode it selects only candidates equal to `[]`.
- Result order MUST match the input order of `candidates`; duplicates in `candidates` are each independently included if they match.
- The function MUST be pure: it MUST NOT mutate its inputs and MUST NOT require a `QueryClient`, cache, timers, network, or any running framework.
- The implementation MUST reuse the package's existing key-comparison primitives so that broad selection stays consistent with how the cache selects entries by prefix and exact selection stays consistent with the stable key hash.

### Expected Functionality

- `selectKeys(['todos'], [['todos'], ['todos', 5], ['users', 5]])` -> `[['todos'], ['todos', 5]]`
- `selectKeys(['todos', 5], [['todos'], ['todos', 5], ['todos', 5, 'comments']])` -> `[['todos', 5], ['todos', 5, 'comments']]`
- `selectKeys(['todos'], candidates, { exact: true })` selects only candidates equivalent to `['todos']`.
- `selectKeys(['t', { b: 2, a: 1 }], [['t', { a: 1, b: 2 }]], { exact: true })` -> `[['t', { a: 1, b: 2 }]]`
- `selectKeys([], anyCandidates)` -> all candidates (broad mode).

## Acceptance Criteria

- `selectKeys` and `SelectKeysOptions` are exported from `@tanstack/query-core` via `packages/query-core/src/index.ts`.
- Broad-mode selection matches the prefix/structural scenarios above; exact-mode selection matches only stable-equivalent keys.
- Returned arrays preserve input order and include duplicates that match.
- Calling `selectKeys` does not mutate the filter or any candidate.
- The test suite is deterministic and runs fully in-process (no network, no timers, no `QueryClient`).
- The following command passes (run from the repo root):

```bash
pnpm --filter @tanstack/query-core exec vitest run src/__tests__/selectKeys.test.tsx
```
