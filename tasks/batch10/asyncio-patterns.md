# Task: Add an Async Circuit Breaker

## Background

When an `aiohttp` client repeatedly calls a failing dependency, it should stop
hammering it and fail fast for a while. This task adds a reusable async circuit
breaker with an injectable clock so its open/half-open/closed transitions are
deterministically testable.

## Files to Create/Modify

- `aiohttp/circuit_breaker.py` (new) — a `CircuitBreaker` class and a
  `CircuitOpenError` exception.
- `tests/test_circuit_breaker.py` (new) — deterministic test suite.

## Requirements

### Public API

Add to `aiohttp/circuit_breaker.py`:

```python
class CircuitOpenError(Exception):
    ...

class CircuitBreaker:
    def __init__(self, *, failure_threshold, reset_timeout, time_func=None) -> None: ...
    async def call(self, factory) -> "object": ...
    @property
    def state(self) -> str: ...   # one of "closed", "open", "half_open"
```

- `failure_threshold` is the number of consecutive failures that trips the breaker
  to `open` (`>= 1`, else `ValueError`).
- `reset_timeout` is the number of seconds the breaker stays `open` before allowing a
  trial call (`> 0`, else `ValueError`).
- `time_func` is a zero-arg callable returning "now" as a float (defaults to
  `asyncio.get_event_loop().time`); injectable for tests.
- `call(factory)` invokes `factory()` (returns an awaitable), awaits it, and returns
  its result on success.

### State machine

- The breaker starts `closed`. In `closed` state, calls are executed normally. A
  successful call resets the consecutive-failure count to `0`.
- Each consecutive failed call increments the failure count; reaching
  `failure_threshold` transitions the breaker to `open`.
- While `open`, any `call` is rejected immediately by raising `CircuitOpenError`
  without invoking `factory` — until `reset_timeout` seconds (per `time_func`) have
  elapsed since it opened.
- After `reset_timeout` elapses, the next `call` is allowed through in a `half_open`
  trial: if it succeeds, the breaker returns to `closed` and the failure count
  resets; if it fails, the breaker returns to `open` and the timer restarts.

### Edge cases

- A successful call in `closed` state after some (sub-threshold) failures clears the
  accumulated failure count.
- The exception raised by `factory` in `closed`/`half_open` state propagates to the
  caller (the breaker records the failure but does not swallow the error).

### Expected Functionality

- Scenario: `failure_threshold=3`; 2 failures then a success -> breaker stays
  `closed` and failure count is cleared.
- Scenario: 3 consecutive failures -> breaker becomes `open`; the next `call` raises
  `CircuitOpenError` and `factory` is not invoked.
- Scenario: while `open`, advance `time_func` past `reset_timeout`, then call with a
  succeeding `factory` -> the call goes through (half-open trial) and the breaker
  returns to `closed`.
- Scenario: half-open trial fails -> breaker returns to `open` and again fast-fails
  until the timeout elapses again.
- Scenario: `failure_threshold=0` or `reset_timeout=0` -> raises `ValueError`.

## Acceptance Criteria

- `aiohttp.circuit_breaker.CircuitBreaker` and `CircuitOpenError` are importable.
- The breaker follows the closed -> open -> half_open -> closed/open transitions
  driven by consecutive failures and the injectable clock.
- In `open` state `factory` is never invoked and `CircuitOpenError` is raised until
  `reset_timeout` elapses.
- Underlying failures propagate in closed/half-open; a success clears the count.
- Invalid constructor arguments raise `ValueError`.
- The following command passes:

```bash
python -m pytest tests/test_circuit_breaker.py -v
```
