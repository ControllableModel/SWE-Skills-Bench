# Task: Build a Multi-Named Database Pool Example with Interface Binding

## Background

The `docs/ex` directory of the `go.uber.org/fx` repository is a standalone Go module (`go.uber.org/fx/docs`, with `replace go.uber.org/fx => ../`) hosting small self-contained example applications, each in its own package with a co-located `_test.go`. This task adds a new example showing how two constructors that build the *same Go type* can both be wired into one graph and selected unambiguously by a consumer, and how a concrete type can be exposed to consumers only through an interface.

## Files to Create/Modify

- `docs/ex/datapool/pool.go` (new) — a `Pool` concrete type and the `Store` interface it satisfies.
- `docs/ex/datapool/wiring.go` (new) — the constructors and the composition root exposing a reusable `Module`.
- `docs/ex/datapool/datapool_test.go` (new) — the deterministic test described in Acceptance Criteria.

All files use package name `datapool`. Reuse the existing `go.uber.org/fx/docs` module; do not create a new module or edit `go.mod`.

## Requirements

### Two pools of the same type

- Define an exported `Pool` struct with a `Label string` field and a `Ping() string` method returning `"pong:" + Label`.
- Provide two constructors, `NewPrimaryPool` and `NewReplicaPool`, both returning `*Pool` (the identical Go type) with labels `"primary"` and `"replica"` respectively.
- Both `*Pool` values must coexist in the same application graph and be retrievable independently. A consumer must be able to demand specifically the primary or specifically the replica without type-asserting at runtime or enumerating all pools.

### Interface binding

- Define an exported `Store` interface with a single method `Ping() string`.
- The graph must additionally expose the primary pool to consumers that depend on the `Store` interface (rather than the concrete `*Pool`). Consumers depending on `Store` must receive the primary.

### Consumer

- Define an exported `Report` struct with fields `Primary string`, `Replica string`, and `ViaInterface string`. Provide an exported `NewReport` constructor that depends on the primary `*Pool`, the replica `*Pool`, and the `Store` interface, and fills the three fields with their respective `Ping()` results.

### Composition root

- Expose an exported `Module` (`fx.Option`) wiring the two pools, the interface binding, and the report. A consumer must be able to boot with only `Module` and pull out a `*Report`.

### Edge cases & constraints

- Booting must not produce a missing-dependency, ambiguous-type, or cycle error.
- A naive single-`*Pool` provider must fail: the graph requires two distinct `*Pool` values to be selectable and one of them exposed as `Store`.
- The report must reflect: `Primary == "pong:primary"`, `Replica == "pong:replica"`, `ViaInterface == "pong:primary"`.

## Expected Functionality

- Scenario: boot and populate a `*Report` → outcome: `Primary == "pong:primary"`, `Replica == "pong:replica"`, `ViaInterface == "pong:primary"`.
- Scenario: depend on `Store` → outcome: receive the primary pool's behavior, not the replica's.

## Acceptance Criteria

- A new package `datapool` exists under `docs/ex/datapool/` exposing `Pool`, `Store`, `Report`, `NewPrimaryPool`, `NewReplicaPool`, `NewReport`, and `Module`.
- `docs/ex/datapool/datapool_test.go` boots via `fxtest.New(t, Module, fx.Populate(&rep))` for a `*Report`, calls `RequireStart().RequireStop()`, and asserts the three fields equal `"pong:primary"`, `"pong:replica"`, and `"pong:primary"`.
- The test asserts the graph is valid (no error) and that both pools are distinct instances.
- The following command, run from the `docs` directory, passes:

  ```bash
  cd docs && go test ./ex/datapool/...
  ```
