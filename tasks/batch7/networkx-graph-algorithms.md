# Task: Add a BFS Distance Histogram

## Background

The `networkx` library's breadth-first machinery lives under
`networkx/algorithms/traversal/`. This task adds a new module that, starting from
a source node, reports how many nodes sit at each hop-distance from the source —
a histogram of shortest-hop distances reachable by breadth-first exploration.

## Files to Create/Modify

- `networkx/algorithms/traversal/distance_histogram.py` (new) — the module implementing the public function below.
- `networkx/algorithms/traversal/__init__.py` (modify) — add `from networkx.algorithms.traversal.distance_histogram import *` so the function resolves as `nx.bfs_distance_histogram`.
- `networkx/algorithms/traversal/tests/test_distance_histogram.py` (new) — the deterministic unit tests.

## Requirements

### Public API

```python
def bfs_distance_histogram(G, source):
    ...
```

- `G` is an undirected `Graph` or directed `DiGraph`.
- `source` is a node present in `G`.

The function returns a `dict` mapping each reachable hop-distance `d` (an `int`
`>= 0`) to the number of nodes whose shortest-hop distance from `source` equals
`d`. Distance is measured in number of edges, ignoring any edge weights; for
directed graphs, edges may only be traversed in their direction.

### Edge cases and constraints

- **Source itself.** Key `0` always maps to `1` (the source).
- **Unreachable nodes.** Nodes not reachable from `source` contribute to no key.
- **Isolated source.** If `source` has no reachable neighbors, the result is
  `{0: 1}`.
- **Missing source.** If `source` is not a node of `G`, raise
  `networkx.NodeNotFound`.
- Only distances with a non-zero count appear as keys (no zero-count entries).
- The input graph `G` must not be mutated.

### Expected Functionality

- Path `0—1—2—3` from `source=0`: `{0: 1, 1: 1, 2: 1, 3: 1}`.
- Star with center `c` and three leaves, `source=c`: `{0: 1, 1: 3}`.
- Directed chain `0→1→2` with extra edge `0→2`, `source=0`: node `2` is at
  distance `1` (direct edge), so the histogram is `{0: 1, 1: 2}`.
- Graph with an isolated component unreachable from `source`: those nodes do not
  appear at any distance.

## Acceptance Criteria

- `nx.bfs_distance_histogram` resolves to the new function after the wiring.
- For every scenario above, the returned dict matches exactly (keys and counts).
- Directed traversal respects edge orientation; weights are ignored.
- `NodeNotFound` is raised for a missing source, and `G` is unchanged.
- The following command passes from the repository root:

```
python -m pytest networkx/algorithms/traversal/tests/test_distance_histogram.py -q
```
