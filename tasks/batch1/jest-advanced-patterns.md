# Task: Add a Deduplicating Async Resource Loader to the shared package

## Background
The `shared` package in this React monorepo holds small, dependency-free utility modules (for example `shallowEqual.js`, `objectIs.js`, `enqueueTask.js`) that are consumed across renderers. This task adds a new reusable utility that batches and de-duplicates asynchronous resource lookups so that many concurrent callers asking for the same key trigger at most one underlying fetch.

## Files to Create/Modify
- `packages/shared/createResourceLoader.js` (new) — the loader implementation.
- `packages/shared/__tests__/createResourceLoader-test.js` (new) — the deterministic test suite for the loader.

## Requirements

### Public API
`createResourceLoader.js` must `export default` a factory function:

```
createResourceLoader(fetcher)
```

- `fetcher` is a function `(key) => Promise<value>`. It is the only external dependency the loader has; the loader must never reach for timers, the network, globals, or any other module to do its work.
- The factory returns a loader object exposing exactly these methods:
  - `load(key) -> Promise<value>`
  - `peek(key) -> value | undefined`
  - `invalidate(key) -> boolean`
  - `clear() -> void`

### load(key)
- Calling `load(key)` returns a promise that resolves to the value produced by `fetcher(key)`.
- While a `load(key)` for a given key is still pending, additional `load(key)` calls for that **same** key must reuse the in-flight work: `fetcher` must be invoked at most once for that key during that window, and every concurrent caller must receive a promise that resolves to the same value.
- Once a key has resolved successfully, the value is cached: later `load(key)` calls must resolve from cache and must **not** invoke `fetcher` again.
- Keys are independent. Concurrent `load` calls for different keys must each invoke `fetcher` exactly once for their own key.
- If `fetcher(key)` rejects, the `load(key)` promise must reject with the same error, and **no** value may be cached for that key. A subsequent `load(key)` must be allowed to call `fetcher` again (the failure is not memoized).

### peek(key)
- Returns the cached value for `key` if (and only if) a successful load for that key has already resolved.
- Returns `undefined` when the key has never been loaded, is still pending, or previously failed.
- `peek` must never invoke `fetcher` and must never return a promise.

### invalidate(key)
- Removes any cached value for `key`. Returns `true` if a cached value was present and removed, otherwise `false`.
- After invalidation, the next `load(key)` must invoke `fetcher` again.
- Invalidating a key that is currently pending must not throw and must not disturb the in-flight promise; callers already awaiting it still receive the resolved value.

### clear()
- Drops all cached values. After `clear()`, `peek` returns `undefined` for every key and the next `load` of any key re-invokes `fetcher`.

### Constraints
- The module must contain no `import` of any other module and must rely solely on the injected `fetcher`.
- Argument validation: if `fetcher` is not a function, the factory must throw a `TypeError`.

### Expected Functionality
- Two concurrent `load('a')` calls, then awaiting both -> `fetcher` called once with `'a'`; both awaited results equal the fetched value.
- `load('a')` resolves, then `load('a')` again -> second call resolves from cache; `fetcher` total call count for `'a'` stays at one.
- `load('a')` and `load('b')` concurrently -> `fetcher` called once per distinct key.
- `fetcher` rejects for `'x'` -> `load('x')` rejects with that error; `peek('x')` is `undefined`; a later `load('x')` calls `fetcher` again.
- `load('a')` resolves, `invalidate('a')` returns `true`, next `load('a')` re-invokes `fetcher`; `invalidate('never')` returns `false`.
- `clear()` after several successful loads -> all `peek` calls return `undefined` and subsequent loads re-fetch.

## Acceptance Criteria
- `packages/shared/createResourceLoader.js` exists, exports the factory by default, and imports no other module.
- `packages/shared/__tests__/createResourceLoader-test.js` exists and covers, with independent test cases, every behavior listed under Requirements (concurrent de-duplication, success caching, per-key isolation, rejection propagation with no caching, `peek`, `invalidate` true/false, pending-key invalidation, `clear`, and the `TypeError` for a non-function `fetcher`). The suite must isolate the loader by supplying its own controllable `fetcher` (rather than any real async source) and must assert how many times that `fetcher` was invoked and with which arguments. Asynchronous outcomes must be asserted on the returned promises (both resolution and rejection paths). Tests must not depend on wall-clock timing, randomness, network, or a running server.
- The following command passes with all assertions green:

```
yarn test packages/shared/__tests__/createResourceLoader-test.js
```
