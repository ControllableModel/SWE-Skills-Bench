# Task: Add a state-filtered query for alerts visible to a set of groups

## Background
Redash (`redash/models/__init__.py`) stores `Alert` records, each tied to a `Query` (and therefore, transitively, to a `DataSource` and the groups that can access it). The `Alert` model already exposes `Alert.all`, which returns every alert reachable from a set of group ids, but there is no way to narrow that down to alerts that are currently in a particular state (for example only `triggered` alerts).

## Files to Create/Modify
- `redash/models/__init__.py` (modify) — add a new classmethod on the `Alert` model that returns alerts in a given state that are reachable from a set of group ids.
- `tests/models/test_alerts.py` (modify) — add a test class/methods that exercise the new classmethod against seeded data.

## Requirements

### New classmethod
Add a classmethod to the `Alert` model with this exact signature:

```python
@classmethod
def in_state(cls, state, group_ids):
    ...
```

It must return an iterable of `Alert` rows. Each returned alert must be in the requested `state` and must be reachable from at least one of the given `group_ids` (through its query's data source).

### Selection rules
- Only alerts whose `state` equals the requested `state` may appear. Alerts in any other state must be excluded.
- Reachability is determined the same way as the existing `Alert.all` behavior: an alert is reachable if its query's data source belongs to a group in `group_ids`. An alert reachable only through a group not in `group_ids` must not appear.
- Each matching alert must appear at most once in the result, even when its data source is associated with multiple groups in `group_ids`.

### Edge cases
- If no alert matches both the state and the group reachability, the result must be empty when wrapped in `list(...)`.
- The method must not mutate the database and must accept exactly two arguments beyond `cls` (`state` and `group_ids`).

### Expected Functionality
- Alert A (state `triggered`, reachable via group G) and Alert B (state `ok`, reachable via group G) → `in_state("triggered", [G.id])` contains A but not B.
- Alert A is reachable only through group G2, and the call passes `[G1.id]` → A does not appear.
- A data source belonging to two groups both in `group_ids` → its triggered alert appears exactly once, not duplicated.

## Acceptance Criteria
- `Alert.in_state(state, group_ids)` exists as a classmethod and returns an iterable of `Alert` objects filtered by both state and group reachability.
- Alerts in other states, and alerts reachable only through groups not in `group_ids`, are excluded.
- Each matching alert appears at most once even when reachable via multiple supplied groups.
- The added tests in `tests/models/test_alerts.py` pass. Run, from the repository root:

  ```
  pytest tests/models/test_alerts.py -k in_state
  ```

  (The full file must also continue to pass: `pytest tests/models/test_alerts.py`.)
