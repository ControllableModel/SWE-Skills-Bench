# Task: Add a Mutation Filter Matcher

## Background

In the framework-agnostic core (`packages/query-core`), pending changes (mutations) are identified by an optional array-shaped key and have a lifecycle status, and consumers select subsets of them with filters by key (broad or exact) and by status. This task adds a self-contained public utility to `@tanstack/query-core` that selects the mutations matching a given filter.

## Files to Create/Modify

- `packages/query-core/src/mutationFilter.ts` (new) — implementation of the matcher and its exported types.
- `packages/query-core/src/index.ts` (modify) — re-export the new function and its types from the package entry point.
- `packages/query-core/src/__tests__/mutationFilter.test.tsx` (new) — vitest suite covering the behavior described below.

## Requirements

Add a single exported function with the signature:

```ts
export type MutationStatus = 'idle' | 'pending' | 'success' | 'error'

export interface MutationRecord {
  mutationKey?: QueryKey
  status: MutationStatus
}

export interface MutationFilter {
  mutationKey?: QueryKey
  exact?: boolean
  status?: MutationStatus
}

export function selectMutations<T extends MutationRecord>(
  filter: MutationFilter,
  mutations: ReadonlyArray<T>,
): Array<T>
```

`QueryKey` is the existing array key type already exported by the package. The function returns the subset of `mutations` (preserving input order) that satisfy every present filter criterion.

### Matching semantics

- If `filter.mutationKey` is provided:
  - A mutation with no `mutationKey` MUST NOT match.
  - In broad mode (default), the mutation matches when `filter.mutationKey` is a structural leading-scope match of the mutation's key (same partial-matching the cache uses; shorter filter keys match by prefix, object elements match by subset, property order irrelevant).
  - In exact mode (`exact: true`), the mutation matches only when its key is equivalent to `filter.mutationKey` under the package's stable, order-independent key equivalence.
- If `filter.status` is provided, the mutation's `status` MUST equal it.
- Criteria combine with AND: a mutation matches only if every provided criterion matches. A filter with no criteria matches all mutations.

### Edge cases and constraints

- A filter `{ mutationKey: ['todo'] }` matches mutations whose key starts with `['todo']` (e.g. `['todo', 5]`) in broad mode, but `{ mutationKey: ['todo'], exact: true }` does not match `['todo', 5]`.
- Status-only filters ignore keys entirely.
- Result order MUST match input order; duplicates are each independently included if they match.
- The function MUST be pure: it MUST NOT mutate inputs and MUST NOT require a `QueryClient`, mutation cache, timers, network, or framework.
- The implementation MUST reuse the package's existing key-comparison primitives for both broad and exact key matching.

### Expected Functionality

- `selectMutations({ status: 'pending' }, mutations)` -> only the `'pending'` mutations, in order.
- `selectMutations({ mutationKey: ['todo'] }, [{ mutationKey: ['todo', 5], status: 'idle' }])` -> matches (broad prefix).
- `selectMutations({ mutationKey: ['todo'], exact: true }, [{ mutationKey: ['todo', 5], status: 'idle' }])` -> empty (not exact).
- `selectMutations({ mutationKey: ['todo'] }, [{ status: 'idle' }])` -> empty (mutation has no key).
- `selectMutations({ mutationKey: ['todo'], status: 'pending' }, mutations)` -> only mutations matching BOTH key and status.
- `selectMutations({}, mutations)` -> all mutations.

## Acceptance Criteria

- `selectMutations`, `MutationFilter`, and `MutationRecord` are exported from `@tanstack/query-core` via `packages/query-core/src/index.ts`.
- Broad/exact key matching, status matching, and AND-combination all behave as specified, including the no-key and status-only cases.
- Result order matches input order.
- Calling the function does not mutate its inputs.
- The test suite is deterministic and runs fully in-process (no network, no timers, no `QueryClient`).
- The following command passes (run from the repo root):

```bash
pnpm --filter @tanstack/query-core exec vitest run src/__tests__/mutationFilter.test.tsx
```
