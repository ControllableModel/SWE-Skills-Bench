# Task: Build an Inventory Ledger Window-Analytics Module

## Background

This repository (`pola-rs/polars`) ships runnable examples under `examples/`. We need a self-contained ledger-analytics module in that area that turns a flat stream of stock movements into per-product running balances and rankings that a warehouse team would inspect. The module operates purely in-memory and depends only on the `polars` Python package the repository builds.

## Files to Create/Modify

- `examples/inventory_ledger/__init__.py` - package marker (new)
- `examples/inventory_ledger/ledger.py` - the analytics module implementing the public functions below (new)
- `examples/inventory_ledger/test_ledger.py` - pytest suite exercising the module (new)

## Requirements

### Module Inputs

All functions accept a single `polars.DataFrame` named `movements` and return a `polars.DataFrame`. The `movements` columns are:

- `seq` (Int64) — global, strictly increasing event sequence number (unique across the whole frame)
- `product` (String) — product code
- `warehouse` (String) — warehouse code
- `delta` (Int64) — signed quantity change (positive = received, negative = shipped)

The input rows are **not** guaranteed to be sorted.

### `running_balance(movements: pl.DataFrame) -> pl.DataFrame`

Return every input row (same `seq` set) plus one added column `balance` (Int64), where `balance` is the cumulative sum of `delta` **within the same `product`**, accumulated in ascending `seq` order. The cumulative total must restart at zero for each distinct `product` and must not leak across products. Output rows must be sorted by `product` ascending, then `seq` ascending. All original columns are preserved.

### `movement_rank(movements: pl.DataFrame) -> pl.DataFrame`

Return one row per `(product, seq)` with columns in this exact order: `product`, `seq`, `delta`, `abs_rank` (UInt32 or Int64). `abs_rank` is the dense rank of the movement's absolute `delta` magnitude **within its product**, where the largest magnitude gets rank `1`. Ties on magnitude receive the same rank, and the next distinct magnitude continues at the next integer (no gaps). Output sorted by `product` ascending, then `abs_rank` ascending, then `seq` ascending.

### `warehouse_share(movements: pl.DataFrame) -> pl.DataFrame`

Return every input row plus a column `received_share` (Float64). Consider only rows with `delta > 0` ("receipts") when forming the denominator: `received_share` is the row's `delta` divided by the total of all positive `delta` values **in the same `warehouse`**. Rows whose `delta <= 0` must have `received_share = 0.0`. A warehouse with no positive receipts at all yields `0.0` for every one of its rows (never a division-by-zero error or `NaN`). Output sorted by `warehouse` ascending, then `seq` ascending; all original columns preserved.

### Expected Functionality

- A product with movements `+5, -2, +3` (in `seq` order) yields `balance` values `5, 3, 6`.
- Two products interleaved by `seq` keep independent running balances.
- Within one product, two movements of magnitude `4` share the same `abs_rank`, and the next smaller magnitude gets the immediately following rank integer.
- A warehouse with receipts `2` and `6` gives `received_share` of `0.25` and `0.75` for those rows and `0.0` for any shipment rows.
- A warehouse containing only shipments (`delta <= 0`) yields `received_share = 0.0` for all its rows.
- An empty `movements` input — every function returns an empty DataFrame with the correct columns and dtypes rather than raising.

## Acceptance Criteria

- `running_balance`, `movement_rank`, and `warehouse_share` exist in `examples/inventory_ledger/ledger.py` with the signatures above and return `polars.DataFrame` objects.
- `balance` is a per-product cumulative sum ordered by `seq`, restarting at zero per product, with no cross-product leakage.
- `abs_rank` is a per-product dense ranking of `|delta|` with the largest magnitude as rank `1` and no gaps for ties.
- `received_share` divides each receipt by its warehouse's total receipts, assigns `0.0` to non-receipt rows, and never produces `NaN` or raises for receipt-free warehouses.
- All functions return correctly-shaped empty results on empty input.
- The following command passes from the repository root:

  ```bash
  python -m pytest examples/inventory_ledger/test_ledger.py -q
  ```
