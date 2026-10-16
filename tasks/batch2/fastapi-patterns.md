# Task: Add Bulk Item Creation for the Current User

## Background

The full-stack FastAPI template (https://github.com/fastapi/full-stack-fastapi-template) lets an authenticated user create items one at a time via `POST /items/` in `backend/app/api/routes/items.py`. The product team wants an authenticated endpoint that accepts several new items in a single request and persists all of them for the current user.

## Files to Create/Modify

- `backend/app/api/routes/items.py` (modify) — add the bulk-create endpoint to the items router
- `backend/app/models.py` (modify) — add any response model needed to return the created items together
- `backend/tests/api/routes/test_items.py` (modify) — add tests for the bulk-create endpoint

## Requirements

### Bulk Create Endpoint

- Add a new authenticated `POST` route on the items router (for example under a `/bulk` path) that accepts a JSON array of new-item payloads and creates them all for the authenticated user.
- The request body is a list of item-creation objects, each carrying a `title` (required, non-empty, max length 255) and an optional `description`. The same validation rules already used for single-item creation must apply to every element of the list.
- The list must contain at least one element; an empty array must be rejected with HTTP 422.
- Every created item must be owned by the authenticated caller, regardless of any owner field a client might attempt to send.
- The response must return the created items and a count of how many were created. Each returned item must expose only the public field set (identifier, title, description, owner identifier, creation timestamp) and never internal or unrelated attributes.

### Expected Functionality

- A request with three valid item objects creates three items, all owned by the caller, and the response reports a count of 3 with the three items echoed back.
- A request whose body is an empty array `[]` is rejected with HTTP 422.
- A request where one element has an empty `title` is rejected with HTTP 422 and no items are persisted.
- An unauthenticated request is rejected (HTTP 401).
- After a successful bulk create, the existing `GET /items/` listing for that user reflects the newly added items.

## Acceptance Criteria

- The bulk-create endpoint is registered on the existing items router and requires authentication.
- A list body of valid items creates exactly that many items, all owned by the caller, and returns them with an accurate count.
- Empty-list bodies and bodies containing an invalid element produce HTTP 422 and persist nothing.
- Responses never leak fields outside the agreed public item shape.
- `pytest backend/tests/api/routes/test_items.py` passes, including the added cases.
