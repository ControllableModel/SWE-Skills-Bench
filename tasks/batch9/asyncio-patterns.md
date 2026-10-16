# Task: Add an Async Background Task Supervisor

## Background

Long-running `aiohttp` servers spawn background tasks (periodic jobs, broadcast
loops) that must be tracked and shut down cleanly. This task adds a reusable
supervisor that owns a set of background tasks, keeps references so they are not
garbage-collected, and shuts them all down deterministically.

## Files to Create/Modify

- `aiohttp/supervisor.py` (new) — a `TaskSupervisor` class.
- `tests/test_supervisor.py` (new) — deterministic test suite.

## Requirements

### Public API

Add to `aiohttp/supervisor.py`:

```python
class TaskSupervisor:
    def __init__(self) -> None: ...
    def spawn(self, coro, *, name=None) -> "object": ...   # returns the created task
    def active_count(self) -> int: ...
    async def shutdown(self, *, timeout=None) -> None: ...
    async def __aenter__(self) -> "TaskSupervisor": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
```

### Behavior

- `spawn(coro, name=...)` schedules `coro` as a background task, retains a strong
  reference to it, and returns the task. The supervisor must hold the reference until
  the task finishes (so it is never garbage-collected mid-flight).
- `active_count()` returns the number of currently-unfinished spawned tasks.
- A task that finishes on its own (normally or with an exception) is automatically
  removed from the active set; its reference is dropped so it can be collected.
- `shutdown()` cancels all still-active tasks, waits for them to finish handling the
  cancellation, and returns once none remain active. If `timeout` is given and some
  task does not stop within it, `shutdown` raises `asyncio.TimeoutError` (and the
  supervisor still considers them no longer its responsibility).
- Using the supervisor as an async context manager calls `shutdown()` on exit,
  including when the body raises (the body's exception still propagates after
  shutting tasks down).

### Error containment

- An exception raised inside a spawned background task must not crash the supervisor
  or other tasks; it is retained so `shutdown` does not deadlock. (Tests may inspect
  that the task ended with that exception via the returned task object.)

### Edge cases

- `shutdown()` on a supervisor with no active tasks completes immediately.
- Calling `shutdown()` twice is safe; the second call is a no-op.

### Expected Functionality

- Scenario: spawn 3 tasks that each sleep, check `active_count()` -> returns `3`
  while they run.
- Scenario: a spawned task returns quickly -> shortly after, `active_count()` drops
  and the supervisor no longer holds it.
- Scenario: spawn long-running tasks then `shutdown()` -> all are cancelled and
  `active_count()` becomes `0`.
- Scenario: a spawned task raises -> the supervisor stays usable and `shutdown()`
  still completes; the task object reports the exception.
- Scenario: `async with TaskSupervisor()` whose body raises -> active tasks are shut
  down and the body's exception propagates.

## Acceptance Criteria

- `aiohttp.supervisor.TaskSupervisor` is importable and usable as an async context
  manager.
- Spawned tasks are tracked (strong reference held until done) and auto-removed on
  completion; `active_count()` reflects unfinished tasks.
- `shutdown()` cancels and drains all active tasks to a count of `0`; `timeout`
  enforcement raises `asyncio.TimeoutError`; double-shutdown is safe.
- A background task exception does not break the supervisor.
- The following command passes:

```bash
python -m pytest tests/test_supervisor.py -v
```
