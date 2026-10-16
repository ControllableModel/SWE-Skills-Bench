# Task: Enforce Response Serialization to Hide Sensitive Fields

## Background

This is the [Fastify](https://github.com/fastify/fastify) web-framework repository. The `examples/shared-schema.js` example shows attaching response schemas to routes. Your task is to add an example module whose user records carry sensitive internal fields that must never reach the client, enforced through response serialization rather than manual field-stripping.

## Files to Create/Modify

- `examples/safe-serialization.js` (new) — a module exporting a factory that builds and returns a configured Fastify instance. Must NOT bind a network port when required.
- `test/safe-serialization.test.js` (new) — a `node:test` test file driving the instance in-process. No sockets, no external services.

## Requirements

### Module shape

- `examples/safe-serialization.js` must `module.exports` a single factory (for example `buildSafeSerialization`) taking no required arguments, constructing the instance via the repository root (`require('..')`), wiring up everything below, and returning the instance. Requiring the module must have no side effects beyond defining the export.

### Internal records

- The factory seeds an in-memory list of at least three user records. Each record carries BOTH public fields — `id` (string), `username` (string), `email` (string) — AND sensitive internal fields that must never be serialized to clients, including at least `passwordHash` (string) and `internalNotes` (string). The handlers may pass the full internal records to the reply; the serialization layer is responsible for withholding the sensitive fields.

### Endpoints with response schemas

- `GET /users` returns `200` with a JSON array; each element must expose ONLY `id`, `username`, `email`. `passwordHash`, `internalNotes`, and any other internal field must be absent from every element.
- `GET /users/:id` returns `200` with a single object exposing ONLY `id`, `username`, `email`; sensitive fields absent. If the `id` matches no record, respond `404` with a JSON body containing `statusCode: 404`.
- `GET /users/:id/admin` returns `200` with an object that DOES include `id`, `username`, `email`, and `internalNotes` (an admin view), but still must NOT include `passwordHash`. This proves the whitelisting is per-route response-schema-driven, not a single global blacklist.

### Constraints

- The hiding of sensitive fields must be enforced by attaching response schemas to the routes so the framework's serializer emits only declared properties — not by manually building trimmed objects (for example via destructuring or `delete`) inside the handlers. A naive implementation that hand-strips fields, or that returns the raw record, must fail the acceptance test (the test passes full internal records through and verifies the wire output is filtered).
- The set of allowed fields differs between the public routes and the admin route, demonstrating per-route response shaping.

### Expected Functionality

- `GET /users` -> `200`, array where every element has exactly `id`, `username`, `email`; no element contains `passwordHash` or `internalNotes`.
- `GET /users/<seeded-id>` -> `200`, object with exactly `id`, `username`, `email`.
- `GET /users/<unknown-id>` -> `404`, body has `statusCode: 404`.
- `GET /users/<seeded-id>/admin` -> `200`, object containing `internalNotes` but NOT `passwordHash`.

## Acceptance Criteria

- `examples/safe-serialization.js` exports a factory returning a Fastify instance and never binds a port when imported.
- `test/safe-serialization.test.js` uses `node:test` (`const { test } = require('node:test')`) and drives the instance in-process via `inject`. It includes at least 10 assertions/cases covering: list endpoint field whitelisting across every element, single-item whitelisting, the `404` path with `statusCode: 404`, the admin view including `internalNotes`, the admin view still excluding `passwordHash`, and explicit assertions that `passwordHash` is absent from public responses.
- The test asserts on status codes AND parsed JSON bodies (`res.json()`), checking both the presence of allowed fields and the absence of sensitive ones.
- The following command passes with all tests green:

  ```
  node --test test/safe-serialization.test.js
  ```
