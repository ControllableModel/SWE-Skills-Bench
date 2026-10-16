# Task: Build a Centralized Error-Surfacing Module

## Background

The `hono` repository ships small, self-contained helper modules under `src/helper/` (for example `src/helper/route/` and `src/helper/testing/`), each exporting a focused feature plus a colocated `index.test.ts`. This task adds a new helper module that demonstrates a uniform error envelope for a small banking-style resource, where domain failures are surfaced through a single centralized error path.

## Files to Create/Modify

- `src/helper/error-surface/index.ts` (new) — the error-surfacing module.
- `src/helper/error-surface/index.test.ts` (new) — the deterministic test suite for the module.

## Requirements

### Module Surface

The module must export a factory function named `createAccounts()`. Calling it returns a fresh sub-application instance holding its own private in-memory map of accounts (each account has a string `id` and a numeric `balance`, starting at `0`). The returned value must be mountable into a parent application under an arbitrary prefix. Two separate calls hold independent account maps.

Domain operations must signal failures by raising errors that are converted into responses by a single centralized error path on the application, rather than each handler hand-building its own error response. Unmatched routes must be handled by a dedicated not-found path. Both paths must produce the uniform envelope described below.

### Routes and Behavior

The contract must hold both directly and when mounted under a non-empty prefix. Every error response (`400`/`404`/`409`/`500`) must have the JSON body shape `{ "error": { "code": <string>, "message": <string> } }`.

#### Opening an account
- A `POST` request to `/accounts` with a JSON body `{ "id": string }` creates an account with that id and `balance` `0`, returning `201` with the created account as JSON.
- If an account with that id already exists, the operation fails and surfaces as `409` with `error.code` equal to `"conflict"`.
- If the body lacks a string `id`, the operation surfaces as `400` with `error.code` equal to `"bad_request"`.

#### Depositing and withdrawing
- A `POST` request to `/accounts/:id/deposit` with a JSON body `{ "amount": number }` increases the balance and returns `200` with the updated account. A non-positive or non-numeric `amount` surfaces as `400` (`"bad_request"`).
- A `POST` request to `/accounts/:id/withdraw` with a JSON body `{ "amount": number }` decreases the balance and returns `200` with the updated account. Attempting to withdraw more than the current balance surfaces as `409` with `error.code` equal to `"insufficient_funds"`, and the balance is unchanged.
- Any operation targeting an id that does not exist surfaces as `404` with `error.code` equal to `"not_found"`.

#### Unmatched routes
- A request to any path not matching a defined route returns `404` with `error.code` equal to `"not_found"`.

### Constraints and Edge Cases

- All error responses must flow through the centralized error path / not-found path and carry the uniform `{ "error": { "code", "message" } }` envelope; no handler may emit a differently shaped error body.
- Failed operations must never mutate the account map or balances.
- An unexpected internal failure (if reachable) must surface as `500` with `error.code` equal to `"internal"`, still using the uniform envelope.
- All behavior must be verifiable through in-memory request dispatch (no network, no external services).

### Expected Functionality

- `POST /accounts` `{ "id": "a" }` then again -> second is `409` `error.code: "conflict"`.
- deposit `50`, withdraw `70` -> `409` `error.code: "insufficient_funds"`, balance still `50`.
- withdraw on unknown id -> `404` `error.code: "not_found"`.
- deposit with `amount: -5` -> `400` `error.code: "bad_request"`.
- `GET /nope` -> `404` `error.code: "not_found"`.

## Acceptance Criteria

- `src/helper/error-surface/index.ts` exports `createAccounts`, which returns a value mountable into a parent application, with each call producing an isolated account map and all failures routed through a centralized error path and a not-found path.
- All operation, status-code, error-code, envelope-shape, and no-mutation-on-failure behaviors above are satisfied, verified by dispatching in-memory requests against both a directly-used and a mounted instance.
- A naive implementation (e.g. inconsistent error bodies, mutating balances on failed withdrawals, or returning plain strings for errors) must fail the test suite.
- The colocated test suite contains at least 10 distinct test cases and passes with:

```
npx vitest --run src/helper/error-surface/index.test.ts
```
