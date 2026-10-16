# Task: Build a Sensor Time-Series Resampling Module

## Background

This repository (`pola-rs/polars`) ships runnable examples under `examples/`. We need a self-contained time-series module in that area that resamples irregular sensor readings into fixed time buckets and computes gap and rolling statistics an operations dashboard would display. The module operates purely in-memory and depends only on the `polars` package the repository builds.

## Files to Create/Modify

- `examples/sensor_series/__init__.py` - package marker (new)
- `examples/sensor_series/series.py` - the time-series module implementing the public functions below (new)
- `examples/sensor_series/test_series.py` - pytest suite exercising the module (new)

## Requirements

### Module Inputs

Functions accept a single `polars.DataFrame` named `readings` and return a `polars.DataFrame`. The `readings` columns are:

- `ts` (`pl.Datetime`) — reading timestamp (microsecond or millisecond precision); not guaranteed sorted
- `sensor` (String) — sensor id
- `value` (Float64) — measured value

### `hourly_mean(readings: pl.DataFrame) -> pl.DataFrame`

For each `sensor`, bucket readings into fixed **1-hour** windows aligned to the top of the hour (e.g. a reading at `10:37` belongs to the `10:00` bucket) and report the mean `value` per bucket. Output columns in this exact order: `sensor` (String), `bucket` (`pl.Datetime`, the truncated hour start), `mean_value` (Float64), `n` (Int64/UInt32 count of readings in the bucket). Only buckets that actually contain at least one reading appear. Output sorted by `sensor` ascending, then `bucket` ascending.

### `add_gap_seconds(readings: pl.DataFrame) -> pl.DataFrame`

Return every input row plus a column `gap_s` (Int64), the number of **whole seconds** between this reading's `ts` and the previous reading's `ts` **for the same sensor**, in ascending `ts` order. The first (earliest) reading of each sensor has `gap_s = null`. Output sorted by `sensor` ascending, then `ts` ascending; all original columns preserved.

### `daily_value_range(readings: pl.DataFrame) -> pl.DataFrame`

For each `sensor` and each calendar **day** (the date part of `ts`), report columns in this exact order: `sensor` (String), `day` (`pl.Date`), `value_range` (Float64 — max `value` minus min `value` within that sensor-day). Only sensor-days containing at least one reading appear. Output sorted by `sensor` ascending, then `day` ascending.

### Expected Functionality

- Two readings at `10:05` and `10:50` for the same sensor land in one `10:00` bucket with `n=2` and the mean of their values.
- A reading at `11:01` for that sensor produces a separate `11:00` bucket.
- `add_gap_seconds` gives `null` for the first reading of each sensor and the correct whole-second difference for subsequent ones, computed per sensor regardless of input row order.
- Two sensors never contaminate each other's buckets, gaps, or daily ranges.
- A sensor-day with a single reading has `value_range = 0.0`.
- Empty `readings` input — every function returns an empty DataFrame with the correct columns and dtypes rather than raising.

## Acceptance Criteria

- `hourly_mean`, `add_gap_seconds`, and `daily_value_range` exist in `examples/sensor_series/series.py` with the signatures above and return `polars.DataFrame` objects.
- `hourly_mean` groups readings into top-of-hour buckets per sensor and reports per-bucket mean and count, omitting empty buckets.
- `add_gap_seconds` computes per-sensor whole-second deltas in timestamp order with `null` for each sensor's first reading, independent of input ordering.
- `daily_value_range` computes max-minus-min per sensor per calendar day.
- All grouping is isolated per sensor with no cross-sensor leakage.
- All functions return correctly-shaped empty results on empty input.
- The following command passes from the repository root:

  ```bash
  python -m pytest examples/sensor_series/test_series.py -q
  ```
