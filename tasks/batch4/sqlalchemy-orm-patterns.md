# Task: Add a per-data-source count of archived queries

## Background
Redash (`redash/models/__init__.py`) stores `Query` records that each reference a `DataSource` through `data_source_id` and carry an `is_archived` boolean flag. There is currently no way to report, for an organization, how many archived queries belong to each data source.

## Files to Create/Modify
- `redash/models/__init__.py` (modify) — add a new classmethod on the `Query` model that returns per-data-source counts of archived queries.
- `tests/models/test_queries.py` (modify) — add a test class/methods that exercise the new classmethod against seeded data.

## Requirements

### New classmethod
Add a classmethod to the `Query` model with this exact signature:

```python
@classmethod
def archived_counts_by_data_source(cls, org):
    ...
```

It must return an iterable of two-element rows, where each row is `(data_source_id, archived_count)`:
- `data_source_id` is the integer id of a data source.
- `archived_count` is the integer number of archived queries belonging to that data source within the given `org`.

When wrapped in `list(...)` the return value must yield a list of `(data_source_id, archived_count)` tuples.

### Selection and aggregation rules
- Only queries belonging to the given `org` may be counted. Queries in other organizations must never contribute.
- Only archived queries (`is_archived` true) may be counted; non-archived queries must be excluded.
- Counts must be grouped by `data_source_id`. A data source that has zero archived queries must not appear as a row at all.
- Results must be ordered by ascending `data_source_id`, so the output order is deterministic.

### Edge cases
- If the org has no archived queries, the result must be empty (an empty `list(...)`).
- The method must not mutate the database and must accept exactly one argument beyond `cls`.
- A data source whose only queries are all non-archived must not appear.

### Expected Functionality
- Data source D1 has 2 archived queries and 1 active query; data source D2 has 1 archived query → result is `[(D1.id, 2), (D2.id, 1)]` (assuming `D1.id < D2.id`).
- All queries in the org are active → result is `[]`.
- An archived query belonging to a different org's data source → it does not contribute to this org's result.

## Acceptance Criteria
- `Query.archived_counts_by_data_source(org)` exists as a classmethod and returns an iterable of `(data_source_id, archived_count)` rows as specified.
- Only archived queries within the given org are counted; non-archived queries and other orgs are excluded.
- Rows are grouped per data source, omit data sources with no archived queries, and are ordered by ascending `data_source_id`.
- The added tests in `tests/models/test_queries.py` pass. Run, from the repository root:

  ```
  pytest tests/models/test_queries.py -k archived_counts
  ```

  (The full file must also continue to pass: `pytest tests/models/test_queries.py`.)
