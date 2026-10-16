# Task: Build a Wide/Long Reshape and Tidy Module

## Background
The pandas repository keeps small, self-contained utilities under `scripts/`, each paired with a deterministic test in `scripts/tests/`. This task adds a utility that converts between wide and long ("tidy") layouts for measurement tables and tidies messy column headers.

## Files to Create/Modify
- `scripts/reshape_tidy.py` (new) — the reshaping module described below.
- `scripts/tests/test_reshape_tidy.py` (new) — the deterministic test suite for the module.

The module must `import pandas as pd` and operate purely in-process (no files, network, or external services).

## Requirements

The module exposes the following public functions. They must work for arbitrary inputs satisfying the stated contracts, not just the examples below.

### `wide_to_long(df, id_cols)`
- `df` is a wide measurement table: `id_cols` is a list of identifier column names; every other column is a measurement whose header is the measurement name and whose cells are float values (some may be missing).
- Return a long frame with columns: the `id_cols` (unchanged), plus `metric` (str, the former column name) and `value` (float).
- Rows whose `value` is missing in the wide table must be **dropped** from the long output (only present measurements survive).
- The long frame is sorted by the `id_cols` (in order) then `metric` ascending, index reset to `0..n-1`.
- The caller's `df` object must not be mutated.

### `long_to_wide(df, id_cols)`
- Inverse of the above: `df` is a long frame with `id_cols`, a `metric` column, and a `value` column. Each `(id_cols..., metric)` combination is unique.
- Return a wide frame with one row per distinct combination of `id_cols`, one column per distinct `metric`, and the corresponding `value` in each cell. Combinations that were absent in the long input are missing in the wide output.
- `id_cols` are ordinary columns (not the index), sorted by `id_cols` ascending, index reset to `0..n-1`. Input must not be mutated.

### `clean_headers(df)`
Return a copy of `df` whose column names are normalized: stripped of leading/trailing whitespace, lowercased, and with any run of internal whitespace replaced by a single underscore (e.g. `"  Order  ID "` -> `"order_id"`). Cell values and row order are unchanged. Input must not be mutated.

### Expected Functionality
- wide_to_long over a wide table with a missing measurement cell -> that cell does not appear as a row.
- long_to_wide is the inverse of wide_to_long for tables with no missing cells (round-trip preserves values).
- clean_headers over `"  Order  ID "` -> `"order_id"`.

## Acceptance Criteria
- `scripts/reshape_tidy.py` defines `wide_to_long`, `long_to_wide`, and `clean_headers` with the behavior above.
- `wide_to_long` drops missing measurements; round-tripping a complete table preserves values.
- `clean_headers` normalizes header whitespace/case as specified.
- All functions leave their inputs unmodified.
- The following command passes from the repository root:

```
python -m pytest scripts/tests/test_reshape_tidy.py -q
```
