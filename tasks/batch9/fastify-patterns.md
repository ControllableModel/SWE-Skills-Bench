# Task: Build a Per-Client Request Quota Guard via a Shared Decorator

## Background

This is the [Fastify](https://github.com/fastify/fastify) web-framework repository. The `examples/` directory holds self-contained apps built from the framework root (`require('../fastify')`). Your task is to add an example module that enforces a deterministic, in-memory per-client request quota using a shared counter exposed on the instance and a lifecycle check that runs before handlers.

## Files to Create/Modify

- `examples/quota-guard.js` (new) — a module exporting a factory that builds and returns a configured Fastify instance. Must NOT bind a network port when required.
- `test/quota-guard.test.js` (new) — a `node:test` test file driving the instance in-process. No sockets, no external services.

## Requirements

### Module shape

- `examples/quota-guard.js` must `module.exports` a single factory (for example `buildQuotaGuard`) taking no required arguments, constructing the instance via the repository root (`require('..')`), wiring up everything below, and returning the instance. Requiring the module must have no side effects beyond defining the export.

### Shared quota state

- The instance must carry a single shared, in-memory quota store attached to the instance itself (so it is reachable from the request lifecycle and shared across routes), keyed by client identity. Client identity is taken from the request header `x-client-id`. The limit is a fixed `3` requests per client for the lifetime of the instance (deterministic — no time windows, no clocks, no randomness).

### Guard behavior (before the handler)

- A lifecycle step that runs before every protected route handler must:
  - Reject any request lacking an `x-client-id` header with status `400` and a JSON body containing `statusCode: 400` and a `message`.
  - Count the request against the client's running total. The first `3` requests for a given client id are allowed through; the `4th` and beyond are rejected with status `429` and a JSON body containing `statusCode: 429`, a `message`, and a `remaining` field equal to `0`.
- Successful (allowed) responses must include in their JSON body a `remaining` field reporting how many requests the client has left after this one (`2`, then `1`, then `0`).

### Protected and unprotected routes

- `GET /data` and `GET /report` are both protected by the same shared guard and share the same per-client counter (so requests across the two routes draw from one quota).
- `GET /health` is NOT protected: it returns `200` `{ status: "ok" }` regardless of headers or prior quota usage, proving the guard is scoped to the protected unit and not the whole instance.

### Constraints

- The shared counter must be attached to the instance (a decoration) and the limit enforced by a lifecycle step that runs ahead of handlers — not by a module-level global variable and not by duplicated counting code inside each handler. Each factory call must yield an instance with its own independent quota store. A naive implementation using a file-scoped global, or re-counting inside each route, must fail the acceptance test (which constructs two independent instances and verifies their quotas do not interfere).

### Expected Functionality

- Three `GET /data` requests with the same `x-client-id` -> `200` with `remaining` `2`, `1`, `0` respectively.
- A 4th request for that client (to `/data` or `/report`) -> `429`, body `{ statusCode: 429, message: <non-empty>, remaining: 0 }`.
- A request with no `x-client-id` -> `400`.
- A different `x-client-id` still gets its own first `3` allowed.
- `GET /health` -> `200`, `{ status: "ok" }`, even after a client is over quota.
- Two independent instances do not share quota counts.

## Acceptance Criteria

- `examples/quota-guard.js` exports a factory returning a Fastify instance and never binds a port when imported.
- `test/quota-guard.test.js` uses `node:test` (`const { test } = require('node:test')`) and drives the instance in-process via `inject` (passing `headers: { 'x-client-id': ... }`). It includes at least 10 assertions/cases covering: the three allowed requests with decreasing `remaining`, the `429` on the 4th with `remaining: 0`, the cross-route shared counting (`/data` + `/report`), the missing-header `400`, an independent second client, the unprotected `/health` always `200`, and two factory instances with isolated quotas.
- The test asserts on status codes AND parsed JSON bodies (`res.json()`).
- The following command passes with all tests green:

  ```
  node --test test/quota-guard.test.js
  ```
