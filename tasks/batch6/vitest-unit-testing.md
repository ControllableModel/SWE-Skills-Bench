# Task: Add a bounded LRU cache for resolver results

## Background

Vite's node layer caches many derived results during module resolution. A small, dependency-free bounded LRU cache is a useful primitive for capping memory of such caches. This task adds an `LruCache` class to the node utilities, with an eviction callback, plus a stateful test suite.

## Files to Create/Modify

- `packages/vite/src/node/lruCache.ts` (new) — the `LruCache` implementation.
- `packages/vite/src/node/__tests__/lruCache.spec.ts` (new) — a dedicated test file exercising the cache.

## Requirements

### Class shape

Export a class from `packages/vite/src/node/lruCache.ts`:

```ts
export class LruCache<K, V> {
  constructor(options: { max: number; onEvict?: (key: K, value: V) => void })
  get(key: K): V | undefined
  set(key: K, value: V): void
  has(key: K): boolean
  delete(key: K): boolean
  get size(): number
  clear(): void
}
```

### Behavior

- `set` inserts or updates a key. Re-setting an existing key updates its value and marks it most-recently-used.
- `get` returns the value (or `undefined` if absent) and, on a hit, marks the key most-recently-used.
- `has` returns whether a key is present **without** changing recency.
- When `set` would push `size` beyond `max`, the least-recently-used entry is removed first; if an `onEvict` callback was provided, it is invoked once with the evicted key and value before that entry is dropped.
- Updating an existing key (rather than inserting a new one) never triggers eviction.
- `delete(key)` removes a key, returns `true` if it was present and `false` otherwise, and does **not** invoke `onEvict`.
- `clear()` removes all entries and does **not** invoke `onEvict`.
- `size` reflects the current number of entries and never exceeds `max`.

### Edge cases

- A cache constructed with `max: 1` holds only the single most-recently-used entry.
- Reading a key with `get` protects it from being the eviction victim on the next insert.
- Using `has` to probe a key must not protect it from eviction.
- Evicting must call `onEvict` exactly once per evicted entry, in least-recently-used-first order.

### Expected Functionality

| Scenario | Outcome |
|----------|---------|
| `max:2`, set a, set b, set c | `a` evicted; `onEvict("a", ...)` called once; `size === 2` |
| `max:2`, set a, set b, get a, set c | `b` evicted (a was refreshed) |
| set then update same key on a full cache | no eviction; `size` unchanged |
| `delete` an existing key | returns `true`, no `onEvict` |

## Acceptance Criteria

- `LruCache` is exported from `packages/vite/src/node/lruCache.ts` with the shape above.
- The new test file imports `LruCache` from `../lruCache`, sets up a fresh cache and an eviction spy before each test (so tests do not share state), and asserts call counts and call arguments of the eviction callback.
- The file contains at least 12 assertions and covers all four scenarios above plus `has`-does-not-refresh and `clear`-does-not-evict.
- Every test passes when run from the repo root:

```
pnpm exec vitest run packages/vite/src/node/__tests__/lruCache.spec.ts
```

- A naive implementation (insertion-order eviction ignoring recency, calling `onEvict` on `delete`/`clear`, or letting `has` refresh recency) must fail at least one assertion.
