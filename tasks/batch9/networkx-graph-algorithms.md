# Task: Add a Minimum Disconnecting Edge-Set Reporter

## Background

The `networkx` library provides flow and connectivity routines under
`networkx/algorithms/connectivity/` and `networkx/algorithms/flow/`. This task
adds a new module that reports the smallest set of edges whose removal severs all
paths between a given source and target — and the size of that set.

## Files to Create/Modify

- `networkx/algorithms/connectivity/min_disconnect.py` (new) — the module implementing the public function below.
- `networkx/algorithms/connectivity/__init__.py` (modify) — add `from networkx.algorithms.connectivity.min_disconnect import *` so the function resolves as `nx.minimum_disconnecting_edges`.
- `networkx/algorithms/connectivity/tests/test_min_disconnect.py` (new) — the deterministic unit tests.

## Requirements

### Public API

```python
def minimum_disconnecting_edges(G, source, target):
    ...
```

- `G` is an undirected `Graph` or directed `DiGraph`, unweighted (every edge
  counts equally).
- `source` and `target` are distinct nodes present in `G`.

The function returns a `dict` with exactly two keys:

- `"size"`: `int`, the minimum number of edges that must be removed so that
  `target` is no longer reachable from `source`.
- `"edges"`: a `set` of edge tuples `(u, v)` forming one such minimum-size
  edge cut. For undirected graphs each tuple may appear in either orientation; the
  test compares them as **frozensets of frozenset-pairs** so orientation does not matter.

The reported `"size"` must equal the cardinality of the local edge connectivity
between `source` and `target`, and removing exactly the reported `"edges"` from a
copy of `G` must leave `target` unreachable from `source`.

### Edge cases and constraints

- **Already disconnected.** If `target` is not reachable from `source`, return
  `{"size": 0, "edges": set()}`.
- **Same endpoints.** If `source == target`, raise `networkx.NetworkXError`.
- **Missing endpoint.** If `source` or `target` is not a node of `G`, raise
  `networkx.NodeNotFound`.
- The input graph `G` must not be mutated.

### Expected Functionality

- Two parallel-disjoint paths `0—1—3` and `0—2—3`, query `source=0, target=3`:
  `size` is `2`, and removing the reported two edges disconnects `0` from `3`.
- A single bridge: two triangles joined by edge `2—3`, query across the bridge
  `source=0, target=5`: `size` is `1`, and the reported single edge is the bridge.
- Directed graph `0→1→2`, query `source=0, target=2`: `size` is `1`.
- Already-disconnected pair (two separate components): `{"size": 0, "edges": set()}`.

## Acceptance Criteria

- `nx.minimum_disconnecting_edges` resolves to the new function after the wiring.
- For every scenario above, `"size"` matches exactly, and **removing the reported
  edges from a fresh copy of `G` actually disconnects `target` from `source`**
  (the test must verify this with reachability, not by matching a specific edge
  set), and `len(result["edges"]) == result["size"]`.
- `NetworkXError` and `NodeNotFound` are raised as specified; `G` is unchanged.
- The following command passes from the repository root:

```
python -m pytest networkx/algorithms/connectivity/tests/test_min_disconnect.py -q
```
