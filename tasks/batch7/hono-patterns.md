# Task: Build a Bindings-Driven Configuration Module

## Background

The `hono` repository ships small, self-contained helper modules under `src/helper/` (for example `src/helper/route/` and `src/helper/factory/`), each exporting a focused feature plus a colocated `index.test.ts`. This task adds a new helper module whose behavior is driven entirely by per-request environment bindings supplied at dispatch time, with derived values shared across handlers via request-scoped variables.

## Files to Create/Modify

- `src/helper/config-endpoint/index.ts` (new) — the configuration module.
- `src/helper/config-endpoint/index.test.ts` (new) — the deterministic test suite for the module.

## Requirements

### Module Surface

The module must export a single sub-application value named `configApp` (not a factory) that reads its configuration from the per-request environment bindings rather than from any module-level mutable state. The application must be parameterized so that its environment carries two string bindings: `SERVICE_NAME` and `FEATURE_FLAGS` (a comma-separated list). The returned value must be mountable into a parent application under an arbitrary prefix.

A request-scoped step must, on every request, parse `FEATURE_FLAGS` into an array of trimmed non-empty flag strings and make that array available to the route handlers as a request-scoped variable named `flags`. Handlers must read the parsed `flags` variable rather than re-parsing the binding themselves.

### Routes and Behavior

Environment bindings are supplied per request through the in-memory dispatch mechanism (the third argument that carries `Bindings`). The contract must hold both directly and when mounted under a non-empty prefix.

#### Service info
- A `GET` request to `/info` returns `200` with a JSON body `{ "service": <value of SERVICE_NAME>, "flags": <parsed flags array> }`.
- When `FEATURE_FLAGS` is an empty string or contains only separators/whitespace, `flags` must be an empty array.

#### Flag check
- A `GET` request to `/flags/:name` returns `200` with a JSON body `{ "name": <the path segment>, "enabled": <boolean> }`, where `enabled` is `true` if and only if the parsed `flags` array contains exactly that flag name.

#### Required binding
- If a request reaches any route while `SERVICE_NAME` is absent or an empty string in the supplied bindings, the response is `500` with a JSON body `{ "error": <string> }`.

### Constraints and Edge Cases

- The same `configApp` value, dispatched with two different binding sets, must produce results consistent with each set independently — there must be no leakage of one request's bindings into another.
- Flag parsing must trim whitespace around each entry and drop empty entries produced by consecutive or trailing separators.
- The flag-membership check must be exact (no substring matching).
- All behavior must be verifiable through in-memory request dispatch with per-request bindings (no network, no external services).

### Expected Functionality

- `GET /info` with bindings `{ SERVICE_NAME: "svc", FEATURE_FLAGS: "a, b ,,c," }` -> `{ "service": "svc", "flags": ["a","b","c"] }`.
- `GET /flags/b` with the same bindings -> `enabled` is `true`; `GET /flags/x` -> `false`.
- `GET /info` with `FEATURE_FLAGS: ""` -> `flags` is `[]`.
- `GET /info` with no `SERVICE_NAME` -> `500`.
- two dispatches with different `SERVICE_NAME` values -> each `/info` reflects its own binding.

## Acceptance Criteria

- `src/helper/config-endpoint/index.ts` exports `configApp`, a value mountable into a parent application whose behavior is fully determined by per-request bindings, with parsed flags shared to handlers as a request-scoped variable.
- All info, flag-check, parsing, isolation, and required-binding behaviors above are satisfied, verified by dispatching in-memory requests with distinct binding sets against both a directly-used and a mounted instance.
- A naive implementation (e.g. caching bindings in module state, re-parsing flags inside each handler instead of reading the shared variable, or skipping the `SERVICE_NAME` requirement) must fail the test suite.
- The colocated test suite contains at least 10 distinct test cases and passes with:

```
npx vitest --run src/helper/config-endpoint/index.test.ts
```
