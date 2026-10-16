# Task: Build a Web-Session Event Sessionization Module

## Background
The pandas repository keeps small, self-contained utilities under `scripts/`, each paired with a deterministic test in `scripts/tests/`. This task adds a utility that groups raw clickstream events into user sessions and summarizes them.

## Files to Create/Modify
- `scripts/sessionize.py` (new) — the sessionization module described below.
- `scripts/tests/test_sessionize.py` (new) — the deterministic test suite for the module.

The module must `import pandas as pd` and operate purely in-process (no files, network, or external services).

## Requirements

The module exposes the following public functions. They must work for arbitrary inputs satisfying the stated contracts, not just the examples below.

### `assign_sessions(events, timeout_minutes)`
- `events` has columns: `user_id` (int), `timestamp` (string parseable as a datetime), `page` (str).
- Within each `user_id` (sorted by `timestamp` ascending), a new session begins at the first event and whenever the gap from the previous event for that user **strictly exceeds** `timeout_minutes` minutes.
- Return a copy of `events` (same rows) with an added integer `session_id` column: for each user, sessions are numbered `0, 1, 2, …` in chronological order. Session numbering restarts at `0` for each user.
- Output sorted by `user_id` then `timestamp` ascending, index reset to `0..n-1`.
- The caller's `events` object must not be mutated.

### `session_summary(events_with_sessions)`
Given the output of `assign_sessions`, return one row per `(user_id, session_id)` with columns:
- `event_count` (number of events in the session),
- `duration_minutes` (float: minutes between the session's first and last event timestamp; `0.0` for a single-event session),
- `start` (the session's earliest timestamp, a datetime).
- Sorted by `user_id` then `session_id` ascending, index reset to `0..n-1`. Input must not be mutated.

### `entry_pages(events_with_sessions)`
Return a frame with columns `page` and `sessions`: for each distinct `page` that is the **first** page (earliest timestamp) of some session, the number of sessions that began on that page. Sorted by `sessions` descending then `page` ascending, index reset to `0..n-1`. Input must not be mutated.

### Expected Functionality
- assign_sessions with `timeout_minutes=30` and gaps of `10` then `40` minutes for one user -> events split into sessions `0, 0, 1`.
- session numbering restarts per user.
- session_summary -> `event_count` and `duration_minutes` per session; single-event session has `duration_minutes == 0.0`.
- entry_pages -> counts of sessions whose first page is each landing page, ordered by count descending.

## Acceptance Criteria
- `scripts/sessionize.py` defines `assign_sessions`, `session_summary`, and `entry_pages` with the behavior above.
- Session boundaries respect the per-user timeout; numbering restarts per user.
- Summaries are flat, sorted, and contiguously indexed.
- All functions leave their inputs unmodified.
- The following command passes from the repository root:

```
python -m pytest scripts/tests/test_sessionize.py -q
```
