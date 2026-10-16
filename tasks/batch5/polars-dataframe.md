# Task: Build a Survey Response Reshaping Module

## Background

This repository (`pola-rs/polars`) ships runnable examples under `examples/`. We need a self-contained reshaping module in that area that converts survey data between a tall ("long") event form and a wide cross-tab form so an analyst can flip representations without losing information. The module operates purely in-memory and depends only on the `polars` package the repository builds.

## Files to Create/Modify

- `examples/survey_reshape/__init__.py` - package marker (new)
- `examples/survey_reshape/reshape.py` - the reshaping module implementing the public functions below (new)
- `examples/survey_reshape/test_reshape.py` - pytest suite exercising the module (new)

## Requirements

### Module Inputs

Functions accept `polars.DataFrame` inputs and return a `polars.DataFrame`.

A "long" responses frame has columns: `respondent` (String), `question` (String), `score` (Int64). Each `(respondent, question)` pair is unique.

A "wide" frame has a `respondent` (String) column followed by one column per question.

### `to_wide(long: pl.DataFrame) -> pl.DataFrame`

Convert the long frame into a wide cross-tab: one row per `respondent`, one column per distinct `question`, cell value being the `score` for that pair. The first column is `respondent` (String), sorted ascending. The remaining columns are the distinct `question` values ordered alphabetically. A `(respondent, question)` pair that does not exist in the input must appear as `null` in the wide cell (the respondent did not answer that question). Every question seen anywhere in the input must produce a column.

### `to_long(wide: pl.DataFrame) -> pl.DataFrame`

Convert a wide frame back into long form with columns in this exact order: `respondent` (String), `question` (String), `score` (Int64). Every non-`respondent` column becomes a `(question, score)` pair. Rows whose `score` is `null` (the respondent left that question blank) must be **dropped** from the long output. Output sorted by `respondent` ascending, then `question` ascending.

### `answered_counts(long: pl.DataFrame) -> pl.DataFrame`

Return one row per `respondent` with columns in this exact order: `respondent` (String), `answered` (Int64/UInt32), `avg_score` (Float64). `answered` is the number of questions that respondent has a (non-null) score for; `avg_score` is the mean of their scores. Output sorted by `respondent` ascending.

### Expected Functionality

- A respondent who answered only question `"q1"` becomes a wide row with their `q1` score and `null` under every other question column.
- Round-tripping: applying `to_long` to the output of `to_wide` reproduces the original `(respondent, question, score)` set (order aside), because null cells are dropped.
- Question columns in the wide output are alphabetically ordered and include every question that appears anywhere in the long input.
- `answered_counts` reports how many questions each respondent answered and their mean score.
- Empty inputs — every function returns an empty DataFrame with the correct columns and dtypes rather than raising.

## Acceptance Criteria

- `to_wide`, `to_long`, and `answered_counts` exist in `examples/survey_reshape/reshape.py` with the signatures above and return `polars.DataFrame` objects.
- `to_wide` produces one alphabetically ordered column per distinct question with `null` for unanswered pairs.
- `to_long` unpivots every question column back to rows and drops `null`-score rows.
- A `to_wide` then `to_long` round trip recovers the original long records as a set.
- `answered_counts` counts non-null answers and averages scores per respondent.
- All functions return correctly-shaped empty results on empty input.
- The following command passes from the repository root:

  ```bash
  python -m pytest examples/survey_reshape/test_reshape.py -q
  ```
