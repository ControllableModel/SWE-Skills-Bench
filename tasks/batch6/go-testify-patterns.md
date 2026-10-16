# Task: Add a Dependency-Layer Computer to the DAG Package

## Background

The `internal/dag` package implements the directed acyclic graph Terraform uses to order resource operations. While it already supports topological walks, it has no helper that groups vertices into parallelizable "layers" (each layer depending only on earlier layers). This task adds a deterministic, self-contained layering helper operating on a plain adjacency description so it can be tested without constructing full graph types.

## Files to Create/Modify

- `internal/dag/layers.go` (new) — a self-contained helper in package `dag`.
- `internal/dag/layers_test.go` (new) — the deterministic test for the new helper.

The new code must live in the existing `dag` package and must not perform any I/O or use randomness.

## Requirements

### `DependencyLayers`

Add an exported function:

```go
func DependencyLayers(nodes []string, dependsOn map[string][]string) ([][]string, error)
```

Given a set of node names and a map from each node to the list of nodes it depends on, it returns the nodes grouped into ordered layers suitable for parallel execution.

Behavior and constraints:

- Layer 0 contains every node with no (in-set) dependencies. Layer `k` contains every node all of whose dependencies appear in layers `0..k-1` and at least one in layer `k-1`.
- Within each layer, node names must be sorted ascending (lexicographic) so output is deterministic.
- Every node in `nodes` appears in exactly one layer; nodes not in `nodes` that appear only in `dependsOn` values are ignored (treated as already-satisfied external references).
- A dependency listed for a node that is not in `nodes` does not block that node (it is ignored).
- Duplicate entries in a node's dependency list are treated as one.
- If the dependency graph (restricted to `nodes`) contains a **cycle**, return a non-nil error and a `nil` layer list (never a panic, never an infinite loop).
- An empty `nodes` slice returns an empty (non-nil) layer list and a nil error.
- The result must be deterministic: identical inputs always produce identical layering.

### Expected Functionality

- `nodes=["a","b","c"]`, `dependsOn={"b":["a"],"c":["a","b"]}` -> `[["a"],["b"],["c"]]`.
- two independent roots `["x","a"]` with no deps -> a single layer `[["a","x"]]` (sorted).
- a self-cycle `{"a":["a"]}` or mutual cycle `{"a":["b"],"b":["a"]}` -> error.

## Acceptance Criteria

The new test file `internal/dag/layers_test.go` must exercise `DependencyLayers` using `github.com/stretchr/testify` (the project already depends on it) and must cover, at minimum:

- a linear chain producing one node per layer in order;
- multiple roots collapsing into a single first layer, sorted within the layer;
- a node whose only dependency is outside `nodes` being placed in layer 0;
- de-duplication of repeated dependency entries;
- both a self-cycle and a two-node mutual cycle returning a non-nil error with a nil layer list;
- an empty `nodes` input returning a non-nil empty layer list and nil error.

The following command, run from the repository root, must pass:

```
go test ./internal/dag/ -run TestDependencyLayers -v
```
