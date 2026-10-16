# Task: Build an SLA Timing Error Module

## Background

The `samber/oops` repository ships several self-contained demonstration modules under `examples/` (each its own Go module, wired into the workspace via `go.work`). This task adds a new example module, `examples/slacheck`, that records how long an operation took and produces a timing-annotated failure when the operation breaches its service-level deadline.

## Files to Create/Modify

- `examples/slacheck/slacheck.go` (new) — the timing check and its error producer.
- `examples/slacheck/slacheck_test.go` (new) — the deterministic tests described below.
- `examples/slacheck/go.mod` (new) — module `github.com/samber/oops/examples/slacheck`, Go 1.21, requiring `github.com/samber/oops`.
- `go.work` (modify) — add `./examples/slacheck` to the `use (...)` block.

## Requirements

The module evaluates timing deterministically from explicit `time.Time`/`time.Duration` values that the caller supplies — it MUST NOT call `time.Now()` or sleep, so tests are fully reproducible.

### Entry point

```go
func CheckSLA(operation string, startedAt time.Time, finishedAt time.Time, budget time.Duration) error
```

`CheckSLA` computes the elapsed duration as `finishedAt.Sub(startedAt)`. If the elapsed duration is less than or equal to `budget`, it returns `nil`. If the elapsed duration exceeds `budget`, it returns a `samber/oops` error that records the timing on the error itself.

### Timing attributes

A breach error MUST satisfy `oops.AsOops(err)` (`ok == true`) and MUST expose:

- `Code()` equal to `"sla_breached"`.
- domain (`Domain()`) equal to `"sla-monitor"`.
- the error's recorded duration (`Duration()`) equal to `finishedAt.Sub(startedAt)` (i.e. the actual elapsed time is carried on the error, not just in the message).
- context attribute `"operation"` equal to `operation`, and `"budget"` equal to `budget` (the budget duration value).

### Edge cases

- Exactly on budget (`elapsed == budget`) -> `nil` (not a breach).
- A `finishedAt` earlier than `startedAt` (negative elapsed) -> `nil` (cannot breach a positive budget).

### Low cardinality

The breach `err.Error()` MUST be constant regardless of `operation`, the elapsed duration, or `budget` — those values MUST be reachable only via `Duration()` and `Context()`, never embedded in the message string. The tests assert this by breaching with two different operations/durations and comparing `Error()` strings for exact equality while confirming `Duration()` and `Context()` differ.

### Expected Functionality

- `CheckSLA("fetch", t0, t0.Add(50*time.Millisecond), 100*time.Millisecond)` -> `nil`.
- `CheckSLA("fetch", t0, t0.Add(100*time.Millisecond), 100*time.Millisecond)` -> `nil` (on budget).
- `CheckSLA("fetch", t0, t0.Add(250*time.Millisecond), 100*time.Millisecond)` -> breach with `Code() == "sla_breached"`, `Domain() == "sla-monitor"`, `Duration() == 250ms`, context `operation == "fetch"`, `budget == 100ms`.
- `CheckSLA("fetch", t0, t0.Add(-10*time.Millisecond), 100*time.Millisecond)` -> `nil`.
- Two breaches with different operations/durations -> identical `Error()` strings, different `Duration()`/`Context()`.

## Acceptance Criteria

- `examples/slacheck/go.mod` declares module `github.com/samber/oops/examples/slacheck` and `go.work` lists `./examples/slacheck`.
- A naive implementation that embeds the elapsed time in the message, omits `Duration()` from the error, or treats the on-budget/negative cases as breaches, fails the tests.
- The added tests are deterministic (no real clock) and pass:

```
go test ./examples/slacheck/...
```

  run from the repository root, including the under-budget, on-budget, breach (with `Duration()` and context verified), negative-elapsed, and cross-breach message-cardinality cases.
