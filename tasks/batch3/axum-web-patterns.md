# Task: Add a paginated, filterable logs query endpoint to shuttle-common

## Background

The `shuttle-common` crate (in `common/`) defines `LogItem` and `LogsResponse` in `common/src/models/log.rs`, and the HTTP-error type `ApiError` in `common/src/models/error.rs` (which converts to a response behind the `axum` feature). This task adds a small, self-contained read-only HTTP API that returns a fixed in-memory set of log lines with pagination and filtering driven entirely by the query string. It lives inside `shuttle-common` and is gated behind the existing `axum` feature.

## Files to Create/Modify

- `common/src/logs_api.rs` (new) — the query-parameter type, the handler(s), the fixed seed dataset, and a public constructor returning a fully wired `axum::Router`.
- `common/src/lib.rs` (modify) — declare the new module, compiled only when both the `axum` and `models` features are enabled.
- `common/Cargo.toml` (modify) — add whatever dev-dependencies are needed to drive the router in-process from a test (no TCP port).
- `common/tests/logs_api.rs` (new) — the deterministic integration test described under Acceptance Criteria.

## Requirements

### Public surface

Expose a single public constructor in `common/src/logs_api.rs`:

```rust
pub fn router() -> axum::Router;
```

`router()` must return a router ready to serve requests immediately. The dataset it serves must be deterministic and identical on every call (seeded in code, no clock or randomness). The module and its `router` function must only exist when the crate is built with the `axum` feature.

### Seed dataset

The router serves a fixed, in-order sequence of exactly 5 log lines, each a `LogItem` whose `source` is one of `"build"` or `"runtime"` and whose `line` is a short label. The seed must contain at least two `"build"` lines and at least two `"runtime"` lines, defined in a stable, documented order in the source.

### Routes and behavior

| Method | Path | Behavior |
| ------ | ---- | -------- |
| GET    | `/logs` | Return a page of logs, filtered and paginated per the query string. |

The response body shape is `LogsResponse`: `{ "logs": [ <LogItem>, ... ] }`, preserving the seed order (after filtering) of the selected slice.

### Query parameters

All parameters are optional and read from the query string:

- `source` — if present, only log lines whose `source` equals this value are eligible. If `source` is given but matches none of the seed sources, the eligible set is empty (not an error).
- `offset` — number of eligible lines to skip from the front; defaults to `0`.
- `limit` — maximum number of lines to return after the offset; defaults to returning all remaining eligible lines.

### Expected Functionality

- **No parameters** — `GET /logs` responds `200 OK` and returns all 5 seed lines in seed order.
- **Filter by source** — `GET /logs?source=build` returns only the `"build"` lines in seed order; `GET /logs?source=runtime` returns only the `"runtime"` lines.
- **Pagination** — `GET /logs?offset=1&limit=2` returns exactly the 2nd and 3rd eligible lines. An `offset` at or beyond the eligible count yields `{"logs":[]}`. A `limit` larger than the remaining count returns all remaining lines.
- **Combined** — filtering then offset/limit compose: `GET /logs?source=runtime&offset=1` skips the first runtime line and returns the rest of the runtime lines.
- **Unknown source** — `GET /logs?source=nope` responds `200 OK` with `{"logs":[]}`.
- **Invalid numeric parameter** — a non-numeric `offset` or `limit` (e.g. `offset=abc`) responds `400 Bad Request` with the crate's standard error body (a JSON object with a `message` field), and returns no logs.

### Constraints

- Pagination and filtering must be derived from the parsed query, not from a hardcoded slice; changing `offset`/`limit`/`source` must visibly change the returned set.
- A request with `limit=0` returns `{"logs":[]}` (zero lines), distinct from omitting `limit`.
- The error response for an unparseable query parameter must use the crate's existing `ApiError`-based shape and status `400`.
- Do not start a server, open a socket, or use network, filesystem, clock, or randomness.

## Acceptance Criteria

- A new module `logs_api` is compiled into `shuttle-common` only under the `axum` feature and exposes `pub fn router() -> axum::Router`.
- `common/tests/logs_api.rs` drives the router fully in-process (no TCP port) and asserts at minimum:
  - No-parameter `GET /logs` returns all 5 seed lines in order.
  - `source=build` and `source=runtime` each return only the matching lines, with correct counts and order.
  - `offset`/`limit` slice correctly, including `limit=0` → empty, large offset → empty, large limit → all remaining.
  - `source=<unknown>` returns `200` with `{"logs":[]}`.
  - A non-numeric `offset` or `limit` returns `400` with a JSON `message`.
- A naive implementation that ignores the query string or returns a fixed slice must fail.
- The following command, run from the repository root, passes:

```
cargo test -p shuttle-common --features axum,models --test logs_api
```
