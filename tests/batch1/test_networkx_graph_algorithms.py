"""Tests for skill: networkx-graph-algorithms.

Task: add a Route-Resilience Analyzer module to networkx that exposes
``nx.route_relay_impact(G, source, target, weight=None)``. The function reports,
for each candidate relay node (every node other than ``source``/``target``), how
much the best source->target connection cost degrades when that relay (and its
incident edges) is removed: ``impact = dr - d0``.

These tests reach into REPO_DIR = /workspace/networkx, import that networkx
build directly (so the agent's edited module is exercised), and dynamically
validate the function's numeric output, edge cases, error handling, graph
immutability, and directed/weighted behavior. Each scenario in the requirement
doc maps to a concrete assertion. Substring/keyword matching on source is
deliberately avoided; the new behavior is exercised end-to-end.
"""

import importlib
import math
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/networkx"

# Front-load REPO_DIR so the agent's edited tree is imported in preference to
# any site-packages networkx. PYTHONPATH is cleared at runtime and cwd is
# /tmp/benchmark_tests, so this insert (done once, at module import) is what
# pins the package we test against. Importing networkx is expensive (~40s for
# the editable dev build), so we import exactly ONCE and cache it; reloading
# per-test would blow the per-test timeout.
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
        """L1: the new route_resilience module file is present."""
        path = os.path.join(REPO_DIR, "networkx", "algorithms", "route_resilience.py")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 0, "route_resilience.py is empty"

    def test_test_file_exists(self):
        """L1: the deliverable unit-test file is present."""
        path = os.path.join(
            REPO_DIR, "networkx", "algorithms", "tests", "test_route_resilience.py"
        )
        assert os.path.isfile(path), f"missing test file: {path}"
        assert os.path.getsize(path) > 0, "test_route_resilience.py is empty"

    def test_public_name_resolves(self):
        """L1: nx.route_relay_impact is wired through the package and callable."""
        nx = _import_networkx()
        assert hasattr(nx, "route_relay_impact"), "nx.route_relay_impact not exposed"
        assert callable(nx.route_relay_impact)

    # ---------------------------------------------------------------- L2 ----
    def test_line_graph_internal_nodes_are_critical(self):
        """L2: path 0-1-2-3 unweighted, 0->3 yields {1: inf, 2: inf}."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3])
        res = nx.route_relay_impact(G, 0, 3)
        assert set(res.keys()) == {1, 2}, f"unexpected relay set: {res}"
        assert math.isinf(res[1]) and res[1] > 0, f"node 1 impact={res[1]!r}"
        assert math.isinf(res[2]) and res[2] > 0, f"node 2 impact={res[2]!r}"

    def test_diamond_unweighted_redundant_relays(self):
        """L2: diamond 0-1-3 / 0-2-3 unweighted, 0->3 yields {1: 0.0, 2: 0.0}."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 3), (0, 2), (2, 3)])
        res = nx.route_relay_impact(G, 0, 3)
        assert set(res.keys()) == {1, 2}, f"unexpected relay set: {res}"
        assert res[1] == 0.0 and isinstance(res[1], float), f"node 1 impact={res[1]!r}"
        assert res[2] == 0.0 and isinstance(res[2], float), f"node 2 impact={res[2]!r}"

    def test_diamond_weighted_impact_values(self):
        """L2: weighted diamond — node on optimal route has impact 8.0, other 0.0."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edge(0, 1, cost=1)
        G.add_edge(1, 3, cost=1)
        G.add_edge(0, 2, cost=5)
        G.add_edge(2, 3, cost=5)
        res = nx.route_relay_impact(G, 0, 3, weight="cost")
        assert set(res.keys()) == {1, 2}, f"unexpected relay set: {res}"
        # best cost = 2 via node 1; removing 1 forces cost-10 detour => 10-2=8
        assert res[1] == 8.0, f"expected node 1 impact 8.0, got {res[1]!r}"
        # node 2 lies off the optimal route => 0 change
        assert res[2] == 0.0, f"expected node 2 impact 0.0, got {res[2]!r}"

    def test_directed_respects_orientation(self):
        """L2: directed chain 0->1->2 with back edge 2->0, 0->2: node 1 is inf."""
        nx = _import_networkx()
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2), (2, 0)])
        res = nx.route_relay_impact(G, 0, 2)
        assert set(res.keys()) == {1}, f"unexpected relay set: {res}"
        assert math.isinf(res[1]), f"node 1 impact={res[1]!r} (expected inf)"

    def test_directed_does_not_traverse_against_edges(self):
        """L2: a directed query must not use reverse edges to find a route.

        0->1->2->3 plus reverse-only 0->2 link is absent; only path is forward.
        Removing 1 (between source 0 and the rest) leaves no forward route to 3,
        proving direction is honored (an undirected reading would find 0-3 only
        through 1/2 anyway, so we assert the directed inf result explicitly).
        """
        nx = _import_networkx()
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2), (2, 3)])
        res = nx.route_relay_impact(G, 0, 3)
        assert set(res.keys()) == {1, 2}, f"relay set {res}"
        assert math.isinf(res[1]), f"node 1 should be inf, got {res[1]!r}"
        assert math.isinf(res[2]), f"node 2 should be inf, got {res[2]!r}"

    def test_off_route_relay_is_zero(self):
        """L2: a relay on no optimal route and changing nothing has impact 0.0."""
        nx = _import_networkx()
        # 0-1-2 main route plus a pendant node 9 attached to 1 only.
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        G.add_edge(1, 9)
        res = nx.route_relay_impact(G, 0, 2)
        # candidates: 1 and 9. Node 1 critical (inf), node 9 irrelevant (0.0).
        assert set(res.keys()) == {1, 9}, f"relay set {res}"
        assert math.isinf(res[1]), f"node 1 impact={res[1]!r}"
        assert res[9] == 0.0, f"node 9 impact={res[9]!r}"

    def test_empty_result_when_only_endpoints(self):
        """L2: with only source and target as nodes, return an empty dict."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edge(0, 3)
        res = nx.route_relay_impact(G, 0, 3)
        assert res == {}, f"expected empty dict, got {res!r}"
        assert isinstance(res, dict)

    def test_unreachable_after_removal_is_inf(self):
        """L2: connected pair becomes unreachable after removing r => impact inf."""
        nx = _import_networkx()
        # bridge node 5 is the sole connector between {0} and {3}
        G = nx.Graph()
        G.add_edges_from([(0, 5), (5, 3), (0, 6), (6, 5)])
        # 6 provides an alternate 0->5 hop but 5 is still a cut vertex for 0->3
        res = nx.route_relay_impact(G, 0, 3)
        assert math.isinf(res[5]), f"node 5 (cut vertex) impact={res[5]!r}"
        # node 6 is redundant for reaching 3 (0-5-3 still exists) => 0.0
        assert res[6] == 0.0, f"node 6 impact={res[6]!r}"

    def test_disconnected_pair_raises_no_path(self):
        """L2: source and target disconnected in full graph => NetworkXNoPath."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (2, 3)])
        with pytest.raises(nx.NetworkXNoPath):
            nx.route_relay_impact(G, 0, 3)

    def test_missing_endpoint_raises_node_not_found(self):
        """L2: missing source or target => NodeNotFound."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        with pytest.raises(nx.NodeNotFound):
            nx.route_relay_impact(G, 0, 99)
        with pytest.raises(nx.NodeNotFound):
            nx.route_relay_impact(G, 99, 2)

    def test_self_query_raises_networkx_error(self):
        """L2: source == target => NetworkXError."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        with pytest.raises(nx.NetworkXError):
            nx.route_relay_impact(G, 1, 1)

    def test_graph_not_mutated(self):
        """L2: the original graph G is unchanged after the call."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edge(0, 1, cost=1)
        G.add_edge(1, 3, cost=1)
        G.add_edge(0, 2, cost=5)
        G.add_edge(2, 3, cost=5)
        nodes_before = set(G.nodes())
        edges_before = set(tuple(sorted(e)) for e in G.edges())
        attrs_before = {e: G.edges[e]["cost"] for e in G.edges()}
        nx.route_relay_impact(G, 0, 3, weight="cost")
        assert set(G.nodes()) == nodes_before, "nodes mutated"
        assert set(tuple(sorted(e)) for e in G.edges()) == edges_before, "edges mutated"
        attrs_after = {e: G.edges[e]["cost"] for e in G.edges()}
        assert attrs_after == attrs_before, "edge attributes mutated"

    def test_weight_none_treats_edges_as_unit_cost(self):
        """L2: weight=None ignores numeric edge attrs and uses hop count."""
        nx = _import_networkx()
        # Heavy 'cost' attributes that, if honored, would change the answer.
        G = nx.Graph()
        G.add_edge(0, 1, cost=100)
        G.add_edge(1, 3, cost=100)  # 2-hop route via 1
        G.add_edge(0, 2, cost=1)
        G.add_edge(2, 4, cost=1)
        G.add_edge(4, 3, cost=1)  # 3-hop route via 2,4
        res = nx.route_relay_impact(G, 0, 3)  # unweighted
        # Unweighted best d0 = 2 (via 1). Removing 1 forces 3-hop => impact 1.0.
        assert res[1] == 1.0, f"node 1 impact={res[1]!r} (expected 1.0 unweighted)"
        # Removing 2 or 4 leaves the 2-hop route => 0.0
        assert res[2] == 0.0, f"node 2 impact={res[2]!r}"
        assert res[4] == 0.0, f"node 4 impact={res[4]!r}"

    def test_native_pytest_passes(self):
        """L2: the deliverable test command passes from the repo root.

        Runs the agent's own committed unit tests via the native toolchain, as
        specified in the Acceptance Criteria.
        """
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "networkx/algorithms/tests/test_route_resilience.py",
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
        """L2: run a fresh driver under the repo's interpreter (no test reuse).

        This exercises the public function in a clean process whose cwd is
        REPO_DIR, so a solution that only patched its own test file (without a
        working implementation) cannot pass.
        """
        driver = textwrap.dedent(
            """
            import math, sys
            import networkx as nx
            assert nx.__file__.startswith(%r), nx.__file__

            # weighted diamond
            G = nx.Graph()
            G.add_edge(0, 1, cost=1); G.add_edge(1, 3, cost=1)
            G.add_edge(0, 2, cost=5); G.add_edge(2, 3, cost=5)
            r = nx.route_relay_impact(G, 0, 3, weight="cost")
            assert r == {1: 8.0, 2: 0.0}, r

            # directed inf
            D = nx.DiGraph(); D.add_edges_from([(0,1),(1,2),(2,0)])
            rd = nx.route_relay_impact(D, 0, 2)
            assert set(rd) == {1} and math.isinf(rd[1]), rd

            # line graph
            L = nx.Graph(); nx.add_path(L, [0,1,2,3])
            rl = nx.route_relay_impact(L, 0, 3)
            assert math.isinf(rl[1]) and math.isinf(rl[2]), rl

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
