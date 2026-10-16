# Task: Add an enabled-member count for a group

## Background
Redash (`redash/models/users.py`) stores `User` records whose `group_ids` array lists the groups each user belongs to, and `Group` records describe those groups. The `Group` model already exposes `Group.members(group_id)`, which returns every user in a group, but there is no way to get just the number of currently enabled members of a group.

## Files to Create/Modify
- `redash/models/users.py` (modify) — add a new classmethod on the `Group` model that returns the count of enabled members of a group.
- `tests/models/test_groups.py` (new) — add a test module (using `tests.BaseTestCase` and `self.factory`) that exercises the new classmethod against seeded data.

## Requirements

### New classmethod
Add a classmethod to the `Group` model with this exact signature:

```python
@classmethod
def enabled_member_count(cls, group_id):
    ...
```

It must return an integer: the number of enabled users who are members of the group identified by `group_id`.

### Counting rules
- A user is a member of the group when `group_id` appears in that user's `group_ids` array.
- Only enabled users may be counted. A disabled user who is a member of the group must not be counted.
- The return value must be a plain integer (usable directly in arithmetic and equality comparisons), not a query or a row.

### Edge cases
- If the group has no enabled members, the return value must be `0`.
- A user belonging to several groups is counted for each group they belong to; membership in another group does not exclude them from this group's count.
- The method must not mutate the database and must accept exactly one argument beyond `cls`.

### Expected Functionality
- A group with three enabled members → returns `3`.
- One of those three members is then disabled → returns `2`.
- A group nobody belongs to → returns `0`.
- A user who belongs to both group G1 and group G2 → contributes `1` to each of `enabled_member_count(G1.id)` and `enabled_member_count(G2.id)`.

## Acceptance Criteria
- `Group.enabled_member_count(group_id)` exists as a classmethod and returns an integer count of enabled members of the group.
- Disabled members are excluded from the count, and users in the group via their `group_ids` array are counted.
- A group with no enabled members returns `0`.
- The added tests in `tests/models/test_groups.py` pass. Run, from the repository root:

  ```
  pytest tests/models/test_groups.py
  ```
