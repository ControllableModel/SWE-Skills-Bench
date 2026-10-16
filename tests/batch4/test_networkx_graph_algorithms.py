"""Tests for skill: networkx-graph-algorithms (variant ext4).

Task: add a deterministic *ring-of-cliques* generator to networkx, living in a
NEW module ``networkx/generators/ring_of_cliques.py`` and wired through the
generators package so it resolves as ``nx.ring_of_cliques(num_cliques,
clique_size)``.

Construction contract under test (re-derived from the ext4 requirement doc):
  * ``num_cliques`` complete graphs each on ``clique_size`` nodes;
  * nodes are integers ``0 .. num_cliques*clique_size - 1`` assigned
    consecutively, clique ``i`` owning ``i*clique_size .. i*clique_size+clique_size-1``;
  * for each ``i`` exactly ONE bridge edge joins the LAST node of clique ``i``
    to the FIRST node of clique ``(i+1) mod num_cliques`` (closed ring);
  * total edges == ``num_cliques*C(clique_size,2) + num_cliques`` bridges;
  * graph carries ``G.graph["ring_of_cliques"] == (num_cliques, clique_size)``;
  * ``num_cliques < 2`` or ``clique_size < 2`` raises ``nx.NetworkXError``;
  * fully deterministic (identical edge/node sets across repeated calls).

NOTE: upstream networkx already ships a *different* ``ring_of_cliques`` (in
``generators/community.py``) that bridges via the SECOND node of each clique and
sets NO graph attribute. This ext4 task asks for a distinct contract (LAST->FIRST
bridge + the ``ring_of_cliques`` graph attribute) in a NEW module. The tests
below therefore assert the exact bridge topology and the graph attribute, so an
agent that merely re-exports the legacy community implementation FAILS.

Verification strategy: import the networkx build from REPO_DIR (so the agent's
edited tree is exercised), then dynamically assert node/edge sets, bridge
endpoints, edge counts, connectivity, determinism, error handling, and graph
immutability. We also run the agent's committed deliverable unit-test file and
an independent fresh-process driver via the native pytest toolchain. No
substring/keyword matching on source.
"""

import importlib
import math
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/networkx"

# Front-load REPO_DIR so the agent's edited tree is imported in preference to any
# site-packages networkx. Importing networkx is expensive, so import ONCE and
# cache it; reloading per-test would blow the per-test timeout.
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


def _undirected_edge_set(G):
    """Return the edge set as frozensets of endpoints (order-independent)."""
    return {frozenset(e) for e in G.edges()}


class TestNetworkxGraphAlgorithms:
    REPO_DIR = "/workspace/networkx"

    # ---------------------------------------------------------------- L1 ----
    def test_module_file_exists(self):
        """L1: the new ring_of_cliques generator module file is present."""
        path = os.path.join(
            REPO_DIR, "networkx", "generators", "ring_of_cliques.py"
        )
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 0, "ring_of_cliques.py is empty"

    def test_deliverable_test_file_exists(self):
        """L1: the deliverable unit-test file is present and non-empty."""
        path = os.path.join(
            REPO_DIR,
            "networkx",
            "generators",
            "tests",
            "test_ring_of_cliques.py",
        )
        assert os.path.isfile(path), f"missing test file: {path}"
        assert os.path.getsize(path) > 0, "test_ring_of_cliques.py is empty"

    def test_public_name_resolves(self):
        """L1: nx.ring_of_cliques is wired through the package and callable."""
        nx = _import_networkx()
        assert hasattr(nx, "ring_of_cliques"), "nx.ring_of_cliques not exposed"
        assert callable(nx.ring_of_cliques)

    # ---------------------------------------------------------------- L2 ----
    def test_basic_counts_3_3(self):
        """L2: ring_of_cliques(3, 3) -> 9 nodes, 12 edges, connected, undirected."""
        nx = _import_networkx()
        G = nx.ring_of_cliques(3, 3)
        assert not G.is_directed(), "result must be an undirected Graph"
        assert G.number_of_nodes() == 9, f"nodes={G.number_of_nodes()}"
        # 3 * C(3,2)=3*3=9 intra-clique + 3 bridges == 12
        assert G.number_of_edges() == 12, f"edges={G.number_of_edges()}"
        assert set(G.nodes()) == set(range(9)), f"node labels={sorted(G.nodes())}"
        assert nx.is_connected(G), "ring of cliques must be connected"

    def test_counts_4_2_is_8_cycle(self):
        """L2: ring_of_cliques(4, 2) is an 8-node single cycle (8 nodes, 8 edges)."""
        nx = _import_networkx()
        G = nx.ring_of_cliques(4, 2)
        assert G.number_of_nodes() == 8, f"nodes={G.number_of_nodes()}"
        # 4 * C(2,2)=4*1=4 intra + 4 bridges == 8
        assert G.number_of_edges() == 8, f"edges={G.number_of_edges()}"
        assert nx.is_connected(G)
        # A single cycle: every node has degree exactly 2.
        degs = {d for _, d in G.degree()}
        assert degs == {2}, f"expected all degree 2 (a cycle), got {dict(G.degree())}"

    def test_counts_2_4_double_bridge(self):
        """L2: ring_of_cliques(2, 4) -> 8 nodes, 14 edges (ring wraps => 2 bridges)."""
        nx = _import_networkx()
        G = nx.ring_of_cliques(2, 4)
        assert G.number_of_nodes() == 8, f"nodes={G.number_of_nodes()}"
        # 2 * C(4,2)=2*6=12 intra + 2 bridges == 14
        assert G.number_of_edges() == 14, f"edges={G.number_of_edges()}"
        assert nx.is_connected(G)

    def test_intra_clique_completeness(self):
        """L2: each clique block is a complete subgraph on its consecutive nodes."""
        nx = _import_networkx()
        num_cliques, clique_size = 3, 4
        G = nx.ring_of_cliques(num_cliques, clique_size)
        edges = _undirected_edge_set(G)
        for i in range(num_cliques):
            block = range(i * clique_size, i * clique_size + clique_size)
            for a in block:
                for b in block:
                    if a < b:
                        assert frozenset((a, b)) in edges, (
                            f"missing intra-clique edge {(a, b)} in clique {i}"
                        )

    def test_bridges_connect_last_to_first_of_next(self):
        """L2: bridges join LAST node of clique i to FIRST node of (i+1)%n.

        This is the discriminating topology: the upstream community generator
        bridges via the *second* node of each clique, so an agent re-exporting
        that would have the wrong bridge endpoints here and FAIL.
        """
        nx = _import_networkx()
        num_cliques, clique_size = 4, 3
        G = nx.ring_of_cliques(num_cliques, clique_size)
        edges = _undirected_edge_set(G)
        for i in range(num_cliques):
            last = i * clique_size + clique_size - 1
            first_next = ((i + 1) % num_cliques) * clique_size
            assert frozenset((last, first_next)) in edges, (
                f"missing bridge from last node {last} of clique {i} to "
                f"first node {first_next} of clique {(i + 1) % num_cliques}"
            )

    def test_exactly_n_bridges_no_extra_inter_clique_edges(self):
        """L2: there are exactly num_cliques inter-clique (bridge) edges."""
        nx = _import_networkx()
        num_cliques, clique_size = 5, 3
        G = nx.ring_of_cliques(num_cliques, clique_size)

        def clique_of(node):
            return node // clique_size

        bridge_edges = [
            (u, v) for u, v in G.edges() if clique_of(u) != clique_of(v)
        ]
        assert len(bridge_edges) == num_cliques, (
            f"expected {num_cliques} bridges, got {len(bridge_edges)}: {bridge_edges}"
        )

    def test_graph_attribute_recorded(self):
        """L2: G.graph['ring_of_cliques'] stores the (num_cliques, clique_size) tuple."""
        nx = _import_networkx()
        G = nx.ring_of_cliques(3, 3)
        assert "ring_of_cliques" in G.graph, (
            "graph-level attribute 'ring_of_cliques' missing"
        )
        assert tuple(G.graph["ring_of_cliques"]) == (3, 3), (
            f"attribute={G.graph['ring_of_cliques']!r}, expected (3, 3)"
        )
        G2 = nx.ring_of_cliques(4, 2)
        assert tuple(G2.graph["ring_of_cliques"]) == (4, 2), (
            f"attribute={G2.graph['ring_of_cliques']!r}, expected (4, 2)"
        )

    def test_determinism_repeated_calls(self):
        """L2: two calls with identical args yield identical node and edge sets."""
        nx = _import_networkx()
        G1 = nx.ring_of_cliques(4, 3)
        G2 = nx.ring_of_cliques(4, 3)
        assert set(G1.nodes()) == set(G2.nodes()), "node sets differ across calls"
        assert _undirected_edge_set(G1) == _undirected_edge_set(G2), (
            "edge sets differ across calls (non-deterministic construction)"
        )

    def test_invalid_num_cliques_raises(self):
        """L2: num_cliques < 2 raises NetworkXError."""
        nx = _import_networkx()
        for bad in (1, 0, -3):
            with pytest.raises(nx.NetworkXError):
                nx.ring_of_cliques(bad, 3)

    def test_invalid_clique_size_raises(self):
        """L2: clique_size < 2 raises NetworkXError."""
        nx = _import_networkx()
        for bad in (1, 0, -2):
            with pytest.raises(nx.NetworkXError):
                nx.ring_of_cliques(3, bad)

    def test_no_self_loops_and_simple(self):
        """L2: the generator produces a simple graph (no self-loops)."""
        nx = _import_networkx()
        G = nx.ring_of_cliques(4, 4)
        self_loops = list(nx.selfloop_edges(G))
        assert self_loops == [], f"unexpected self-loops: {self_loops}"

    def test_native_pytest_passes(self):
        """L2: the deliverable test command passes from the repo root.

        Runs the agent's committed unit tests via the native toolchain exactly as
        specified in the ext4 Acceptance Criteria.
        """
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "networkx/generators/tests/test_ring_of_cliques.py",
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

        Exercises nx.ring_of_cliques in a clean process whose cwd is REPO_DIR, so
        a solution that only patched its own test file (without a working
        implementation matching the ext4 contract) cannot pass. Asserts the exact
        bridge topology, edge counts, the graph attribute, connectivity, and the
        error contract.
        """
        driver = textwrap.dedent(
            """
            import sys
            import networkx as nx
            assert nx.__file__.startswith(%r), nx.__file__

            G = nx.ring_of_cliques(3, 3)
            assert G.number_of_nodes() == 9, G.number_of_nodes()
            assert G.number_of_edges() == 12, G.number_of_edges()
            assert nx.is_connected(G)
            assert tuple(G.graph["ring_of_cliques"]) == (3, 3), G.graph

            # exact bridge endpoints: last of clique i -> first of (i+1)%n
            n, k = 4, 3
            H = nx.ring_of_cliques(n, k)
            E = {frozenset(e) for e in H.edges()}
            for i in range(n):
                last = i * k + k - 1
                first_next = ((i + 1) %% n) * k
                assert frozenset((last, first_next)) in E, (i, last, first_next)

            # 4x2 is an 8-cycle (all degree 2)
            C = nx.ring_of_cliques(4, 2)
            assert C.number_of_edges() == 8, C.number_of_edges()
            assert {d for _, d in C.degree()} == {2}, dict(C.degree())

            # 2x4 wraps with two bridges => 14 edges
            W = nx.ring_of_cliques(2, 4)
            assert W.number_of_edges() == 14, W.number_of_edges()

            # error contract
            for bad in ((1, 3), (3, 1)):
                try:
                    nx.ring_of_cliques(*bad)
                except nx.NetworkXError:
                    pass
                else:
                    raise AssertionError("expected NetworkXError for %%r" %% (bad,))

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
