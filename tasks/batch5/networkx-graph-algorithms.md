# Task: Add a Weighted Adjacency-CSV Reader and Writer

## Background

The `networkx` library exposes file-format readers and writers under
`networkx/readwrite/`. This task adds a new module providing a compact CSV
serialization for weighted graphs and its inverse, so graphs can round-trip
through a plain comma-separated edge table.

## Files to Create/Modify

- `networkx/readwrite/weighted_csv.py` (new) — the module implementing the two functions below.
- `networkx/readwrite/__init__.py` (modify) — add `from networkx.readwrite.weighted_csv import *` so the functions resolve as `nx.write_weighted_csv` and `nx.read_weighted_csv`.
- `networkx/readwrite/tests/test_weighted_csv.py` (new) — the deterministic unit tests.

## Requirements

### Public API

```python
def write_weighted_csv(G, path, weight="weight", default=1.0):
    ...

def read_weighted_csv(path, weight="weight", create_using=None):
    ...
```

### Writer contract

- `path` is a filesystem path (string or `os.PathLike`).
- The first line is the exact header `source,target,weight`.
- Each subsequent line encodes one edge as `u,v,w` where `w` is the value of the
  named `weight` edge attribute, or `default` when that attribute is absent.
- Edges are written in the order produced by iterating `G.edges()`.
- Node labels are written via `str(node)`; the test inputs use only string and
  integer labels that contain no commas or newlines.

### Reader contract

- `read_weighted_csv` parses a file in the format above and returns a graph.
- `create_using` follows NetworkX convention: `None` produces an undirected
  `Graph`; a graph class or instance selects the type (e.g. `nx.DiGraph`).
- Node labels are read back as **strings** (no type inference).
- The third column is parsed as `float` and stored under the `weight` attribute name.

### Edge cases and constraints

- **Round-trip on labels.** Because the writer uses `str(node)`, reading back a
  graph that was written from integer labels yields the **string** forms (e.g.
  node `1` becomes `"1"`); tests must reflect this.
- **Missing weights on write.** Edges lacking the attribute are written with
  `default`.
- **Malformed line.** A non-header data line that does not have exactly three
  comma-separated fields must raise `networkx.NetworkXError`.
- **Empty graph.** Writing a graph with no edges produces a file containing only
  the header line; reading it back yields a graph with no edges.

### Expected Functionality

- Write `Graph` with edges `("a","b",weight=2.5)` and `("b","c")` (no weight,
  `default=1.0`); the file body is `a,b,2.5` then `b,c,1.0`. Reading it back with
  `read_weighted_csv` reproduces both edges with float weights `2.5` and `1.0`.
- Writing a `DiGraph` and reading back with `create_using=nx.DiGraph` preserves
  edge direction.

## Acceptance Criteria

- `nx.write_weighted_csv` and `nx.read_weighted_csv` resolve after the wiring.
- A write-then-read round trip reproduces the edge set (with stringified labels)
  and float weights for all scenarios above.
- The header line is exactly `source,target,weight`; a malformed data line raises
  `networkx.NetworkXError`; the empty-graph case behaves as specified.
- Tests must use `tmp_path` for file paths (no network, no fixed absolute paths).
- The following command passes from the repository root:

```
python -m pytest networkx/readwrite/tests/test_weighted_csv.py -q
```
