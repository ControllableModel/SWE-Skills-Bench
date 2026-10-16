"""Tests for skill: networkx-graph-algorithms (variant ext7).

Task: add a BFS Distance Histogram module to networkx that exposes
``nx.bfs_distance_histogram(G, source)``. Starting from ``source``, the function
returns a ``dict`` mapping each reachable shortest-hop distance ``d`` (int >= 0)
to the count of nodes whose shortest-hop distance from ``source`` equals ``d``.
Distance is measured in edges, ignoring edge weights; directed graphs traverse
edges only in their orientation.

Deliverables (per the requirement doc):
  - networkx/algorithms/traversal/distance_histogram.py            (new module)
  - networkx/algorithms/traversal/__init__.py                      (wire star-import)
  - networkx/algorithms/traversal/tests/test_distance_histogram.py (unit tests)

Verification strategy: these tests reach into REPO_DIR = /workspace/networkx,
import that networkx build directly (so the agent's edited module is exercised),
and dynamically validate exact histogram dicts, all four worked scenarios from
the doc (path, star, directed chain with skip edge, unreachable component),
the edge cases (source key 0->1, isolated source {0:1}, no zero-count keys),
NodeNotFound on a missing source, and graph immutability. A naive stub that
hardcodes a result, ignores the source, honors weights, or skips direction
must fail. Substring/keyword matching on source is deliberately avoided; the
new behavior is exercised end-to-end, including the native pytest command and
an independent driver run under the repo interpreter.
"""

import importlib
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/networkx"

# Front-load REPO_DIR so the agent's edited tree is imported in preference to
# any site-packages networkx. Importing networkx (editable dev build) is
# expensive, so we import exactly ONCE and cache it.
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

_NX = None


def _import_networkx():
    """Return the networkx package imported from REPO_DIR (cached, import-once)."""
    global _NX
    if _NX is None:
        nx = importlib.import_module("networkx")
        assert os.path.realpath(nx.__file__).startswith(os.path.realpath(REPO_DIR)), (
            f"imported networkx from {nx.__file__}, expected under {REPO_DIR}"
        )
        _NX = nx
    return _NX


class TestNetworkxGraphAlgorithms:
    REPO_DIR = "/workspace/networkx"

    # ---------------------------------------------------------------- L1 ----
    def test_module_file_exists(self):
        """L1: the new distance_histogram module file is present and non-empty."""
        path = os.path.join(
            REPO_DIR,
            "networkx",
            "algorithms",
            "traversal",
            "distance_histogram.py",
        )
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 0, "distance_histogram.py is empty"

    def test_test_file_exists(self):
        """L1: the deliverable unit-test file is present and non-empty."""
        path = os.path.join(
            REPO_DIR,
            "networkx",
            "algorithms",
            "traversal",
            "tests",
            "test_distance_histogram.py",
        )
        assert os.path.isfile(path), f"missing test file: {path}"
        assert os.path.getsize(path) > 0, "test_distance_histogram.py is empty"

    def test_public_name_resolves(self):
        """L1: nx.bfs_distance_histogram is wired through the package and callable."""
        nx = _import_networkx()
        assert hasattr(nx, "bfs_distance_histogram"), (
            "nx.bfs_distance_histogram not exposed"
        )
        assert callable(nx.bfs_distance_histogram)

    # ---------------------------------------------------------------- L2 ----
    def test_path_graph_histogram(self):
        """L2: path 0-1-2-3 from source 0 yields {0:1, 1:1, 2:1, 3:1}."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3])
        res = nx.bfs_distance_histogram(G, 0)
        assert res == {0: 1, 1: 1, 2: 1, 3: 1}, f"unexpected histogram: {res!r}"
        assert isinstance(res, dict)

    def test_star_graph_histogram(self):
        """L2: star with center c and three leaves from c yields {0:1, 1:3}."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([("c", "a"), ("c", "b"), ("c", "d")])
        res = nx.bfs_distance_histogram(G, "c")
        assert res == {0: 1, 1: 3}, f"unexpected histogram: {res!r}"

    def test_source_key_zero_always_one(self):
        """L2: key 0 always maps to 1 (the source itself) regardless of shape."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (0, 3), (3, 4), (4, 5)])
        res = nx.bfs_distance_histogram(G, 0)
        assert res.get(0) == 1, f"key 0 must be 1 (source), got {res!r}"

    def test_isolated_source_returns_single_entry(self):
        """L2: a source with no reachable neighbors yields exactly {0: 1}."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_node("lonely")
        G.add_edge("x", "y")  # unrelated component, not reachable from source
        res = nx.bfs_distance_histogram(G, "lonely")
        assert res == {0: 1}, f"isolated source must give {{0:1}}, got {res!r}"

    def test_unreachable_nodes_excluded(self):
        """L2: nodes in a disconnected component contribute to no key."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])  # reachable: 0,1,2
        G.add_edges_from([(7, 8), (8, 9)])  # separate component, unreachable
        res = nx.bfs_distance_histogram(G, 0)
        assert res == {0: 1, 1: 1, 2: 1}, (
            f"unreachable component must be excluded, got {res!r}"
        )
        # Total counted nodes must equal only the reachable set size (3).
        assert sum(res.values()) == 3, f"counted too many nodes: {res!r}"

    def test_counts_aggregate_multiple_nodes_per_distance(self):
        """L2: several nodes at the same hop distance are summed into one key."""
        nx = _import_networkx()
        # source 0 connects to 1,2,3 (dist 1); each of 1,2 connects to a leaf at
        # dist 2 (=> count 2 at distance 2).
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (0, 3), (1, 10), (2, 20)])
        res = nx.bfs_distance_histogram(G, 0)
        assert res == {0: 1, 1: 3, 2: 2}, f"unexpected histogram: {res!r}"

    def test_no_zero_count_keys(self):
        """L2: only distances with a non-zero count appear as keys."""
        nx = _import_networkx()
        nx_ = nx
        G = nx_.Graph()
        nx_.add_path(G, [0, 1, 2, 3])
        res = nx_.bfs_distance_histogram(G, 0)
        assert all(v > 0 for v in res.values()), f"zero-count key present: {res!r}"
        # keys must be a contiguous-or-sparse set of the actually-present dists,
        # never padded with empty distances beyond the reachable frontier.
        assert max(res.keys()) == 3, f"unexpected max distance: {res!r}"

    def test_directed_skip_edge_shortens_distance(self):
        """L2: directed 0->1->2 plus extra 0->2, source 0 yields {0:1, 1:2}.

        Node 2 is at distance 1 via the direct edge (not 2 via the chain),
        proving the histogram uses the shortest hop count.
        """
        nx = _import_networkx()
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2), (0, 2)])
        res = nx.bfs_distance_histogram(G, 0)
        assert res == {0: 1, 1: 2}, f"unexpected histogram: {res!r}"

    def test_directed_respects_orientation(self):
        """L2: in a directed graph, edges traverse only in their direction.

        Chain 0->1->2->3 from source 0 reaches all forward => {0:1,1:1,2:1,3:1};
        but from source 3 nothing forward is reachable => {0:1}. The asymmetry
        proves orientation is honored (an undirected reading would give a full
        histogram from node 3 too).
        """
        nx = _import_networkx()
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2), (2, 3)])
        forward = nx.bfs_distance_histogram(G, 0)
        backward = nx.bfs_distance_histogram(G, 3)
        assert forward == {0: 1, 1: 1, 2: 1, 3: 1}, f"forward={forward!r}"
        assert backward == {0: 1}, f"backward={backward!r}"

    def test_weights_are_ignored(self):
        """L2: edge weights do not affect hop-distance histogram.

        Heavy weights that would reorder a weighted shortest path must not
        change the result; distance is pure hop count.
        """
        nx = _import_networkx()
        G = nx.Graph()
        # 0-1 is a single heavy hop; 0-2-3-1 is a 3-hop light detour.
        G.add_edge(0, 1, weight=100)
        G.add_edge(0, 2, weight=1)
        G.add_edge(2, 3, weight=1)
        G.add_edge(3, 1, weight=1)
        res = nx.bfs_distance_histogram(G, 0)
        # By hops: dist1 = {1,2}; dist2 = {3}. Node 1 is 1 hop despite heavy edge.
        assert res == {0: 1, 1: 2, 2: 1}, f"weights must be ignored, got {res!r}"

    def test_missing_source_raises_node_not_found(self):
        """L2: a source absent from G raises networkx.NodeNotFound."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        with pytest.raises(nx.NodeNotFound):
            nx.bfs_distance_histogram(G, 99)

    def test_graph_not_mutated(self):
        """L2: the original graph G is unchanged after the call."""
        nx = _import_networkx()
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2), (0, 2)])
        G.add_node("solo")
        nodes_before = set(G.nodes())
        edges_before = set(G.edges())
        nx.bfs_distance_histogram(G, 0)
        assert set(G.nodes()) == nodes_before, "nodes mutated"
        assert set(G.edges()) == edges_before, "edges mutated"

    def test_native_pytest_passes(self):
        """L2: the deliverable test command passes from the repo root.

        Runs the agent's own committed unit tests via the native toolchain, as
        specified in the Acceptance Criteria:
            python -m pytest \
              networkx/algorithms/traversal/tests/test_distance_histogram.py -q
        """
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "networkx/algorithms/traversal/tests/test_distance_histogram.py",
                "-q",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "native pytest failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    def test_independent_driver_against_native_python(self):
        """L2: run a fresh driver under the repo interpreter (no test reuse).

        Exercises the public function in a clean process whose cwd is REPO_DIR,
        so a solution that only patched its own test file (without a working
        implementation) cannot pass. Covers all four worked doc scenarios.
        """
        driver = textwrap.dedent(
            """
            import networkx as nx
            assert nx.__file__.startswith(%r), nx.__file__

            # path 0-1-2-3
            P = nx.Graph(); nx.add_path(P, [0, 1, 2, 3])
            assert nx.bfs_distance_histogram(P, 0) == {0: 1, 1: 1, 2: 1, 3: 1}

            # star, center c, three leaves
            S = nx.Graph(); S.add_edges_from([("c","a"),("c","b"),("c","d")])
            assert nx.bfs_distance_histogram(S, "c") == {0: 1, 1: 3}

            # directed chain 0->1->2 with skip 0->2
            D = nx.DiGraph(); D.add_edges_from([(0,1),(1,2),(0,2)])
            assert nx.bfs_distance_histogram(D, 0) == {0: 1, 1: 2}

            # isolated component unreachable from source
            U = nx.Graph(); nx.add_path(U, [0, 1, 2]); U.add_edges_from([(7,8),(8,9)])
            assert nx.bfs_distance_histogram(U, 0) == {0: 1, 1: 1, 2: 1}

            print("DRIVER_OK")
            """
            % (os.path.realpath(REPO_DIR),)
        )
        proc = subprocess.run(
            [sys.executable, "-c", driver],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, (
            "driver failed:\nSTDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr
        )
        assert "DRIVER_OK" in proc.stdout, proc.stdout
