# Task: Build a versioned, nested API with per-section fallbacks in shuttle-common

## Background

The `shuttle-common` crate (in `common/`) holds shared platform types for Shuttle, including `ApiError` in `common/src/models/error.rs`, which converts to an HTTP response behind the `axum` feature. This task adds a small, self-contained HTTP API that mounts two independent versioned sub-APIs under distinct path prefixes, each with its own not-found behavior, plus a top-level catch-all. It lives inside `shuttle-common` and is gated behind the existing `axum` feature.

## Files to Create/Modify

- `common/src/versioned_api.rs` (new) — the sub-routers for each version, their fallbacks, the top-level fallback, and a public constructor returning the composed `axum::Router`.
- `common/src/lib.rs` (modify) — declare the new module, compiled only when the `axum` feature is enabled.
- `common/Cargo.toml` (modify) — add whatever dev-dependencies are needed to drive the router in-process from a test (no TCP port).
- `common/tests/versioned_api.rs` (new) — the deterministic integration test described under Acceptance Criteria.

## Requirements

### Public surface

Expose a single public constructor in `common/src/versioned_api.rs`:

```rust
pub fn router() -> axum::Router;
```

`router()` must return the fully composed router ready to serve requests. The module and its `router` function must only exist when the crate is built with the `axum` feature.

### Composition

The router mounts two sub-APIs under prefixes and defines a top-level catch-all:

- Under `/api/v1`: a sub-router with `GET /status` (responds with a fixed v1 status body) and its own not-found handler.
- Under `/api/v2`: a sub-router with `GET /status` (responds with a fixed v2 status body, distinct from v1) and its own not-found handler.
- A top-level not-found handler for any path matching neither mounted sub-API.

Each not-found handler returns the crate's standard error body (a JSON object with a `message` field) and a `404` status, but the three messages must be distinguishable so a caller can tell which section handled the miss (e.g. the v1 message mentions v1, the v2 message mentions v2, and the top-level message is generic).

### Expected Functionality

- **v1 hit** — `GET /api/v1/status` responds `200 OK` with the v1 status body.
- **v2 hit** — `GET /api/v2/status` responds `200 OK` with the v2 status body, which differs from v1's.
- **v1 miss** — `GET /api/v1/does-not-exist` responds `404 Not Found` with the v1-specific not-found message.
- **v2 miss** — `GET /api/v2/does-not-exist` responds `404 Not Found` with the v2-specific not-found message, distinct from v1's.
- **Top-level miss** — `GET /something-else` (not under any mounted prefix) responds `404 Not Found` with the top-level message, distinct from both section messages.
- **Method mismatch within a section** — a `POST /api/v1/status` (wrong method on an existing path) does not produce the success body.

### Constraints

- The two sub-APIs must be defined as independent routers and mounted under their prefixes, so each `/status` handler sees only the path relative to its own mount point.
- Each section's not-found behavior must be governed by that section's fallback, not by the top-level one; the three messages must be distinct, proving the correct fallback handled each miss.
- All `404` bodies must use the crate's existing `ApiError`-based shape.
- Do not start a server, open a socket, or use network, filesystem, clock, or randomness.

## Acceptance Criteria

- A new module `versioned_api` is compiled into `shuttle-common` only under the `axum` feature and exposes `pub fn router() -> axum::Router`.
- `common/tests/versioned_api.rs` drives the router fully in-process (no TCP port) and asserts at minimum:
  - `GET /api/v1/status` and `GET /api/v2/status` each return `200` with their distinct bodies.
  - `GET /api/v1/<missing>` returns `404` with the v1 message; `GET /api/v2/<missing>` returns `404` with the v2 message; the two messages differ.
  - `GET /<unmounted-path>` returns `404` with the top-level message, distinct from both section messages.
  - Every `404` body is a JSON object containing a `message` field.
- A naive implementation that uses a single shared fallback, returns identical messages, or fails to mount the sub-APIs under their prefixes must fail.
- The following command, run from the repository root, passes:

```
cargo test -p shuttle-common --features axum --test versioned_api
```
