# Task: Add a Reusable Pagination Dependency and Apply It to Item Listing

## Background

The full-stack FastAPI template (https://github.com/fastapi/full-stack-fastapi-template) declares shared dependency helpers in `backend/app/api/deps.py` (e.g. the DB session and current-user dependencies) and repeats raw `skip` / `limit` parameters across listing endpoints such as `read_items` in `backend/app/api/routes/items.py`. The team wants a single, validated, reusable pagination input that listing endpoints can share.

## Files to Create/Modify

- `backend/app/api/deps.py` (modify) — add a reusable pagination dependency and a type alias for it
- `backend/app/api/routes/items.py` (modify) — use the reusable pagination input in the existing item-listing endpoint
- `backend/tests/api/routes/test_items.py` (modify) — add tests covering pagination validation on the listing endpoint

## Requirements

### Reusable Pagination Dependency

- Add a dependency in `deps.py` that produces a small pagination object carrying `skip` and `limit`, validated from the request query parameters. `skip` must be `>= 0` and `limit` must be within `1..100`. Out-of-range values must yield HTTP 422.
- Provide a reusable, importable type alias for this dependency so that multiple endpoints can declare it as a single parameter rather than re-declaring `skip` and `limit` individually.

### Apply to Item Listing

- Update the existing authenticated item-listing endpoint (`GET /items/`) to obtain its pagination from the new shared dependency instead of declaring `skip` / `limit` inline.
- The listing behavior must remain otherwise unchanged: the same authenticated owner-scoping rules, the same `data` + `count` response shape, and the same ordering.

### Expected Functionality

- `GET /items/?skip=0&limit=10` returns up to 10 of the caller's items with the existing `data`/`count` shape.
- `GET /items/?limit=0`, `GET /items/?limit=101`, and `GET /items/?skip=-1` are rejected with HTTP 422.
- Default behavior (no query parameters) continues to work and returns the caller's items.
- All previously passing item-listing tests continue to pass.

## Acceptance Criteria

- A single reusable pagination dependency with an importable type alias exists in `deps.py` and validates `skip`/`limit` bounds (422 on out-of-range).
- The item-listing endpoint consumes pagination through the shared dependency, with unchanged owner-scoping, response shape, and ordering.
- `pytest backend/tests/api/routes/test_items.py` passes, including the added cases.
