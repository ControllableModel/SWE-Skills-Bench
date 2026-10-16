# Task: Build a Content-Negotiating Representation Module

## Background

The `hono` repository ships small, self-contained helper modules under `src/helper/` (for example `src/helper/route/` and `src/helper/css/`), each exporting a focused feature plus a colocated `index.test.ts`. This task adds a new helper module that serves the same resource in different representations based on the request's `Accept` header.

## Files to Create/Modify

- `src/helper/representation/index.ts` (new) — the representation module.
- `src/helper/representation/index.test.ts` (new) — the deterministic test suite for the module.

## Requirements

### Module Surface

The module must export a factory function named `createRepresentation()`. Calling it returns a fresh, independent sub-application instance that serves a fixed in-memory resource (a record with `name` and `count` fields). The returned value must be mountable into a parent application under an arbitrary prefix. Two separate calls must never share state.

### Routes and Behavior

A single resource route at the collection root selects its representation from the request's `Accept` header. The contract must hold both directly and when mounted under a non-empty prefix.

#### Representation selection
- A `GET` request whose `Accept` header is `application/json` returns `200` with a JSON body `{ "name": <string>, "count": <number> }` and a `Content-Type` response header whose value begins with `application/json`.
- A `GET` request whose `Accept` header is `text/html` returns `200` with an HTML body that contains both the resource `name` and the string form of `count`, and a `Content-Type` response header whose value begins with `text/html`.
- A `GET` request whose `Accept` header is `text/plain` returns `200` with a plain-text body of the exact form `<name>:<count>` and a `Content-Type` response header whose value begins with `text/plain`.
- A `GET` request with no recognizable `Accept` header, or one that lists none of the three supported types, returns `406` with a JSON body `{ "error": <string> }`.

#### Mutating the resource
- A `POST` request to the collection root with a JSON body `{ "name": string }` updates the resource's `name`, increments its `count` by one, and returns `200` with a JSON body `{ "name": <string>, "count": <number> }` reflecting the new state.
- Subsequent `GET` requests must reflect the updated `name` and `count` in every representation.

### Constraints and Edge Cases

- Representation selection must inspect the actual `Accept` header value; a wildcard `*/*` must select the JSON representation.
- A `406` response must never mutate the resource.
- `count` starts at `0` and is advanced only by `POST`, never by `GET`.
- All behavior must be verifiable through in-memory request dispatch, inspecting both response bodies and the `Content-Type` response header (no network, no external services).

### Expected Functionality

- `GET` with `Accept: text/plain` after initial state -> body `seed:0` (for a seed name `seed`).
- `GET` with `Accept: text/html` -> body contains the name and count.
- `GET` with `Accept: application/xml` -> `406`.
- `POST` `{ "name": "next" }` then `GET` with `Accept: application/json` -> `{ "name": "next", "count": 1 }`.
- `GET` with `Accept: */*` -> JSON representation.

## Acceptance Criteria

- `src/helper/representation/index.ts` exports `createRepresentation`, which returns a value mountable into a parent application, with each call producing an isolated resource.
- All representation-selection, `Content-Type`-header, status-code (`200`/`406`), and mutation behaviors above are satisfied, verified by dispatching in-memory requests against both a directly-used and a mounted instance.
- A naive implementation (e.g. always returning JSON, ignoring the `Accept` header, or advancing `count` on reads) must fail the test suite.
- The colocated test suite contains at least 10 distinct test cases and passes with:

```
npx vitest --run src/helper/representation/index.test.ts
```
