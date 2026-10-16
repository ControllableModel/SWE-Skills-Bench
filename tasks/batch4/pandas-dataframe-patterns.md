# Task: Build a Survey Response Cleaning Module

## Background
The pandas repository keeps small, self-contained utilities under `scripts/`, each paired with a deterministic test in `scripts/tests/`. This task adds a utility that cleans raw survey responses: deduplicating, normalizing types, and imputing missing answers.

## Files to Create/Modify
- `scripts/survey_clean.py` (new) — the cleaning module described below.
- `scripts/tests/test_survey_clean.py` (new) — the deterministic test suite for the module.

The module must `import pandas as pd` and operate purely in-process (no files, network, or external services).

## Requirements

The module exposes the following public functions. They must work for arbitrary inputs satisfying the stated contracts, not just the examples below.

### `dedupe_responses(responses)`
- `responses` has columns: `respondent_id` (int), `submitted_at` (string parseable as a datetime), `rating` (float, may be missing), `comment` (str, may be missing).
- A respondent may have submitted more than once. Return a frame keeping exactly one row per `respondent_id`: the one with the latest `submitted_at`. Ties on `submitted_at` are broken by keeping the last occurrence in input order.
- The result has one row per distinct `respondent_id`, with the index reset to `0..n-1`, sorted by `respondent_id` ascending.
- The caller's `responses` object must not be mutated.

### `impute(responses)`
Return a copy in which missing answers are filled:
- Missing `rating` is filled with the **median** of the present `rating` values (over the whole table).
- Missing `comment` is filled with the literal string `"(no comment)"`.
- After imputation the result has no missing values in `rating` or `comment`.
- The function must not mutate its input.

### `normalize_types(responses)`
Return a copy with corrected dtypes:
- `respondent_id` must be an integer dtype.
- `submitted_at` must be a datetime dtype (not object/string).
- `comment` must be converted to a categorical dtype.
- `rating` must be a float dtype.
- Values must be preserved (only the representation/dtype changes). The function must not mutate its input.

### Expected Functionality
- dedupe_responses with two rows for respondent `7` at `2023-01-01` and `2023-02-01` -> only the `2023-02-01` row survives.
- dedupe_responses -> output sorted by `respondent_id`, contiguous index from `0`.
- impute over ratings `[2.0, NaN, 4.0, 6.0]` -> the gap becomes `4.0` (median of present values).
- impute over a missing comment -> becomes `"(no comment)"`.
- normalize_types -> `submitted_at` is datetime, `comment` is categorical, `respondent_id` integer.

## Acceptance Criteria
- `scripts/survey_clean.py` defines `dedupe_responses`, `impute`, and `normalize_types` with the behavior above.
- `dedupe_responses` yields exactly one row per respondent, keeping the latest submission.
- `impute` leaves no missing `rating` or `comment`.
- `normalize_types` produces the specified dtypes while preserving values.
- All functions leave their inputs unmodified.
- The following command passes from the repository root:

```
python -m pytest scripts/tests/test_survey_clean.py -q
```
