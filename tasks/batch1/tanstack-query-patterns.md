# Task: Add a Query-Key Relationship Utility

## Background

In the framework-agnostic core (`packages/query-core`), cached entries are identified by array-shaped keys, and many cache operations select entries by comparing a candidate key against a filter key. This task adds a small, self-contained public utility to `@tanstack/query-core` that classifies the relationship between two such keys so that callers can reason about selection scope without re-implementing the comparison logic.

## Files to Create/Modify

- `packages/query-core/src/keyRelation.ts` (new) — implementation of the new utility and its exported types.
- `packages/query-core/src/index.ts` (modify) — re-export the new function and its return type from the package entry point.
- `packages/query-core/src/__tests__/keyRelation.test.tsx` (new) — vitest suite covering the behavior described below.

## Requirements

Add a single exported function with the signature:

```ts
export type KeyRelation = 'exact' | 'ancestor' | 'descendant' | 'disjoint'

export function relateKeys(a: QueryKey, b: QueryKey): KeyRelation
```

`QueryKey` is the existing array key type already exported by the package (`ReadonlyArray<unknown>`). The function reports how `a` relates to `b`.

### Relationship semantics

For two keys `a` and `b`, the result MUST be:

- `'exact'` — `a` and `b` identify the same cache entry: they are equivalent under the package's standard serializable-key comparison.
- `'ancestor'` — `a` is a strict, broader scope that encompasses `b`. Selecting by `a` (in the non-exact sense) would include the entry identified by `b`, but `a` and `b` are not equivalent.
- `'descendant'` — `a` is a strict, narrower scope contained within `b`. This is the inverse direction of `'ancestor'` (i.e. `relateKeys(a, b) === 'descendant'` iff `relateKeys(b, a) === 'ancestor'`).
- `'disjoint'` — neither key contains or equals the other.

### Containment rules

"Contains" must follow the same partial-matching rules the cache already uses when a non-exact filter key selects entries:

- A shorter key whose elements all match the corresponding leading elements of a longer key contains the longer key. Example: `['todos']` contains `['todos', 5]`; `['todos', 5]` contains `['todos', 5, 'comments']`.
- Element comparison is structural, not reference-based. Plain-object elements are compared by checking that every property of the filter element is present and (recursively) matches in the candidate element; extra properties on the candidate element do not break the match. Example: `['todos', { status: 'done' }]` contains `['todos', { status: 'done', page: 2 }]`, but `['todos', { status: 'done' }]` does NOT contain `['todos', { status: 'open' }]`.
- Property ordering inside object elements MUST NOT affect equivalence. `['t', { a: 1, b: 2 }]` and `['t', { b: 2, a: 1 }]` are `'exact'`.
- Array nesting is supported the same way (an array element is compared element-wise against the candidate's element at that position).

### Edge cases and constraints

- An empty key `[]` is an ancestor of every non-empty key, and `relateKeys([], [])` is `'exact'`.
- Equivalent keys MUST return `'exact'`, never `'ancestor'` or `'descendant'`.
- When neither key is a prefix of the other (including the case where a shared-length element differs, e.g. `['a', 1]` vs `['a', 2]`), the result MUST be `'disjoint'`.
- Two keys of equal length that are not equivalent are `'disjoint'` (equal length rules out a strict prefix relationship).
- The function MUST be pure: it MUST NOT mutate `a` or `b`, and calling it MUST NOT require a `QueryClient`, cache, timers, network, or any running framework.
- The implementation MUST reuse the package's existing key-comparison primitives rather than introducing a divergent comparison (so that results stay consistent with how the cache selects entries).

### Expected Functionality

- `relateKeys(['todos'], ['todos'])` -> `'exact'`
- `relateKeys(['todos'], ['todos', 5])` -> `'ancestor'`
- `relateKeys(['todos', 5], ['todos'])` -> `'descendant'`
- `relateKeys(['todos', 5], ['users', 5])` -> `'disjoint'`
- `relateKeys(['todos', 5], ['todos', 6])` -> `'disjoint'`
- `relateKeys(['todos', { status: 'done' }], ['todos', { status: 'done', page: 2 }])` -> `'ancestor'`
- `relateKeys(['todos', { status: 'done', page: 2 }], ['todos', { status: 'done' }])` -> `'descendant'`
- `relateKeys(['todos', { status: 'done' }], ['todos', { status: 'open' }])` -> `'disjoint'`
- `relateKeys(['t', { a: 1, b: 2 }], ['t', { b: 2, a: 1 }])` -> `'exact'`
- `relateKeys([], ['anything'])` -> `'ancestor'`
- `relateKeys([], [])` -> `'exact'`

## Acceptance Criteria

- `relateKeys` and the `KeyRelation` type are exported from `@tanstack/query-core` via `packages/query-core/src/index.ts`.
- The function returns the correct relation for all scenarios listed above, including the structural/plain-object cases, the property-order-independent equivalence case, and the empty-key cases.
- `relateKeys(a, b) === 'ancestor'` holds if and only if `relateKeys(b, a) === 'descendant'`, for all key pairs.
- Calling `relateKeys` does not mutate either argument.
- The new test suite is deterministic and runs fully in-process (no network, no timers, no `QueryClient` instance required for the relation logic itself).
- The following command passes (run from the repo root):

```bash
pnpm --filter @tanstack/query-core exec vitest run src/__tests__/keyRelation.test.tsx
```
