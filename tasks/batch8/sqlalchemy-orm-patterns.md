# Task: Add a cached-result count per data source

## Background
Redash (`redash/models/__init__.py`) stores `QueryResult` records, each tied to a `DataSource` through `data_source_id` and carrying the time it was `retrieved_at`. The model already exposes `QueryResult.unused` and `QueryResult.get_latest`, but there is no way to report how many cached results each data source currently holds.

## Files to Create/Modify
- `redash/models/__init__.py` (modify) — add a new classmethod on the `QueryResult` model that returns the number of stored results per data source.
- `tests/models/test_query_results.py` (modify) — add a test class/methods that exercise the new classmethod against seeded data.

## Requirements

### New classmethod
Add a classmethod to the `QueryResult` model with this exact signature:

```python
@classmethod
def counts_by_data_source(cls, org):
    ...
```

It must return an iterable of two-element rows, where each row is `(data_source_id, result_count)`:
- `data_source_id` is the integer id of a data source.
- `result_count` is the integer number of `QueryResult` rows stored for that data source within the given `org`.

When wrapped in `list(...)` the return value must yield a list of `(data_source_id, result_count)` tuples.

### Selection and aggregation rules
- Only results belonging to the given `org` may be counted. Results in other organizations must never contribute.
- Counts must be grouped by `data_source_id`. A data source with zero stored results must not appear as a row.
- Results must be ordered by ascending `data_source_id`, so the output order is deterministic.

### Edge cases
- If the org has no stored results, the result must be empty (an empty `list(...)`).
- The method must not mutate the database and must accept exactly one argument beyond `cls`.
- Every stored result counts, regardless of how old its `retrieved_at` is.

### Expected Functionality
- Data source D1 has 3 stored results and D2 has 1 → result is `[(D1.id, 3), (D2.id, 1)]` (assuming `D1.id < D2.id`).
- A data source with no stored results → it does not appear.
- A stored result belonging to a different org → it does not contribute to this org's result.

## Acceptance Criteria
- `QueryResult.counts_by_data_source(org)` exists as a classmethod and returns an iterable of `(data_source_id, result_count)` rows as specified.
- Only results within the given org are counted; other orgs are excluded.
- Rows are grouped per data source, omit data sources with no results, and are ordered by ascending `data_source_id`.
- The added tests in `tests/models/test_query_results.py` pass. Run, from the repository root:

  ```
  pytest tests/models/test_query_results.py -k counts_by_data_source
  ```

  (The full file must also continue to pass: `pytest tests/models/test_query_results.py`.)
