# Task: Build a Deferred Log-Query Engine

## Background

This repository (`pola-rs/polars`) ships runnable examples under `examples/`. We need a self-contained query module in that area that answers questions over potentially large CSV access logs without materializing the whole file. The module reads a CSV path lazily, applies row/column reductions, and only then produces a small in-memory result. It depends only on the `polars` package the repository builds.

## Files to Create/Modify

- `examples/log_query/__init__.py` - package marker (new)
- `examples/log_query/engine.py` - the query module implementing the public functions below (new)
- `examples/log_query/test_engine.py` - pytest suite exercising the module (new)

## Requirements

### CSV Shape

Each function accepts a `csv_path: str` pointing at a CSV with header columns:

- `ts` (parsed as Int64 — epoch seconds)
- `endpoint` (String)
- `status` (Int64 — HTTP status code)
- `latency_ms` (Int64)
- `bytes` (Int64)

The CSV may be far larger than memory in principle; the implementation must avoid loading unneeded columns and rows into a full eager frame. Tests will write small CSVs to a temporary directory and pass their paths.

### `slow_error_endpoints(csv_path: str, min_latency: int) -> pl.DataFrame`

Return a `polars.DataFrame` with columns, in this exact order: `endpoint` (String), `error_count` (Int64/UInt32). Consider only rows where `status >= 500` **and** `latency_ms >= min_latency`. Group the surviving rows by `endpoint` and count them as `error_count`. Only the `status`, `latency_ms`, and `endpoint` columns are relevant; the `ts` and `bytes` columns must never influence the result. Output sorted by `error_count` descending, then `endpoint` ascending. If no row survives, return an empty DataFrame with those two columns.

### `endpoint_latency_stats(csv_path: str) -> pl.DataFrame`

Return one row per `endpoint` with columns in this exact order: `endpoint` (String), `requests` (Int64/UInt32), `p_max_latency` (Int64), `avg_latency` (Float64). `requests` is the count of all rows for that endpoint, `p_max_latency` is the maximum `latency_ms`, and `avg_latency` is the mean `latency_ms`. Output sorted by `endpoint` ascending.

### `total_bytes_after(csv_path: str, after_ts: int) -> int`

Return a single Python `int`: the sum of the `bytes` column over rows whose `ts > after_ts`. If no row qualifies, return `0`. Only the `ts` and `bytes` columns are relevant to this computation.

### Expected Functionality

- A CSV containing a `status=500, latency_ms=300` row on `/a` and a `status=200` row on `/a` — `slow_error_endpoints(path, 100)` reports `/a` with `error_count=1` (the 200 is excluded).
- A `status=503` row with `latency_ms` below `min_latency` is excluded from `slow_error_endpoints`.
- `endpoint_latency_stats` reports `requests`, max, and mean per endpoint regardless of status.
- `total_bytes_after(path, t)` sums `bytes` strictly after `t` and returns `0` when nothing qualifies.
- Endpoints and rows excluded by a filter never appear in or affect any aggregate.

## Acceptance Criteria

- `slow_error_endpoints`, `endpoint_latency_stats`, and `total_bytes_after` exist in `examples/log_query/engine.py` with the signatures above.
- The module reads the CSV through a deferred (non-eager) path so that column and row reductions are expressed before the result is materialized; tests confirm correct results when only a subset of columns/rows is needed.
- `slow_error_endpoints` applies both the status and latency conditions, counts per endpoint, sorts as specified, and returns the correct empty shape when nothing matches.
- `endpoint_latency_stats` returns count, max, and mean latency per endpoint sorted by endpoint.
- `total_bytes_after` returns a plain Python `int` and `0` when no row qualifies.
- The following command passes from the repository root:

  ```bash
  python -m pytest examples/log_query/test_engine.py -q
  ```
