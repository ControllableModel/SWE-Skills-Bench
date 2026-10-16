# Task: Add a per-object-type breakdown of a user's favorites

## Background
Redash (`redash/models/__init__.py`) records each thing a user marks as a favorite as a `Favorite` row whose `object_type` distinguishes the kind of object (for example `"Query"` versus `"Dashboard"`) and whose `user` is the owning user. The model can already test individual or bulk favorite membership (`is_favorite`, `are_favorites`), but there is no way to report how many favorites a user has of each type.

## Files to Create/Modify
- `redash/models/__init__.py` (modify) — add a new classmethod on the `Favorite` model that returns per-type favorite counts for a user.
- `tests/models/test_favorites.py` (new) — add a test module (using `tests.BaseTestCase` and `self.factory`) that exercises the new classmethod against seeded data.

## Requirements

### New classmethod
Add a classmethod to the `Favorite` model with this exact signature:

```python
@classmethod
def counts_by_type(cls, user):
    ...
```

It must return an iterable of two-element rows, where each row is `(object_type, count)`:
- `object_type` is one favorite object-type string (for example `"Query"` or `"Dashboard"`).
- `count` is the integer number of the user's favorites of that type.

When wrapped in `list(...)` the return value must yield a list of `(object_type, count)` tuples, ordered **alphabetically by object_type** (ascending).

### Selection and aggregation rules
- Only favorites belonging to the given `user` may be counted. Favorites owned by a different user must never contribute.
- Counts must be grouped by `object_type`. An object type for which the user has no favorites must not appear as a row.
- Results must be ordered alphabetically by `object_type`, so the output order is deterministic.

### Edge cases
- If the user has no favorites, the result must be empty (an empty `list(...)`).
- The method must not mutate the database and must accept exactly one argument beyond `cls`.
- Two users favoriting the same object are counted independently; one user's favorites never inflate the other's counts.

### Expected Functionality
- User favorites two queries and one dashboard → `[("Dashboard", 1), ("Query", 2)]`.
- A second user favorites three queries → the first user's result is unaffected.
- A user with only dashboard favorites → `[("Dashboard", <n>)]`, with no `"Query"` row.
- A user with no favorites → `[]`.

## Acceptance Criteria
- `Favorite.counts_by_type(user)` exists as a classmethod and returns an iterable of `(object_type, count)` rows as specified.
- Only the given user's favorites are counted; other users' favorites are excluded.
- Rows are grouped per object type, omit types with no favorites, and are ordered alphabetically by `object_type`.
- The added tests in `tests/models/test_favorites.py` pass. Run, from the repository root:

  ```
  pytest tests/models/test_favorites.py
  ```
