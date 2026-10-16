# Task: Build a Request-Scoped Error Context Propagation Module

## Background

The `samber/oops` repository ships several self-contained demonstration modules under `examples/` (each its own Go module, wired into the workspace via `go.work`). This task adds a new example module, `examples/reqscope`, that seeds request-scoped error metadata at the edge of a request and lets a deep handler produce a failure that automatically inherits that metadata via a Go `context.Context`.

## Files to Create/Modify

- `examples/reqscope/reqscope.go` (new) — the edge seeder and the deep handler.
- `examples/reqscope/reqscope_test.go` (new) — the deterministic tests described below.
- `examples/reqscope/go.mod` (new) — module `github.com/samber/oops/examples/reqscope`, Go 1.21, requiring `github.com/samber/oops`.
- `go.work` (modify) — add `./examples/reqscope` to the `use (...)` block.

## Requirements

The module simulates a request pipeline using only `context.Context` values — no HTTP server, no network. There are two stages: an **edge** stage that enriches a context with request-scoped error metadata, and a **handler** stage that, several calls deep, emits an error that must inherit that metadata without it being passed explicitly.

### Edge stage

Provide:

```go
func Seed(ctx context.Context, traceID string, tenantID string) context.Context
```

`Seed` returns a derived context carrying request-scoped error metadata: a trace/correlation id equal to `traceID`, a domain `"http-edge"`, and a context attribute `"tenant_id"` equal to `tenantID`. The original context MUST NOT be mutated; a new derived context is returned.

### Handler stage

Provide a small call chain (at least two functions deep) whose entry point is:

```go
func Handle(ctx context.Context, action string) error
```

`Handle` (and the helper it delegates to) emits a `samber/oops` error built **from the context produced by `Seed`** so that the failure automatically carries the seeded trace id, domain, and tenant attribute without `Handle`'s signature receiving them as parameters. The emitted error MUST additionally carry code `"action_rejected"` and a context attribute `"action"` equal to `action`. `Handle` returns `nil` only when `action == "allow"`; for any other action it returns the structured error.

### Inheritance requirement

For a context produced by `Seed(ctx, "trace-9", "tenant-7")`, an error from `Handle(seededCtx, "delete")` MUST expose, through its oops accessors:

- `Trace()` equal to `"trace-9"`.
- `Context()["tenant_id"]` equal to `"tenant-7"` (inherited from the seed) AND `Context()["action"]` equal to `"delete"` (added by the handler).
- `Code()` equal to `"action_rejected"`.

If `Handle` is called with a context that was NOT seeded, it MUST still return a usable oops error for a rejected action (carrying at least the `"action"` context and the `action_rejected` code), simply without the inherited trace/tenant.

### Expected Functionality

- `Handle(Seed(context.Background(), "trace-9", "tenant-7"), "allow")` -> `nil`.
- `Handle(Seed(context.Background(), "trace-9", "tenant-7"), "delete")` -> oops error with `Trace() == "trace-9"`, `Context()["tenant_id"] == "tenant-7"`, `Context()["action"] == "delete"`, code `action_rejected`.
- `Handle(context.Background(), "delete")` -> oops error with code `action_rejected` and `Context()["action"] == "delete"` (no inherited trace/tenant required).

## Acceptance Criteria

- `examples/reqscope/go.mod` declares module `github.com/samber/oops/examples/reqscope` and `go.work` lists `./examples/reqscope`.
- A naive implementation that threads `traceID`/`tenantID` as explicit parameters into `Handle`, rather than inheriting them from the context, fails the tests (the `Handle` signature is fixed as above).
- The added tests are deterministic and pass:

```
go test ./examples/reqscope/...
```

  run from the repository root, including the allow case, the seeded-inheritance case (trace + tenant + action all verified), and the unseeded fallback case.
