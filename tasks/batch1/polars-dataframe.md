# Task: Build a Sales Performance Reporting Module

## Background

This repository (`pola-rs/polars`) ships runnable examples under `examples/`. We need a small, self-contained reporting module in that area that turns raw transaction and staff records into the aggregated, per-store and per-employee tables a sales team would review each month. The module must operate purely in-memory and rely only on the `polars` Python package that the repository builds.

## Files to Create/Modify

- `examples/sales_pipeline/__init__.py` - package marker (new)
- `examples/sales_pipeline/report.py` - the reporting module implementing the public functions described below (new)
- `examples/sales_pipeline/test_report.py` - pytest test suite exercising the module (new)

## Requirements

### Module Inputs

All functions accept `polars.DataFrame` inputs (never file paths) and return `polars.DataFrame` outputs. Two input shapes are used:

- `transactions` columns:
  - `txn_id` (Int64) — unique transaction id
  - `store` (String) — store name
  - `employee_id` (Int64) — id of the employee who made the sale
  - `category` (String) — product category (e.g. `"food"`, `"drink"`, `"misc"`)
  - `amount` (Float64) — sale amount; may be **null** for voided/incomplete transactions
- `employees` columns:
  - `employee_id` (Int64) — unique employee id
  - `name` (String) — employee display name
  - `store` (String) — store the employee belongs to

### `store_summary(transactions: pl.DataFrame) -> pl.DataFrame`

Produce one row per `store` with these columns, in this exact order:

- `store` (String)
- `total_amount` (Float64) — sum of `amount` over the store, treating null amounts as `0.0`
- `txn_count` (Int64/UInt32) — number of transactions belonging to the store, including ones with a null `amount`
- `valid_txn_count` (Int64/UInt32) — number of transactions with a non-null `amount`
- `avg_valid_amount` (Float64) — mean of `amount` over only the non-null transactions; for a store whose every transaction has a null amount this must be `null`, not `0.0` and not `NaN`

Rows must be sorted by `store` ascending. A store that appears only with null amounts must still appear with a row.

### `top_employee_per_store(transactions: pl.DataFrame, employees: pl.DataFrame) -> pl.DataFrame`

Return, for each store, the single employee with the highest total non-null sales `amount`, with columns in this order:

- `store` (String)
- `employee_id` (Int64)
- `name` (String) — resolved from `employees`
- `employee_total` (Float64) — that employee's summed `amount` (nulls treated as `0.0`)

Rules:

- The `store` used for grouping is the store recorded on the **transaction**, which is authoritative; ignore the store column of `employees` for grouping.
- If two employees in the same store tie on `employee_total`, the one with the smaller `employee_id` wins.
- An `employee_id` present in `transactions` but absent from `employees` must still appear, with `name` equal to `null`.
- Employees who have no transactions must not appear.
- Output sorted by `store` ascending.

### `category_pivot(transactions: pl.DataFrame) -> pl.DataFrame`

Return a wide table with one row per `store` and one column per distinct `category`, where each cell is the summed non-null `amount` of that `(store, category)` combination.

- The first column is `store` (String), rows sorted by `store` ascending.
- Remaining columns are named exactly by the category values, ordered alphabetically.
- A `(store, category)` combination with no matching transactions must be `0.0` (not `null`).
- A category present anywhere in the input must yield a column even if some stores never sold it.

### `flag_outlier_transactions(transactions: pl.DataFrame) -> pl.DataFrame`

Return the original `transactions` rows (same `txn_id` set, preserving original row order) with one added column:

- `above_store_avg` (Boolean) — `True` when the transaction's `amount` is strictly greater than the average non-null `amount` of all transactions in the **same store**; `False` otherwise.

Rules:

- Transactions with a null `amount` get `False`.
- The per-store average is computed from non-null amounts only and is the same reference value used for every row of that store.
- The result must keep all original columns plus the new one; no rows added or removed.

### Expected Functionality

- Two stores `"A"` and `"B"`, with `"B"` having one valid sale and one voided (null) sale — `store_summary` yields `txn_count=2`, `valid_txn_count=1` for `"B"`, and `total_amount` equal to the single valid amount.
- A store where every transaction is voided (null amount) — `store_summary` returns `avg_valid_amount = null` and `total_amount = 0.0` for that store.
- An employee appears in `transactions` but not in `employees` and is the top seller of their store — `top_employee_per_store` lists them with `name = null`.
- Two employees in store `"A"` tie on total — the smaller `employee_id` is returned.
- A category `"drink"` exists in the data but store `"A"` never sold it — `category_pivot` still has a `drink` column with `0.0` in store `"A"`'s row.
- A store with a single non-null transaction — that transaction is never flagged (`above_store_avg=False`, since it is not strictly greater than its own average).
- Empty `transactions` input — every function returns an empty DataFrame with the correct columns and dtypes rather than raising.

## Acceptance Criteria

- `store_summary`, `top_employee_per_store`, `category_pivot`, and `flag_outlier_transactions` exist in `examples/sales_pipeline/report.py` with the signatures above and return `polars.DataFrame` objects.
- Null `amount` values are treated as `0.0` for sums but excluded from averages and `valid_txn_count`, including the all-null store case where the average is `null`.
- `top_employee_per_store` resolves names via a join, breaks ties by smallest `employee_id`, groups by the transaction's store, and tolerates unknown employee ids (name `null`).
- `category_pivot` produces one alphabetically ordered column per distinct category with `0.0` fills for absent combinations.
- `flag_outlier_transactions` preserves original row count and order, uses a per-store average of non-null amounts as the comparison reference for each row, and flags strictly-greater rows only.
- All functions return correctly-shaped empty results on empty input.
- The following command passes from the repository root:

  ```bash
  python -m pytest examples/sales_pipeline/test_report.py -q
  ```
