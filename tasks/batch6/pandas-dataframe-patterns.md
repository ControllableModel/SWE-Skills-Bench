# Task: Build a Memory-Efficient Type Optimization Module

## Background
The pandas repository keeps small, self-contained utilities under `scripts/`, each paired with a deterministic test in `scripts/tests/`. This task adds a utility that shrinks the in-memory footprint of a wide numeric/categorical table without changing its values.

## Files to Create/Modify
- `scripts/dtype_optimize.py` (new) — the optimization module described below.
- `scripts/tests/test_dtype_optimize.py` (new) — the deterministic test suite for the module.

The module must `import pandas as pd` and operate purely in-process (no files, network, or external services).

## Requirements

The module exposes the following public functions. They must work for arbitrary inputs satisfying the stated contracts, not just the examples below.

### `optimize(df, max_category_ratio=0.5)`
Return a copy of `df` with reduced-size dtypes, preserving every value:
- Integer columns must be downcast to the smallest signed integer dtype that holds all their values.
- Float columns must be downcast to the smallest float dtype (no wider than the original) that holds their values.
- Object (string) columns whose number of distinct values divided by the number of rows is **strictly less than** `max_category_ratio` must be converted to a categorical dtype; object columns at or above that ratio must be left as object.
- Element-wise values must compare equal to the input after optimization (no data loss).
- The caller's `df` object must not be mutated.

### `memory_report(df)`
Return a frame with one row per column of `df` and columns `column`, `dtype` (string name of the dtype), and `bytes` (deep memory usage of that column in bytes, as an integer). The result is indexed `0..n-1` and ordered to match the column order of `df`. Input must not be mutated.

### `savings(original, optimized)`
Given two frames with identical column names, return a float: the fraction of deep memory saved, computed as `1 - optimized_total / original_total`, where each total is the deep memory usage summed across all columns. Neither input may be mutated.

### Expected Functionality
- optimize over an int column with values `[1, 2, 3]` -> dtype becomes `int8` (smallest signed int that holds them).
- optimize over an object column with 2 distinct values in 100 rows -> becomes categorical; an object column where every value is unique -> stays object.
- optimize preserves values: the optimized frame compares equal element-wise to the input.
- memory_report -> one row per column with a positive integer `bytes`.
- savings(original, optimized) where optimized uses less memory -> a value strictly between `0` and `1`.

## Acceptance Criteria
- `scripts/dtype_optimize.py` defines `optimize`, `memory_report`, and `savings` with the behavior above.
- `optimize` never changes any value and chooses the smallest valid integer dtype.
- Low-cardinality object columns become categorical; high-cardinality ones do not.
- All functions leave their inputs unmodified.
- The following command passes from the repository root:

```
python -m pytest scripts/tests/test_dtype_optimize.py -q
```
