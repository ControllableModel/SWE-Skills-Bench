# Task: Add a Degree-Histogram Structural Fingerprint

## Background

The `networkx` library offers many descriptive graph metrics across
`networkx/algorithms/`. This task adds a new module that produces a compact,
order-independent "fingerprint" of a graph's structure and a comparison helper
that decides whether two graphs share the same fingerprint — a cheap necessary
condition for structural similarity.

## Files to Create/Modify

- `networkx/algorithms/structural_fingerprint.py` (new) — the module implementing the two functions below.
- `networkx/algorithms/__init__.py` (modify) — add `from networkx.algorithms.structural_fingerprint import *` so the functions resolve as `nx.structural_fingerprint` and `nx.same_fingerprint` (follow the existing `from networkx.algorithms.<module> import *` style).
- `networkx/algorithms/tests/test_structural_fingerprint.py` (new) — the deterministic unit tests.

## Requirements

### Public API

```python
def structural_fingerprint(G):
    ...

def same_fingerprint(G, H):
    ...
```

### Fingerprint contract

`structural_fingerprint(G)` returns a `dict` with exactly these keys:

- `"n_nodes"`: `int`, number of nodes.
- `"n_edges"`: `int`, number of edges.
- `"degree_histogram"`: a `tuple` of `int`s where index `d` holds the count of
  nodes of degree `d`, trimmed so the last element is non-zero (the empty graph
  yields an empty tuple `()`).
- `"n_triangles"`: `int`, the total number of triangles in the graph (each
  triangle counted once).

The dict must be independent of node labels and of node/edge insertion order:
two graphs that differ only by relabeling nodes produce **equal** dicts.

### Comparison contract

`same_fingerprint(G, H)` returns `True` iff `structural_fingerprint(G) ==
structural_fingerprint(H)`, else `False`.

### Edge cases and constraints

- Both functions operate on undirected `Graph`s; if either argument is directed,
  raise `networkx.NetworkXNotImplemented`.
- **Empty graph.** `structural_fingerprint` of a graph with no nodes returns
  `{"n_nodes": 0, "n_edges": 0, "degree_histogram": (), "n_triangles": 0}`.
- Neither input graph may be mutated.

### Expected Functionality

- A triangle and a path on 3 nodes have the **same** `n_nodes` and `n_edges`?
  No — triangle has 3 edges, path has 2; `same_fingerprint` returns `False`.
- Two triangles built with different node labels (`{0,1,2}` vs `{"a","b","c"}`)
  produce **equal** fingerprints; `same_fingerprint` returns `True`.
- A 4-cycle `0—1—2—3—0` has `degree_histogram=(0, 0, 4)` (four degree-2 nodes)
  and `n_triangles=0`.
- A triangle has `degree_histogram=(0, 0, 3)` and `n_triangles=1`.

## Acceptance Criteria

- `nx.structural_fingerprint` and `nx.same_fingerprint` resolve after the wiring.
- For every scenario above, fingerprints and comparison results match exactly;
  relabeled isomorphic graphs always compare equal.
- `NetworkXNotImplemented` is raised for directed inputs; neither graph is
  mutated.
- The following command passes from the repository root:

```
python -m pytest networkx/algorithms/tests/test_structural_fingerprint.py -q
```
