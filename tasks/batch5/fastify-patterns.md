# Task: Implement a Custom Not-Found Handler with Suggestions

## Background

This is the [Fastify](https://github.com/fastify/fastify) web-framework repository. The `examples/` directory holds self-contained apps built from the framework root (`require('../fastify')`). Your task is to add an example module that replaces the default not-found behavior with a custom handler returning a structured, helpful response, and that distinguishes a missing path from an unsupported method on a known path.

## Files to Create/Modify

- `examples/not-found-handler.js` (new) — a module exporting a factory that builds and returns a configured Fastify instance. Must NOT bind a network port when required.
- `test/not-found-handler.test.js` (new) — a `node:test` test file driving the instance in-process. No sockets, no external services.

## Requirements

### Module shape

- `examples/not-found-handler.js` must `module.exports` a single factory (for example `buildNotFoundHandler`) taking no required arguments, constructing the instance via the repository root (`require('..')`), wiring up everything below, and returning the instance. Requiring the module must have no side effects beyond defining the export.

### Known routes

- The instance registers a small, fixed set of known routes: `GET /docs`, `GET /users`, and `POST /users`. Each returns `200` with a small JSON body identifying itself (for example `{ "route": "GET /docs" }`).

### Custom not-found behavior

- Any request whose path matches no registered route must be answered by a custom not-found responder (not the framework default), returning status `404` and a JSON body with exactly:
  - `statusCode` (number) equal to `404`,
  - `message` (string, non-empty),
  - `requested` (string) — the path that was requested,
  - `available` (array of strings) — the list of known registered paths, sorted ascending.
- The `available` list must be derived from what was actually registered (so adding a route changes it), not a hardcoded literal that ignores the real route table.

### Method vs path distinction

- `DELETE /users` (a method that is NOT registered on a path that IS registered for other methods) must resolve to `404` through the same custom responder (Fastify routes unmatched methods to the not-found path), and its body's `requested` must reflect `/users`.

### Constraints

- The custom not-found response must be installed via the framework's not-found mechanism so it applies uniformly to every unmatched request, not via a catch-all wildcard route that re-implements matching. A naive implementation that only special-cases a couple of literal paths, or returns the framework default 404 body, must fail the acceptance test.

### Expected Functionality

- `GET /docs` -> `200`, `{ route: "GET /docs" }`.
- `GET /nope` -> `404`, body `{ statusCode: 404, message: <non-empty>, requested: "/nope", available: [...] }` where `available` is the sorted list of registered paths and includes `/docs` and `/users`.
- `DELETE /users` -> `404`, `requested: "/users"`.
- `available` is sorted ascending and contains no duplicates.

## Acceptance Criteria

- `examples/not-found-handler.js` exports a factory returning a Fastify instance and never binds a port when imported.
- `test/not-found-handler.test.js` uses `node:test` (`const { test } = require('node:test')`) and drives the instance in-process via `inject`. It includes at least 10 assertions/cases covering: at least two known routes returning `200`, an unknown path returning the structured `404`, the `available` list being sorted and containing the known paths, the unsupported-method-on-known-path `404` with the correct `requested`, and the not-found body having exactly the four documented fields with `statusCode === 404`.
- The test asserts on status codes AND parsed JSON bodies (`res.json()`).
- The following command passes with all tests green:

  ```
  node --test test/not-found-handler.test.js
  ```
