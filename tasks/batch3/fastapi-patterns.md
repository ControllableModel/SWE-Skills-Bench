# Task: Add an Admin-Only Maintenance Sub-Router

## Background

The full-stack FastAPI template (https://github.com/fastapi/full-stack-fastapi-template) wires its routers together in `backend/app/api/main.py` and already has a superuser guard `get_current_active_superuser` in `backend/app/api/deps.py`. The operations team needs a small group of maintenance endpoints that are reachable only by superusers, grouped under a single `/admin` prefix.

## Files to Create/Modify

- `backend/app/api/routes/admin.py` (new) — a new router exposing the maintenance endpoints
- `backend/app/api/main.py` (modify) — register the new router
- `backend/app/models.py` (modify) — add response model(s) for the maintenance payloads if needed
- `backend/tests/api/routes/test_admin.py` (new) — tests for the maintenance endpoints

## Requirements

### Router and Access Control

- Create a new router mounted under the `/admin` prefix with a `admin` tag. Every endpoint on this router must require an active superuser; a normal authenticated user must receive HTTP 403 and an unauthenticated request must receive HTTP 401. The superuser requirement must be enforced for all current and future routes on this router without repeating the guard on each individual route.

### Endpoints

- A `GET` "counts" route that returns the total number of users and the total number of items currently stored, as a small structured object with named integer fields.
- A `GET` "orphan-items" route that returns the number of items whose owner no longer exists in the users table (this count is `0` in normal operation but the endpoint must compute it correctly).

### Expected Functionality

- A superuser calling the counts route receives an object with a user count and an item count that match the real number of stored rows.
- A normal user calling either route receives HTTP 403.
- An unauthenticated caller receives HTTP 401.
- The counts route response contains only the agreed named integer fields and no extra data.

## Acceptance Criteria

- The new router is mounted under `/admin` and registered with the application.
- All routes on the router reject non-superusers (403) and unauthenticated callers (401) via a single shared guard rather than per-route repetition.
- The counts and orphan-items routes return accurate values in the agreed structured shape.
- `pytest backend/tests/api/routes/test_admin.py` passes, including the added cases.
