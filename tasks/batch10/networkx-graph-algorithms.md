# Task: Add an Attribute-Filtered Ego Subgraph Extractor

## Background

The `networkx` library exposes ego-network construction in
`networkx/algorithms/ego.py` and supports rich node/edge attributes. This task
adds a new module that extracts the neighborhood around a center node while
keeping only nodes whose attributes satisfy a caller-supplied predicate.

## Files to Create/Modify

- `networkx/algorithms/ego_filtered.py` (new) — the module implementing the public function below.
- `networkx/algorithms/__init__.py` (modify) — add `from networkx.algorithms.ego_filtered import *` so the function resolves as `nx.filtered_ego_graph` (follow the existing `from networkx.algorithms.<module> import *` style).
- `networkx/algorithms/tests/test_ego_filtered.py` (new) — the deterministic unit tests.

## Requirements

### Public API

```python
def filtered_ego_graph(G, center, radius=1, node_filter=None):
    ...
```

- `G` is an undirected `Graph` or directed `DiGraph`.
- `center` is a node present in `G`; it is **always** included in the result
  regardless of the filter.
- `radius` is a non-negative `int`: include nodes whose shortest-hop distance
  from `center` is `<= radius` (directed graphs follow edge direction).
- `node_filter` is `None` (keep all in-range nodes) or a callable
  `f(node, attrs) -> bool` receiving the node id and its attribute dict; only
  nodes for which it returns truthy are kept (the center is exempt).

The function returns a **new** `Graph`/`DiGraph` (same type as `G`) that is the
subgraph induced on the kept node set, carrying over the node and edge attributes
from `G`. The returned graph must be an independent copy (mutating it must not
affect `G`).

### Edge cases and constraints

- **Radius 0.** Returns a graph containing only `center` (with its attributes)
  and no edges.
- **Center always kept.** Even if `node_filter(center, ...)` is falsy, `center`
  remains in the result.
- **Induced edges only.** An edge is present iff **both** its endpoints survive
  filtering and the range cutoff.
- **Missing center.** If `center` is not a node of `G`, raise
  `networkx.NodeNotFound`.
- The input graph `G` must not be mutated.

### Expected Functionality

- Star: center `c` (attr `team="A"`) with leaves `x,y,z` where `x.team="A"`,
  `y.team="B"`, `z.team="A"`; `radius=1`, `node_filter=lambda n, d: d.get("team")=="A"`:
  result keeps `{c, x, z}` and the edges `c—x`, `c—z` only.
- Path `0—1—2—3` with `center=0, radius=2, node_filter=None`: result keeps
  `{0,1,2}` and edges `0—1`, `1—2`.
- `radius=0` on any graph returns a single-node graph holding only `center`.
- Directed chain `0→1→2`, `center=0, radius=2`: keeps `{0,1,2}` with directed
  edges `0→1`, `1→2`; the reverse direction is never added.

## Acceptance Criteria

- `nx.filtered_ego_graph` resolves to the new function after the wiring.
- For every scenario above, the returned graph's node set and edge set match
  exactly, node/edge attributes are preserved, and the result is the correct
  graph type.
- The result is an independent copy; `NodeNotFound` is raised for a missing
  center; `G` is unchanged after any call.
- The following command passes from the repository root:

```
python -m pytest networkx/algorithms/tests/test_ego_filtered.py -q
```
