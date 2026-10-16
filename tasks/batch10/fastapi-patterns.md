# Task: Add a Tag-Filtered Item Listing with a Validated Tag List

## Background

The full-stack FastAPI template (https://github.com/fastapi/full-stack-fastapi-template) stores items with a free-text `title` and `description` in `backend/app/models.py`, served from `backend/app/api/routes/items.py`. The product team wants the current user to filter their own items by one or more keyword tokens, supplied as a repeatable query parameter, where an item matches if its title contains all requested tokens.

## Files to Create/Modify

- `backend/app/api/routes/items.py` (modify) — add the tag-filtered listing endpoint to the items router
- `backend/app/models.py` (modify) — reuse or add the response model for the filtered page
- `backend/tests/api/routes/test_items.py` (modify) — add tests for the tag-filtered listing

## Requirements

### Tag-Filtered Listing Endpoint

- Add a new authenticated `GET` route on the items router (for example under a `/filter` path) that returns a paginated page of the caller's own items, filtered by a list of keyword tokens supplied as a repeatable query parameter (for example `?tag=foo&tag=bar`).
- The token list must contain at least one token; a request with no tokens must be rejected with HTTP 422. Each token must be a non-empty string.
- An item matches only if its title contains every requested token (case-insensitive, logical AND across tokens). Only the caller's own items are eligible.
- Accept pagination: an offset (`skip`, `>= 0`) and a page size (`limit`, within `1..100`); out-of-range values must be rejected with HTTP 422.
- The response must include the page of matching items plus the total number of the caller's items matching the full token set (independent of pagination). Each item must expose only the public item field set.

### Expected Functionality

- For a caller owning items titled "alpha beta", "alpha gamma", and "delta", `?tag=alpha` returns the first two and a total of 2.
- `?tag=alpha&tag=beta` returns only "alpha beta" and a total of 1.
- A request with no `tag` parameter is rejected with HTTP 422.
- `limit=0` or `skip=-1` produce HTTP 422.
- An unauthenticated request is rejected (HTTP 401), and the listing never includes items owned by other users.

## Acceptance Criteria

- The tag-filtered listing endpoint is registered on the items router and requires authentication.
- Multi-token matching uses case-insensitive logical-AND over the title, scoped to the caller's own items, with an accurate filter-aware total alongside the page.
- An empty token set and out-of-range pagination produce HTTP 422.
- Responses are limited to the public item shape and never include other users' items.
- `pytest backend/tests/api/routes/test_items.py` passes, including the added cases.
