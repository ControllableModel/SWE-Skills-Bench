# Task: Add Batch Deletion of the Current User's Items

## Background

The full-stack FastAPI template (https://github.com/fastapi/full-stack-fastapi-template) deletes items one at a time through `DELETE /items/{id}` in `backend/app/api/routes/items.py`. Users want to remove several of their own items in one request.

## Files to Create/Modify

- `backend/app/api/routes/items.py` (modify) — add the batch-delete endpoint to the items router
- `backend/app/models.py` (modify) — add a response model summarizing the deletion result if needed
- `backend/tests/api/routes/test_items.py` (modify) — add tests for the batch-delete endpoint

## Requirements

### Batch Delete Endpoint

- Add a new authenticated route on the items router (for example `POST /items/batch-delete`) that accepts a JSON array of item identifiers and deletes the matching items that belong to the authenticated user.
- The request body is a list of item identifiers; it must contain at least one identifier, and an empty list must be rejected with HTTP 422.
- A normal user may delete only their own items. Identifiers referring to items owned by someone else, or identifiers that do not exist, must be skipped (not deleted) rather than causing the whole request to fail.
- A superuser may delete any of the listed items.
- The response must report how many items were actually deleted and the identifiers that were not deleted (because they were missing or not owned by the caller), in a structured object with named fields.

### Expected Functionality

- A user submitting three identifiers they own deletes all three; the response reports 3 deleted and an empty "not deleted" list.
- A user submitting a mix of owned and other-owned/nonexistent identifiers deletes only the owned ones; the response reports the deleted count and lists the skipped identifiers.
- An empty array body is rejected with HTTP 422.
- An unauthenticated request is rejected (HTTP 401).
- After a batch delete, the deleted items no longer appear in the caller's `GET /items/` listing.

## Acceptance Criteria

- The batch-delete endpoint is registered on the items router and requires authentication.
- Only items owned by a normal caller are deleted; other identifiers are reported as skipped, not errored.
- Empty-list bodies produce HTTP 422.
- The response accurately reports the deleted count and the skipped identifiers in the agreed structured shape.
- `pytest backend/tests/api/routes/test_items.py` passes, including the added cases.
