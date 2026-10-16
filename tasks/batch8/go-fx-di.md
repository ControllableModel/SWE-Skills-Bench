# Task: Build a Health-Check Aggregator Example with Many-to-One Wiring

## Background

The `docs/ex` directory of the `go.uber.org/fx` repository is a standalone Go module (`go.uber.org/fx/docs`, with `replace go.uber.org/fx => ../`) hosting small self-contained example applications, each in its own package with a co-located `_test.go`. This task adds a new example showing how multiple independently-registered check producers are gathered into one aggregator that reports overall health, using parameter and result struct wiring rather than long positional constructor signatures.

## Files to Create/Modify

- `docs/ex/healthagg/check.go` (new) — the `Check` abstraction (name + status func).
- `docs/ex/healthagg/producers.go` (new) — three independent check producers, each emitting its check through a result struct.
- `docs/ex/healthagg/aggregator.go` (new) — the aggregator consuming all checks through a parameter struct, plus the reusable `Module`.
- `docs/ex/healthagg/healthagg_test.go` (new) — the deterministic test described in Acceptance Criteria.

All files use package name `healthagg`. Reuse the existing `go.uber.org/fx/docs` module; do not create a new module or edit `go.mod`.

## Requirements

### Check abstraction

- Define an exported `Check` struct with a `Name string` field and a `Status func() bool` field (returns true when healthy).
- Provide three independent producers `NewDiskCheck`, `NewMemCheck`, and `NewNetCheck`. Each emits one `Check` named `"disk"`, `"mem"`, and `"net"` respectively. Each producer must emit its `Check` via a result struct so the value joins a shared collection; producers must not enumerate each other.

### Aggregator with parameter struct

- Define an exported `Aggregator` type. Its constructor `NewAggregator` must receive the full collection of registered `Check` values through a parameter struct (the aggregator must additionally accept a `*zap.Logger`, demonstrating mixed dependencies). The aggregator must NOT reference the individual producers by name.
- `Aggregator` must expose `Healthy() bool` (true iff every check's `Status()` returns true) and `Report() map[string]bool` mapping each check name to its current status.
- Adding a fourth producer later must change the aggregated report with no edit to `aggregator.go`.

### Composition root

- Expose an exported `Module` (`fx.Option`) wiring the three producers and the aggregator, such that booting `Module` plus a supplied `*zap.Logger` yields a working `*Aggregator`.

### Edge cases & constraints

- Booting must not produce a missing-dependency or cycle error.
- `Report()` must contain exactly one entry per registered check (3 here); a hardcoded 3-key map detached from the collection must not satisfy the count-equals-collection-size assertion.
- Status functions must be deterministic for the test (e.g. disk and mem healthy, net configurable) so `Healthy()` is reproducible.

## Expected Functionality

- Scenario: all three checks healthy → outcome: `Healthy() == true` and `Report()` has 3 keys all `true`.
- Scenario: the net check reports unhealthy → outcome: `Healthy() == false` and `Report()["net"] == false`.
- Scenario: add a fourth producer → outcome: `Report()` gains a 4th key with no change to `aggregator.go`.

## Acceptance Criteria

- A new package `healthagg` exists under `docs/ex/healthagg/` exposing `Check`, `NewDiskCheck`, `NewMemCheck`, `NewNetCheck`, `Aggregator` (with `Healthy()` and `Report()`), `NewAggregator`, and `Module`.
- `docs/ex/healthagg/healthagg_test.go` boots via `fxtest.New(t, Module, fx.Supply(zap.NewNop()), fx.Populate(&agg))`, calls `RequireStart().RequireStop()`, and asserts: `Report()` has exactly 3 keys; with all healthy, `Healthy()` is true; and the key set is `{"disk","mem","net"}`.
- The aggregator constructor receives its checks through a parameter struct (verified by the wiring compiling and the collection size matching the number of producers).
- The following command, run from the `docs` directory, passes:

  ```bash
  cd docs && go test ./ex/healthagg/...
  ```
