# Task: Build a Schema-Validated Paginated Listing Endpoint

## Background

This is the [Fastify](https://github.com/fastify/fastify) web-framework repository. The `examples/` directory holds small self-contained apps assembled from the framework root (`require('../fastify')`). Your task is to add an example module exposing a paginated, query-driven listing endpoint over an in-memory dataset, plus a deterministic in-process test.

## Files to Create/Modify

- `examples/orders-listing.js` (new) — a module that exports a factory building and returning a configured Fastify instance. The module must NOT bind a network port when required.
- `test/orders-listing.test.js` (new) — a `node:test` test file that imports the factory and verifies all behavior via the instance's in-process request API. No sockets, no external services.

## Requirements

### Module shape

- `examples/orders-listing.js` must `module.exports` a single factory (for example `buildOrdersListing`) that takes no required arguments, constructs the instance using the repository root (`require('..')` / `require('../fastify')`), wires up the endpoint below, and returns the instance. Requiring the module must have no side effects beyond defining the export.
- The dataset is an in-memory array of at least 25 order records seeded inside the factory. Each order has `id` (string), `customer` (string), `total` (number), and `status` (string, one of `"open"`, `"paid"`, `"cancelled"`). Seeds must have deterministic, predictable `id`s and a known distribution of statuses so the test can assert exact counts.

### Endpoint and input contract

- `GET /orders` returns a page of orders. It accepts these optional query parameters, which must be declared and enforced before any handler logic runs:
  - `page` — integer, minimum `1`, default `1`.
  - `limit` — integer, minimum `1`, maximum `50`, default `10`.
  - `status` — string restricted to the closed set `open`, `paid`, `cancelled`.
- Query values arrive as strings on the wire; `page` and `limit` must be coerced to numbers by the request lifecycle so the handler receives real integers (the response must reflect numeric, not string, values).
- A request with `page=0`, `limit=0`, `limit=51`, a non-integer `page`, or a `status` outside the allowed set must be rejected with `400` before the handler executes. The dataset must not be touched on rejection.

### Response shape

- The success response (`200`) is a JSON object with: `page` (number), `limit` (number), `total` (number — count of records matching the active `status` filter, across all pages), and `items` (array of order records for the requested page). When `status` is provided, both `total` and `items` reflect only matching records. Pagination is applied after filtering.
- Each item in `items` exposes exactly `id`, `customer`, `total`, `status` and no other fields.

### Constraints

- Validation, coercion, and defaulting must be driven by the framework's request lifecycle, not by ad-hoc parsing/`if`-checks inside the handler. A naive implementation that reads `req.query.page` as a raw string, applies no bounds, or skips validation must fail the acceptance test.

### Expected Functionality

- `GET /orders` (no query) -> `200`, `page=1`, `limit=10`, `items.length === 10`, `total === 25`.
- `GET /orders?page=3&limit=10` -> `200`, `items.length === 5` (last page).
- `GET /orders?status=paid` -> `200`, `total` equals the seeded count of paid orders; every item has `status === "paid"`.
- `GET /orders?limit=51` -> `400`; `GET /orders?page=0` -> `400`; `GET /orders?status=bogus` -> `400`.
- Response `page` and `limit` are JSON numbers, not strings.

## Acceptance Criteria

- `examples/orders-listing.js` exports a factory returning a Fastify instance and never binds a port when imported.
- `test/orders-listing.test.js` uses `node:test` (`const { test } = require('node:test')`) and drives the instance entirely in-process via `inject` (no real sockets). It includes at least 10 assertions/cases covering: default page, explicit page/limit, last-page partial page, status filtering with exact `total`, numeric (not string) `page`/`limit` in the body, and at least three distinct out-of-bounds/invalid-query rejections (`400`).
- The test asserts on status codes AND parsed JSON bodies (`res.json()`), including item field whitelisting and numeric typing of `page`/`limit`.
- The following command passes with all tests green:

  ```
  node --test test/orders-listing.test.js
  ```
