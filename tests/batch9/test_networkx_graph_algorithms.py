"""Tests for skill: networkx-graph-algorithms  (variant ext9).

Task: add a Minimum Disconnecting Edge-Set Reporter to networkx. A new module
``networkx/algorithms/connectivity/min_disconnect.py`` exposes
``nx.minimum_disconnecting_edges(G, source, target)`` which returns a dict with
exactly two keys:

    "size"  -> int : minimum number of edges to remove so ``target`` is no
                     longer reachable from ``source`` (local edge connectivity).
    "edges" -> set : one such minimum-size edge cut, as (u, v) tuples.

Verification strategy: these tests import the networkx build that lives in
REPO_DIR = /workspace/networkx (so the agent's edited tree is exercised, not a
site-packages copy), then dynamically validate:
  * the reported ``size`` matches the true local edge connectivity,
  * ``len(result["edges"]) == result["size"]``,
  * removing exactly the reported edges from a FRESH COPY of G actually
    severs reachability from source to target (checked with nx.has_path /
    descendants, NOT by matching a hard-coded edge set), so orientation of the
    returned tuples is irrelevant,
  * edge cases: already-disconnected -> {"size":0,"edges":set()},
    source==target -> NetworkXError, missing endpoint -> NodeNotFound,
  * input graph immutability,
  * directed orientation is honored.

A naive/stub implementation -- e.g. one that returns a fixed ``{"size": 1, ...}``,
ignores the graph, hard-codes a particular edge set, or fails to actually
disconnect the pair -- must fail these tests. The deliverable native pytest
command is also driven, and an independent in-process driver re-derives the
answers under the repo interpreter so a solution that only edited its own test
file cannot pass.

No substring/keyword matching on source is used; behavior is exercised
end-to-end.
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
# expensive, so import exactly ONCE and cache.
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


def _reachable(nx, G, source, target):
    """True iff target is reachable from source in G (directed-aware)."""
    if source not in G or target not in G:
        return False
    if G.is_directed():
        return target in nx.descendants(G, source) or target == source
    return nx.has_path(G, source, target)


def _normalize_edges(edges):
    """Normalize an edge set into frozensets of frozenset-pairs (orientation-free)."""
    return frozenset(frozenset(e) for e in edges)


class TestNetworkxGraphAlgorithms:
    REPO_DIR = "/workspace/networkx"

    # ---------------------------------------------------------------- L1 ----
    def test_module_file_exists(self):
        """L1: the new min_disconnect module file is present and non-empty."""
        path = os.path.join(
            REPO_DIR, "networkx", "algorithms", "connectivity", "min_disconnect.py"
        )
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 0, "min_disconnect.py is empty"

    def test_test_file_exists(self):
        """L1: the deliverable unit-test file is present and non-empty."""
        path = os.path.join(
            REPO_DIR,
            "networkx",
            "algorithms",
            "connectivity",
            "tests",
            "test_min_disconnect.py",
        )
        assert os.path.isfile(path), f"missing test file: {path}"
        assert os.path.getsize(path) > 0, "test_min_disconnect.py is empty"

    def test_public_name_resolves(self):
        """L1: nx.minimum_disconnecting_edges is wired through and callable."""
        nx = _import_networkx()
        assert hasattr(nx, "minimum_disconnecting_edges"), (
            "nx.minimum_disconnecting_edges not exposed"
        )
        assert callable(nx.minimum_disconnecting_edges)

    # ---------------------------------------------------------------- L2 ----
    def test_result_shape_and_keys(self):
        """L2: result is a dict with exactly {"size","edges"}; types are int/set."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 3), (0, 2), (2, 3)])
        res = nx.minimum_disconnecting_edges(G, 0, 3)
        assert isinstance(res, dict), f"result is not a dict: {type(res)}"
        assert set(res.keys()) == {"size", "edges"}, f"wrong keys: {set(res.keys())}"
        assert isinstance(res["size"], int), f"size not int: {type(res['size'])}"
        assert isinstance(res["edges"], set), f"edges not set: {type(res['edges'])}"

    def test_diamond_two_disjoint_paths(self):
        """L2: diamond 0-1-3 / 0-2-3, 0->3: size==2 and removal disconnects."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 3), (0, 2), (2, 3)])
        res = nx.minimum_disconnecting_edges(G, 0, 3)
        # The true local edge connectivity is 2.
        assert res["size"] == 2, f"expected size 2, got {res['size']!r}"
        assert res["size"] == nx.edge_connectivity(G, 0, 3), "size != edge_connectivity"
        assert len(res["edges"]) == res["size"], "len(edges) != size"
        # Removing the reported edges from a fresh copy must sever 0->3.
        H = G.copy()
        H.remove_edges_from(res["edges"])
        assert not _reachable(nx, H, 0, 3), "0 still reaches 3 after removing edges"
        # And it must still be reachable before removal (sanity on the fixture).
        assert _reachable(nx, G, 0, 3)

    def test_single_bridge_size_one(self):
        """L2: two triangles joined by bridge 2-3, 0->5: size==1, bridge cut works."""
        nx = _import_networkx()
        G = nx.Graph()
        # Triangle A: 0,1,2 ; Triangle B: 3,4,5 ; bridge 2-3.
        G.add_edges_from(
            [(0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (2, 3)]
        )
        res = nx.minimum_disconnecting_edges(G, 0, 5)
        assert res["size"] == 1, f"expected size 1 (bridge), got {res['size']!r}"
        assert len(res["edges"]) == 1, "edges set must have a single edge"
        # The reported single edge must be the bridge (orientation-free compare).
        assert _normalize_edges(res["edges"]) == _normalize_edges(
            {(2, 3)}
        ), f"reported edge is not the bridge: {res['edges']!r}"
        H = G.copy()
        H.remove_edges_from(res["edges"])
        assert not _reachable(nx, H, 0, 5), "0 still reaches 5 after removing bridge"

    def test_removal_actually_disconnects_dense_case(self):
        """L2: a denser graph (size>=3) -- removing reported edges must disconnect.

        Guards against a stub that hard-codes a 1- or 2-edge answer: here the
        true min cut is 3, and an under-sized reported set cannot disconnect.
        """
        nx = _import_networkx()
        G = nx.Graph()
        # Three internally-disjoint 0->4 paths => edge connectivity 3.
        G.add_edges_from([(0, 1), (1, 4)])
        G.add_edges_from([(0, 2), (2, 4)])
        G.add_edges_from([(0, 3), (3, 4)])
        res = nx.minimum_disconnecting_edges(G, 0, 4)
        assert res["size"] == 3, f"expected size 3, got {res['size']!r}"
        assert res["size"] == nx.edge_connectivity(G, 0, 4)
        assert len(res["edges"]) == 3, "must report exactly 3 edges"
        H = G.copy()
        H.remove_edges_from(res["edges"])
        assert not _reachable(nx, H, 0, 4), "0 still reaches 4 after removal"

    def test_directed_chain_size_one(self):
        """L2: directed 0->1->2, source=0 target=2: size==1; removal disconnects."""
        nx = _import_networkx()
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2)])
        res = nx.minimum_disconnecting_edges(G, 0, 2)
        assert res["size"] == 1, f"expected size 1, got {res['size']!r}"
        assert len(res["edges"]) == 1
        H = G.copy()
        H.remove_edges_from(res["edges"])
        assert not _reachable(nx, H, 0, 2), "0 still reaches 2 in directed graph"

    def test_directed_orientation_honored(self):
        """L2: directed min cut respects orientation (asymmetric capacities).

        0->1->2->3 forward chain plus a single back link 3->0. The forward cut
        from 0 to 3 has size 1 (any one forward edge). A naive undirected
        reading would overcount; we assert size==1 and verify directed removal.
        """
        nx = _import_networkx()
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 0)])
        res = nx.minimum_disconnecting_edges(G, 0, 3)
        assert res["size"] == 1, f"expected size 1, got {res['size']!r}"
        assert res["size"] == nx.edge_connectivity(G, 0, 3)
        H = G.copy()
        H.remove_edges_from(res["edges"])
        assert not _reachable(nx, H, 0, 3), "0 still reaches 3 after directed cut"

    def test_already_disconnected_returns_zero(self):
        """L2: target unreachable from source => {"size":0,"edges":set()}."""
        nx = _import_networkx()
        G = nx.Graph()
        # Two separate components.
        G.add_edges_from([(0, 1), (1, 2), (3, 4), (4, 5)])
        res = nx.minimum_disconnecting_edges(G, 0, 5)
        assert res["size"] == 0, f"expected size 0, got {res['size']!r}"
        assert res["edges"] == set(), f"expected empty set, got {res['edges']!r}"

    def test_size_matches_edge_connectivity_random_topology(self):
        """L2: cross-check size against nx.edge_connectivity on a fixed topology.

        Deterministic structure (no randomness): a 3x3 grid graph. The reported
        size must equal the library's own local edge connectivity, and the
        reported cut must truly disconnect the endpoints.
        """
        nx = _import_networkx()
        G = nx.grid_2d_graph(3, 3)
        s, t = (0, 0), (2, 2)
        res = nx.minimum_disconnecting_edges(G, s, t)
        expected = nx.edge_connectivity(G, s, t)
        assert res["size"] == expected, (
            f"size {res['size']} != edge_connectivity {expected}"
        )
        assert len(res["edges"]) == res["size"], "len(edges) != size"
        H = G.copy()
        H.remove_edges_from(res["edges"])
        assert not _reachable(nx, H, s, t), "grid endpoints still connected"

    def test_same_endpoints_raise_networkx_error(self):
        """L2: source == target => NetworkXError."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        with pytest.raises(nx.NetworkXError):
            nx.minimum_disconnecting_edges(G, 1, 1)

    def test_missing_endpoint_raises_node_not_found(self):
        """L2: missing source or target node => NodeNotFound."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        with pytest.raises(nx.NodeNotFound):
            nx.minimum_disconnecting_edges(G, 0, 99)
        with pytest.raises(nx.NodeNotFound):
            nx.minimum_disconnecting_edges(G, 99, 2)

    def test_graph_not_mutated(self):
        """L2: the original graph G is unchanged after the call."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 3), (0, 2), (2, 3)])
        nodes_before = set(G.nodes())
        edges_before = _normalize_edges(G.edges())
        nx.minimum_disconnecting_edges(G, 0, 3)
        assert set(G.nodes()) == nodes_before, "nodes mutated"
        assert _normalize_edges(G.edges()) == edges_before, "edges mutated"

    def test_reported_edges_are_real_graph_edges(self):
        """L2: every reported edge must exist in G (guards fabricated outputs)."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 3), (0, 2), (2, 3)])
        res = nx.minimum_disconnecting_edges(G, 0, 3)
        for u, v in res["edges"]:
            assert G.has_edge(u, v), f"reported edge ({u},{v}) not in graph"

    def test_native_pytest_passes(self):
        """L2: the deliverable native test command passes from the repo root.

        Drives exactly the Acceptance-Criteria command:
            python -m pytest networkx/algorithms/connectivity/tests/test_min_disconnect.py -q
        """
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "networkx/algorithms/connectivity/tests/test_min_disconnect.py",
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
        re-deriving every answer (size + actual reachability after removal), so
        a solution that only patched its own test file cannot pass.
        """
        driver = textwrap.dedent(
            """
            import sys
            import networkx as nx
            assert nx.__file__.startswith(%r), nx.__file__

            def reachable(G, s, t):
                if G.is_directed():
                    return t in nx.descendants(G, s)
                return nx.has_path(G, s, t)

            # diamond: size 2, removal disconnects
            G = nx.Graph()
            G.add_edges_from([(0,1),(1,3),(0,2),(2,3)])
            r = nx.minimum_disconnecting_edges(G, 0, 3)
            assert r["size"] == 2, r
            assert len(r["edges"]) == 2, r
            H = G.copy(); H.remove_edges_from(r["edges"])
            assert not reachable(H, 0, 3), "diamond not disconnected"

            # bridge: size 1, edge is the bridge (2,3)
            B = nx.Graph()
            B.add_edges_from([(0,1),(1,2),(2,0),(3,4),(4,5),(5,3),(2,3)])
            rb = nx.minimum_disconnecting_edges(B, 0, 5)
            assert rb["size"] == 1, rb
            assert frozenset(map(frozenset, rb["edges"])) == frozenset([frozenset((2,3))]), rb

            # directed chain: size 1
            D = nx.DiGraph(); D.add_edges_from([(0,1),(1,2)])
            rd = nx.minimum_disconnecting_edges(D, 0, 2)
            assert rd["size"] == 1, rd
            HD = D.copy(); HD.remove_edges_from(rd["edges"])
            assert not reachable(HD, 0, 2), "directed not disconnected"

            # already disconnected: size 0, empty set
            S = nx.Graph(); S.add_edges_from([(0,1),(3,4)])
            rs = nx.minimum_disconnecting_edges(S, 0, 4)
            assert rs["size"] == 0 and rs["edges"] == set(), rs

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
