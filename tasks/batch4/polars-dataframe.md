# Task: Build an Order-Fulfillment Reconciliation Module

## Background

This repository (`pola-rs/polars`) ships runnable examples under `examples/`. We need a self-contained reconciliation module in that area that compares placed orders against shipment and catalog records to find what was fulfilled, what is missing, and what was shipped but never ordered. The module operates purely in-memory and depends only on the `polars` package the repository builds.

## Files to Create/Modify

- `examples/order_recon/__init__.py` - package marker (new)
- `examples/order_recon/recon.py` - the reconciliation module implementing the public functions below (new)
- `examples/order_recon/test_recon.py` - pytest suite exercising the module (new)

## Requirements

### Module Inputs

All functions accept `polars.DataFrame` inputs and return a `polars.DataFrame`. Three input shapes are used:

- `orders` columns: `order_id` (Int64, unique), `sku` (String), `qty_ordered` (Int64)
- `shipments` columns: `order_id` (Int64), `qty_shipped` (Int64)
- `catalog` columns: `sku` (String, unique), `product_name` (String), `unit_price` (Float64)

### `enrich_orders(orders: pl.DataFrame, catalog: pl.DataFrame) -> pl.DataFrame`

Return every order with catalog details attached, columns in this exact order: `order_id`, `sku`, `qty_ordered`, `product_name` (String), `line_total` (Float64). `line_total` is `qty_ordered * unit_price`. An order whose `sku` is absent from `catalog` must still appear, with `product_name = null` and `line_total = null` (do not drop it, do not treat the price as zero). Output sorted by `order_id` ascending.

### `unshipped_orders(orders: pl.DataFrame, shipments: pl.DataFrame) -> pl.DataFrame`

Return the subset of `orders` (all original columns of `orders`, unchanged) whose `order_id` does **not** appear anywhere in `shipments`. No shipment columns are added. Output sorted by `order_id` ascending. If every order has at least one shipment, return an empty DataFrame with the `orders` columns.

### `fulfillment_status(orders: pl.DataFrame, shipments: pl.DataFrame) -> pl.DataFrame`

Return one row per `order_id` from `orders`, columns in this exact order: `order_id`, `qty_ordered`, `qty_shipped_total` (Int64), `status` (String). `qty_shipped_total` is the sum of `qty_shipped` across all matching shipment rows for that order (an order with no shipments gets `0`, never `null`). `status` is:

- `"complete"` when `qty_shipped_total >= qty_ordered` and `qty_shipped_total > 0`
- `"partial"` when `0 < qty_shipped_total < qty_ordered`
- `"pending"` when `qty_shipped_total == 0`

Output sorted by `order_id` ascending.

### `orphan_shipments(orders: pl.DataFrame, shipments: pl.DataFrame) -> pl.DataFrame`

Return the subset of `shipments` (all original `shipments` columns) whose `order_id` has **no** matching row in `orders`. Output sorted by `order_id` ascending, then preserving original relative order for equal `order_id`.

### Expected Functionality

- An order with a `sku` missing from `catalog` survives `enrich_orders` with `null` name and `null` line total.
- An order with no shipment row appears in `unshipped_orders` and gets `status="pending"`, `qty_shipped_total=0` in `fulfillment_status`.
- An order with two partial shipments summing to its `qty_ordered` is `"complete"`.
- A shipment whose `order_id` is not in `orders` appears in `orphan_shipments`.
- Empty inputs — every function returns an empty DataFrame with the correct columns and dtypes rather than raising.

## Acceptance Criteria

- `enrich_orders`, `unshipped_orders`, `fulfillment_status`, and `orphan_shipments` exist in `examples/order_recon/recon.py` with the signatures above and return `polars.DataFrame` objects.
- `enrich_orders` keeps unmatched orders with null catalog fields and computes `line_total` only where a price exists.
- `unshipped_orders` and `orphan_shipments` each return exactly the rows present in one frame but absent (by `order_id`) from the other, without adding columns from the other frame.
- `fulfillment_status` sums shipped quantity per order (0 when none) and assigns the three statuses by the stated thresholds.
- All functions return correctly-shaped empty results on empty input.
- The following command passes from the repository root:

  ```bash
  python -m pytest examples/order_recon/test_recon.py -q
  ```
