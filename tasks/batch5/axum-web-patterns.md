# Task: Add request-id middleware to a shuttle-common router

## Background

The `shuttle-common` crate (in `common/`) holds shared platform types for Shuttle, including `ApiError` in `common/src/models/error.rs`. This task adds a small, self-contained HTTP API whose every request passes through a middleware layer that assigns a per-request identifier, makes it available to handlers, and echoes it on every response — including error responses. It lives inside `shuttle-common` and is gated behind the existing `axum` feature.

## Files to Create/Modify

- `common/src/request_id_api.rs` (new) — the middleware, the value it injects, the handlers, and a public constructor returning a fully wired `axum::Router` with the middleware already applied.
- `common/src/lib.rs` (modify) — declare the new module, compiled only when the `axum` feature is enabled.
- `common/Cargo.toml` (modify) — add whatever dev-dependencies are needed to drive the router in-process from a test (no TCP port).
- `common/tests/request_id_api.rs` (new) — the deterministic integration test described under Acceptance Criteria.

## Requirements

### Public surface

Expose a single public constructor in `common/src/request_id_api.rs`:

```rust
pub fn router() -> axum::Router;
```

`router()` must return a router with the request-id middleware already attached to all routes; the caller must not apply any further layers. The module and its `router` function must only exist when the crate is built with the `axum` feature.

### Request id behavior

For every incoming request, a middleware step determines the request id as follows:

- If the request carries an `x-request-id` header with a non-empty value, that value is the request id.
- Otherwise the request id is a fixed, documented constant defined in the module (the literal `"generated"`). (No clock or randomness — the fallback is deterministic.)

The chosen request id must be:

1. Made available to handlers as a typed value they can read (handlers must obtain it from request-scoped data placed by the middleware, not by re-reading the header).
2. Present as an `x-request-id` response header on the final response of every route, including the error route below.

### Routes and behavior

| Method | Path | Behavior |
| ------ | ---- | -------- |
| GET    | `/echo`  | Returns a JSON body that includes the request id observed by the handler. |
| GET    | `/fail`  | Always returns a `500`-class error via the crate's error type. |

### Expected Functionality

- **Header provided** — `GET /echo` with `x-request-id: abc123` responds `200 OK`, the response has header `x-request-id: abc123`, and the JSON body reports `abc123` as the id the handler saw (e.g. `{"request_id":"abc123"}`).
- **Header absent** — `GET /echo` with no `x-request-id` header responds `200 OK`, the response header `x-request-id` equals `generated`, and the body reports `generated`.
- **Empty header** — `GET /echo` with an empty `x-request-id` value falls back to `generated` for both the response header and the body.
- **Error path carries the id** — `GET /fail` with `x-request-id: zzz` responds with a `5xx` status, the crate's standard error body (a JSON object with a `message` field), and still carries the `x-request-id: zzz` response header.
- **Handler/header agreement** — for any request, the id reported in the `/echo` body equals the id in the response's `x-request-id` header.

### Constraints

- The id must be injected by the middleware and read by the handler from request-scoped data; the handler must not parse the header itself.
- The response header must be set for both the success and the error route, demonstrating the layer wraps the whole handler chain.
- The error response must use the crate's existing `ApiError`-based shape.
- Do not start a server, open a socket, or use network, filesystem, clock, or randomness.

## Acceptance Criteria

- A new module `request_id_api` is compiled into `shuttle-common` only under the `axum` feature and exposes `pub fn router() -> axum::Router`.
- `common/tests/request_id_api.rs` drives the router fully in-process (no TCP port) and asserts at minimum:
  - With `x-request-id: abc123`, `/echo` returns `200`, response header `x-request-id == abc123`, and the body reports `abc123`.
  - With no header, `/echo` returns `200`, response header and body both report `generated`.
  - With an empty header value, the fallback `generated` is used.
  - `/fail` returns a `5xx` with a JSON `message` and still carries the incoming `x-request-id` on the response.
  - The body id always equals the response header id.
- A naive implementation that omits the response header, ignores the incoming header, or has the handler read the header directly instead of the injected value must fail.
- The following command, run from the repository root, passes:

```
cargo test -p shuttle-common --features axum --test request_id_api
```
