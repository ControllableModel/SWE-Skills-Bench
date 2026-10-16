# Task: Build a certificate registry API with a custom error type in shuttle-common

## Background

The `shuttle-common` crate (in `common/`) defines certificate request/response types in `common/src/models/certificate.rs` (`AddCertificateRequest`, `CertificateResponse`, `CertificateListResponse`) and the `ApiError` type in `common/src/models/error.rs`, which converts to an HTTP response behind the `axum` feature. This task adds a small, self-contained HTTP API for registering TLS certificate subjects whose handlers all return a single domain-specific error type that maps each failure cause to a distinct HTTP status. It lives inside `shuttle-common` and is gated behind the existing `axum` feature.

## Files to Create/Modify

- `common/src/certs_api.rs` (new) — the domain error type, its conversion into an HTTP response, the shared in-memory registry, the handlers, and a public constructor returning a fully wired `axum::Router`.
- `common/src/lib.rs` (modify) — declare the new module, compiled only when both the `axum` and `models` features are enabled.
- `common/Cargo.toml` (modify) — add whatever dev-dependencies are needed to drive the router in-process from a test (no TCP port).
- `common/tests/certs_api.rs` (new) — the deterministic integration test described under Acceptance Criteria.

## Requirements

### Public surface

Expose a single public constructor in `common/src/certs_api.rs`:

```rust
pub fn router() -> axum::Router;
```

`router()` must return a router ready to serve requests immediately, each call producing an independent, empty registry. The module and its `router` function must only exist when the crate is built with the `axum` feature.

### Domain error type

Define one error type in the module that enumerates these failure causes and maps each to a status when turned into a response: a not-found cause → `404`, a conflict (already exists) cause → `409`, and a validation cause → `400`. Every handler returns `Result<_, ThatErrorType>`, and the type's response body must be the crate's standard error shape (a JSON object with a `message` field). The message must describe the specific cause.

### Data model

A certificate registration is identified by its `subject` (a domain string). The registry keeps at most one entry per `subject`. A response uses the existing `CertificateResponse`/`CertificateListResponse` types from `common/src/models/certificate.rs`; the `id`, `serial_hex`, and `not_after` fields may be filled with stable, deterministic placeholder values derived from the subject (no clock or randomness). Listing returns entries ordered by `subject` ascending.

### Routes and behavior

| Method | Path | Behavior |
| ------ | ---- | -------- |
| POST   | `/certificates`              | Register a new subject; body is `AddCertificateRequest`. |
| GET    | `/certificates`              | List all registered certificates, `subject`-ascending. |
| GET    | `/certificates/{subject}`    | Read one certificate by subject. |
| DELETE | `/certificates/{subject}`    | Remove a certificate by subject. |

### Expected Functionality

- **Register** — `POST /certificates` with `{"subject":"example.com"}` responds `201 Created` and the body is a `CertificateResponse` whose `subject` is `example.com`. A second `POST` of the same subject triggers the conflict cause → `409 Conflict`, leaving the existing entry intact.
- **Validation** — `POST /certificates` with an empty `subject` (or a body missing the field) triggers the validation cause → `400 Bad Request`; nothing is stored.
- **Read** — `GET /certificates/example.com` after registration responds `200 OK` with the matching `CertificateResponse`. `GET` of an unregistered subject triggers the not-found cause → `404 Not Found`.
- **List** — `GET /certificates` responds `200 OK`; an empty registry yields `{"certificates":[]}`; multiple subjects appear `subject`-ascending.
- **Delete** — `DELETE /certificates/example.com` of an existing entry responds `204 No Content` with an empty body; a following read triggers `404`. `DELETE` of an unregistered subject triggers the not-found cause → `404`.
- **Status mapping is cause-driven** — the `404`, `409`, and `400` responses must each originate from the corresponding variant of the single domain error type, all carrying a descriptive `message`.

### Constraints

- All handlers must return the one domain error type; status codes must come from mapping the cause inside that type's response conversion, not from per-handler ad-hoc status codes.
- The registry must be shared safely across concurrent requests via the router's shared application data, not a global, and not passed in by the caller.
- All error bodies must use the crate's existing `ApiError`-based shape.
- Do not start a server, open a socket, or use network, filesystem, clock, or randomness.

## Acceptance Criteria

- A new module `certs_api` is compiled into `shuttle-common` only under the `axum` feature and exposes `pub fn router() -> axum::Router`.
- `common/tests/certs_api.rs` drives the router fully in-process (no TCP port) and asserts at minimum:
  - First `POST` of a subject yields `201` with a `CertificateResponse` whose `subject` matches; a duplicate yields `409`.
  - `POST` with an empty/missing subject yields `400` and stores nothing (a subsequent read `404`s).
  - `GET` of a registered subject yields `200`; of an unregistered subject yields `404`, each error body containing a `message`.
  - `GET` list yields `{"certificates":[]}` empty, then a `subject`-ascending array.
  - `DELETE` of an existing subject yields `204` empty then a `404` read; `DELETE` of an unknown subject yields `404`.
- A naive implementation that returns a fixed status, hardcodes responses, or skips storage must fail.
- The following command, run from the repository root, passes:

```
cargo test -p shuttle-common --features axum,models --test certs_api
```
