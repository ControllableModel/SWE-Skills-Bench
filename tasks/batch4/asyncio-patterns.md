# Task: Add an Async Producer/Consumer Pipeline Runner

## Background

`aiohttp` processes streams of work items (requests, chunks, messages). This task
adds a small, reusable producer/consumer pipeline utility built on an internal
async queue so callers can feed items in and have a fixed pool of workers process
them concurrently.

## Files to Create/Modify

- `aiohttp/pipeline.py` (new) — a `run_pipeline` coroutine function.
- `tests/test_pipeline.py` (new) — deterministic test suite.

## Requirements

### Public API

Add to `aiohttp/pipeline.py`:

```python
async def run_pipeline(items, worker, *, workers, queue_size=0):
    ...
```

- `items` is an iterable of input values fed to the workers.
- `worker` is a callable taking one item and returning an awaitable that produces a
  result for that item.
- `workers` is the number of concurrent consumer tasks; it must be `>= 1`, else
  raise `ValueError`.
- `queue_size` bounds the internal queue (`0` means unbounded). When the queue is
  bounded and full, the producer must wait rather than overflow.
- Returns a `dict` mapping each input item to its worker result. (Items are assumed
  hashable and unique.)

### Concurrency behavior

- At most `workers` consumer coroutines may be processing items at any instant.
- Items are distributed across workers; total processed equals the number of inputs,
  each exactly once.
- The function returns only after every queued item has been fully processed.

### Error handling

- If any `worker` invocation raises, `run_pipeline` stops feeding new items,
  cancels the remaining in-flight and idle worker tasks, and propagates the first
  exception. It must not hang and must leave no worker task running.

### Edge cases

- Empty `items` returns an empty dict and starts no meaningful work.
- `workers` greater than the number of items is allowed (extra workers stay idle and
  shut down cleanly).

### Expected Functionality

- Scenario: `items=range(10)`, `worker` returns `x*10`, `workers=4` -> returns
  `{0:0, 1:10, ..., 9:90}` and at no point do more than 4 workers run concurrently.
- Scenario: each worker records the live worker count; with `workers=3` and 12 items
  the observed peak equals exactly 3.
- Scenario: `queue_size=1` with a slow consumer -> the producer never enqueues more
  than 1 pending item beyond what workers hold.
- Scenario: one item's `worker` raises -> the call raises that exception and all
  worker tasks are cancelled/finished (no lingering tasks).
- Scenario: `workers=0` -> raises `ValueError`.

## Acceptance Criteria

- `aiohttp.pipeline.run_pipeline` is importable and is a coroutine function.
- All inputs are processed exactly once and mapped to their results.
- Peak concurrent workers never exceeds `workers`; with 12 items and 3 workers the
  peak is exactly 3.
- A worker exception cancels remaining tasks and propagates; no task is left running.
- `workers < 1` raises `ValueError`; empty input returns `{}`.
- The following command passes:

```bash
python -m pytest tests/test_pipeline.py -v
```
