# Task: Build a Request Lifecycle Audit and Normalization Pipeline

## Background

This is the [Fastify](https://github.com/fastify/fastify) web-framework repository. The `examples/hooks.js` example demonstrates the request lifecycle hook points. Your task is to add an example module that uses lifecycle hooks to normalize incoming data and record an in-memory audit trail of each handled request, then exposes that trail for inspection.

## Files to Create/Modify

- `examples/audit-pipeline.js` (new) — a module exporting a factory that builds and returns a configured Fastify instance, plus an accessor to read the recorded audit trail. Must NOT bind a network port when required.
- `test/audit-pipeline.test.js` (new) — a `node:test` test file driving the instance in-process. No sockets, no external services.

## Requirements

### Module shape

- `examples/audit-pipeline.js` must `module.exports` a single factory (for example `buildAuditPipeline`) taking no required arguments, constructing the instance via the repository root (`require('..')`), wiring up everything below, and returning the instance. The recorded audit trail must be reachable for assertions (for example via an instance accessor such as `app.auditTrail()` returning the array). Requiring the module must have no side effects beyond defining the export.

### Normalization before the handler

- `POST /signup` declares a body schema requiring `email` (string) and `name` (string). Before the route handler runs, a lifecycle step must normalize the validated body so the handler receives `email` lowercased and trimmed, and `name` trimmed. The normalization must happen after schema validation has accepted the body and before the handler executes, so the handler operates on already-clean data.
- The handler returns `200` with `{ "email": <normalized>, "name": <normalized> }`.
- A body that fails the schema (missing `email`, wrong type) is rejected with `400` before normalization and before the handler, and such a request must NOT be appended to the audit trail.

### Audit recording after the response

- For every request that produces a final response, a lifecycle step running after the response is sent must append one record to the in-memory audit trail with: `method` (string), `url` (string), and `statusCode` (number). Records are appended in request order.
- The audit trail starts empty and persists across requests within the same instance. Each factory call yields its own independent trail.

### Inspection endpoint

- `GET /audit` returns `200` with the current audit trail as a JSON array. (This GET itself will also be recorded; the test must account for ordering.)

### Constraints

- Normalization and audit recording must be implemented through the framework's request lifecycle hook points, not by editing every handler to mutate input and push log entries inline. A naive implementation that normalizes inside each handler, or skips recording rejected vs accepted requests correctly, must fail the acceptance test.

### Expected Functionality

- `POST /signup` with `{ email: "  USER@Example.COM ", name: "  Ada  " }` -> `200`, `{ email: "user@example.com", name: "Ada" }`.
- A failed `POST /signup` (missing `email`) -> `400`, and the audit trail length is unchanged by that request.
- After two successful `POST /signup` calls, the audit trail contains exactly two matching `{ method: "POST", url: "/signup", statusCode: 200 }` records, in order.
- `GET /audit` returns the recorded records as an array.

## Acceptance Criteria

- `examples/audit-pipeline.js` exports a factory returning a Fastify instance with a readable audit trail, and never binds a port when imported.
- `test/audit-pipeline.test.js` uses `node:test` (`const { test } = require('node:test')`) and drives the instance in-process via `inject`. It includes at least 10 assertions/cases covering: normalization of email/name on success, schema rejection (`400`) NOT recorded, ordered audit records for multiple successful requests with correct `method`/`url`/`statusCode`, two independent instances having independent trails, and the `GET /audit` body being an array.
- The test asserts on status codes AND parsed JSON bodies (`res.json()`) and on the audit trail contents.
- The following command passes with all tests green:

  ```
  node --test test/audit-pipeline.test.js
  ```
