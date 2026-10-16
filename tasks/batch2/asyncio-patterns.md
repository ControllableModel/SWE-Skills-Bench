# Task: Add a Concurrency-Limited Async Task Pool

## Background

The `aiohttp` package keeps small async helper modules alongside its core code
(for example `aiohttp/tcp_helpers.py` and helpers inside `aiohttp/helpers.py`).
This task adds a reusable task-pool utility that lets a caller submit many
coroutine-producing jobs while never letting more than a fixed number run at the
same time.

## Files to Create/Modify

- `aiohttp/task_pool.py` (new) — a `TaskPool` class.
- `tests/test_task_pool.py` (new) — deterministic test suite for the pool.

## Requirements

### Public API

Add a class `TaskPool` to `aiohttp/task_pool.py` usable as an async context manager:

```python
class TaskPool:
    def __init__(self, max_concurrency: int) -> None: ...
    async def __aenter__(self) -> "TaskPool": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    def submit(self, coro) -> "object": ...   # returns a handle that is awaitable
    async def join(self) -> list: ...          # wait for all submitted work, return results in submission order
```

- `max_concurrency` is a positive integer; a value `<= 0` must raise `ValueError`
  from `__init__`.
- `submit(coro)` accepts an already-created coroutine object, schedules it under
  the pool's concurrency cap, and returns a handle. Awaiting the handle yields
  that job's return value (or re-raises its exception).
- `join()` waits for every submitted job to finish and returns a list of their
  results **in the order the jobs were submitted**, regardless of completion order.

### Concurrency behavior

- At no instant may more than `max_concurrency` submitted coroutines be actively
  running (between their first suspension and completion).
- When more jobs are submitted than `max_concurrency`, a finishing job must
  immediately free a slot for the next waiting job (no fixed-size batching).

### Lifecycle and cleanup

- On normal `__aexit__`, the pool waits for all outstanding jobs to complete.
- If the `async with` body raises, `__aexit__` must cancel any jobs that have not
  yet completed before propagating, leaving no job still running afterwards.

### Edge cases

- Submitting nothing and then exiting the context must complete cleanly.
- `submit` called after the context has exited must raise `RuntimeError`.

### Expected Functionality

- Scenario: submit 8 jobs each recording the live running count, `max_concurrency=3`
  -> observed peak running count equals exactly 3.
- Scenario: submit jobs that return `i*i` for `i` in `0..5` and call `join()`
  -> returns `[0, 1, 4, 9, 16, 25]` in submission order even if later jobs finish first.
- Scenario: a job raises inside the `async with` body -> remaining unfinished jobs
  are cancelled and the original exception propagates.
- Scenario: `TaskPool(0)` -> raises `ValueError`.

## Acceptance Criteria

- `aiohttp.task_pool.TaskPool` is importable and works as an async context manager.
- Peak simultaneous running jobs never exceeds `max_concurrency`; with 8 jobs and
  cap 3 the observed peak is exactly 3.
- `join()` returns results positionally aligned with submission order.
- Exiting the context on error cancels unfinished jobs; `submit` after exit raises
  `RuntimeError`; `TaskPool(0)` raises `ValueError`.
- The following command passes:

```bash
python -m pytest tests/test_task_pool.py -v
```
