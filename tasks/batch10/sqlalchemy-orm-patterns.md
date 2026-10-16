# Task: Add a listing of a user's unpublished dashboards

## Background
Redash (`redash/models/__init__.py`) stores `Dashboard` records that carry an `is_draft` flag (an unpublished dashboard) and an `is_archived` flag, and each dashboard has an owning `user`. The model already exposes `Dashboard.by_user`, which returns every dashboard a user authored, but there is no way to list only the user's still-unpublished (draft) dashboards in a stable order.

## Files to Create/Modify
- `redash/models/__init__.py` (modify) — add a new classmethod on the `Dashboard` model that returns a user's unpublished, non-archived dashboards.
- `tests/models/test_dashboards.py` (modify) — add a test class/methods that exercise the new classmethod against seeded data.

## Requirements

### New classmethod
Add a classmethod to the `Dashboard` model with this exact signature:

```python
@classmethod
def drafts_by_user(cls, user):
    ...
```

It must return an iterable of `Dashboard` rows authored by the given `user` that are still drafts and not archived.

### Selection rules
- Only dashboards whose owning user is the given `user` may appear. A draft dashboard authored by a different user must never appear.
- Only dashboards with `is_draft` true may appear; a published dashboard (draft false) authored by the user must be excluded.
- Archived dashboards must be excluded even when they are drafts authored by the user.
- Results must be ordered by ascending dashboard `id`, so the output order is deterministic.

### Edge cases
- If the user has no draft dashboards, the result must be empty when wrapped in `list(...)`.
- The method must not mutate the database and must accept exactly one argument beyond `cls`.
- Each qualifying dashboard must appear exactly once in the result.

### Expected Functionality
- User authors draft dashboard A and published dashboard B → only A appears.
- User authors draft dashboards A then C (in that id order) → result is `[A, C]` in that order.
- A draft dashboard authored by the user is archived → it does not appear.
- A draft dashboard authored by a different user → it does not appear in this user's result.

## Acceptance Criteria
- `Dashboard.drafts_by_user(user)` exists as a classmethod and returns an iterable of the user's draft, non-archived dashboards.
- Published dashboards, archived dashboards, and dashboards by other users are excluded.
- Each qualifying dashboard appears exactly once, ordered by ascending `id`, and the result is empty when the user has no drafts.
- The added tests in `tests/models/test_dashboards.py` pass. Run, from the repository root:

  ```
  pytest tests/models/test_dashboards.py -k drafts_by_user
  ```

  (The full file must also continue to pass: `pytest tests/models/test_dashboards.py`.)
