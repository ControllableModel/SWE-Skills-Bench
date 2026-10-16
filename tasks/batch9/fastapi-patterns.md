# Task: Add a Per-User Item-Count Summary Endpoint

## Background

The full-stack FastAPI template (https://github.com/fastapi/full-stack-fastapi-template) relates each user to their items through the `User.items` relationship in `backend/app/models.py`, with user routes in `backend/app/api/routes/users.py`. Administrators want a summary of how many items each user owns.

## Files to Create/Modify

- `backend/app/api/routes/users.py` (modify) — add the summary endpoint to the users router
- `backend/app/models.py` (modify) — add the response model(s) describing the per-user summary rows and the page wrapper
- `backend/tests/api/routes/test_users.py` (modify) — add tests for the summary endpoint

## Requirements

### Summary Endpoint

- Add a superuser-only `GET` route on the users router (for example under an `/item-counts` path) that returns a paginated list of summary rows, one per user, where each row contains the user's identifier, the user's email, and the number of items that user owns.
- Accept pagination query parameters: an offset (`skip`, `>= 0`) and a page size (`limit`, within `1..100`). Out-of-range values must be rejected with HTTP 422.
- The response must include the page of summary rows plus the total number of users (independent of pagination).
- Users who own zero items must still appear with an item count of `0`.
- Each summary row must expose only the agreed fields (user identifier, email, item count) and must never include hashed passwords or other secret columns.
- A normal user receives HTTP 403; an unauthenticated caller receives HTTP 401.

### Expected Functionality

- A superuser calling the endpoint receives a page of rows; a user with three items shows an item count of 3, and a user with no items shows `0`.
- The reported total equals the real number of users.
- `limit=0` or `skip=-1` produce HTTP 422.
- A normal user receives HTTP 403; an unauthenticated caller receives HTTP 401.
- No summary row exposes a hashed password or other secret field.

## Acceptance Criteria

- The summary endpoint is registered on the users router and restricted to superusers.
- Each row reports the correct per-user item count (including `0` for users with no items), alongside an accurate total and validated pagination (422 on out-of-range).
- Rows are limited to the agreed fields and never leak secret columns.
- `pytest backend/tests/api/routes/test_users.py` passes, including the added cases.
