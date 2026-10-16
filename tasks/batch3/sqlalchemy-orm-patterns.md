# Task: Add a query for users with a pending invitation

## Background
Redash (`redash/models/users.py`) stores `User` records scoped to an organization. The invitation state of a user is exposed through the `is_invitation_pending` attribute (a value derived from the JSON `details` column). The model already has `User.all`, `User.search`, and `User.pending`, but there is no single convenience entry point that lists every still-pending user in an organization in a stable order.

## Files to Create/Modify
- `redash/models/users.py` (modify) — add a new classmethod on the `User` model that returns the org's users whose invitation is still pending.
- `tests/models/test_users.py` (modify) — add a test class/methods that exercise the new classmethod against seeded data.

## Requirements

### New classmethod
Add a classmethod to the `User` model with this exact signature:

```python
@classmethod
def pending_in_org(cls, org):
    ...
```

It must return an iterable of `User` rows. Each returned user must belong to the given `org` and must currently have a pending invitation.

### Selection rules
- A user qualifies only when their invitation-pending state is true. A user whose invitation is not pending (the value is false or absent) must be excluded.
- Only users belonging to the given `org` may appear. Users in a different organization must never appear, even if their invitation is pending.
- Disabled users must be excluded from the result.
- Results must be ordered by ascending user `id` (i.e. earliest-created first by id), so the output order is deterministic.

### Edge cases
- If the org has no pending users, the result must be empty when wrapped in `list(...)`.
- The method must not mutate the database and must accept exactly one argument beyond `cls`.
- Iterating the result and calling `len(list(...))` must reflect the exact count of qualifying users.

### Expected Functionality
- Org has user X (pending) and user Y (not pending) → only X appears.
- Org has users P and Q both pending, created in that id order → result is `[P, Q]` in that order.
- A pending user is disabled → that user does not appear.
- A pending user belongs to a different org → that user does not appear in this org's result.

## Acceptance Criteria
- `User.pending_in_org(org)` exists as a classmethod and returns an iterable of `User` objects filtered to that org's enabled, pending users.
- Non-pending users, disabled users, and users from other orgs are excluded.
- Results are ordered by ascending `id`, and the result is empty when no users qualify.
- The added tests in `tests/models/test_users.py` pass. Run, from the repository root:

  ```
  pytest tests/models/test_users.py -k pending_in_org
  ```

  (The full file must also continue to pass: `pytest tests/models/test_users.py`.)
