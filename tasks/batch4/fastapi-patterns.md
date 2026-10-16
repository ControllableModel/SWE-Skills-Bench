# Task: Add a Superuser User-Search Endpoint with Filters

## Background

The full-stack FastAPI template (https://github.com/fastapi/full-stack-fastapi-template) exposes a superuser-only user listing at `GET /users/` in `backend/app/api/routes/users.py`, but it offers no filtering. Administrators need to search users by email fragment and filter by active status.

## Files to Create/Modify

- `backend/app/api/routes/users.py` (modify) — add the search endpoint to the users router
- `backend/app/models.py` (modify) — reuse or add the response model used to shape the search results
- `backend/tests/api/routes/test_users.py` (modify) — add tests for the search endpoint

## Requirements

### Search Endpoint

- Add a superuser-only `GET` route on the users router (for example under a `/search` path) that returns a filtered, paginated page of users.
- Accept query parameters: an optional case-insensitive email substring filter (`email`), an optional boolean `is_active` filter, an offset (`skip`, must be `>= 0`), and a page size (`limit`, must be within `1..100`).
- When `email` is provided, only users whose email contains the given fragment (case-insensitive) are returned. When `is_active` is provided, only users with that active status are returned. The two filters combine (logical AND). When neither is provided, all users are eligible.
- The response must include the page of matching users plus the total number of users matching the current filter, independent of pagination.
- Each returned user must expose only the public, non-sensitive field set. The hashed password and any other secret column must never appear in the response.
- Out-of-range pagination values (`limit` outside `1..100`, negative `skip`) must be rejected with HTTP 422 rather than silently clamped.

### Expected Functionality

- A superuser searching with `email=admin` returns only users whose email contains "admin" (case-insensitive) and a total reflecting just those matches.
- Searching with `is_active=false` returns only inactive users.
- Combining `email=x&is_active=true` returns only active users whose email contains "x".
- A normal user calling the route receives HTTP 403; an unauthenticated caller receives HTTP 401.
- `limit=0` or `skip=-1` produce HTTP 422.
- No response object ever contains a hashed password or other secret field.

## Acceptance Criteria

- The search endpoint is registered on the users router and restricted to superusers.
- Email-substring and active-status filters apply correctly and combine, with an accurate filter-aware total count alongside the page.
- Pagination bounds are enforced (422 on out-of-range values).
- Responses never leak hashed passwords or other secret fields.
- `pytest backend/tests/api/routes/test_users.py` passes, including the added cases.
