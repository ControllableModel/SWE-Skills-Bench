# Task: Build an Encapsulated Catalog API Module

## Background

This is the [Fastify](https://github.com/fastify/fastify) web-framework repository. The `examples/` directory holds small, self-contained apps that demonstrate how to assemble a real Fastify service (see `examples/use-plugin.js` and `examples/route-prefix.js`). Your task is to add a new example module that exposes a small in-memory product catalog API, plus a deterministic test for it that exercises the module entirely in-process.

## Files to Create/Modify

- `examples/catalog-api.js` (new) — a module that exports a factory building and returning a configured Fastify instance for the catalog API (the module must NOT bind to a network port when required).
- `test/catalog-api.test.js` (new) — a `node:test` test file that imports the factory and verifies all behavior using the in-process request API. No port binding, no real network, no external services.

## Requirements

### Module shape

- `examples/catalog-api.js` must `module.exports` a single factory function (for example `buildCatalogApi`) that takes no required arguments, constructs a Fastify instance using the repository root (`require('..')` / `require('../fastify')`), wires up everything described below, and returns the instance. Requiring the module must have no side effects beyond defining the export (it must not start listening).
- The catalog data is an in-memory list seeded inside the factory. Each item has the fields: `id` (string), `name` (string), `price` (number, > 0), and `tags` (array of strings). Seed at least three items with known, distinct `id` values so the test can assert on them.

### Route group and isolation

- All catalog routes must live under the URL prefix `/api/catalog` and must be contained in their own registered unit, so that route concerns are isolated from the top-level instance. Configuration applied inside that unit (decorators, hooks, error handling) must not leak out to the root instance.

### Endpoints and their input contracts

- `GET /api/catalog/items` — returns the full list. It accepts an optional `tag` query parameter (a non-empty string). When `tag` is provided, only items whose `tags` contain that value are returned. When the query is malformed (e.g. `tag` present but empty), the request must be rejected with a `400` status before any handler logic runs.
- `GET /api/catalog/items/:id` — returns the single item whose `id` matches the path parameter. The `id` parameter must be a non-empty string with a minimum length of 1; a structurally invalid parameter must be rejected with `400`. If the `id` is well-formed but no item matches, respond with `404`.
- `POST /api/catalog/items` — creates a new item from the JSON request body. The body must contain `name` (non-empty string), `price` (number strictly greater than 0), and `tags` (array of strings); these constraints must be enforced before the handler executes. A request whose body is missing a required field, has the wrong type, or violates a numeric/length bound must be rejected with `400` and the item must NOT be added. On success respond with `201` and the created item, including a server-assigned `id`. A subsequent `GET` of the same `id` must return the created item.

### Response shaping

- The success response for the item-collection and single-item endpoints must expose only the documented item fields (`id`, `name`, `price`, `tags`). If the in-memory records ever carry extra internal fields, those must not appear in the serialized response body.

### Error contract

- All error responses produced by this module — both validation failures (`400`) and not-found (`404`) — must be returned as a JSON object with a stable, predictable shape rather than a raw exception or HTML. At minimum each error body must include a numeric `statusCode` field equal to the HTTP status and a human-readable `message` string field. The not-found case for a missing item must be surfaced through this same error shape with `statusCode` equal to `404`.

### Constraints

- The validation, not-found behavior, and error shaping must be driven by the framework's request lifecycle, not by ad-hoc `if`-checks scattered across handlers that re-implement what the framework already provides. A naive implementation that hardcodes responses or skips input validation must fail the acceptance test.
- No global mutable singleton: each call to the factory must yield an independent instance with its own seed data, so that a `POST` against one instance does not affect another.

### Expected Functionality

- `GET /api/catalog/items` -> `200`, JSON array containing every seeded item with exactly the four documented fields.
- `GET /api/catalog/items?tag=<known-tag>` -> `200`, only items carrying that tag.
- `GET /api/catalog/items?tag=` (empty) -> `400` with the error shape.
- `GET /api/catalog/items/<seeded-id>` -> `200`, the matching item.
- `GET /api/catalog/items/<unknown-id>` -> `404` with `statusCode: 404` in the body.
- `POST /api/catalog/items` with a valid body -> `201`, the created item with a new `id`; that `id` is then retrievable via `GET`.
- `POST /api/catalog/items` with `price: 0`, a missing field, or a non-array `tags` -> `400`, and the catalog length is unchanged.

## Acceptance Criteria

- `examples/catalog-api.js` exports a factory that returns a Fastify instance and never binds a port when imported.
- `test/catalog-api.test.js` uses `node:test` (`const { test } = require('node:test')`) and drives the instance entirely in-process via the instance's `inject` API (no real sockets). It must include at least 10 assertions/cases covering: full listing, tag filtering, empty-tag rejection (`400`), single-item fetch, not-found (`404`) with the error shape, successful creation (`201`) followed by retrieval, and at least two distinct invalid-body rejections (`400`) that leave the catalog size unchanged.
- The test must assert on response status codes AND parsed JSON bodies (e.g. `res.json()`), including that success bodies contain exactly the four documented item fields and that error bodies contain a numeric `statusCode` matching the HTTP status.
- The following command passes with all tests green:

  ```
  node --test test/catalog-api.test.js
  ```
