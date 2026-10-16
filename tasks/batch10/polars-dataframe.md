# Task: Build a Nutrition Dataset Analytics Module

## Background

This repository (`pola-rs/polars`) ships bundled sample CSVs under `examples/datasets/` (such as `foods1.csv` with columns `category,calories,fats_g,sugars_g`) and runnable examples under `examples/`. We need a self-contained analytics module in that area that reads these real food CSVs from disk, aggregates them per category, and writes a tidy summary back out — the kind of I/O round trip a reporting job performs. The module depends only on the `polars` package the repository builds.

## Files to Create/Modify

- `examples/nutrition_report/__init__.py` - package marker (new)
- `examples/nutrition_report/report.py` - the analytics module implementing the public functions below (new)
- `examples/nutrition_report/test_report.py` - pytest suite exercising the module (new)

## Requirements

### Input Files

`load_foods` and `category_summary` read CSVs with header columns `category` (String), `calories` (Int64), `fats_g` (Float64), `sugars_g` (Float64). The repository's own `examples/datasets/foods1.csv` conforms to this shape and may be used by tests; tests may also write small CSVs to a temporary directory.

### `load_foods(paths: list[str]) -> pl.DataFrame`

Read every CSV path in `paths` and return a single `polars.DataFrame` containing all their rows stacked together, with columns `category`, `calories`, `fats_g`, `sugars_g` in that order. Rows appear in the order the files are listed, preserving each file's internal row order. An empty `paths` list returns an empty DataFrame with those four columns and the correct dtypes.

### `category_summary(paths: list[str]) -> pl.DataFrame`

Read and stack the given CSVs, then return one row per distinct `category` with columns in this exact order: `category` (String), `n_items` (Int64/UInt32), `avg_calories` (Float64), `total_sugars` (Float64), `max_fats` (Float64). These are, per category: the number of rows, the mean of `calories`, the sum of `sugars_g`, and the maximum of `fats_g`. Output sorted by `category` ascending.

### `write_summary(summary: pl.DataFrame, out_path: str) -> None`

Write the given `summary` DataFrame to `out_path` as CSV (with a header row). The function returns `None`. The file written must be re-readable into a DataFrame with the same column names and the same row count and values as `summary` (numeric values compared with a small tolerance).

### Expected Functionality

- Reading two CSVs with `load_foods` returns the concatenation of their rows in file-list order.
- `category_summary` over a file where category `"fruit"` appears in three rows reports `n_items = 3` for `"fruit"` with the correct mean calories, summed sugars, and max fats.
- `write_summary` followed by reading the output CSV back reproduces the summary's columns, row count, and values.
- An empty `paths` list yields an empty four-column DataFrame from `load_foods` (no file read, no exception).

## Acceptance Criteria

- `load_foods`, `category_summary`, and `write_summary` exist in `examples/nutrition_report/report.py` with the signatures above.
- `load_foods` reads and row-stacks all listed CSVs in order and returns the four-column frame, with a correct empty result for an empty list.
- `category_summary` aggregates per category into count, mean calories, summed sugars, and max fats, sorted by category.
- `write_summary` writes a header-bearing CSV that round-trips back to the same columns, row count, and values.
- All functions operate on real on-disk CSV files (read and written), not just in-memory frames.
- The following command passes from the repository root:

  ```bash
  python -m pytest examples/nutrition_report/test_report.py -q
  ```
