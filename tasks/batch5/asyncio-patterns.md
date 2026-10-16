# Task: Add an Async Result Cache with Single-Flight Deduplication

## Background

`aiohttp` clients often fetch the same key concurrently and waste work doing it
multiple times. This task adds a reusable async cache that, when many callers
request the same key at once, computes the value only once and shares the result
with all waiters.

## Files to Create/Modify

- `aiohttp/single_flight.py` (new) — an `AsyncCache` class.
- `tests/test_single_flight.py` (new) — deterministic test suite.

## Requirements

### Public API

Add to `aiohttp/single_flight.py`:

```python
class AsyncCache:
    def __init__(self) -> None: ...
    async def get(self, key, loader) -> "object": ...
    def invalidate(self, key) -> None: ...
```

- `get(key, loader)` returns the cached value for `key`. On a cache miss it calls
  `loader(key)` (which returns an awaitable), awaits it, stores the value, and
  returns it.
- `loader` is only ever invoked on a miss; a subsequent `get` for the same key
  returns the stored value without calling `loader` again.
- `invalidate(key)` removes the cached value for `key` (no error if absent); the
  next `get` for that key recomputes via `loader`.

### Single-flight behavior

- If multiple `get` calls for the **same** key happen concurrently while the value
  is still being loaded, `loader` for that key must be invoked **exactly once**, and
  all concurrent callers must receive the same resulting value.
- Concurrent `get` calls for **different** keys must be able to load in parallel
  (one slow key must not block loading of a different key).

### Error handling

- If `loader` raises while loading a key, every caller currently awaiting that key
  receives that exception, and nothing is cached for the key (a later `get` retries
  the load).

### Expected Functionality

- Scenario: 10 concurrent `get("x", loader)` where `loader` increments a counter and
  awaits -> all 10 receive the same value and the counter shows `loader` ran once.
- Scenario: `get("a", ...)` then later `get("a", ...)` (after first completes) ->
  second call does not invoke `loader`.
- Scenario: concurrent `get("a", ...)` and `get("b", ...)` with a slow loader for
  `"a"` -> `"b"` resolves without waiting for `"a"`.
- Scenario: `loader` raises for a key while 3 callers wait -> all 3 see the
  exception; a following `get` for that key calls `loader` again.
- Scenario: `invalidate("x")` after a cached load -> next `get("x", ...)` re-invokes
  `loader`.

## Acceptance Criteria

- `aiohttp.single_flight.AsyncCache` is importable.
- Concurrent same-key loads collapse to a single `loader` invocation; all waiters
  get the same value.
- Different-key loads proceed in parallel; cache hits skip `loader`.
- A failing load propagates to all current waiters and caches nothing.
- `invalidate` forces recomputation on the next access.
- The following command passes:

```bash
python -m pytest tests/test_single_flight.py -v
```
