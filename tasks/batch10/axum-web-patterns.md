# Task: Build a team-invite API accepting form and JSON bodies in shuttle-common

## Background

The `shuttle-common` crate (in `common/`) defines team types in `common/src/models/team.rs` (including the `TeamRole` enum, which serializes lowercase as `"owner"`, `"admin"`, `"member"`) and the `ApiError` type in `common/src/models/error.rs`, which converts to an HTTP response behind the `axum` feature. This task adds a small, self-contained HTTP API for issuing team invites where the create endpoint accepts an HTML-form-encoded body while the read endpoint returns JSON. It lives inside `shuttle-common` and is gated behind the existing `axum` feature.

## Files to Create/Modify

- `common/src/invites_api.rs` (new) — the form payload type, the JSON response types, the shared in-memory invite store, the handlers, and a public constructor returning a fully wired `axum::Router`.
- `common/src/lib.rs` (modify) — declare the new module, compiled only when both the `axum` and `models` features are enabled.
- `common/Cargo.toml` (modify) — add whatever dev-dependencies are needed to drive the router in-process from a test (no TCP port). The `axum` form extractor must be available.
- `common/tests/invites_api.rs` (new) — the deterministic integration test described under Acceptance Criteria.

## Requirements

### Public surface

Expose a single public constructor in `common/src/invites_api.rs`:

```rust
pub fn router() -> axum::Router;
```

`router()` must return a router ready to serve requests immediately, each call producing an independent, empty store. The module and its `router` function must only exist when the crate is built with the `axum` feature.

### Data model

An invite belongs to a `team` (a string in the URL path) and is identified by an `email`; it carries a `role` that is the existing `TeamRole` value. The store keeps at most one invite per `(team, email)` pair.

- The create body is `application/x-www-form-urlencoded` with fields `email` and `role` (the role string must be one of the `TeamRole` values).
- The single-invite JSON response is `{ "email": "<string>", "role": "<role>" }`.
- The list JSON response is `{ "invites": [ { "email": ..., "role": ... }, ... ] }`, entries ordered by `email` ascending.

### Routes and behavior

| Method | Path | Request body | Behavior |
| ------ | ---- | ------------ | -------- |
| POST   | `/teams/{team}/invites`           | form-encoded | Create or replace an invite. |
| GET    | `/teams/{team}/invites`           | none         | List the team's invites (JSON), `email`-ascending. |
| GET    | `/teams/{team}/invites/{email}`   | none         | Read one invite (JSON). |

### Expected Functionality

- **Create from form** — `POST /teams/acme/invites` with form body `email=a@x.com&role=admin` responds `201 Created`. A following `GET /teams/acme/invites/a@x.com` responds `200 OK` with JSON `{"email":"a@x.com","role":"admin"}`.
- **Replace** — a second form `POST` for the same `(team, email)` with a different role responds `200 OK` (not `201`) and updates the role; a subsequent read returns the new role; the store still holds exactly one entry for that pair.
- **Invalid role** — a form `POST` whose `role` is not a valid `TeamRole` (e.g. `role=superuser`) responds `400 Bad Request` and creates nothing.
- **Missing field / wrong content type** — a `POST` body missing `email` or `role`, or one that is not form-encoded, responds `400 Bad Request` and creates nothing.
- **Read missing** — `GET` of an `(team, email)` never created responds `404 Not Found` with the crate's standard error body (a JSON object with a `message` field). An email invited to a different team is treated as missing.
- **List** — `GET /teams/{team}/invites` responds `200 OK`; an empty team yields `{"invites":[]}`; multiple invites appear `email`-ascending and never include invites from other teams.

### Constraints

- The create handler must consume a form-encoded body; the read/list handlers return JSON. A create request sent as raw JSON (rather than form encoding) must be rejected with `400`.
- The `role` must round-trip through the existing `TeamRole` enum; an unrecognized role string must be rejected before any mutation.
- The store must be shared safely across concurrent requests via the router's shared application data, not a global, and not passed in by the caller.
- All error bodies must use the crate's existing `ApiError`-based shape with the status codes specified.
- Do not start a server, open a socket, or use network, filesystem, clock, or randomness.

## Acceptance Criteria

- A new module `invites_api` is compiled into `shuttle-common` only under the `axum` feature and exposes `pub fn router() -> axum::Router`.
- `common/tests/invites_api.rs` drives the router fully in-process (no TCP port) and asserts at minimum:
  - A form `POST` with a valid role yields `201`; the read returns JSON `{"email":...,"role":...}` matching what was sent.
  - A second form `POST` to the same path with a different valid role yields `200` and the read reflects the new role; only one entry exists for that pair.
  - A form `POST` with an invalid role yields `400` and creates nothing (a subsequent read `404`s).
  - A `POST` missing a required field, or sent as JSON instead of form encoding, yields `400` and creates nothing.
  - `GET` of an unknown `(team, email)` yields `404` with a JSON `message`; an email under team `a` reads `404` under team `b`.
  - `GET` list yields `{"invites":[]}` for an empty team and an `email`-ascending array scoped to one team.
- A naive implementation that ignores the team segment, accepts any role, hardcodes responses, or accepts JSON for create must fail.
- The following command, run from the repository root, passes:

```
cargo test -p shuttle-common --features axum,models --test invites_api
```
