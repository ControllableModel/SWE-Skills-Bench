# Task: Build a Multi-Method Webhook Dispatcher Module

## Background

The `hono` repository ships small, self-contained helper modules under `src/helper/` (for example `src/helper/route/` and `src/helper/proxy/`), each exporting a focused feature plus a colocated `index.test.ts`. This task adds a new helper module that exposes a single webhook endpoint that behaves differently depending on the HTTP method and an incoming signature header.

## Files to Create/Modify

- `src/helper/webhook-dispatcher/index.ts` (new) — the webhook dispatcher module.
- `src/helper/webhook-dispatcher/index.test.ts` (new) — the deterministic test suite for the module.

## Requirements

### Module Surface

The module must export a factory function named `createWebhook(secret: string)`. Calling it returns a fresh, fully independent sub-application instance that records received events in its own private in-memory log. Two separate calls must never share state. The returned sub-application must be mountable into a parent application under an arbitrary prefix.

### Routes and Behavior

A single hook endpoint at the collection root accepts multiple HTTP methods. The contract must hold both when the sub-application is exercised directly and when it is mounted beneath a non-empty prefix.

#### Receiving events
- The hook endpoint at the root must respond to the methods `POST`, `PUT`, and `DELETE`. Any of these, when authorized (see below), appends a record `{ "method": <the HTTP method as uppercase string>, "id": <number> }` to the log and returns `202` with the appended record as JSON. The `id` of each appended record is a distinct, monotonically increasing integer within the instance.
- A `GET` request to the root must NOT be accepted by the hook endpoint; it returns `405` with a JSON body `{ "error": <string> }` and the `Allow` response header listing the accepted methods.

#### Authorization
- Every accepted method requires the request header `X-Webhook-Secret` to exactly equal the `secret` passed to `createWebhook`. If the header is missing or does not match, the request returns `401` with a JSON body `{ "error": <string> }` and nothing is appended to the log.

#### Inspecting the log
- A `GET` request to a separate `/events` path returns `200` with a JSON body `{ "events": [...] }` listing every appended record in append order.
- A `GET` request to `/events` supports a `method` query parameter; when present, only records whose `method` equals that exact value (case-insensitively compared as uppercase) are returned.

### Constraints and Edge Cases

- The accepted-methods set for the hook endpoint is exactly `POST`, `PUT`, `DELETE`; an unaccepted method on the root yields `405`, not `404`.
- Unauthorized requests (`401`) must never mutate the log or advance the id counter.
- Records appear in the log in the order they were accepted, with strictly increasing ids.
- All behavior must be verifiable through in-memory request dispatch (no network, no external services).

### Expected Functionality

- `POST` to root with correct secret -> `202`, record `{ "method": "POST", "id": 1 }`.
- `PUT` then `DELETE` with correct secret -> ids `2` then `3`.
- `POST` to root with wrong/absent secret -> `401`, log unchanged.
- `GET` root -> `405` with an `Allow` header.
- `GET /events?method=put` -> only the `PUT` records.

## Acceptance Criteria

- `src/helper/webhook-dispatcher/index.ts` exports `createWebhook`, which returns a value mountable into a parent application, with each call producing an isolated in-memory log and id counter.
- All method-routing, authorization, status-code (`202`/`401`/`405`), `Allow`-header, ordering, and filtering behaviors above are satisfied, verified by dispatching in-memory requests against both a directly-used and a mounted instance.
- A naive implementation (e.g. accepting all methods, skipping the secret check, returning `404` for `GET` on the root, or sharing the log globally) must fail the test suite.
- The colocated test suite contains at least 10 distinct test cases and passes with:

```
npx vitest --run src/helper/webhook-dispatcher/index.test.ts
```
