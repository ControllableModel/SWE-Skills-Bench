# Task: Add a validating project-create endpoint to shuttle-common

## Background

The `shuttle-common` crate (in `common/`) defines `ProjectCreateRequest` in `common/src/models/project.rs`, whose `name` is documented to match the pattern `^[a-z0-9-]{1,32}$`, and the `ApiError` type in `common/src/models/error.rs`, which converts to an HTTP response behind the `axum` feature. This task adds a small, self-contained HTTP API that accepts project-creation requests through a reusable request component that both parses the JSON body and enforces the name rules before the handler runs. It lives inside `shuttle-common` and is gated behind the existing `axum` feature.

## Files to Create/Modify

- `common/src/projects_api.rs` (new) — the validating request component, the shared in-memory project store, the handlers, and a public constructor returning a fully wired `axum::Router`.
- `common/src/lib.rs` (modify) — declare the new module, compiled only when both the `axum` and `models` features are enabled.
- `common/Cargo.toml` (modify) — add whatever dev-dependencies are needed to drive the router in-process from a test (no TCP port).
- `common/tests/projects_api.rs` (new) — the deterministic integration test described under Acceptance Criteria.

## Requirements

### Public surface

Expose a single public constructor in `common/src/projects_api.rs`:

```rust
pub fn router() -> axum::Router;
```

`router()` must return a router ready to serve requests immediately, each call producing an independent, empty store. The module and its `router` function must only exist when the crate is built with the `axum` feature.

### Validating request component

Define a reusable request component (a type used directly as a handler parameter) that parses a JSON body into `ProjectCreateRequest` and then enforces these rules on `name` before the handler runs:

- length between 1 and 32 characters inclusive;
- only the characters `a`–`z`, `0`–`9`, and `-` are allowed;
- no uppercase letters, spaces, or other punctuation.

When the body is not valid JSON, or the JSON does not match `ProjectCreateRequest`, or the name violates the rules, the component rejects the request itself (the create handler body must not run) with `400 Bad Request` and the crate's standard error body (a JSON object with a `message` field).

### Data model and routes

The store keeps at most one project per `name`. A stored project is represented by its `name`; the listing returns `{ "projects": [ "<name>", ... ] }` ordered by `name` ascending.

| Method | Path | Behavior |
| ------ | ---- | -------- |
| POST   | `/projects`           | Create a project; body validated by the component above. |
| GET    | `/projects`           | List all project names, ascending. |
| GET    | `/projects/{name}`    | Report whether a project exists. |

### Expected Functionality

- **Valid create** — `POST /projects` with `{"name":"my-app-1"}` responds `201 Created`; a following `GET /projects/my-app-1` responds `200 OK` and `GET /projects` includes `my-app-1`.
- **Duplicate** — a second `POST` with the same valid name responds `409 Conflict` and does not add a second entry.
- **Invalid names rejected (400)** — each of these responds `400 Bad Request` and stores nothing: an empty name; a name longer than 32 characters; a name containing an uppercase letter (e.g. `My-App`); a name with a space; a name with a disallowed symbol (e.g. `app_1` or `app.1`).
- **Malformed body** — a body that is not a JSON object with a string `name` (missing field, wrong type, or invalid JSON) responds `400 Bad Request` and stores nothing.
- **List ordering** — after creating several valid projects, `GET /projects` returns their names `name`-ascending; an empty store returns `{"projects":[]}`.
- **Existence check** — `GET /projects/{name}` for a created name responds `200 OK`; for an absent name responds `404 Not Found` with a JSON `message`.

### Constraints

- The name validation must live in the reusable component so the create handler receives an already-valid value and performs no parsing or pattern checks itself.
- Rejections must short-circuit before the create handler runs and must not mutate the store.
- All error bodies must use the crate's existing `ApiError`-based shape with status `400` for validation/parse failures and `404`/`409` where specified.
- Do not start a server, open a socket, or use network, filesystem, clock, or randomness.

## Acceptance Criteria

- A new module `projects_api` is compiled into `shuttle-common` only under the `axum` feature and exposes `pub fn router() -> axum::Router`.
- `common/tests/projects_api.rs` drives the router fully in-process (no TCP port) and asserts at minimum:
  - A valid `POST` yields `201`, then the name is readable (`200`) and appears in the list.
  - A duplicate valid name yields `409` and does not double-insert.
  - Empty name, over-length name, uppercase name, name with a space, and name with a disallowed symbol each yield `400` and store nothing.
  - A non-`{"name": <string>}` body yields `400` and stores nothing.
  - `GET /projects` returns `name`-ascending names, and `{"projects":[]}` when empty.
  - `GET /projects/{name}` yields `200` for present and `404` (with a `message`) for absent.
- A naive implementation that accepts any name, hardcodes acceptance, or validates inside the handler instead of the component must fail.
- The following command, run from the repository root, passes:

```
cargo test -p shuttle-common --features axum,models --test projects_api
```
