# Task: Build a deployments HTTP API for shuttle-common

## Background

The `shuttle-common` crate (in `common/`) holds shared platform types for Shuttle. The `DeploymentState` enum lives in `common/src/models/deployment.rs` and the HTTP-error type `ApiError` in `common/src/models/error.rs` already converts itself into a response behind the `axum` feature. This task adds a small, self-contained HTTP API for tracking per-project deployments that lives inside `shuttle-common` and is gated behind the existing `axum` feature.

## Files to Create/Modify

- `common/src/deployments_api.rs` (new) — the request/response payloads, the shared in-memory deployment registry, the handlers, and a public constructor returning a fully wired `axum::Router` with no leftover state requirement.
- `common/src/lib.rs` (modify) — declare the new module, compiled only when both the `axum` and `models` features are enabled.
- `common/Cargo.toml` (modify) — add whatever dev-dependencies are needed to drive the router in-process from a test (the router must be exercised without binding a TCP port).
- `common/tests/deployments_api.rs` (new) — the deterministic integration test described under Acceptance Criteria.

## Requirements

### Public surface

Expose a single public constructor in `common/src/deployments_api.rs`:

```rust
pub fn router() -> axum::Router;
```

Calling `router()` must return a router ready to serve requests immediately, with no further configuration, store, or state to supply. Each call must produce an independent instance whose registry starts empty and shares no data with any other instance. The module and its `router` function must only exist when the crate is built with the `axum` feature.

### Data model

A deployment belongs to a `project` (a string in the URL path) and is identified by an `id` (a string), and carries a `state` that is the existing `DeploymentState` value (serialized exactly as that enum serializes, e.g. lowercase `"pending"`, `"building"`, `"running"`, `"stopped"`). The registry keeps at most one entry per `(project, id)` pair.

- The JSON used to create a deployment is `{ "id": "<string>" }`. A newly created deployment starts in the `Pending` state.
- The JSON used to advance a deployment's state is `{ "state": "<deployment-state>" }`.
- The JSON returned for a single deployment is `{ "id": "<string>", "state": "<deployment-state>" }`.
- The JSON returned when listing is `{ "deployments": [ { "id": ..., "state": ... }, ... ] }`, entries ordered by `id` ascending.

### Routes and behavior

| Method | Path | Behavior |
| ------ | ---- | -------- |
| GET    | `/projects/{project}/deployments`        | List deployments for the project, `id`-ascending. |
| POST   | `/projects/{project}/deployments`        | Create a new deployment in the `Pending` state. |
| GET    | `/projects/{project}/deployments/{id}`   | Read one deployment. |
| PATCH  | `/projects/{project}/deployments/{id}`   | Update only the deployment's state. |
| DELETE | `/projects/{project}/deployments/{id}`   | Remove the deployment. |

The five routes must be expressed across exactly two route paths, with multiple HTTP methods attached per path.

### Expected Functionality

- **Create** — `POST /projects/p/deployments` with `{"id":"d1"}` responds `201 Created` and the body reflects `{"id":"d1","state":"pending"}`. A second `POST` with the same `id` for the same project responds `409 Conflict` and does not change the existing entry.
- **Read** — `GET` of an existing deployment responds `200 OK` with its current id and state. `GET` of an unknown id, or of an id that exists only under a different project, responds `404 Not Found` with the crate's standard error body (a JSON object with a `message` field).
- **Advance state** — `PATCH` with `{"state":"running"}` responds `200 OK`, persists the new state, and a following read reflects it. A `PATCH` body whose `state` is not a recognized deployment state responds `400 Bad Request` and leaves the stored state unchanged. A `PATCH` to an unknown deployment responds `404`.
- **List** — `GET` the collection responds `200 OK`; an empty project yields `{"deployments":[]}`; multiple deployments appear `id`-ascending and never include deployments from other projects.
- **Delete** — `DELETE` of an existing deployment responds `204 No Content` with an empty body; a following read responds `404`. `DELETE` of an unknown deployment responds `404`.

### Constraints

- The registry must be shared safely across concurrent requests through the router's shared application data, never a global, and must not be passed in by the caller of `router()`.
- State values must round-trip through the existing `DeploymentState` enum rather than being stored as free-form strings; an unrecognized state string must be rejected before any mutation occurs.
- Error responses must use the crate's existing `ApiError`-based shape and the exact status codes specified.
- Do not start a server, open a socket, or use network, filesystem, clock, or randomness in the module or its test.

## Acceptance Criteria

- A new module `deployments_api` is compiled into `shuttle-common` only under the `axum` feature and exposes `pub fn router() -> axum::Router`.
- `common/tests/deployments_api.rs` drives the router fully in-process (no TCP port) and asserts at minimum:
  - First `POST` of an id yields `201` with `state == "pending"`; a duplicate `POST` yields `409`.
  - `GET` of an unknown id yields `404` with a JSON `message`; an id under project `a` reads `404` under project `b`.
  - `PATCH` to `"running"` yields `200` and the read reflects it; `PATCH` with an invalid state yields `400` and the stored state is unchanged; `PATCH` to an unknown id yields `404`.
  - `GET` list yields `{"deployments":[]}` empty, then an `id`-ascending array scoped to one project.
  - `DELETE` yields `204` empty then a `404` read; `DELETE` of an unknown id yields `404`.
- A naive implementation that ignores the project segment, returns a fixed status, hardcodes responses, or skips storage must fail.
- The following command, run from the repository root, passes:

```
cargo test -p shuttle-common --features axum,models --test deployments_api
```
