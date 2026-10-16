# Task: Add Item Ownership Transfer

## Background

The full-stack FastAPI template (https://github.com/fastapi/full-stack-fastapi-template) ties each item to an owner via `owner_id` in `backend/app/models.py`, with item routes in `backend/app/api/routes/items.py`. Administrators need to reassign an item from its current owner to a different existing user.

## Files to Create/Modify

- `backend/app/api/routes/items.py` (modify) — add the transfer endpoint to the items router
- `backend/app/models.py` (modify) — add the request/response model(s) for the transfer if needed
- `backend/tests/api/routes/test_items.py` (modify) — add tests for the transfer endpoint

## Requirements

### Transfer Endpoint

- Add a superuser-only route on the items router that reassigns a single item to a new owner. The item is identified by a path parameter, and the new owner's identifier is supplied in the request (path, query, or body — your choice, but it must be validated as a UUID).
- The item identifier path parameter must be validated as a UUID; a malformed identifier must produce HTTP 422.
- If the item does not exist, respond with HTTP 404. If the target owner user does not exist, respond with HTTP 404. If the target owner is the same as the current owner, respond with HTTP 400.
- On success, the item's `owner_id` is updated to the target user and the updated item is returned, exposing only the public item field set.
- Only a superuser may perform a transfer; a normal user receives HTTP 403 and an unauthenticated caller receives HTTP 401.

### Expected Functionality

- A superuser transferring an existing item to a different existing user succeeds, and the returned item shows the new owner identifier.
- Transferring a nonexistent item yields HTTP 404; transferring to a nonexistent target user yields HTTP 404.
- Transferring an item to its current owner yields HTTP 400.
- A malformed item identifier in the path yields HTTP 422.
- A normal user receives HTTP 403; an unauthenticated caller receives HTTP 401.

## Acceptance Criteria

- The transfer endpoint is registered on the items router and restricted to superusers.
- Item and target-owner identifiers are validated as UUIDs, with the documented 404/400/422 outcomes for missing item, missing target, same-owner, and malformed-id cases.
- On success the item's owner is updated and the response is limited to the public item shape.
- `pytest backend/tests/api/routes/test_items.py` passes, including the added cases.
