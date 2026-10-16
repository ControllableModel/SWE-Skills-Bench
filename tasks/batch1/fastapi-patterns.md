# Task: Add a Public Paginated Item Catalog with Filtering and Aggregate Stats

## Background

The full-stack FastAPI template (https://github.com/fastapi/full-stack-fastapi-template) exposes an `Item` resource that is owned by authenticated users and served from `backend/app/api/routes/items.py`. The project needs a **read-only public catalog** so that items can be browsed without authentication, plus a small **aggregate stats** endpoint. Only public-facing fields may be exposed, and the existing owner-scoped endpoints must be left intact.

## Files to Create/Modify

- `backend/app/api/routes/items.py` (modify) — add the public catalog listing endpoint and the stats endpoint to the items router
- `backend/app/models.py` (modify) — add the response model(s) used to shape the catalog page and the stats payload
- `backend/app/crud.py` (modify) — add query helpers for filtered listing and for the aggregate counts
- `backend/tests/api/routes/test_items.py` (modify) — add tests exercising the new public endpoints

## Requirements

### Catalog Listing Endpoint

- Expose a public `GET` route on the items router (e.g. under a `/catalog` path) that requires no authentication and returns a paginated page of items.
- Accept query parameters for pagination and search: an offset (`skip`, must be `>= 0`), a page size (`limit`, must be within `1..100`), and an optional case-insensitive title filter (`q`).
- The response must include both the page of items and the **total number of items matching the current filter** (independent of pagination), so a client can render page counts.
- Each returned item must expose only public fields (identifier, title, description, owner identifier). Internal-only or sensitive attributes must never appear in the response body.
- Out-of-range pagination values (e.g. `limit` above the maximum, negative `skip`) must be rejected with HTTP 422 rather than silently clamped.

### Stats Endpoint

- Expose a public `GET` stats route that returns aggregate counts: the total number of items and the number of items matching an optional `q` title filter using the same matching rule as the listing endpoint.
- The two counts must be consistent with what the listing endpoint reports for the same `q`.

### Expected Functionality

- `GET /catalog?limit=10&skip=0` on a catalog of 3 items returns all 3 items and a total of 3.
- `GET /catalog?q=alpha` returns only items whose title contains "alpha" (case-insensitive) and a total reflecting just those matches.
- `GET /catalog?limit=2&skip=2` returns the third item only, while still reporting the full filtered total.
- `GET /catalog?limit=0` and `GET /catalog?skip=-1` are rejected with HTTP 422.
- A catalog response never contains fields beyond the agreed public shape, even though items are stored with owner and internal metadata.
- `GET` stats with `q=alpha` reports a matching count equal to the number of items the listing endpoint returns for `q=alpha`.

## Acceptance Criteria

- The public catalog and stats endpoints are reachable without authentication and are registered on the existing items router.
- Listing responses contain a page of items plus an accurate filter-aware total count; pagination and the `q` filter combine correctly.
- Item objects in responses are limited to the public field set and never leak owner-internal or sensitive fields.
- Invalid pagination parameters produce HTTP 422 validation errors instead of unbounded or negative queries.
- The stats endpoint's totals stay consistent with the listing endpoint for the same filter.
- `pytest backend/tests/api/routes/test_items.py` passes, including the added cases.
