# Task: Build a Multi-Tenant Authorization Error Module

## Background

The `samber/oops` repository ships several self-contained demonstration modules under `examples/` (each its own Go module, wired into the workspace via `go.work`). This task adds a new example module, `examples/authz`, that models an authorization decision and attaches both the acting user and their tenant — with associated attributes — onto the failure so an audit trail can be reconstructed from the error alone.

## Files to Create/Modify

- `examples/authz/authz.go` (new) — the authorization check and its error producer.
- `examples/authz/authz_test.go` (new) — the deterministic tests described below.
- `examples/authz/go.mod` (new) — module `github.com/samber/oops/examples/authz`, Go 1.21, requiring `github.com/samber/oops`.
- `go.work` (modify) — add `./examples/authz` to the `use (...)` block.

## Requirements

The module evaluates an authorization request in-memory. No identity provider or network.

### Domain types

Define in `examples/authz/authz.go`:

- `Principal struct { UserID string; Email string; Role string; TenantID string; Plan string }`
- `AccessRequest struct { Principal Principal; Resource string; Action string }`

### Entry point

```go
func Authorize(req AccessRequest) error
```

`Authorize` returns `nil` when access is permitted and a structured `samber/oops` error when denied. Access is permitted only when `req.Principal.Role == "admin"`; for any other role, access is denied.

### Denial attributes

A denial error MUST satisfy `oops.AsOops(err)` (`ok == true`) and MUST expose:

- `Code()` equal to `"permission_denied"`.
- a public-facing message (`oops.GetPublic(err, "<fallback>")`) equal to `"You do not have access to this resource."`.
- through the user accessor (`User()` returning `(id, data)`): `id` equal to `req.Principal.UserID`, and the `data` map containing `"email"` equal to `req.Principal.Email` and `"role"` equal to `req.Principal.Role`.
- through the tenant accessor (`Tenant()` returning `(id, data)`): `id` equal to `req.Principal.TenantID`, and the `data` map containing `"plan"` equal to `req.Principal.Plan`.
- context attribute `"resource"` equal to `req.Resource` and `"action"` equal to `req.Action`.

### Low cardinality

The denial `err.Error()` MUST be constant across different principals/resources/actions — none of the variable identity, resource, or action data may appear in the message string; it MUST be reachable only through the user/tenant/context accessors. The tests assert this by denying two different requests and comparing `Error()` strings for exact equality while confirming the user/tenant/context values differ.

### Expected Functionality

- `Authorize(AccessRequest{Principal: Principal{Role:"admin", ...}, ...})` -> `nil`.
- `Authorize(AccessRequest{Principal: Principal{UserID:"u1", Email:"u1@x.io", Role:"viewer", TenantID:"t1", Plan:"pro"}, Resource:"billing", Action:"delete"})` -> denial with `Code() == "permission_denied"`, public `"You do not have access to this resource."`, user id `"u1"` + data `email/role`, tenant id `"t1"` + data `plan == "pro"`, context `resource == "billing"`, `action == "delete"`.
- Two denials with different principals produce byte-identical `Error()` strings but different `User()`/`Tenant()`/`Context()` values.

## Acceptance Criteria

- `examples/authz/go.mod` declares module `github.com/samber/oops/examples/authz` and `go.work` lists `./examples/authz`.
- A naive implementation that interpolates the user/tenant/resource into the message, or omits the user/tenant attributes, fails the tests.
- The added tests are deterministic and pass:

```
go test ./examples/authz/...
```

  run from the repository root, including the permit case, the deny case (all user/tenant/context attributes verified), and the cross-request message-cardinality case.
