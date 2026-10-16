# Task: Add a Custom CSV Content-Type Parser with a Size Guard

## Background

This is the [Fastify](https://github.com/fastify/fastify) web-framework repository. The `examples/parser.js` example shows registering a custom body parser. Your task is to add an example module that accepts a `text/csv` upload, parses it into structured rows through a custom content-type parser, and guards against oversized payloads.

## Files to Create/Modify

- `examples/csv-parser.js` (new) — a module exporting a factory that builds and returns a configured Fastify instance. Must NOT bind a network port when required.
- `test/csv-parser.test.js` (new) — a `node:test` test file driving the instance in-process. No sockets, no external services.

## Requirements

### Module shape

- `examples/csv-parser.js` must `module.exports` a single factory (for example `buildCsvParser`) taking no required arguments, constructing the instance via the repository root (`require('..')`), wiring up everything below, and returning the instance. Requiring the module must have no side effects beyond defining the export.

### Custom CSV parsing

- The instance must accept request bodies sent with content-type `text/csv` and parse them into an array of objects via a content-type parser registered for that media type. The first CSV line is the header row (comma-separated field names); each subsequent non-empty line is a record whose cells map positionally to the header fields. Leading/trailing whitespace around the whole body is ignored; trailing blank lines are ignored.
- `POST /import` consumes the parsed CSV. It returns `200` with `{ "count": <number of parsed rows>, "rows": <array of parsed objects> }`. The handler must receive the already-parsed array (not a raw string), proving parsing happened in the content-type layer.

### Malformed input

- A `text/csv` body where a data line has a different number of cells than the header must be rejected with `400` (the parse fails); the handler must NOT run for such input.
- An empty `text/csv` body (no header) must be rejected with `400`.

### Size guard

- The instance must enforce a maximum accepted body size of `1024` bytes for this route group. A `text/csv` body larger than the limit must be rejected with status `413` and the body must not be parsed or handled.

### JSON still works

- `POST /echo` accepts a normal `application/json` body and returns `200` with `{ "received": <the json body> }`, confirming the custom CSV parser does not disturb the default JSON parsing.

### Constraints

- CSV parsing must be performed by a registered content-type parser tied to `text/csv`, and the size limit must be enforced by the framework's body-limit mechanism — not by reading the raw stream and splitting strings inside the route handler, and not by a manual length check inside the handler. A naive implementation that parses the CSV inside the handler or hand-checks `content-length` must fail the acceptance test.

### Expected Functionality

- `POST /import` with `text/csv` body `"id,name\n1,Ada\n2,Lin\n"` -> `200`, `{ count: 2, rows: [{ id: "1", name: "Ada" }, { id: "2", name: "Lin" }] }`.
- `POST /import` with a row whose cell count mismatches the header -> `400`; handler did not run.
- `POST /import` with an empty `text/csv` body -> `400`.
- `POST /import` with a `text/csv` body exceeding `1024` bytes -> `413`.
- `POST /echo` with `application/json` `{ "a": 1 }` -> `200`, `{ received: { a: 1 } }`.

## Acceptance Criteria

- `examples/csv-parser.js` exports a factory returning a Fastify instance and never binds a port when imported.
- `test/csv-parser.test.js` uses `node:test` (`const { test } = require('node:test')`) and drives the instance in-process via `inject` (passing an explicit `headers: { 'content-type': 'text/csv' }` and a string `payload` for CSV cases). It includes at least 10 assertions/cases covering: a valid multi-row parse with exact `rows`, a cell-count mismatch `400`, an empty-body `400`, an over-limit `413`, and the JSON `/echo` round-trip.
- The test asserts on status codes AND parsed JSON bodies (`res.json()`).
- The following command passes with all tests green:

  ```
  node --test test/csv-parser.test.js
  ```
