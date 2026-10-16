# Task: Build a Multi-Key Transaction Reconciliation Module

## Background
The pandas repository keeps small, self-contained utilities under `scripts/`, each paired with a deterministic test in `scripts/tests/`. This task adds a reconciliation utility that matches transaction records against an expected-ledger table on a composite key and reports discrepancies.

## Files to Create/Modify
- `scripts/txn_reconcile.py` (new) — the reconciliation module described below.
- `scripts/tests/test_txn_reconcile.py` (new) — the deterministic test suite for the module.

The module must `import pandas as pd` and operate purely in-process (no files, network, or external services).

## Requirements

The module exposes the following public functions. They must work for arbitrary inputs satisfying the stated contracts, not just the examples below.

### `match_transactions(actual, expected)`
Combine an actual-transaction table with an expected-ledger table on the composite key `(account_id, period)`.

- `actual` has columns: `account_id` (int), `period` (str, e.g. `2023-Q1`), `txn_id` (int), `amount` (float).
- `expected` has columns: `account_id` (int), `period` (str), `expected_amount` (float). Each `(account_id, period)` pair appears at most once.
- Return a new table: every row of `actual` exactly once (same `txn_id` set, same row count as `actual`), with an `expected_amount` column attached from the matching `(account_id, period)`.
- Rows of `actual` whose `(account_id, period)` is absent from `expected` must still appear, with a missing `expected_amount`.
- If `expected` contains a duplicated `(account_id, period)` pair, the function must raise an error rather than multiplying `actual` rows.
- The caller's `actual` object must not be mutated.

### `flag_discrepancies(matched, tolerance)`
Given the output of `match_transactions` and a non-negative float `tolerance`, return a copy adding:
- a `delta` column equal to `amount - expected_amount`;
- a boolean `is_match` column that is `True` when `expected_amount` is present and `abs(delta) <= tolerance`, and `False` otherwise (including when `expected_amount` is missing).
- Rows with a missing `expected_amount` must have a missing `delta` but `is_match == False`.
- The function must not mutate its input.

### `unmatched_only(matched)`
Return the subset of rows from a matched table whose `(account_id, period)` had no expected entry (i.e. `expected_amount` is missing), as a frame with the index reset to `0..n-1`. Input must not be mutated.

### Expected Functionality
- match + an `actual` row whose `(account_id, period)` is absent from `expected` -> that row survives with a missing `expected_amount`.
- match + duplicated `(account_id, period)` in `expected` -> an error is raised.
- flag_discrepancies with `amount=100.0`, `expected_amount=100.4`, `tolerance=0.5` -> `is_match == True`; with `tolerance=0.1` -> `is_match == False`.
- a row with missing `expected_amount` -> `is_match == False` and `delta` missing.
- unmatched_only -> only the rows with no expected entry, contiguous index from `0`.

## Acceptance Criteria
- `scripts/txn_reconcile.py` defines `match_transactions`, `flag_discrepancies`, and `unmatched_only` with the behavior above.
- All functions leave their inputs unmodified and never silently drop or duplicate `actual` rows.
- Duplicate composite keys in the expected ledger cause an exception.
- The following command passes from the repository root:

```
python -m pytest scripts/tests/test_txn_reconcile.py -q
```
