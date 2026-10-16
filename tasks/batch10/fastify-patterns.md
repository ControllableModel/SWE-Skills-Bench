# Task: Implement Ordered Resource Cleanup on Instance Close

## Background

This is the [Fastify](https://github.com/fastify/fastify) web-framework repository. The `examples/hooks.js` example demonstrates the `onClose` lifecycle hook. Your task is to add an example module that registers two fake downstream resources (for example a "database" and a "queue") and tears them down in a deterministic order when the instance closes, recording the shutdown sequence for inspection.

## Files to Create/Modify

- `examples/graceful-cleanup.js` (new) — a module exporting a factory that builds and returns a configured Fastify instance plus a way to read the recorded shutdown log. Must NOT bind a network port when required.
- `test/graceful-cleanup.test.js` (new) — a `node:test` test file driving the instance in-process. No sockets, no real signals, no external services.

## Requirements

### Module shape

- `examples/graceful-cleanup.js` must `module.exports` a single factory (for example `buildGracefulCleanup`) taking no required arguments, constructing the instance via the repository root (`require('..')`), wiring up everything below, and returning the instance. The shutdown log must be readable for assertions (for example via an instance accessor such as `app.shutdownLog()` returning the array). Requiring the module must have no side effects beyond defining the export. The module must NOT register process signal handlers or call `process.exit` at import time (that would interfere with the test runner).

### Fake resources and a health route

- Inside the factory, model two fake resources, each with a `name` and an async `close()` method that, when awaited, appends its `name` to the shared in-memory shutdown log. Neither resource performs real I/O.
- `GET /status` returns `200` with `{ "open": true }` while the instance is open, confirming the instance serves requests normally before close.

### Cleanup wiring

- When the instance is closed (`await app.close()`), each fake resource's `close()` must be awaited exactly once as part of the instance's shutdown, through the framework's close lifecycle (not by the caller manually invoking the resources). The shutdown log must end up containing both resource names.
- The cleanup must run in a deterministic order: the resource registered later must be closed before the resource registered earlier (last-registered-closes-first). The test asserts the exact order of names in the shutdown log.
- Each resource's `close()` must run exactly once even if `app.close()` semantics are exercised; the log must not contain duplicate entries for a single close.

### Constraints

- Cleanup must be driven by the framework's close lifecycle so that a single `app.close()` triggers all teardown in order — not by the test or the caller invoking each resource's `close()` directly, and not by signal handlers registered at import time. A naive implementation that closes resources only when the caller calls them, or that registers `process.on('SIGTERM', ...)` at import, must fail the acceptance test.
- The shutdown log starts empty; it must be empty before close and fully populated after `await app.close()` resolves.

### Expected Functionality

- Before close: `GET /status` -> `200`, `{ open: true }`; `app.shutdownLog()` is an empty array.
- After `await app.close()`: `app.shutdownLog()` contains both resource names in last-registered-first order, with no duplicates.
- Two independent factory instances maintain independent shutdown logs.

## Acceptance Criteria

- `examples/graceful-cleanup.js` exports a factory returning a Fastify instance with a readable shutdown log, never binds a port when imported, and registers no process signal handlers at import time.
- `test/graceful-cleanup.test.js` uses `node:test` (`const { test } = require('node:test')`) and drives the instance in-process via `inject` and `await app.close()`. It includes at least 10 assertions/cases covering: `GET /status` `200` before close, empty shutdown log before close, the log populated after `await app.close()`, the exact last-registered-first ordering of names, no duplicate entries, and two instances with independent logs.
- The test asserts on status codes AND parsed JSON bodies (`res.json()`) and on the shutdown log contents and order.
- The following command passes with all tests green:

  ```
  node --test test/graceful-cleanup.test.js
  ```
