# Task: Add a Route-Resilience Analyzer Module

## Background

The `networkx` library ships many analysis routines under `networkx/algorithms/`.
This task adds a new self-contained module that reports how dependent a given
origin/destination connection is on each individual relay node in a transportation
or communication network, so operators can see which intermediate sites are
single points of failure for that route.

## Files to Create/Modify

- `networkx/algorithms/route_resilience.py` (new) — the new module implementing the public function(s) described below.
- `networkx/algorithms/__init__.py` (modify) — expose the new module's public names so the function is reachable as `nx.<function_name>` (follow the existing `from networkx.algorithms.<module> import *` style already used in this file).
- `networkx/algorithms/tests/test_route_resilience.py` (new) — the deterministic unit tests for the new function(s).

## Requirements

### Public API

Add a function with the following exact signature in the new module and export it
through the package so it is callable as `nx.route_relay_impact`:

```python
def route_relay_impact(G, source, target, weight=None):
    ...
```

- `G` may be either an undirected `Graph` or a directed `DiGraph`.
- `source` and `target` are node identifiers present in `G`.
- `weight` is either `None` (every edge counts as cost 1) or a string naming the
  edge attribute that holds a non-negative numeric cost.

The function returns a `dict` mapping **each candidate relay node** to a single
non-negative `float` "impact" value (defined below). A *candidate relay node* is
any node of `G` other than `source` and `target`.

### Impact definition

For a candidate relay node `r`, the **impact** measures how much the best
`source`→`target` connection degrades when `r` (and all of its incident edges) is
removed from the network:

- Let `d0` be the cost of the best `source`→`target` connection in the full graph.
- Let `dr` be the cost of the best `source`→`target` connection after `r` is
  removed.
- The impact of `r` is `dr - d0`.

The "best connection cost" must respect edge direction for directed graphs and
edge costs when `weight` is provided.

### Edge cases and constraints

- **Unreachable after removal.** If `source` and `target` are connected in the
  full graph but removing `r` leaves no `source`→`target` connection at all, the
  impact of `r` must be reported as `float('inf')`.
- **Critical relays.** A relay whose removal disconnects the pair therefore has
  impact `inf`; a relay that lies on no optimal route and changes nothing has
  impact `0.0`.
- **Disconnected pair in the full graph.** If `source` and `target` are not
  connected in the original graph, raise `networkx.NetworkXNoPath`.
- **Missing endpoints.** If `source` or `target` is not a node of `G`, raise
  `networkx.NodeNotFound`.
- **Self-query.** If `source == target`, raise `networkx.NetworkXError`.
- **Empty result.** If the only nodes are `source` and `target`, return an empty
  dict.
- The original graph `G` must not be mutated by the call.
- Negative edge costs are out of scope; you may assume all provided weights are
  non-negative.

### Expected Functionality

- Line graph `0—1—2—3` (unweighted), query `source=0, target=3`: every internal
  node `1` and `2` is indispensable, so the result is `{1: inf, 2: inf}`.
- Diamond `0—1—3`, `0—2—3` (unweighted), query `source=0, target=3`: removing
  either `1` or `2` still leaves a length-2 route, so both have impact `0.0`,
  giving `{1: 0.0, 2: 0.0}`.
- Diamond with costs — edges `0—1` and `1—3` cost 1 each, edges `0—2` and `2—3`
  cost 5 each, `weight="cost"`, query `0→3`: the best cost is 2 via node `1`;
  removing `1` forces the cost-10 detour, so node `1` has impact `8.0`, while node
  `2` (off the optimal route) has impact `0.0`.
- Directed chain `0→1→2` with a back edge `2→0`, query `source=0, target=2`:
  removing node `1` makes `2` unreachable from `0`, so node `1` has impact `inf`.

## Acceptance Criteria

- A new module `networkx/algorithms/route_resilience.py` defines
  `route_relay_impact` and `nx.route_relay_impact` resolves to it after the import
  wiring is added.
- For every scenario in **Expected Functionality**, the returned dict matches the
  stated values exactly (using `math.isinf` for the infinite entries and exact
  float equality for finite ones).
- Weighted queries honor the named edge-cost attribute; unweighted queries treat
  every edge as cost 1.
- Directed queries respect edge orientation (a directed query must not traverse
  edges against their direction).
- The error conditions (`NetworkXNoPath`, `NodeNotFound`, `NetworkXError`) are
  raised as specified, and `G` is unchanged after any call.
- The following command passes from the repository root:

```
python -m pytest networkx/algorithms/tests/test_route_resilience.py -q
```
