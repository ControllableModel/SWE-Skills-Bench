# Task: Build a Stock Price Rolling-Window Analytics Module

## Background
The pandas repository keeps small, self-contained utilities under `scripts/`, each paired with a deterministic test in `scripts/tests/`. This task adds a utility that computes rolling-window technical indicators and per-symbol returns from a daily price log.

## Files to Create/Modify
- `scripts/price_analytics.py` (new) — the analytics module described below.
- `scripts/tests/test_price_analytics.py` (new) — the deterministic test suite for the module.

The module must `import pandas as pd` and operate purely in-process (no files, network, or external services).

## Requirements

The module exposes the following public functions. They must work for arbitrary inputs satisfying the stated contracts, not just the examples below.

### `daily_returns(prices)`
- `prices` has columns: `symbol` (str), `date` (string parseable as a date), `close` (float).
- For each `symbol`, sorted by `date` ascending, compute the simple daily return: `(close - prev_close) / prev_close`, where `prev_close` is the previous day's close **for the same symbol**.
- Return a copy of `prices` (same row count, same rows) with an added `daily_return` column. The first observed row of each symbol has a missing `daily_return` (no prior close). Returns must never bleed across symbols.
- Output sorted by `symbol` then `date` ascending, index reset to `0..n-1`.
- The caller's `prices` object must not be mutated.

### `moving_average(prices, window)`
Given `prices` and an integer `window >= 1`, return a copy with an added `ma` column: the trailing rolling mean of `close` over `window` rows, computed **independently per symbol** (sorted by date). The first `window - 1` rows of each symbol are missing. Output sorted by `symbol` then `date`, index reset. Input must not be mutated.

### `max_drawdown(prices)`
Return a frame with columns `symbol` and `max_drawdown`: for each symbol (sorted by date) the most negative value of `(close - running_max) / running_max`, where `running_max` is the cumulative maximum close up to and including that row. A symbol whose price never falls below its running max has `max_drawdown == 0.0`. Sorted by `symbol`, index reset to `0..n-1`. Input must not be mutated.

### Expected Functionality
- daily_returns with closes `[100, 110]` for one symbol -> second row `0.1`, first row missing.
- daily_returns with two interleaved symbols -> returns computed per symbol, never crossing.
- moving_average with `window=2` over `[10, 20, 30]` -> `[NaN, 15, 25]`.
- max_drawdown over closes `[100, 80, 120]` -> `-0.2` (the dip to 80 from a running max of 100).

## Acceptance Criteria
- `scripts/price_analytics.py` defines `daily_returns`, `moving_average`, and `max_drawdown` with the behavior above.
- All per-symbol computations are isolated; no value bleeds between symbols.
- Rolling/return leading positions are correctly missing.
- All functions leave their inputs unmodified.
- The following command passes from the repository root:

```
python -m pytest scripts/tests/test_price_analytics.py -q
```
