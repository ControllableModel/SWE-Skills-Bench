# Task: Add a Cancellation-Safe Async Timeout Guard

## Background

`aiohttp` already deals with deadlines around network operations. This task adds a
small, reusable timeout-guard async context manager that bounds the runtime of an
arbitrary block of async code and guarantees the inner work is cancelled cleanly
when the deadline is exceeded.

## Files to Create/Modify

- `aiohttp/timeout_guard.py` (new) — a `timeout_after` async context manager.
- `tests/test_timeout_guard.py` (new) — deterministic test suite.

## Requirements

### Public API

Add to `aiohttp/timeout_guard.py`:

```python
def timeout_after(delay):
    """Return an async context manager bounding the enclosed block to `delay` seconds."""
```

The returned object is used as:

```python
async with timeout_after(0.05) as guard:
    await some_work()
```

- `delay` is a non-negative number of seconds. A negative `delay` raises
  `ValueError`. `delay is None` means no timeout (the block runs unbounded).
- If the enclosed block completes before the deadline, control leaves the
  `async with` normally and `guard.expired` is `False`.
- If the deadline is reached while the block is still running, the block's currently
  awaiting operation must be cancelled and the context manager must raise
  `asyncio.TimeoutError` to the caller, with `guard.expired` set to `True`.

### Cancellation guarantees

- When the timeout fires, any coroutine started/awaited inside the block must be
  cancelled (receive `CancelledError`) rather than continue running in the
  background after the `async with` exits.
- A `CancelledError` originating from the inner work because of the timeout must be
  surfaced to the caller as `asyncio.TimeoutError`, not as a bare `CancelledError`.
- If the caller's own task is cancelled from outside (not by this guard), that
  cancellation must propagate as `CancelledError` (it must NOT be masked as a
  `TimeoutError`).

### Edge cases

- `delay == 0` with a block that awaits anything must time out.
- `delay is None` must never time out, even for long-running inner work.

### Expected Functionality

- Scenario: block sleeps 0.01s inside `timeout_after(1.0)` -> completes normally,
  `guard.expired` is `False`.
- Scenario: block sleeps 1.0s inside `timeout_after(0.02)` -> raises
  `asyncio.TimeoutError`, `guard.expired` is `True`, and the inner sleep was cancelled.
- Scenario: inner block launches a child task and the timeout fires -> the child
  task ends cancelled, not still running, after the context exits.
- Scenario: `timeout_after(-1)` -> raises `ValueError`.
- Scenario: `timeout_after(None)` around a 0.05s sleep -> completes normally.

## Acceptance Criteria

- `aiohttp.timeout_guard.timeout_after` is importable and usable as an async context
  manager exposing an `expired` attribute.
- Work finishing in time leaves `expired == False`; exceeding the deadline raises
  `asyncio.TimeoutError`, sets `expired == True`, and cancels the inner work.
- External cancellation is not converted into `TimeoutError`.
- Negative `delay` raises `ValueError`; `None` disables the timeout.
- The following command passes:

```bash
python -m pytest tests/test_timeout_guard.py -v
```
