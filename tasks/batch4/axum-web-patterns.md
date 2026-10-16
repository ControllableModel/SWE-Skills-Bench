# Task: Add API-key gated routes to shuttle-common

## Background

The `shuttle-common` crate (in `common/`) holds shared platform types for Shuttle, including the `ApiError` type in `common/src/models/error.rs`, which converts itself into an HTTP response behind the `axum` feature. This task adds a small, self-contained HTTP API in which some routes are public and others require a valid API key presented in a request header, with the key requirement enforced through a reusable typed request component rather than ad-hoc checks inside each handler. It lives inside `shuttle-common` and is gated behind the existing `axum` feature.

## Files to Create/Modify

- `common/src/auth_api.rs` (new) — the typed request component that extracts and validates the API key, the handlers, and a public constructor returning a fully wired `axum::Router`.
- `common/src/lib.rs` (modify) — declare the new module, compiled only when the `axum` feature is enabled.
- `common/Cargo.toml` (modify) — add whatever dev-dependencies are needed to drive the router in-process from a test (no TCP port).
- `common/tests/auth_api.rs` (new) — the deterministic integration test described under Acceptance Criteria.

## Requirements

### Public surface

Expose a single public constructor in `common/src/auth_api.rs`:

```rust
pub fn router() -> axum::Router;
```

`router()` must return a router ready to serve requests immediately. The accepted API key is a fixed, documented constant defined in the module (the value `"sk-test-key"`). The module and its `router` function must only exist when the crate is built with the `axum` feature.

### Authentication component

Define a reusable typed request component (a type used directly as a handler parameter) that, before a protected handler runs, inspects the request's `authorization` header and admits the request only when the header is exactly `Bearer sk-test-key`. When the header is missing, malformed, uses a different scheme, or carries the wrong key, the component must reject the request itself (the protected handler body must not run) with the appropriate status and the crate's standard error body. Each protected handler must obtain the authenticated caller's identity from this component, not by re-reading the header.

### Routes and behavior

| Method | Path | Auth | Behavior |
| ------ | ---- | ---- | -------- |
| GET    | `/public/ping`     | none      | Always succeeds. |
| GET    | `/private/whoami`  | required  | Returns the caller identity derived from the validated key. |
| GET    | `/private/data`    | required  | Returns a fixed protected payload. |

### Expected Functionality

- **Public route** — `GET /public/ping` responds `200 OK` regardless of any header, returning a small fixed body.
- **Protected with valid key** — `GET /private/whoami` with header `Authorization: Bearer sk-test-key` responds `200 OK` and returns a JSON object identifying the caller (e.g. `{"caller":"sk-test-key"}` or an equivalent stable identity field documented in the module). `GET /private/data` with the same header responds `200 OK` with its fixed payload.
- **Missing header** — a protected route with no `Authorization` header responds `401 Unauthorized` with the crate's standard error body (a JSON object with a `message` field) and does not return the protected payload.
- **Wrong key** — a protected route with `Authorization: Bearer wrong` responds `401 Unauthorized`.
- **Malformed header** — a protected route whose `Authorization` value lacks the `Bearer ` scheme (e.g. just `sk-test-key`) responds `401 Unauthorized`.
- **Auth does not affect public** — sending a wrong or missing key to `/public/ping` still responds `200 OK`.

### Constraints

- The header validation must live in the reusable component, so that adding another protected route requires only declaring that component as a handler parameter — protected handlers must not duplicate the parsing/validation logic.
- Rejections must short-circuit before the protected handler body runs.
- Error responses must use the crate's existing `ApiError`-based shape and status `401` for every auth failure.
- Do not start a server, open a socket, or use network, filesystem, clock, or randomness.

## Acceptance Criteria

- A new module `auth_api` is compiled into `shuttle-common` only under the `axum` feature and exposes `pub fn router() -> axum::Router`.
- `common/tests/auth_api.rs` drives the router fully in-process (no TCP port) and asserts at minimum:
  - `GET /public/ping` returns `200` with and without any auth header.
  - `GET /private/whoami` and `GET /private/data` with `Bearer sk-test-key` return `200`, and `whoami`'s body carries the caller identity.
  - The same protected routes return `401` with a JSON `message` when the header is missing, when the key is wrong, and when the `Bearer ` scheme is absent.
- A naive implementation that returns `200` for protected routes regardless of the header, or that hardcodes the identity without checking the key, must fail.
- The following command, run from the repository root, passes:

```
cargo test -p shuttle-common --features axum --test auth_api
```
