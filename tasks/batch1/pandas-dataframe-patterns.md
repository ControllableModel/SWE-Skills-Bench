# Task: Build a Sales Reporting Module

## Background
The pandas repository keeps a collection of small, self-contained maintenance and reporting utilities under `scripts/`, each paired with a deterministic test in `scripts/tests/`. This task adds a new reporting utility that turns raw order records into a set of summary reports for downstream consumption.

## Files to Create/Modify
- `scripts/sales_report.py` (new) — the reporting module described below.
- `scripts/tests/test_sales_report.py` (new) — the deterministic test suite for the module.

The module must `import pandas as pd` and operate purely in-process (no files, network, or external services).

## Requirements

The module exposes the following public functions. All functions accept and return `pandas` objects and must work for arbitrary inputs that satisfy the stated contracts, not just the examples below.

### `enrich_orders(orders, customers)`
Combine an order-level table with a customer reference table.

- `orders` has columns: `order_id` (int), `customer_id` (int), `region` (str), `order_date` (string in `YYYY-MM-DD` form), `units` (int), `unit_price` (float). Some `unit_price` values may be missing.
- `customers` has columns: `customer_id` (int), `segment` (str). Each `customer_id` appears at most once.
- Return a new table that is `orders` with a `segment` column attached for the matching `customer_id`.
- The attachment must be a left-side enrichment: every input order row must be present exactly once in the output, with the same `order_id` set and the same number of rows as `orders`. Orders whose `customer_id` has no match in `customers` must still appear, with a missing `segment`.
- If the customer reference table contains a duplicated `customer_id`, the function must raise an error rather than silently multiplying order rows.
- The output must add a `revenue` column equal to `units * unit_price` (computed before any missing-price handling described below; rows with a missing `unit_price` therefore have a missing `revenue`).
- The input `orders` object passed by the caller must not be mutated.

### `fill_prices(orders)`
Return a copy of an enriched order table in which missing `unit_price` values are imputed, so the result has no missing prices.

- Missing prices are filled with the median `unit_price` **within the same `region`**. Use the per-region median computed from the rows that do have a price.
- After filling, the `revenue` column must be recomputed so it is consistent with the filled prices (`units * unit_price`) and contains no missing values.
- A region for which every price is missing is out of scope and will not be tested.
- The function must not mutate its input.

### `region_segment_summary(orders)`
Produce an aggregated summary, one row per `(region, segment)` combination present in the data.

- Columns of the result: `region`, `segment`, `total_revenue` (sum of `revenue`), `total_units` (sum of `units`), `order_count` (number of distinct `order_id`), `avg_unit_price` (mean of `unit_price`).
- The result must be a flat table (a plain integer-indexed frame with the grouping keys as ordinary columns), sorted by `region` then `segment` in ascending order, with the index reset to `0..n-1`.
- Input must not be mutated.

### `revenue_pivot(orders)`
Produce a cross-tabulation of total revenue with one row per `region` and one column per `segment`.

- Cell values are the summed `revenue` for that `(region, segment)`.
- Any `(region, segment)` combination that does not occur in the data must appear as `0.0`, not as a missing value (the result must contain no missing values).
- Row index is `region`; columns are the distinct `segment` values.

### `daily_revenue(orders)`
Produce a daily revenue time series.

- Treat `order_date` as a calendar date. Return a series/frame indexed by **every calendar day** from the earliest to the latest order date inclusive, with no gaps, giving the total `revenue` for each day.
- Days that have orders sum their revenue; days in the range that have no orders must be present with a value of `0.0`.
- The index must be sorted ascending and have one entry per day in the full range.

### Expected Functionality
- enrich + an order whose `customer_id` is absent from `customers` -> that order survives with a missing `segment`.
- enrich + duplicated `customer_id` in `customers` -> an error is raised.
- fill_prices over a region with prices `[10.0, NaN, 20.0]` -> the gap becomes `15.0` and its revenue is recomputed accordingly.
- region_segment_summary -> flat, sorted, one row per occurring `(region, segment)`, `order_count` counts distinct orders.
- revenue_pivot -> a `(region, segment)` pair with no orders shows `0.0`.
- daily_revenue over orders spanning `2023-01-01` and `2023-01-03` (none on the 2nd) -> three rows, the middle one `0.0`.

## Acceptance Criteria
- `scripts/sales_report.py` defines `enrich_orders`, `fill_prices`, `region_segment_summary`, `revenue_pivot`, and `daily_revenue` with the behavior above.
- All functions leave their inputs unmodified and never silently drop or duplicate order rows.
- No function returns an object containing missing values where the spec forbids them (`fill_prices`, `revenue_pivot`, `daily_revenue`, and the aggregated columns of `region_segment_summary`).
- Duplicate customer keys in `enrich_orders` cause an exception.
- The following command passes from the repository root:

```
python -m pytest scripts/tests/test_sales_report.py -q
```
