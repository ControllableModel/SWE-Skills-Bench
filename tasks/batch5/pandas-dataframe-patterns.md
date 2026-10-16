# Task: Build an Inventory Pivot and Cross-Tab Module

## Background
The pandas repository keeps small, self-contained utilities under `scripts/`, each paired with a deterministic test in `scripts/tests/`. This task adds a utility that reshapes a long inventory-movement log into wide pivot reports.

## Files to Create/Modify
- `scripts/inventory_pivot.py` (new) — the reshaping module described below.
- `scripts/tests/test_inventory_pivot.py` (new) — the deterministic test suite for the module.

The module must `import pandas as pd` and operate purely in-process (no files, network, or external services).

## Requirements

The module exposes the following public functions. They must work for arbitrary inputs satisfying the stated contracts, not just the examples below.

### `quantity_by_warehouse_product(movements)`
- `movements` has columns: `warehouse` (str), `product` (str), `direction` (str, either `"in"` or `"out"`), `quantity` (int).
- Return a wide table with one row per `warehouse` and one column per `product`, whose cell is the **net** quantity for that pair: sum of `quantity` where `direction == "in"` minus sum where `direction == "out"`.
- Any `(warehouse, product)` pair that never appears must show `0`, not a missing value (the result must contain no missing values).
- Row index is `warehouse`; columns are the distinct `product` values. Index and columns sorted ascending.
- The caller's `movements` object must not be mutated.

### `direction_counts(movements)`
Return a cross-tabulation counting rows: one row per `warehouse`, columns `in` and `out`, each cell the number of movement rows of that direction for that warehouse. Missing combinations are `0`. Input must not be mutated.

### `top_product_per_warehouse(movements)`
Return a frame with columns `warehouse` and `product`, giving for each warehouse the product with the greatest net quantity (as defined in `quantity_by_warehouse_product`). Ties are broken by choosing the alphabetically smallest `product`. The result has one row per warehouse, sorted by `warehouse` ascending, with the index reset to `0..n-1`. Input must not be mutated.

### Expected Functionality
- quantity_by_warehouse_product with `in 10`, `out 3` for `(W1, A)` -> cell value `7`.
- a `(warehouse, product)` pair that never appears -> cell `0`, no missing values.
- direction_counts -> integer counts per direction per warehouse, missing combinations `0`.
- top_product_per_warehouse with net `{A: 5, B: 5}` for `W1` -> picks `A` (tie broken alphabetically).

## Acceptance Criteria
- `scripts/inventory_pivot.py` defines `quantity_by_warehouse_product`, `direction_counts`, and `top_product_per_warehouse` with the behavior above.
- Pivot/cross-tab outputs contain no missing values; absent combinations are `0`.
- `top_product_per_warehouse` returns one row per warehouse with deterministic tie-breaking.
- All functions leave their inputs unmodified.
- The following command passes from the repository root:

```
python -m pytest scripts/tests/test_inventory_pivot.py -q
```
