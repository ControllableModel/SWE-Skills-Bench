# Task: Build a Versioned API Aggregator Module

## Background

The `hono` repository ships small, self-contained helper modules under `src/helper/` (for example `src/helper/route/` and `src/helper/factory/`), each exporting a focused feature plus a colocated `index.test.ts`. This task adds a new helper module that assembles several independent resource sub-applications into a single versioned API tree.

## Files to Create/Modify

- `src/helper/api-aggregator/index.ts` (new) — the aggregator module.
- `src/helper/api-aggregator/index.test.ts` (new) — the deterministic test suite for the module.

## Requirements

### Module Surface

The module must export a factory function named `createApi()`. Calling it returns a fresh, fully independent sub-application instance whose routes are all reachable beneath a fixed `/v1` segment, regardless of the prefix under which the returned value is later mounted in a parent application. Two separate calls must never share state.

Internally the API exposes two independent resources — `ping` and `echo` — each authored as its own self-contained group and combined into the returned value so that the resources do not share variables or storage.

### Routes and Behavior

The contract below must hold both when the returned value is exercised directly and when it is mounted beneath a non-empty prefix in a parent application. Concretely, if mounted at `/app`, the ping health route is reachable at `/app/v1/ping`.

#### Health group (`ping`)
- A `GET` request to `<base>/v1/ping` returns `200` with a JSON body `{ "status": "ok", "version": "v1" }`.
- A `GET` request to `<base>/v1/ping/deep` returns `200` with a JSON body `{ "status": "ok", "depth": <number> }`, where `depth` is `1`.

#### Echo group (`echo`)
- A `POST` request to `<base>/v1/echo` with any JSON body returns `200` with a JSON body `{ "echo": <the parsed request body> }`.
- A `GET` request to `<base>/v1/echo/:phrase` returns `200` with a JSON body `{ "phrase": <the path segment> }`.
- A `GET` request to `<base>/v1/echo/:phrase` where the same path also carries a repeated query parameter `repeat` (e.g. `?repeat=a&repeat=b`) returns `200` with a JSON body that also includes `"repeats": <array of every supplied repeat value, in order>`. When `repeat` is absent, `repeats` must be an empty array.

### Constraints and Edge Cases

- The `/v1` segment must be intrinsic to the returned value; mounting it under any parent prefix must still route correctly without the caller re-adding `/v1`.
- A request to any path under `/v1` that does not match a defined route returns `404`.
- A request to a path that omits the `/v1` segment entirely (e.g. `<base>/ping`) must not be served by the ping group and returns `404`.
- The two groups must be independent values combined into the API; reusing one group instance must not leak routes of the other under the wrong prefix.
- All behavior must be verifiable through in-memory request dispatch (no network, no external services).

### Expected Functionality

- mount at `/app`, `GET /app/v1/ping` -> `200` `{ "status": "ok", "version": "v1" }`.
- `POST /v1/echo` with `{ "a": 1 }` -> `{ "echo": { "a": 1 } }`.
- `GET /v1/echo/hi?repeat=x&repeat=y` -> `{ "phrase": "hi", "repeats": ["x","y"] }`.
- `GET /v1/echo/hi` (no repeat) -> `repeats` is `[]`.
- `GET /ping` (missing `/v1`) -> `404`.

## Acceptance Criteria

- `src/helper/api-aggregator/index.ts` exports `createApi`, which returns a value mountable into a parent application via the parent's sub-app mounting mechanism, with all routes reachable beneath an intrinsic `/v1` segment.
- All route, grouping, status-code, repeated-query, and edge-case behaviors above are satisfied, verified by dispatching in-memory requests against both a directly-used and a mounted instance.
- A naive implementation (e.g. hardcoding `/v1` at mount time, collapsing the two groups into one shared object, or ignoring repeated `repeat` params) must fail the test suite.
- The colocated test suite contains at least 10 distinct test cases and passes with:

```
npx vitest --run src/helper/api-aggregator/index.test.ts
```
