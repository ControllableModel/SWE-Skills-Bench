# Task: Build a Data-Cleaning and Bucketing Module

## Background

This repository (`pola-rs/polars`) ships runnable examples under `examples/`. We need a self-contained cleaning module in that area that repairs messy raw measurements — filling and imputing nulls, coercing types, and assigning conditional categories — before they enter an analytics warehouse. The module operates purely in-memory and depends only on the `polars` package the repository builds.

## Files to Create/Modify

- `examples/data_clean/__init__.py` - package marker (new)
- `examples/data_clean/clean.py` - the cleaning module implementing the public functions below (new)
- `examples/data_clean/test_clean.py` - pytest suite exercising the module (new)

## Requirements

### Module Inputs

Functions accept a single `polars.DataFrame` named `raw` and return a `polars.DataFrame`. The `raw` columns are:

- `id` (Int64, unique)
- `group` (String) — category key; may be `null`
- `temperature` (Float64) — may be `null`
- `count_str` (String) — an integer encoded as text such as `"42"`; may be `null` or an empty string `""`

### `impute_temperature(raw: pl.DataFrame) -> pl.DataFrame`

Return every input row plus a column `temperature_filled` (Float64). For each row, if `temperature` is non-null keep it; otherwise replace it with the **mean of the non-null `temperature` values within the same `group`**. If an entire group has no non-null temperature (or the row's `group` is `null` and there is no usable group mean), the filled value remains `null`. All original columns are preserved; output sorted by `id` ascending.

### `parse_counts(raw: pl.DataFrame) -> pl.DataFrame`

Return every input row plus a column `count` (Int64), parsed from `count_str`. A `null` `count_str` and an empty-string `count_str` both yield `count = null`. A well-formed integer string yields its integer value. All original columns are preserved; output sorted by `id` ascending. The function must not raise on null or empty inputs.

### `bucket_temperature(raw: pl.DataFrame) -> pl.DataFrame`

Return every input row plus a column `band` (String) derived from the original `temperature` (not the imputed one) by these rules, evaluated in order:

- `temperature` is `null` -> `band = "unknown"`
- `temperature < 0.0` -> `"cold"`
- `0.0 <= temperature < 25.0` -> `"mild"`
- `temperature >= 25.0` -> `"hot"`

All original columns are preserved; output sorted by `id` ascending.

### `group_health(raw: pl.DataFrame) -> pl.DataFrame`

Return one row per distinct `group` value (including a row for the `null` group if present) with columns in this exact order: `group` (String), `rows` (Int64/UInt32), `null_temp` (Int64/UInt32 — count of rows in the group with a null `temperature`). Output sorted by `group` ascending with the `null` group, if present, sorted last.

### Expected Functionality

- A row with `null` `temperature` in group `"A"` (whose other rows average `20.0`) gets `temperature_filled = 20.0`, while its `band` stays `"unknown"`.
- A group whose every temperature is `null` leaves `temperature_filled` as `null` for all its rows.
- `count_str` values `"7"`, `""`, and `null` yield `count` of `7`, `null`, `null` respectively, with no exception.
- A temperature of exactly `0.0` is `"mild"`, exactly `25.0` is `"hot"`, and `-3.0` is `"cold"`.
- `group_health` reports row and null-temperature counts per group, with the `null` group placed last.
- Empty `raw` input — every function returns an empty DataFrame with the correct columns and dtypes rather than raising.

## Acceptance Criteria

- `impute_temperature`, `parse_counts`, `bucket_temperature`, and `group_health` exist in `examples/data_clean/clean.py` with the signatures above and return `polars.DataFrame` objects.
- `impute_temperature` fills nulls with the per-group mean of non-null temperatures and leaves nulls where no group mean exists.
- `parse_counts` converts integer strings to `Int64`, mapping `null` and empty strings to `null` without raising.
- `bucket_temperature` assigns the four bands by the exact stated boundaries, with `null` mapping to `"unknown"`.
- `group_health` counts rows and null temperatures per group with the `null` group sorted last.
- All functions return correctly-shaped empty results on empty input.
- The following command passes from the repository root:

  ```bash
  python -m pytest examples/data_clean/test_clean.py -q
  ```
