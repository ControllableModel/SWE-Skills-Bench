# Task: Add a Public Service Info Endpoint

## Background

The full-stack FastAPI template (https://github.com/fastapi/full-stack-fastapi-template) keeps a small set of operational endpoints in `backend/app/api/routes/utils.py`, including a health check. Monitoring tooling needs a public endpoint that reports a few structured pieces of service metadata.

## Files to Create/Modify

- `backend/app/api/routes/utils.py` (modify) — add the service-info endpoint to the utils router
- `backend/app/models.py` (modify) — add the response model describing the service-info payload
- `backend/tests/api/routes/test_utils.py` (new) — add tests for the service-info endpoint

## Requirements

### Service Info Endpoint

- Add a public, unauthenticated `GET` route on the utils router (for example under an `/info` path) that returns a structured object with named fields describing the running service.
- The payload must include at minimum: the project name (read from application settings), the configured environment name (read from settings), and a boolean indicating whether the API is healthy (always `true` from this endpoint).
- The response must be shaped by an explicit response model so that the returned object contains exactly the agreed named fields and nothing more — internal settings, secrets, or unrelated configuration must never appear.
- The endpoint must not require any database access and must not block; it only reflects in-process settings.

### Expected Functionality

- A `GET` to the info route succeeds without authentication and returns the project name and environment matching the application settings, plus a healthy flag of `true`.
- The response body contains only the agreed named fields; no secret or unrelated settings value is exposed.
- The endpoint is reachable when the database is unavailable (it performs no DB query).

## Acceptance Criteria

- The service-info endpoint is registered on the utils router and is reachable without authentication.
- The response is shaped by an explicit response model and contains exactly the agreed named fields with values matching application settings.
- No secret or unrelated configuration leaks into the response.
- `pytest backend/tests/api/routes/test_utils.py` passes, including the added cases.
