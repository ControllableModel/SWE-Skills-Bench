# Task: Add an in-memory secrets HTTP API to shuttle-common

## Background

The `shuttle-common` crate (in `common/`) holds the shared platform types for Shuttle, including the `Secret<T>` wrapper in `common/src/secrets.rs` and the `ApiError` type in `common/src/models/error.rs` (which already converts itself into an HTTP response behind the `axum` feature). This task adds a small, self-contained HTTP API for managing per-project secrets that lives inside `shuttle-common` and is gated behind the existing `axum` feature.

## Files to Create/Modify

- `common/src/secrets_api.rs` (new) — the HTTP API: its request/response payloads, the shared in-memory store, the handlers, and a public constructor that returns a fully wired `axum::Router` with no leftover state requirement.
- `common/src/lib.rs` (modify) — declare the new module, gated so it is only compiled when the `axum` feature is enabled.
- `common/Cargo.toml` (modify) — add whatever dev-dependency is needed to drive the router in-process from a test (the router must be exercised without binding a TCP port).
- `common/tests/secrets_api.rs` (new) — the deterministic integration test described under Acceptance Criteria.

## Requirements

### Public surface

Expose a single public constructor in `common/src/secrets_api.rs`:

```rust
pub fn router() -> axum::Router;
```

Calling `router()` must return a router that is ready to serve requests immediately — the caller must not need to supply any further configuration, store, or state before using it. Each call to `router()` must produce an independent API instance whose store starts empty and does not share data with any other instance.

The module (and its `router` function) must only exist when the crate is built with the `axum` feature; it must not affect builds that do not enable that feature.

### Data model

A secret is identified by a `project` name and a `key`, both strings, and holds a string `value`. The store keeps at most one entry per `(project, key)` pair.

- The JSON shape used to create or replace a secret is an object with a single field: `{ "value": "<string>" }`.
- The JSON shape returned when reading a single secret is an object: `{ "key": "<string>", "value": "<string>" }`.
- The JSON shape returned when listing the secrets of a project is an object: `{ "secrets": [ { "key": ..., "value": ... }, ... ] }`, with entries ordered by `key` ascending.

Stored secret values must be held using the crate's existing `Secret` wrapper from `common/src/secrets.rs` rather than as bare `String`s. The plaintext value is only reconstructed when a response body is produced.

### Routes and behavior

The router must expose exactly these routes (paths are relative to the router root, with `project` and `key` taken from the URL path):

| Method | Path                                  | Behavior |
| ------ | ------------------------------------- | -------- |
| GET    | `/projects/{project}/secrets`         | List all secrets for the project. |
| PUT    | `/projects/{project}/secrets/{key}`   | Create or replace the secret. |
| GET    | `/projects/{project}/secrets/{key}`   | Read a single secret. |
| DELETE | `/projects/{project}/secrets/{key}`   | Remove a single secret. |

### Expected Functionality

- **Create then read** — `PUT /projects/alpha/secrets/TOKEN` with body `{"value":"abc"}` responds `201 Created`. A following `GET /projects/alpha/secrets/TOKEN` responds `200 OK` with body `{"key":"TOKEN","value":"abc"}`.
- **Replace** — A second `PUT` to the same `(project, key)` with a different value responds `200 OK` (not `201`) and updates the stored value; a subsequent read returns the new value. The store still holds exactly one entry for that pair.
- **Read missing** — `GET` for a `(project, key)` that was never created responds `404 Not Found`, and the JSON body carries a human-readable message (the body is the crate's standard API error shape with a `message` field). A key that exists under a different project is still treated as missing.
- **List** — `GET /projects/{project}/secrets` responds `200 OK`. For a project with no secrets the body is `{"secrets":[]}`. For a project with several secrets the entries appear sorted by `key` ascending. Secrets belonging to other projects never appear in the list.
- **Delete** — `DELETE` of an existing secret responds `204 No Content` with an empty body and removes it (a following read returns `404`). `DELETE` of a secret that does not exist responds `404 Not Found`.
- **Malformed create body** — `PUT` whose body is not a JSON object with a string `value` field (e.g. missing the field, wrong type, or syntactically invalid JSON) responds `400 Bad Request` and does not create or modify any entry.

### Constraints

- The shared store must be safe to use across concurrent requests (handlers receive it through the router's shared application data, not via a global). It must not require the caller of `router()` to construct or pass it in.
- Reading or listing must reflect the most recent successful create/replace/delete for the same router instance.
- Error responses for the cases above must use the crate's existing `ApiError`-based response shape (a JSON object containing a `message` string) and the status codes specified, rather than ad-hoc bodies.
- Do not start a server, open a socket, or use any network, filesystem, clock, or randomness in the module or its test.

## Acceptance Criteria

- A new module `secrets_api` is compiled into `shuttle-common` only under the `axum` feature and exposes `pub fn router() -> axum::Router`.
- `common/tests/secrets_api.rs` drives the router fully in-process (no TCP port) and asserts, at minimum:
  - `PUT` of a new secret yields `201`; reading it yields `200` with body `{"key":...,"value":...}` matching what was written.
  - A second `PUT` to the same path yields `200` and the read reflects the updated value.
  - `GET` of an unknown key yields `404` with a JSON body containing a `message` field.
  - A key created under project `a` is reported `404` when read under project `b`.
  - `GET` list returns `{"secrets":[]}` for an empty project and a `key`-ascending ordered array once multiple secrets exist, scoped to one project only.
  - `DELETE` of an existing secret yields `204` with an empty body, after which the read yields `404`; `DELETE` of an unknown secret yields `404`.
  - A `PUT` with a body that is not `{"value": <string>}` yields `400` and leaves the store unchanged (a subsequent read still `404`s).
- A naive implementation that ignores the project segment, returns a fixed status code, hardcodes the response, or skips storage must fail the test.
- The following command, run from the repository root, passes:

```
cargo test -p shuttle-common --features axum --test secrets_api
```
