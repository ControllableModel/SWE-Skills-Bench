# Task: Add a recursive object-key sorter for config serialization

## Background

Vite's node utilities in `packages/vite/src/node/utils.ts` already expose `sortObjectKeys`, which sorts only the top-level keys of a plain object. When serializing nested config objects deterministically (for caching and snapshotting), nested keys must also be sorted. This task adds a recursive variant together with a focused, table-driven test suite.

## Files to Create/Modify

- `packages/vite/src/node/utils.ts` (modify) — add and export a new function `sortObjectKeysDeep`.
- `packages/vite/src/node/__tests__/sortObjectKeysDeep.spec.ts` (new) — a dedicated test file exercising the new function.

## Requirements

### Function signature

Add an exported function:

```ts
export function sortObjectKeysDeep<T>(value: T): T
```

It returns a structurally-equal value whose every plain-object's keys are ordered ascending by the default string sort, recursively at every nesting depth.

### Behavior and constraints

- For a plain object, the result is a new object whose own enumerable keys appear in ascending sorted order; each value is itself recursively processed.
- For an array, the result is a new array of the same length and element order (array element order is preserved — only object keys are reordered), with each element recursively processed.
- Primitive values (string, number, boolean, `null`, `undefined`) are returned unchanged.
- The function must be pure: it must not mutate its input at any depth, and the returned object must not share object/array references with the input.
- Key ordering for objects must match the order produced by `Object.keys(obj).sort()`.
- Non-plain objects such as `Date`, `RegExp`, and `Map` instances must be returned as-is (same reference), not copied or descended into.

### Edge cases

- An empty object returns a new empty object.
- An array of objects sorts each object's keys but keeps the array order intact.
- Deeply nested objects (at least three levels) are sorted at every level.
- A value that is `null` is returned as `null` (not treated as an object).

### Expected Functionality

| Input | Resulting top-level key order |
|-------|-------------------------------|
| `{ b: 1, a: 2 }` | `["a", "b"]` |
| `{ z: { y: 1, x: 2 } }` | top: `["z"]`, nested: `["x", "y"]` |
| `[{ b: 1, a: 2 }]` | array length 1, element keys `["a", "b"]` |

## Acceptance Criteria

- `sortObjectKeysDeep` is exported from `packages/vite/src/node/utils.ts` with the signature above.
- The new test file imports `sortObjectKeysDeep` from `../utils` and uses a `test.each` (or `it.each`) table to drive at least 6 distinct input/expected pairs, plus separate assertions for: input immutability (the original object's key order is unchanged after the call), reference non-sharing for the returned object, `null`/primitive pass-through, and `Date`/`RegExp` pass-through by reference.
- The file contains at least 10 assertions total.
- Every test passes when run from the repo root:

```
pnpm exec vitest run packages/vite/src/node/__tests__/sortObjectKeysDeep.spec.ts
```

- A naive implementation (only sorting the top level, mutating the input, or descending into `Date`/`RegExp`) must fail at least one assertion.
