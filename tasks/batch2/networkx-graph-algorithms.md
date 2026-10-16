# Task: Add a Hub-Set Mediation Scorer

## Background

The `networkx` library groups its centrality routines under
`networkx/algorithms/centrality/`. This task adds a new self-contained module
that measures, for a designated *set* of nodes treated as a single gateway, how
much of the all-pairs shortest-path traffic in the rest of the network must pass
through that gateway.

## Files to Create/Modify

- `networkx/algorithms/centrality/hub_mediation.py` (new) — the module implementing the public function below.
- `networkx/algorithms/centrality/__init__.py` (modify) — add `from networkx.algorithms.centrality.hub_mediation import *` so the function resolves as `nx.hub_set_mediation` (follow the existing `from ... import *` lines in this file).
- `networkx/algorithms/centrality/tests/test_hub_mediation.py` (new) — the deterministic unit tests.

## Requirements

### Public API

```python
def hub_set_mediation(G, hubs, weight=None):
    ...
```

- `G` is an undirected `Graph` or directed `DiGraph`.
- `hubs` is an iterable of node identifiers, all present in `G`; treat it as a set `S`.
- `weight` is `None` (each edge has cost 1) or a string naming a non-negative edge-cost attribute.

The function returns a single `float` in the closed interval `[0.0, 1.0]`.

### Score definition

Consider every **ordered pair** `(s, t)` of nodes where `s` and `t` are both
**outside** `S`, `s != t`, and `t` is reachable from `s`. For each such pair let
`sigma(s, t)` be the number of distinct shortest `s`→`t` paths, and
`sigma_S(s, t)` the number of those shortest paths that contain **at least one**
node of `S` as an interior node (not as the endpoint). The score is

```
sum over valid (s, t) of  sigma_S(s, t) / sigma(s, t)
-----------------------------------------------------
        number of valid ordered pairs (s, t)
```

For undirected graphs, count each unordered pair once (i.e. only pairs with a
fixed orientation, not both `(s,t)` and `(t,s)`).

### Edge cases and constraints

- **Empty hub set.** If `hubs` is empty, return `0.0`.
- **Hubs cover everything.** If every node of `G` is in `S` (no node outside),
  there are no valid pairs; return `0.0`.
- **No valid reachable pairs.** If no ordered pair of outside nodes is connected,
  return `0.0`.
- **Unknown hub.** If any element of `hubs` is not a node of `G`, raise
  `networkx.NodeNotFound`.
- The input graph `G` must not be mutated.

### Expected Functionality

- Path `0—1—2—3—4` (unweighted), `hubs={2}`: outside pairs whose unique shortest
  path passes through node `2` are exactly `(0,3),(0,4),(1,3),(1,4)`; of the
  outside-pair set the fraction routed through `2` gives score `0.4`.
- Star with center `c` and leaves `a,b,d` (`hubs={c}`): every leaf-to-leaf
  shortest path goes through `c`, so the score is `1.0`.
- Triangle `0—1—2` with `hubs={2}`: the only outside pair `(0,1)` has a direct
  edge whose shortest path never uses node `2`, so the score is `0.0`.

## Acceptance Criteria

- `nx.hub_set_mediation` resolves to the new function after the import wiring.
- All scenarios in **Expected Functionality** produce the stated float values
  (exact equality after the division).
- The result always lies in `[0.0, 1.0]`; weighted queries honor the named
  attribute; directed queries respect edge orientation.
- The error condition (`NodeNotFound`) is raised as specified and `G` is
  unchanged after any call.
- The following command passes from the repository root:

```
python -m pytest networkx/algorithms/centrality/tests/test_hub_mediation.py -q
```
