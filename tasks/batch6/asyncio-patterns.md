# Task: Add an Async Token-Bucket Rate Limiter

## Background

`aiohttp` clients calling external services need to cap their request rate. This
task adds a reusable async rate limiter built on a token-bucket model with an
injectable clock so its timing behavior is deterministically testable.

## Files to Create/Modify

- `aiohttp/rate_limit.py` (new) — a `TokenBucket` class.
- `tests/test_rate_limit.py` (new) — deterministic test suite.

## Requirements

### Public API

Add to `aiohttp/rate_limit.py`:

```python
class TokenBucket:
    def __init__(self, rate, capacity, *, time_func=None, sleep=None) -> None: ...
    async def acquire(self, tokens: int = 1) -> None: ...
    async def __aenter__(self) -> "TokenBucket": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
```

- `rate` is tokens refilled per second (`> 0`, else `ValueError`).
- `capacity` is the maximum number of tokens the bucket can hold (`>= 1`, else
  `ValueError`). The bucket starts full.
- `time_func` is a zero-arg callable returning a monotonically increasing float
  "now" (defaults to `asyncio.get_event_loop().time`); injectable for tests.
- `sleep` is an async delay function (defaults to `asyncio.sleep`); injectable so a
  test can record requested sleep durations without real waiting.
- `acquire(tokens)` removes `tokens` from the bucket, waiting (via `sleep`) until
  enough tokens are available based on the elapsed time reported by `time_func`.
- Using the limiter as an async context manager acquires exactly one token on entry.

### Behavior

- Tokens regenerate continuously at `rate` per second since the last update, capped
  at `capacity` (never exceeding it).
- If the bucket already holds at least `tokens`, `acquire` returns immediately and
  does not call `sleep`.
- If it holds fewer than `tokens`, `acquire` must wait for the exact time needed to
  accumulate the shortfall before consuming them; the requested wait is computed as
  `shortfall / rate`.
- Requesting more than `capacity` tokens in a single `acquire` raises `ValueError`.

### Edge cases

- Tokens never accumulate above `capacity` no matter how much time passes between
  calls.
- `acquire(0)` returns immediately and consumes nothing.

### Expected Functionality

- Scenario: full bucket of capacity 5, first `acquire(1)` -> returns at once, no
  `sleep`; bucket now holds ~4.
- Scenario: empty the bucket then `acquire(1)` with `rate=2` and no advancing clock
  -> `sleep` is requested with `0.5` seconds.
- Scenario: advance `time_func` by 10 seconds with `rate=1, capacity=3` -> available
  tokens are capped at 3, not 10.
- Scenario: `acquire(capacity + 1)` -> raises `ValueError`.
- Scenario: `TokenBucket(rate=0, capacity=5)` -> raises `ValueError`.

## Acceptance Criteria

- `aiohttp.rate_limit.TokenBucket` is importable and usable as an async context
  manager that takes one token on entry.
- Available tokens are computed from elapsed `time_func` and never exceed `capacity`.
- Sufficient tokens -> no `sleep`; insufficient -> `sleep` requested with the exact
  `shortfall / rate` seconds.
- Invalid `rate`/`capacity` and over-capacity acquires raise `ValueError`.
- The following command passes:

```bash
python -m pytest tests/test_rate_limit.py -v
```
