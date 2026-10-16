# Task: Add a per-tag usage breakdown for a user's favorite queries

## Background
Redash (`redash/models/__init__.py`) stores `Query` records that each carry a free-form list of `tags` and lets a user mark individual queries as favorites through the `Favorite` model. Today the `Query` model can report tag-usage counts across *all* queries a user can see (`Query.all_tags`), but there is no way to report tag-usage counts limited to the queries the user has actually favorited.

## Files to Create/Modify
- `redash/models/__init__.py` (modify) — add a new classmethod on the `Query` model that returns per-tag usage counts restricted to the requesting user's favorited queries.
- `tests/models/test_queries.py` (modify) — add a test class/methods that exercise the new classmethod against seeded data.

## Requirements

### New classmethod
Add a classmethod to the `Query` model with this exact signature:

```python
@classmethod
def favorite_tags(cls, user):
    ...
```

It must return an iterable of two-element rows, where each row is `(tag, usage_count)`:
- `tag` is one individual tag string.
- `usage_count` is the integer number of the user's favorited queries that carry that tag.

The return value must be iterable and, when wrapped in `list(...)`, yield a list of `(tag, usage_count)` tuples. The ordering of the result must be **alphabetical by tag** (ascending).

### Scope of counting
- Only queries that the given `user` has marked as favorites may contribute to the counts. A query favorited by a *different* user must never affect this user's result.
- A favorite is represented by a `Favorite` row whose `object` is a `Query` and whose `user_id` matches the requesting user. Favorites pointing at other object types (for example dashboards) must be ignored.
- Each favorited query contributes exactly once to each distinct tag it carries. A single query carrying three tags contributes to three different tag counts; the same tag appearing on two different favorited queries yields a count of 2 for that tag.
- Queries with no tags (an empty list or a null tags value) must not produce any rows and must not raise.

### Edge cases
- If the user has no favorited queries, the result must be empty (an empty `list(...)`).
- Tags are case-sensitive: `"sql"` and `"SQL"` are distinct tags and must be counted separately.
- The method must not mutate the database and must not require any arguments beyond `user`.

### Expected Functionality
- User favorites query A (tags `["alpha", "beta"]`) and query B (tags `["beta"]`) → `[("alpha", 1), ("beta", 2)]`.
- User favorites query A (tags `["zeta"]`); a second user favorites query C (tags `["zeta"]`) → for the first user the result is `[("zeta", 1)]`, unaffected by the second user's favorite.
- User has favorited a dashboard but no queries → result is `[]`.
- User favorites a query whose tags list is empty → result is `[]`.

## Acceptance Criteria
- `Query.favorite_tags(user)` exists as a classmethod and returns an iterable of `(tag, usage_count)` rows as specified above.
- Counts reflect only the given user's favorited queries; favorites by other users and non-query favorites are excluded.
- Each distinct tag of a favorited query is counted once per query; per-tag counts aggregate across the user's favorited queries.
- Results are ordered alphabetically by tag, and an empty result is returned when the user has no favorited queries.
- The added tests in `tests/models/test_queries.py` pass. Run, from the repository root:

  ```
  pytest tests/models/test_queries.py -k favorite_tags
  ```

  (The full file must also continue to pass: `pytest tests/models/test_queries.py`.)
