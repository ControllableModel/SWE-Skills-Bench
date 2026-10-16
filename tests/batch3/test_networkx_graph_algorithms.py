"""Tests for skill: networkx-graph-algorithms (variant ext3).

Task: add a *Partition Cohesion Reporter* to networkx's community subpackage.
A new module ``networkx/algorithms/community/cohesion.py`` exposes a public
function wired through the package so it resolves as
``nx.community.partition_cohesion(G, communities)``.

Given an undirected graph ``G`` and ``communities`` (an iterable of node-sets
that together *partition* the nodes of ``G``), the function returns a ``list``
of ``dict`` -- one per community, in the order supplied -- each holding:

    "size"           int   number of nodes in the community
    "internal_edges" int   edges with both endpoints inside the community
    "boundary_edges" int   edges with exactly one endpoint inside the community
    "conductance"    float boundary_edges / (2*internal_edges + boundary_edges),
                           with 0/0 defined as 0.0

Verification strategy: these tests reach into REPO_DIR = /workspace/networkx,
import that networkx build directly (so the agent's edited module is the one
exercised), and dynamically validate numeric output, dict shape/key types,
ordering, the conductance formula, the singleton / isolated / whole-graph edge
cases, NetworkXError on non-partition input, and graph immutability. The native
acceptance command (the agent's own committed unit tests) is also driven via
subprocess, and an independent in-process driver re-derives the canonical
scenarios so a solution that only edited its own test file cannot pass.
No substring/keyword matching on source is used.
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
# any site-packages networkx. Importing networkx is expensive for the editable
# dev build, so we import exactly ONCE and cache it; reloading per-test would
# blow the per-test timeout.
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


def _resolve(nx):
    """Resolve the public partition_cohesion function via the documented path."""
    assert hasattr(nx, "community"), "nx.community subpackage missing"
    assert hasattr(nx.community, "partition_cohesion"), (
        "nx.community.partition_cohesion not exposed"
    )
    fn = nx.community.partition_cohesion
    assert callable(fn), "partition_cohesion is not callable"
    return fn


def _two_triangles_bridge(nx):
    """Two triangles {0,1,2} and {3,4,5} joined by a single bridge edge 2-3."""
    G = nx.Graph()
    G.add_edges_from([(0, 1), (1, 2), (0, 2)])  # triangle A
    G.add_edges_from([(3, 4), (4, 5), (3, 5)])  # triangle B
    G.add_edge(2, 3)  # bridge
    return G


class TestNetworkxGraphAlgorithms:
    REPO_DIR = "/workspace/networkx"

    # ---------------------------------------------------------------- L1 ----
    def test_module_file_exists(self):
        """L1: the new cohesion module file is present and non-empty."""
        path = os.path.join(
            REPO_DIR, "networkx", "algorithms", "community", "cohesion.py"
        )
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 0, "cohesion.py is empty"

    def test_test_file_exists(self):
        """L1: the deliverable unit-test file is present and non-empty."""
        path = os.path.join(
            REPO_DIR,
            "networkx",
            "algorithms",
            "community",
            "tests",
            "test_cohesion.py",
        )
        assert os.path.isfile(path), f"missing test file: {path}"
        assert os.path.getsize(path) > 0, "test_cohesion.py is empty"

    def test_public_name_resolves(self):
        """L1: nx.community.partition_cohesion is wired through and callable."""
        nx = _import_networkx()
        fn = _resolve(nx)
        assert fn is not None

    # ---------------------------------------------------------------- L2 ----
    def test_two_triangles_bridge_values(self):
        """L2: two triangles + bridge -> size=3, internal=3, boundary=1, c=1/7."""
        nx = _import_networkx()
        fn = _resolve(nx)
        G = _two_triangles_bridge(nx)
        res = fn(G, [{0, 1, 2}, {3, 4, 5}])
        assert isinstance(res, list), f"expected list, got {type(res)!r}"
        assert len(res) == 2, f"expected 2 reports, got {len(res)}"
        for i, d in enumerate(res):
            assert isinstance(d, dict), f"report {i} not a dict: {d!r}"
            assert set(d.keys()) == {
                "size",
                "internal_edges",
                "boundary_edges",
                "conductance",
            }, f"report {i} keys = {sorted(d.keys())}"
            assert d["size"] == 3 and isinstance(d["size"], int)
            assert d["internal_edges"] == 3 and isinstance(d["internal_edges"], int)
            assert d["boundary_edges"] == 1 and isinstance(d["boundary_edges"], int)
            assert not isinstance(d["conductance"], bool)
            assert isinstance(d["conductance"], float)
            assert math.isclose(d["conductance"], 1.0 / 7.0, abs_tol=1e-9), (
                f"report {i} conductance={d['conductance']!r}, expected 1/7"
            )

    def test_path_partition_values(self):
        """L2: path 0-1-2-3 with [{0,1},{2,3}] -> internal=1, boundary=1, c=1/3."""
        nx = _import_networkx()
        fn = _resolve(nx)
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3])
        res = fn(G, [{0, 1}, {2, 3}])
        assert len(res) == 2, res
        for i, d in enumerate(res):
            assert d["size"] == 2, f"report {i}: {d!r}"
            assert d["internal_edges"] == 1, f"report {i}: {d!r}"
            assert d["boundary_edges"] == 1, f"report {i}: {d!r}"
            assert math.isclose(d["conductance"], 1.0 / 3.0, abs_tol=1e-9), (
                f"report {i} conductance={d['conductance']!r}, expected 1/3"
            )

    def test_order_is_preserved(self):
        """L2: reports come back in the exact order communities were supplied.

        A naive implementation that sorts groups or keys by size would reorder
        the output; the size-3 group is given second here, so the second report
        must be the larger one.
        """
        nx = _import_networkx()
        fn = _resolve(nx)
        G = nx.Graph()
        # triangle {2,3,4} plus a single attached node 1 (edge 1-2 is boundary
        # for both groups).
        G.add_edges_from([(2, 3), (3, 4), (2, 4), (1, 2)])
        res = fn(G, [{1}, {2, 3, 4}])
        assert [d["size"] for d in res] == [1, 3], (
            f"order not preserved: sizes={[d['size'] for d in res]}"
        )
        assert res[0]["internal_edges"] == 0, res[0]
        assert res[1]["internal_edges"] == 3, res[1]

    def test_singleton_with_boundary_conductance_one(self):
        """L2: a one-node community with a boundary edge has conductance 1.0."""
        nx = _import_networkx()
        fn = _resolve(nx)
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2)])  # node 0 singleton, has boundary edge 0-1
        res = fn(G, [{0}, {1, 2}])
        d0 = res[0]
        assert d0["size"] == 1, d0
        assert d0["internal_edges"] == 0, d0
        assert d0["boundary_edges"] == 1, d0
        assert d0["conductance"] == 1.0, d0
        assert isinstance(d0["conductance"], float)

    def test_isolated_community_conductance_zero(self):
        """L2: a community with no internal and no boundary edges => 0/0 == 0.0."""
        nx = _import_networkx()
        fn = _resolve(nx)
        G = nx.Graph()
        G.add_edges_from([(1, 2)])  # edge within {1,2}
        G.add_node(0)  # node 0 fully isolated
        res = fn(G, [{0}, {1, 2}])
        d0 = res[0]
        assert d0["size"] == 1, d0
        assert d0["internal_edges"] == 0, d0
        assert d0["boundary_edges"] == 0, d0
        assert d0["conductance"] == 0.0, d0
        assert isinstance(d0["conductance"], float)

    def test_whole_graph_single_community(self):
        """L2: one community holding every node => boundary=0, conductance=0.0."""
        nx = _import_networkx()
        fn = _resolve(nx)
        G = _two_triangles_bridge(nx)
        res = fn(G, [{0, 1, 2, 3, 4, 5}])
        assert len(res) == 1, res
        d = res[0]
        assert d["size"] == 6, d
        # 6 triangle edges + 1 bridge = 7 internal edges, all inside.
        assert d["internal_edges"] == 7, d
        assert d["boundary_edges"] == 0, d
        assert d["conductance"] == 0.0, d
        assert isinstance(d["conductance"], float)

    def test_conductance_formula_holds_generally(self):
        """L2: independently recompute conductance from the reported integers.

        This pins the *exact* formula boundary/(2*internal+boundary) rather
        than any plausible-looking ratio, across an asymmetric partition.
        """
        nx = _import_networkx()
        fn = _resolve(nx)
        # 4-node clique {0,1,2,3} plus two pendants 4-0 and 5-1, grouped with 6.
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)])
        G.add_edge(0, 4)
        G.add_edge(1, 5)
        G.add_edge(4, 5)
        G.add_node(6)
        res = fn(G, [{0, 1, 2, 3}, {4, 5, 6}])
        for d in res:
            ie, be = d["internal_edges"], d["boundary_edges"]
            denom = 2 * ie + be
            expected = 0.0 if denom == 0 else be / denom
            assert math.isclose(d["conductance"], expected, abs_tol=1e-9), (
                f"conductance {d['conductance']!r} != {expected!r} for {d!r}"
            )
        # Group A: clique has 6 internal edges, 2 boundary edges (0-4, 1-5).
        assert res[0]["internal_edges"] == 6, res[0]
        assert res[0]["boundary_edges"] == 2, res[0]
        # Group B {4,5,6}: internal edge 4-5; boundary edges 0-4, 1-5.
        assert res[1]["internal_edges"] == 1, res[1]
        assert res[1]["boundary_edges"] == 2, res[1]

    def test_accepts_frozenset_and_list_groups(self):
        """L2: communities may be frozensets / lists, not only python sets."""
        nx = _import_networkx()
        fn = _resolve(nx)
        G = _two_triangles_bridge(nx)
        res = fn(G, [frozenset({0, 1, 2}), [3, 4, 5]])
        assert res[0]["internal_edges"] == 3 and res[0]["boundary_edges"] == 1, res[0]
        assert res[1]["internal_edges"] == 3 and res[1]["boundary_edges"] == 1, res[1]

    def test_non_partition_missing_node_raises(self):
        """L2: a node left out of every group => NetworkXError."""
        nx = _import_networkx()
        fn = _resolve(nx)
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3])
        with pytest.raises(nx.NetworkXError):
            fn(G, [{0, 1}, {2}])  # node 3 missing

    def test_non_partition_duplicate_node_raises(self):
        """L2: a node placed in two groups => NetworkXError."""
        nx = _import_networkx()
        fn = _resolve(nx)
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3])
        with pytest.raises(nx.NetworkXError):
            fn(G, [{0, 1, 2}, {2, 3}])  # node 2 duplicated

    def test_non_partition_foreign_node_raises(self):
        """L2: a node not in G appearing in a group => NetworkXError."""
        nx = _import_networkx()
        fn = _resolve(nx)
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3])
        with pytest.raises(nx.NetworkXError):
            fn(G, [{0, 1}, {2, 3, 99}])  # 99 not in G

    def test_graph_not_mutated(self):
        """L2: the original graph G is unchanged after the call."""
        nx = _import_networkx()
        fn = _resolve(nx)
        G = _two_triangles_bridge(nx)
        nodes_before = set(G.nodes())
        edges_before = {tuple(sorted(e)) for e in G.edges()}
        fn(G, [{0, 1, 2}, {3, 4, 5}])
        assert set(G.nodes()) == nodes_before, "nodes mutated"
        assert {tuple(sorted(e)) for e in G.edges()} == edges_before, "edges mutated"

    def test_native_pytest_passes(self):
        """L2: the deliverable test command passes from the repo root.

        Drives the agent's committed unit tests via the native toolchain, as
        named in the Acceptance Criteria:
            python -m pytest networkx/algorithms/community/tests/test_cohesion.py -q
        """
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "networkx/algorithms/community/tests/test_cohesion.py",
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

        Exercises partition_cohesion in a clean process whose cwd is REPO_DIR,
        so a solution that only patched its own test file (without a working
        implementation) cannot pass. Re-derives the canonical scenarios.
        """
        driver = textwrap.dedent(
            """
            import math
            import networkx as nx
            assert nx.__file__.startswith(%r), nx.__file__

            fn = nx.community.partition_cohesion

            # two triangles + bridge
            G = nx.Graph()
            G.add_edges_from([(0,1),(1,2),(0,2),(3,4),(4,5),(3,5),(2,3)])
            r = fn(G, [{0,1,2}, {3,4,5}])
            assert [d["size"] for d in r] == [3, 3], r
            assert [d["internal_edges"] for d in r] == [3, 3], r
            assert [d["boundary_edges"] for d in r] == [1, 1], r
            for d in r:
                assert math.isclose(d["conductance"], 1/7, abs_tol=1e-9), d

            # path partition -> 1/3 each
            P = nx.Graph(); nx.add_path(P, [0,1,2,3])
            rp = fn(P, [{0,1},{2,3}])
            for d in rp:
                assert d["internal_edges"] == 1 and d["boundary_edges"] == 1, d
                assert math.isclose(d["conductance"], 1/3, abs_tol=1e-9), d

            # whole graph -> boundary 0, conductance 0.0
            rw = fn(G, [{0,1,2,3,4,5}])
            assert len(rw) == 1, rw
            assert rw[0]["boundary_edges"] == 0 and rw[0]["conductance"] == 0.0, rw[0]

            # non-partition raises
            try:
                fn(P, [{0,1},{2}])
                raise SystemExit("expected NetworkXError for non-partition")
            except nx.NetworkXError:
                pass

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
