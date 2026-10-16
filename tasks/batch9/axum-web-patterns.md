# Task: Add a shared-state metrics endpoint to shuttle-common

## Background

The `shuttle-common` crate (in `common/`) holds shared platform types for Shuttle, including `ApiError` in `common/src/models/error.rs`. This task adds a small, self-contained HTTP API that maintains per-route hit counters in shared, concurrency-safe application data and reports them, with one handler that builds its HTTP response by hand (custom status and headers). It lives inside `shuttle-common` and is gated behind the existing `axum` feature.

## Files to Create/Modify

- `common/src/metrics_api.rs` (new) — the shared counter state, the handlers (including one that builds a full response with custom headers), and a public constructor returning a fully wired `axum::Router` whose state is already attached.
- `common/src/lib.rs` (modify) — declare the new module, compiled only when the `axum` feature is enabled.
- `common/Cargo.toml` (modify) — add whatever dev-dependencies are needed to drive the router in-process from a test (no TCP port).
- `common/tests/metrics_api.rs` (new) — the deterministic integration test described under Acceptance Criteria.

## Requirements

### Public surface

Expose a single public constructor in `common/src/metrics_api.rs`:

```rust
pub fn router() -> axum::Router;
```

`router()` must return a router with its counter state already attached; the caller supplies nothing further. Each call must produce an independent instance whose counters all start at zero and share no data with any other instance. The module and its `router` function must only exist when the crate is built with the `axum` feature.

### Shared counter state

The router maintains independent hit counters for the two countable routes below. Every successful request to a countable route increments that route's counter by exactly one before responding. The counters live in the router's shared application data and must be safe to mutate under concurrent requests (the test may issue many sequential requests and expect exact totals).

### Routes and behavior

| Method | Path | Behavior |
| ------ | ---- | -------- |
| GET    | `/hit/a`   | Increments counter A, then responds `200 OK`. |
| GET    | `/hit/b`   | Increments counter B, then responds `200 OK`. |
| GET    | `/metrics` | Reports the current counters; does NOT increment any counter. |

### Expected Functionality

- **Counting** — after `N` calls to `/hit/a` and `M` calls to `/hit/b` (in any interleaving), `GET /metrics` reports exactly `a == N` and `b == M`. The `/metrics` route itself never changes the counters, so repeated `GET /metrics` calls return the same numbers.
- **Independence per instance** — counters from one `router()` instance never appear in another instance built by a separate `router()` call.
- **Custom response on `/metrics`** — the `/metrics` handler must build its response explicitly with status `200 OK`, a `content-type: application/json` header, and an additional custom header `x-metrics-source` whose value is a fixed documented constant (e.g. `shuttle-common`). The body is a JSON object `{ "a": <number>, "b": <number> }`.
- **Initial state** — before any `/hit/*` request, `GET /metrics` reports `{"a":0,"b":0}` with the custom header present.

### Constraints

- The counters must be held in concurrency-safe shared state attached via the router's state mechanism, not a process-global; the caller of `router()` must not construct or pass the state.
- `/metrics` must read the live counters (not a snapshot taken at construction) and must not mutate them.
- The `/metrics` response must be assembled as a full response with the specified status and the two headers; a response that omits `x-metrics-source` or the JSON content type fails.
- Do not start a server, open a socket, or use network, filesystem, clock, or randomness.

## Acceptance Criteria

- A new module `metrics_api` is compiled into `shuttle-common` only under the `axum` feature and exposes `pub fn router() -> axum::Router`.
- `common/tests/metrics_api.rs` drives the router fully in-process (no TCP port) and asserts at minimum:
  - A fresh router reports `{"a":0,"b":0}` and the `/metrics` response carries `content-type: application/json` and `x-metrics-source` with the documented value.
  - After a known number of `/hit/a` and `/hit/b` requests, `/metrics` reports those exact counts.
  - Repeated `/metrics` requests do not change the counts.
  - A second independent `router()` instance starts again at `{"a":0,"b":0}`.
- A naive implementation that hardcodes the counts, increments on `/metrics`, shares a global counter across instances, or omits the custom header must fail.
- The following command, run from the repository root, passes:

```
cargo test -p shuttle-common --features axum --test metrics_api
```
