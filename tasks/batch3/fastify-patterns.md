# Task: Assemble Two Independently Encapsulated API Versions

## Background

This is the [Fastify](https://github.com/fastify/fastify) web-framework repository. The `examples/route-prefix.js` example shows mounting sub-instances under different prefixes. Your task is to add an example module that composes two independently encapsulated API versions on a single instance, where each version carries its own private configuration that must not leak into the other or into the root.

## Files to Create/Modify

- `examples/versioned-api.js` (new) — a module exporting a factory that builds and returns a configured Fastify instance with two versioned sub-units. Must NOT bind a network port when required.
- `test/versioned-api.test.js` (new) — a `node:test` test file driving the instance in-process. No sockets, no external services.

## Requirements

### Module shape

- `examples/versioned-api.js` must `module.exports` a single factory (for example `buildVersionedApi`) that takes no required arguments, constructs the instance via the repository root (`require('..')`), wires up everything below, and returns the instance. Requiring the module must have no side effects beyond defining the export.

### Two isolated versions

- The instance mounts two route groups, each as its own registered, encapsulated unit:
  - One group serves requests under the URL prefix `/api/v1`.
  - One group serves requests under the URL prefix `/api/v2`.
- Each group privately attaches a value identifying its version (for example a per-group accessor returning the string `"v1"` or `"v2"`) that its own routes use. This per-group value must be visible only inside its own unit: it must NOT be reachable from the other version's unit, and must NOT be reachable from the root instance after the instance is ready.

### Endpoints

- Both versions expose `GET /info`, resolving to `/api/v1/info` and `/api/v2/info` respectively.
  - `/api/v1/info` returns a JSON object `{ "version": "v1", "fields": ["id", "name"] }`.
  - `/api/v2/info` returns a JSON object `{ "version": "v2", "fields": ["id", "name", "email"] }`.
  - The `version` value in each response MUST come from that group's privately attached version value (proving isolation), not from a literal duplicated across both handlers in a way that ignores encapsulation.
- Both versions expose `GET /ping` -> `200` with body `{ "pong": true }`, demonstrating each group routes independently.
- A request to a prefix that does not exist (for example `/api/v3/info`) resolves to `404`.

### Constraints

- The two versions must be genuinely isolated registered units; configuration applied inside one (its private version value, any decorators or hooks) must not appear on the other unit or on the root. A flat implementation that registers both sets of routes on the root instance and reads a single shared variable must fail the acceptance test, which probes that the root instance does NOT expose either version's private value once ready.

### Expected Functionality

- `GET /api/v1/info` -> `200`, `{ version: "v1", fields: ["id","name"] }`.
- `GET /api/v2/info` -> `200`, `{ version: "v2", fields: ["id","name","email"] }`.
- `GET /api/v1/ping` and `GET /api/v2/ping` -> `200`, `{ pong: true }`.
- `GET /api/v3/info` -> `404`.
- After `await app.ready()`, the root instance does NOT expose the private per-version value of either group.

## Acceptance Criteria

- `examples/versioned-api.js` exports a factory returning a Fastify instance and never binds a port when imported.
- `test/versioned-api.test.js` uses `node:test` (`const { test } = require('node:test')`) and drives the instance in-process via `inject`. It includes at least 10 assertions/cases covering: both `/info` endpoints with their distinct bodies, both `/ping` endpoints, the unknown-prefix `404`, and an explicit isolation check proving the root instance does not expose either group's private version value after `ready()`.
- The test asserts on status codes AND parsed JSON bodies (`res.json()`).
- The following command passes with all tests green:

  ```
  node --test test/versioned-api.test.js
  ```
