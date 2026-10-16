# Task: Add a Neighborhood Triangle Profile

## Background

The `networkx` library keeps clustering and triangle-counting routines in
`networkx/algorithms/cluster.py`. This task adds a new self-contained module that
reports, for each node, both the raw number of triangles it participates in and
its local clustering coefficient, together in one pass.

## Files to Create/Modify

- `networkx/algorithms/triangle_profile.py` (new) — the module implementing the public function below.
- `networkx/algorithms/__init__.py` (modify) — add `from networkx.algorithms.triangle_profile import *` so the function resolves as `nx.triangle_profile` (follow the existing `from networkx.algorithms.<module> import *` style).
- `networkx/algorithms/tests/test_triangle_profile.py` (new) — the deterministic unit tests.

## Requirements

### Public API

```python
def triangle_profile(G, nodes=None):
    ...
```

- `G` is an undirected `Graph` without self-loops in test inputs.
- `nodes` is `None` (report every node) or an iterable of node identifiers present in `G`.

The function returns a `dict` mapping each requested node to a `dict` with
exactly these keys:

- `"triangles"`: `int`, the number of triangles the node belongs to.
- `"degree"`: `int`, the node's degree.
- `"clustering"`: `float`, the local clustering coefficient, defined as
  `2 * triangles / (degree * (degree - 1))` for `degree >= 2`, otherwise `0.0`.

### Edge cases and constraints

- **Low degree.** A node with degree `0` or `1` has `triangles=0` and
  `clustering=0.0`.
- **Single node query.** When `nodes` names one node, the returned dict has a
  single entry for that node.
- **Unknown node.** If any element of `nodes` is not in `G`, raise
  `networkx.NodeNotFound`.
- **Directed input.** If `G` is directed, raise `networkx.NetworkXNotImplemented`.
- The input graph `G` must not be mutated.

### Expected Functionality

- Triangle `0—1—2`: every node has `triangles=1, degree=2, clustering=1.0`.
- Path `0—1—2`: node `1` has `degree=2, triangles=0, clustering=0.0`; endpoints
  have `degree=1, clustering=0.0`.
- "Bowtie" (two triangles `{0,1,2}` and `{2,3,4}` sharing node `2`): node `2` has
  `triangles=2, degree=4, clustering=2*2/(4*3)=1/3`; the other four nodes have
  `triangles=1, degree=2, clustering=1.0`.

## Acceptance Criteria

- `nx.triangle_profile` resolves to the new function after the wiring.
- For every scenario above, the per-node dicts match: `triangles` and `degree`
  exact ints, `clustering` within tolerance `1e-9`.
- `NodeNotFound` and `NetworkXNotImplemented` are raised as specified, and `G`
  is unchanged after any call.
- The following command passes from the repository root:

```
python -m pytest networkx/algorithms/tests/test_triangle_profile.py -q
```
