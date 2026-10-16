# Task: Add an Async Retry-with-Backoff Wrapper

## Background

`aiohttp` clients frequently need to retry transient failures. This task adds a
reusable async retry helper to the package so callers can wrap any coroutine
factory with bounded retries and deterministic, injectable delays.

## Files to Create/Modify

- `aiohttp/retry.py` (new) — an async `retry` coroutine function.
- `tests/test_retry.py` (new) — deterministic test suite.

## Requirements

### Public API

Add to `aiohttp/retry.py`:

```python
async def retry(factory, *, attempts, retry_on=(Exception,), backoff=None, sleep=None):
    ...
```

- `factory` is a zero-argument callable that returns a fresh awaitable each time
  it is called (`factory()` must be re-callable; the same awaitable is never reused).
- `attempts` is the maximum number of times `factory()` is invoked; it must be an
  integer `>= 1`, otherwise raise `ValueError`.
- `retry_on` is a tuple of exception types that are considered retryable.
- `backoff` is an optional callable mapping the zero-based attempt index to a delay
  in seconds (`backoff(0)` is the wait before the 2nd attempt, etc.). If `None`, the
  delay is always `0`.
- `sleep` is an optional async delay function (defaults to `asyncio.sleep`); it is
  awaited between attempts so tests may inject a recorder.

### Behavior

- On the first successful awaitable, `retry` returns its value immediately and does
  not call `factory` again.
- If an awaitable raises an exception that is an instance of one of `retry_on` and
  attempts remain, `retry` awaits `sleep(backoff(i))` (with `i` the zero-based index
  of the just-failed attempt) and then calls `factory()` again.
- If the final allowed attempt still fails with a retryable exception, that last
  exception propagates to the caller.
- An exception NOT matching `retry_on` propagates immediately with no further
  attempts and no sleep.

### Edge cases

- `attempts == 1` means `factory()` is called exactly once and any failure
  propagates without sleeping.
- The number of `sleep` calls is always exactly the number of failed attempts that
  were followed by a retry (i.e. failures minus the terminal failure when exhausted).

### Expected Functionality

- Scenario: `factory` fails twice with a retryable error then succeeds, `attempts=5`
  -> returns the success value; `factory` called 3 times; `sleep` called twice.
- Scenario: `factory` always raises a retryable error, `attempts=3` -> the third
  failure propagates; `factory` called 3 times; `sleep` called twice.
- Scenario: `factory` raises a non-retryable error on the first try -> it propagates
  immediately; `factory` called once; `sleep` never called.
- Scenario: `backoff=lambda i: i * 0.5` with two failures -> `sleep` receives `0.0`
  then `0.5` in that order.
- Scenario: `attempts=0` -> raises `ValueError` before calling `factory`.

## Acceptance Criteria

- `aiohttp.retry.retry` is importable and is a coroutine function.
- Successful awaitables short-circuit; retryable failures trigger exactly the right
  number of `factory` and `sleep` calls with the documented backoff arguments.
- Non-retryable exceptions propagate immediately without sleeping.
- `attempts < 1` raises `ValueError`.
- The following command passes:

```bash
python -m pytest tests/test_retry.py -v
```
