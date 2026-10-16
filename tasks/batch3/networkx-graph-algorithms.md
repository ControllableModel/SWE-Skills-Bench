# Task: Add a Partition Cohesion Reporter

## Background

The `networkx` library keeps community-structure code under
`networkx/algorithms/community/`. This task adds a new module that, given a
user-supplied grouping of nodes into communities, reports per-community
structural statistics describing how internally cohesive and externally
separated each group is.

## Files to Create/Modify

- `networkx/algorithms/community/cohesion.py` (new) — the module implementing the public function below.
- `networkx/algorithms/community/__init__.py` (modify) — add `from networkx.algorithms.community.cohesion import *` so the function resolves as `nx.community.partition_cohesion`.
- `networkx/algorithms/community/tests/test_cohesion.py` (new) — the deterministic unit tests.

## Requirements

### Public API

```python
def partition_cohesion(G, communities):
    ...
```

- `G` is an undirected `Graph` (no self-loops in the test inputs).
- `communities` is an iterable of node-sets (each a `set`/`frozenset`/iterable) that
  together form a **partition** of all nodes of `G` (every node in exactly one group).

The function returns a `list` of `dict`s, one per input community, **in the same
order** the communities were provided. Each dict has exactly these keys:

- `"size"`: `int`, the number of nodes in the community.
- `"internal_edges"`: `int`, edges with both endpoints inside the community.
- `"boundary_edges"`: `int`, edges with exactly one endpoint inside the community.
- `"conductance"`: `float`, defined as `boundary_edges / (2 * internal_edges + boundary_edges)`.

### Edge cases and constraints

- **Singleton community.** A community with one node has `internal_edges == 0`;
  its conductance is `boundary_edges / boundary_edges == 1.0` if it has any
  boundary edge, else `0.0`.
- **Isolated community.** A community with no internal and no boundary edges has
  conductance `0.0` (define `0/0` as `0.0`).
- **Not a partition.** If the supplied groups do not cover every node exactly
  once (a node missing, duplicated, or a node not in `G`), raise
  `networkx.NetworkXError`.
- The input graph `G` must not be mutated.

### Expected Functionality

- Two triangles `{0,1,2}` and `{3,4,5}` joined by a single bridge edge `2—3`,
  partition `[{0,1,2}, {3,4,5}]`: each community reports
  `size=3, internal_edges=3, boundary_edges=1, conductance=1/7`.
- Path `0—1—2—3` with partition `[{0,1}, {2,3}]`: each community reports
  `internal_edges=1, boundary_edges=1, conductance=1/3`.
- A single community containing every node has `boundary_edges=0` and
  `conductance=0.0`.

## Acceptance Criteria

- `nx.community.partition_cohesion` resolves to the new function after the wiring.
- For every scenario above, the returned list (order and dict contents) matches
  exactly; integer keys are `int`, `conductance` compared with a tolerance of
  `1e-9`.
- The `NetworkXError` is raised for any non-partition input, and `G` is unchanged.
- The following command passes from the repository root:

```
python -m pytest networkx/algorithms/community/tests/test_cohesion.py -q
```
