# Task: Centralize Error Handling with a Stable Error Envelope

## Background

This is the [Fastify](https://github.com/fastify/fastify) web-framework repository. The `examples/` directory holds self-contained apps built from the framework root (`require('../fastify')`). Your task is to add an example module whose routes deliberately fail in different ways, all funneled through a single centralized failure handler that returns one stable, machine-readable error envelope.

## Files to Create/Modify

- `examples/error-envelope.js` (new) — a module exporting a factory that builds and returns a configured Fastify instance. Must NOT bind a network port when required.
- `test/error-envelope.test.js` (new) — a `node:test` test file driving the instance in-process. No sockets, no external services.

## Requirements

### Module shape

- `examples/error-envelope.js` must `module.exports` a single factory (for example `buildErrorEnvelope`) taking no required arguments, constructing the instance via the repository root (`require('..')`), wiring up everything below, and returning the instance. Requiring the module must have no side effects beyond defining the export.

### Stable error envelope

- Every error response produced anywhere in this instance must share one consistent JSON shape with these fields and nothing else at the top level:
  - `statusCode` (number) — equals the HTTP status of the response.
  - `code` (string) — a stable, uppercase, application-defined error code (for example `VALIDATION_FAILED`, `NOT_FOUND`, `TEAPOT`, `INTERNAL`).
  - `message` (string) — a human-readable, non-empty description.
- This envelope must be produced centrally, not re-implemented inside each route handler. Internal exception details (stack traces, raw error objects) must never appear in the response body.

### Routes that fail in distinct ways

- `GET /boom` — the handler throws a generic unexpected `Error`. The response must be `500` with `code: "INTERNAL"` and a generic message that does NOT include the thrown error's internal detail.
- `GET /teapot` — the handler fails with an application error carrying HTTP status `418`. The response must be `418` with `code: "TEAPOT"`.
- `POST /validate` — declares a body schema requiring `email` (string) and `age` (integer, minimum `0`). When the body violates the schema, the framework's validation failure must be translated by the central handler into the envelope with status `400` and `code: "VALIDATION_FAILED"`. A valid body returns `200` with `{ "ok": true }`.
- A request to any unregistered route resolves to the envelope with status `404` and `code: "NOT_FOUND"`.

### Constraints

- The translation from a raw framework/validation failure into the envelope must be centralized through the framework's error-handling mechanism (one place), not duplicated as `try/catch` blocks in each handler. A naive implementation that hand-builds different ad-hoc JSON in each route, or leaks the framework's default error body / stack trace, must fail the acceptance test.
- The status code on the wire and the `statusCode` field in the body must always agree.

### Expected Functionality

- `GET /boom` -> `500`, `{ statusCode: 500, code: "INTERNAL", message: <non-empty> }`, message free of the thrown internal text.
- `GET /teapot` -> `418`, `code: "TEAPOT"`.
- `POST /validate` with `{ email: 123 }` or missing `age` -> `400`, `code: "VALIDATION_FAILED"`.
- `POST /validate` with `{ email: "a@b.c", age: 30 }` -> `200`, `{ ok: true }`.
- `GET /no-such-route` -> `404`, `code: "NOT_FOUND"`.
- Every error body has exactly the three envelope fields, with `statusCode` matching the response status.

## Acceptance Criteria

- `examples/error-envelope.js` exports a factory returning a Fastify instance and never binds a port when imported.
- `test/error-envelope.test.js` uses `node:test` (`const { test } = require('node:test')`) and drives the instance in-process via `inject`. It includes at least 10 assertions/cases covering: the `500`/`INTERNAL` path with leak-free message, the `418`/`TEAPOT` path, at least two distinct `400`/`VALIDATION_FAILED` bodies, the `200` happy path, and the `404`/`NOT_FOUND` path, plus a check that each error body has exactly the three envelope fields with `statusCode` equal to the response status.
- The test asserts on status codes AND parsed JSON bodies (`res.json()`).
- The following command passes with all tests green:

  ```
  node --test test/error-envelope.test.js
  ```
