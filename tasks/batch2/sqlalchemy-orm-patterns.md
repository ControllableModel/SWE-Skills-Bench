# Task: Add per-tag usage counts for a user's own dashboards

## Background
Redash (`redash/models/__init__.py`) stores `Dashboard` records that each carry a free-form list of `tags`. The model already exposes `Dashboard.all_tags`, which counts tag usage across every dashboard a user is allowed to see, but there is no way to report tag-usage counts restricted to the dashboards a given user has actually authored.

## Files to Create/Modify
- `redash/models/__init__.py` (modify) — add a new classmethod on the `Dashboard` model that returns per-tag usage counts limited to the dashboards owned by a given user.
- `tests/models/test_dashboards.py` (modify) — add a test class/methods that exercise the new classmethod against seeded data.

## Requirements

### New classmethod
Add a classmethod to the `Dashboard` model with this exact signature:

```python
@classmethod
def owned_tags(cls, user):
    ...
```

It must return an iterable of two-element rows, where each row is `(tag, usage_count)`:
- `tag` is one individual tag string.
- `usage_count` is the integer number of the user's own (authored) dashboards that carry that tag.

When wrapped in `list(...)` the return value must yield a list of `(tag, usage_count)` tuples, ordered **alphabetically by tag** (ascending).

### Scope of counting
- Only dashboards whose owning user is the given `user` may contribute to the counts. A dashboard authored by a different user must never affect this user's result, even if it is otherwise visible to them.
- Archived dashboards must be excluded from the counts.
- Each owned dashboard contributes exactly once to each distinct tag it carries. A single dashboard with three tags contributes to three different tag counts; the same tag appearing on two different owned dashboards yields a count of 2 for that tag.
- Dashboards with no tags (an empty list or a null tags value) must not produce any rows and must not raise.

### Edge cases
- If the user owns no dashboards (or none with tags), the result must be empty (an empty `list(...)`).
- Tags are case-sensitive: `"prod"` and `"PROD"` are distinct tags and must be counted separately.
- The method must not mutate the database and must not require any arguments beyond `user`.

### Expected Functionality
- User authors dashboard A (tags `["alpha", "beta"]`) and dashboard B (tags `["beta"]`) → `[("alpha", 1), ("beta", 2)]`.
- User authors dashboard A (tags `["zeta"]`); a second user authors dashboard C (tags `["zeta"]`) → for the first user the result is `[("zeta", 1)]`, unaffected by the second user's dashboard.
- A tagged dashboard owned by the user is archived → it contributes nothing.
- User authors a dashboard whose tags list is empty → result is `[]`.

## Acceptance Criteria
- `Dashboard.owned_tags(user)` exists as a classmethod and returns an iterable of `(tag, usage_count)` rows as specified above.
- Counts reflect only the given user's own, non-archived dashboards; dashboards by other users and archived dashboards are excluded.
- Each distinct tag of an owned dashboard is counted once per dashboard; per-tag counts aggregate across the user's owned dashboards.
- Results are ordered alphabetically by tag, and an empty result is returned when the user owns no tagged dashboards.
- The added tests in `tests/models/test_dashboards.py` pass. Run, from the repository root:

  ```
  pytest tests/models/test_dashboards.py -k owned_tags
  ```

  (The full file must also continue to pass: `pytest tests/models/test_dashboards.py`.)
