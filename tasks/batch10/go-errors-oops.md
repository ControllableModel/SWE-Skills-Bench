# Task: Build a Per-Layer Error Annotation Module

## Background

The `samber/oops` repository ships several self-contained demonstration modules under `examples/` (each its own Go module, wired into the workspace via `go.work`). This task adds a new example module, `examples/pipeline`, that pushes a single failure up through a fixed stack of named stages, where each stage annotates the error so the final value records the full path the error travelled.

## Files to Create/Modify

- `examples/pipeline/pipeline.go` (new) — the staged pipeline and its error producer.
- `examples/pipeline/pipeline_test.go` (new) — the deterministic tests described below.
- `examples/pipeline/go.mod` (new) — module `github.com/samber/oops/examples/pipeline`, Go 1.21, requiring `github.com/samber/oops`.
- `go.work` (modify) — add `./examples/pipeline` to the `use (...)` block.

## Requirements

The module runs a fixed three-stage pipeline entirely in-memory (no network). The stages, from innermost to outermost, are: `storage` -> `domain` -> `api`. A failure originates in `storage` and is forwarded outward through `domain` and `api`, with each stage adding its own annotation.

### Entry point

```go
func Process(recordID string) error
```

`Process` is the outermost (`api`) stage. It calls the `domain` stage, which calls the `storage` stage. When `recordID == "ok"`, the whole pipeline succeeds and `Process` returns `nil`. For any other `recordID`, the `storage` stage originates a failure that is forwarded (wrapped) by `domain` and then by `api`.

### Per-stage annotation requirements

The single error returned by `Process` for a failing `recordID` MUST satisfy `oops.AsOops(err)` (`ok == true`) and MUST aggregate metadata contributed by all three stages:

- The **originating** (deepest) stage MUST set domain `"storage"`, code `"record_unreadable"`, and context attribute `"record_id"` equal to `recordID`.
- The **domain** stage MUST contribute its own context attribute `"stage"` equal to `"domain"` while forwarding the inner error.
- The **api** stage MUST contribute a trace/correlation id and forward the inner error.

The error chain MUST be inspectable such that:

- `oops.AsOops(err)` then `.Code()` resolves to `"record_unreadable"` (the deepest code is surfaced).
- `.Domain()` resolves to `"storage"` (the deepest domain).
- `.Context()` (the flattened context across the chain) contains BOTH `"record_id"` (from storage) AND `"stage" == "domain"` (from the domain layer).
- the error's layer chain has at least three distinct layers (i.e. `len(oopsErr.Layers()) >= 3`), reflecting that three stages each annotated it.

Forwarding MUST be done without nil checks at each layer (a passed-through `nil` from an inner stage MUST yield `nil` at the outer stage), so that on the success path `Process("ok")` returns `nil` cleanly even though it flows through all three wrapping stages.

### Expected Functionality

- `Process("ok")` -> `nil` (flows through all three stages, each of which is a no-op wrap over a nil inner error).
- `Process("missing")` -> single oops error with deepest `Code() == "record_unreadable"`, deepest `Domain() == "storage"`, flattened `Context()` containing `record_id == "missing"` and `stage == "domain"`, and `len(Layers()) >= 3`.

## Acceptance Criteria

- `examples/pipeline/go.mod` declares module `github.com/samber/oops/examples/pipeline` and `go.work` lists `./examples/pipeline`.
- A naive implementation that produces the error at a single layer (no per-stage annotation, fewer than three layers), or that adds explicit nil checks that break the clean success path, fails the tests.
- The added tests are deterministic and pass:

```
go test ./examples/pipeline/...
```

  run from the repository root, including the success case and the failure case asserting the surfaced code, domain, flattened context keys from two different layers, and `len(Layers()) >= 3`.
