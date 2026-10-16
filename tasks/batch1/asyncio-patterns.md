# Task: Add a Bounded-Concurrency Coroutine Mapper Helper

## Background

The `aiohttp` framework exposes a number of small reusable utilities in `aiohttp/helpers.py` (for example timeout handling, future result/exception setters, and context managers). This task adds a new general-purpose utility that runs many coroutines for a collection of inputs while keeping only a limited number of them in flight at once.

## Files to Create/Modify

- `aiohttp/helpers.py` (modify) — add a new public coroutine function `map_concurrent`.
- `tests/test_map_concurrent.py` (new) — deterministic test suite for the new helper.

## Requirements

### Public API

Add a single new coroutine function to `aiohttp/helpers.py`:

```python
async def map_concurrent(func, items, *, limit, return_exceptions=False):
    ...
```

- `func` is a callable that accepts exactly one argument (an item) and returns an awaitable (i.e. `func(item)` is a coroutine/awaitable).
- `items` is an iterable of input values. It must be fully materialized before any work starts (accept any iterable, not only sequences).
- `limit` is a positive integer giving the maximum number of `func` invocations that may be **in progress simultaneously**.
- The function returns a `list` of results, **one entry per input item, in the same order as `items`** — regardless of the order in which individual awaitables finish.

### Concurrency behavior

- At no point may the number of simultaneously in-progress `func` invocations exceed `limit`.
- When there are more items than `limit`, work must proceed concurrently: as soon as one in-progress invocation finishes, the next pending item must be started (the function must not process items in lock-step batches of size `limit`, nor strictly one at a time).
- If `limit` is greater than or equal to the number of items, all invocations may run at once.

### Result ordering

- Result at index `i` of the returned list must correspond to `items[i]`, even though the underlying awaitables may complete out of order.

### Input validation

- A `limit` that is not a positive integer (e.g. `0`, a negative number) must raise `ValueError` before any item is processed.

### Empty input

- An empty `items` iterable returns an empty list and never calls `func`.

### Error handling

- When `return_exceptions=False` (the default) and one invocation raises, `map_concurrent` propagates that exception to its caller, and it must not leave other started invocations running in the background after it returns: any still-pending invocations it started must be cancelled before the exception propagates out.
- When `return_exceptions=True`, an invocation that raises must not abort the others. Instead, the raised exception object is placed in the result list at that item's position, while successful invocations keep their normal return values. The output remains positionally aligned with `items`.

### Expected Functionality

- Scenario: `func` squares a number, `items=[1,2,3,4]`, `limit=2` -> returns `[1, 4, 9, 16]` and never more than 2 invocations run at once.
- Scenario: 6 items, `limit=2`, each invocation awaits and records the peak number of concurrently-running invocations -> the observed peak equals 2 (not 1, not 6).
- Scenario: `func` raises for one specific item, `return_exceptions=False` -> the call raises that exception, and any other invocations that were still pending are cancelled rather than left running.
- Scenario: `func` raises for one specific item, `return_exceptions=True` -> the result list has the exception object at that item's index and correct values elsewhere.
- Scenario: `limit=0` -> raises `ValueError` and `func` is never called.
- Scenario: `items=[]` -> returns `[]` and `func` is never called.

## Acceptance Criteria

- `aiohttp.helpers.map_concurrent` is importable and is a coroutine function.
- A call with `limit=2` over 6 items where each invocation tracks the live count observes a maximum concurrency of exactly `2`.
- Results are always positionally aligned with the input order, independent of completion order.
- `return_exceptions=False` re-raises the first failure and cancels the invocations it had started that were still pending; `return_exceptions=True` returns exception objects in-place.
- Invalid `limit` raises `ValueError`; empty input returns `[]` without invoking `func`.
- The following command passes:

```bash
python -m pytest tests/test_map_concurrent.py -v
```
