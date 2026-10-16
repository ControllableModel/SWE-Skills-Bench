# Task: Add an LRU Cache to the shared package

## Background
The `shared` package in this React monorepo holds small, dependency-free utility modules (for example `objectIs.js`, `hasOwnProperty.js`) consumed across renderers. This task adds a bounded least-recently-used cache that renderers can use to retain a fixed number of recently-touched entries while evicting the stalest ones.

## Files to Create/Modify
- `packages/shared/createLRUCache.js` (new) — the LRU cache implementation.
- `packages/shared/__tests__/createLRUCache-test.js` (new) — the deterministic test suite for the cache.

## Requirements

### Public API
`createLRUCache.js` must `export default` a factory function:

```
createLRUCache(capacity)
```

- `capacity` is a positive integer: the maximum number of entries retained at once.
- The factory returns a cache object exposing exactly these methods:
  - `get(key) -> value | undefined`
  - `set(key, value) -> void`
  - `has(key) -> boolean`
  - `delete(key) -> boolean`
  - `keys() -> Array<key>` (ordered from least-recently-used to most-recently-used)
  - `size() -> number`

### Recency and eviction
- `set(key, value)` inserts or updates an entry and marks it most-recently-used.
- `get(key)` returns the value and marks that key most-recently-used; on a miss it returns `undefined` and changes nothing.
- When inserting a **new** key would exceed `capacity`, the least-recently-used entry is evicted before/at insertion so `size()` never exceeds `capacity`.
- Updating the value of an existing key must not change `size()` and must refresh that key's recency.
- `has(key)` reports membership without affecting recency.
- `delete(key)` removes the entry, returns `true` if it existed (else `false`), and a deleted key is no longer counted or eligible for eviction.
- `keys()` returns current keys ordered least- to most-recently-used.

### Validation
- If `capacity` is not a positive integer, the factory throws a `RangeError`.

### Expected Functionality
- Capacity 2: `set('a',1)`, `set('b',2)`, `set('c',3)` -> `'a'` evicted; `has('a')` is `false`; `keys()` is `['b','c']`.
- Capacity 2: `set('a',1)`, `set('b',2)`, `get('a')`, `set('c',3)` -> `'b'` evicted (because `'a'` was just used); `keys()` is `['a','c']`.
- Updating an existing key's value -> `size()` unchanged and that key becomes most-recently-used.
- `get` on a missing key -> `undefined` and no recency change.
- `delete` an existing key returns `true`; deleting it again returns `false`.

## Acceptance Criteria
- `packages/shared/createLRUCache.js` exists, exports the factory by default, and imports no other module.
- `packages/shared/__tests__/createLRUCache-test.js` exists and covers, with independent test cases, every behavior above (insertion, LRU eviction on overflow, recency refresh via `get` and via update, `has` neutrality, `delete` true/false, `keys()` ordering, `size()` bounds, and the `RangeError` for invalid capacity). The suite must assert the precise contents and ordering of `keys()` and the exact `size()` after sequences of operations, using array/value equality matchers. Tests must not depend on wall-clock timing, randomness, network, or a running server.
- The following command passes with all assertions green:

```
yarn test packages/shared/__tests__/createLRUCache-test.js
```
