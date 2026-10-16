# Task: Add a Ring-of-Cliques Generator

## Background

The `networkx` library's synthetic-graph constructors live under
`networkx/generators/`. This task adds a new deterministic generator that builds
a "ring of cliques": several equal-sized fully-connected clusters arranged in a
cycle, each cluster joined to the next by a single bridge edge.

## Files to Create/Modify

- `networkx/generators/ring_of_cliques.py` (new) — the module implementing the public function below.
- `networkx/generators/__init__.py` (modify) — add `from networkx.generators.ring_of_cliques import *` so the function resolves as `nx.ring_of_cliques`.
- `networkx/generators/tests/test_ring_of_cliques.py` (new) — the deterministic unit tests.

## Requirements

### Public API

```python
def ring_of_cliques(num_cliques, clique_size):
    ...
```

Returns an undirected `Graph`.

### Construction contract

- Build `num_cliques` cliques, each a complete graph on `clique_size` nodes.
- Nodes are integers `0 .. num_cliques * clique_size - 1`, assigned consecutively:
  clique `i` owns nodes `i*clique_size .. i*clique_size + clique_size - 1`.
- For each `i`, add exactly **one** bridge edge connecting the **last** node of
  clique `i` to the **first** node of clique `(i + 1) mod num_cliques`, so the
  cliques form a closed ring.
- The result has exactly `num_cliques * (clique_size choose 2)` intra-clique
  edges plus `num_cliques` bridge edges.
- The graph carries a graph-level attribute `G.graph["ring_of_cliques"] = (num_cliques, clique_size)`.

### Edge cases and constraints

- `num_cliques < 2` must raise `networkx.NetworkXError`.
- `clique_size < 2` must raise `networkx.NetworkXError`.
- The construction must be fully deterministic (no randomness): two calls with
  identical arguments produce graphs with identical node sets and edge sets.

### Expected Functionality

- `ring_of_cliques(3, 3)`: 9 nodes; `3 * 3 = 9` intra-clique edges plus `3`
  bridges, total `12` edges. The graph is connected.
- `ring_of_cliques(4, 2)`: each "clique" is a single edge (2 nodes); 8 nodes,
  `4` intra edges plus `4` bridges = `8` edges, forming one cycle of length 8.
- For `ring_of_cliques(2, 4)` the two cliques are joined by exactly 2 bridges
  (the ring wraps), giving `2*6 + 2 = 14` edges.

## Acceptance Criteria

- `nx.ring_of_cliques` resolves to the new function after the wiring.
- Node count, edge count, connectivity, and the `G.graph["ring_of_cliques"]`
  attribute match the scenarios above exactly.
- Invalid arguments raise `networkx.NetworkXError`; repeated calls with the same
  arguments yield identical edge sets.
- The following command passes from the repository root:

```
python -m pytest networkx/generators/tests/test_ring_of_cliques.py -q
```
