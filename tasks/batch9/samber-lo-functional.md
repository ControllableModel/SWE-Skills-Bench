# Task: Build a Dependency Topology Validator

## Background

This repository (`github.com/samber/lo`) is a generics-first utility library for Go. To exercise the library against a realistic workload, add a small self-contained example application under a new `examples/depgraph` package that validates a build-dependency graph and produces a deterministic, layered build order.

## Files to Create/Modify

- `examples/depgraph/depgraph.go` (new) — the graph logic, in `package depgraph`.
- `examples/depgraph/depgraph_test.go` (new) — table-driven tests, in `package depgraph`, using only the Go stdlib `testing` package.

Both files belong to the existing module `github.com/samber/lo` (`go 1.18`), so the import path for the new package is `github.com/samber/lo/examples/depgraph`. You may import `github.com/samber/lo` from within the new package.

## Requirements

### Input and output types

Define the following exported types in `examples/depgraph/depgraph.go`:

```go
// Node names a build target; DependsOn lists target names it requires built first.
type Node struct {
    Name      string
    DependsOn []string
}

// A Layer is a set of targets buildable in parallel (no intra-layer dependency),
// listed in ascending lexicographic order.
type Layer []string
```

### Behavior

Implement:

```go
// Layers returns the targets grouped into dependency layers: layer 0 has all
// targets with no dependencies, layer k has targets whose dependencies are all
// satisfied by layers < k.
func Layers(nodes []Node) ([]Layer, error)
```

with the following rules:

#### Validation
- If two nodes share the same `Name`, return `(nil, error)` (duplicate definition); do not panic.
- If any `DependsOn` entry names a target that is not defined as a `Node`, return `(nil, error)` (dangling dependency); do not panic.
- If the dependency graph contains a cycle, return `(nil, error)`; do not panic.

#### Layering
- Layer 0 contains every target whose `DependsOn` is empty (after de-duplicating its own dependency list).
- Layer `k` (k>0) contains every not-yet-placed target all of whose dependencies appear in layers `0..k-1`.
- Within each `Layer`, target names are sorted ascending lexicographically.
- A target's `DependsOn` may list the same dependency more than once; duplicates have no additional effect.

### Edge cases
- An empty `nodes` slice returns an empty (non-nil) `[]Layer` and a nil error.
- A target depending on itself is a cycle and yields an error.
- `Layers` must not mutate the caller's input or any node's `DependsOn` slice.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| Linear chain a<-b<-c | Three layers: `[a]`, `[b]`, `[c]` |
| Two independent roots | Both in layer 0, sorted |
| Duplicate node name | Non-nil error |
| Dependency on undefined target | Non-nil error |
| Cycle (incl. self-loop) | Non-nil error |
| Empty input | Empty non-nil layers, nil error |

## Acceptance Criteria

- The package `github.com/samber/lo/examples/depgraph` compiles.
- `Layers` satisfies every rule above, verified by the new table-driven test covering: correct layer assignment for chains and diamonds, intra-layer ascending sort, duplicate-name error, dangling-dependency error, cycle detection (including a self-loop), duplicate-dependency tolerance, the empty-input case, and input-immutability (at least 10 assertions/cases total).
- The following command, run from the repository root, passes with no failures:

```
go test ./examples/depgraph/ -run TestLayers -count=1
```

- A naive implementation that ignores cycles, fails to detect dangling/duplicate definitions, mis-layers transitive dependencies, or leaves layers unsorted must fail the test.
