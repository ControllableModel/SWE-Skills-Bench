# Task: Build a Sensor Time-Series Resampling Module

## Background
The pandas repository keeps small, self-contained utilities under `scripts/`, each paired with a deterministic test in `scripts/tests/`. This task adds a utility that turns irregular sensor readings into regular, gap-free time series.

## Files to Create/Modify
- `scripts/sensor_resample.py` (new) — the resampling module described below.
- `scripts/tests/test_sensor_resample.py` (new) — the deterministic test suite for the module.

The module must `import pandas as pd` and operate purely in-process (no files, network, or external services).

## Requirements

The module exposes the following public functions. They must work for arbitrary inputs satisfying the stated contracts, not just the examples below.

### `to_hourly(readings)`
Aggregate irregular per-event readings into regular hourly buckets.

- `readings` has columns: `timestamp` (string parseable as a datetime, e.g. `2023-01-01 00:30:00`), `sensor_id` (str), `value` (float).
- Consider only one `sensor_id` per call is NOT assumed; aggregation is across all rows by hour bucket.
- Return a frame indexed by **every hour** from the floor of the earliest timestamp to the floor of the latest timestamp inclusive, with no gaps, containing two columns: `reading_count` (number of readings in that hour) and `mean_value` (mean of `value` in that hour).
- Hours within the range that contain no readings must be present with `reading_count == 0` and a missing `mean_value`.
- The index must be a sorted, regular hourly DatetimeIndex with one entry per hour in the full range.
- The caller's `readings` object must not be mutated.

### `fill_gaps(hourly)`
Given the output of `to_hourly`, return a copy in which the `mean_value` series has its interior gaps filled by linear interpolation over time, so that any missing value that lies strictly between two present values is replaced with a time-proportional interpolated value.
- Missing values at the very start (before the first present value) must be back-filled from the first present value; missing values at the very end must be forward-filled from the last present value, so the result has no missing `mean_value`.
- `reading_count` must be left unchanged.
- The function must not mutate its input.

### `rolling_average(hourly, window)`
Given an hourly frame (as from `to_hourly`) and an integer `window >= 1`, return a copy adding a `rolling_mean` column: the trailing rolling mean of `mean_value` over `window` hours. The first `window - 1` positions (which lack a full window) must be missing. Input must not be mutated.

### Expected Functionality
- to_hourly over readings at `00:10`, `00:50`, `02:05` -> three hourly rows (00:00, 01:00, 02:00); the 01:00 row has `reading_count == 0` and missing `mean_value`.
- fill_gaps with means `[10.0, NaN, 20.0]` over consecutive hours -> middle becomes `15.0`.
- fill_gaps with a missing value at the leading edge -> filled from the first present value.
- rolling_average with `window=2` -> first row missing, second row is the mean of the first two.

## Acceptance Criteria
- `scripts/sensor_resample.py` defines `to_hourly`, `fill_gaps`, and `rolling_average` with the behavior above.
- `to_hourly` produces a contiguous hourly index with no missing hours and empty hours flagged by `reading_count == 0`.
- `fill_gaps` leaves no missing `mean_value`.
- All functions leave their inputs unmodified.
- The following command passes from the repository root:

```
python -m pytest scripts/tests/test_sensor_resample.py -q
```
