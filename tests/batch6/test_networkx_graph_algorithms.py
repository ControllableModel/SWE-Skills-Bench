"""Tests for skill: networkx-graph-algorithms  (variant batch: ext6).

Task: add a Neighborhood Triangle Profile module to networkx that exposes
``nx.triangle_profile(G, nodes=None)``. For each requested node the function
returns a dict with exactly the keys ``triangles`` (int), ``degree`` (int) and
``clustering`` (float, the local clustering coefficient
``2 * triangles / (degree * (degree - 1))`` for degree >= 2, else ``0.0``).

Deliverables (per the requirement doc):
  - networkx/algorithms/triangle_profile.py            (new module)
  - networkx/algorithms/__init__.py                    (wires nx.triangle_profile)
  - networkx/algorithms/tests/test_triangle_profile.py (new unit tests)

Verification strategy
---------------------
These tests reach into REPO_DIR = /workspace/networkx, import that networkx
build directly (so the agent's edited module is exercised), and dynamically
validate the numeric output, the exact dict shape/keys, edge cases (degree 0/1,
single-node query), error handling (NodeNotFound for unknown nodes,
NetworkXNotImplemented for directed input), and graph immutability. The doc's
worked scenarios (triangle, path, bowtie) map to concrete numeric assertions.

A naive/stub implementation must fail: returning a fixed value, ignoring the
``nodes`` argument, hardcoding ``clustering`` without the degree formula, or
forgetting the directed/unknown-node guards each break specific cases below.
Substring/keyword matching on source is deliberately avoided; the new behavior
is exercised end-to-end, and an independent driver runs in a clean process so a
solution that only edits its own test file cannot pass. The native acceptance
command ``python -m pytest networkx/algorithms/tests/test_triangle_profile.py
-q`` is also driven directly.
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
# risk the per-test timeout.
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


def _check_entry(entry, *, triangles, degree, clustering):
    """Assert one per-node result dict has exactly the right keys/types/values."""
    assert isinstance(entry, dict), f"per-node value is not a dict: {entry!r}"
    assert set(entry.keys()) == {"triangles", "degree", "clustering"}, (
        f"unexpected keys: {sorted(entry.keys())}"
    )
    assert isinstance(entry["triangles"], int) and not isinstance(
        entry["triangles"], bool
    ), f"triangles must be int, got {type(entry['triangles'])}"
    assert isinstance(entry["degree"], int) and not isinstance(
        entry["degree"], bool
    ), f"degree must be int, got {type(entry['degree'])}"
    assert isinstance(entry["clustering"], float), (
        f"clustering must be float, got {type(entry['clustering'])}"
    )
    assert entry["triangles"] == triangles, (
        f"triangles {entry['triangles']!r} != {triangles!r}"
    )
    assert entry["degree"] == degree, f"degree {entry['degree']!r} != {degree!r}"
    assert math.isclose(entry["clustering"], clustering, abs_tol=1e-9), (
        f"clustering {entry['clustering']!r} != {clustering!r}"
    )


class TestNetworkxGraphAlgorithms:
    REPO_DIR = "/workspace/networkx"

    # ---------------------------------------------------------------- L1 ----
    def test_module_file_exists(self):
        """L1: the new triangle_profile module file is present and non-empty."""
        path = os.path.join(REPO_DIR, "networkx", "algorithms", "triangle_profile.py")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 0, "triangle_profile.py is empty"

    def test_test_file_exists(self):
        """L1: the deliverable unit-test file is present and non-empty."""
        path = os.path.join(
            REPO_DIR, "networkx", "algorithms", "tests", "test_triangle_profile.py"
        )
        assert os.path.isfile(path), f"missing test file: {path}"
        assert os.path.getsize(path) > 0, "test_triangle_profile.py is empty"

    def test_public_name_resolves(self):
        """L1: nx.triangle_profile is wired through the package and callable."""
        nx = _import_networkx()
        assert hasattr(nx, "triangle_profile"), "nx.triangle_profile not exposed"
        assert callable(nx.triangle_profile)

    # ---------------------------------------------------------------- L2 ----
    def test_triangle_all_nodes(self):
        """L2: triangle 0-1-2 => every node triangles=1, degree=2, clustering=1.0."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (0, 2)])
        res = nx.triangle_profile(G)
        assert set(res.keys()) == {0, 1, 2}, f"unexpected node set: {sorted(res)}"
        for n in (0, 1, 2):
            _check_entry(res[n], triangles=1, degree=2, clustering=1.0)

    def test_path_internal_and_endpoints(self):
        """L2: path 0-1-2 => node 1 deg2/tri0/clust0; endpoints deg1/clust0."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        res = nx.triangle_profile(G)
        _check_entry(res[1], triangles=0, degree=2, clustering=0.0)
        _check_entry(res[0], triangles=0, degree=1, clustering=0.0)
        _check_entry(res[2], triangles=0, degree=1, clustering=0.0)

    def test_bowtie_shared_node_one_third(self):
        """L2: bowtie shares node 2 => node2 tri=2 deg=4 clust=1/3; leaves clust=1.0.

        A naive implementation that hardcodes clustering=1.0 (or that drops the
        degree*(degree-1) denominator) fails on the shared node here.
        """
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (0, 2)])  # triangle {0,1,2}
        G.add_edges_from([(2, 3), (3, 4), (2, 4)])  # triangle {2,3,4}
        res = nx.triangle_profile(G)
        _check_entry(res[2], triangles=2, degree=4, clustering=1.0 / 3.0)
        for n in (0, 1, 3, 4):
            _check_entry(res[n], triangles=1, degree=2, clustering=1.0)

    def test_isolated_and_pendant_low_degree(self):
        """L2: degree 0 and degree 1 nodes => triangles=0, clustering=0.0."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_node(7)            # isolated, degree 0
        G.add_edge(8, 9)         # both degree 1
        res = nx.triangle_profile(G)
        _check_entry(res[7], triangles=0, degree=0, clustering=0.0)
        _check_entry(res[8], triangles=0, degree=1, clustering=0.0)
        _check_entry(res[9], triangles=0, degree=1, clustering=0.0)

    def test_single_node_query(self):
        """L2: nodes naming a single node yields a one-entry dict for that node."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (0, 2), (2, 3)])
        res = nx.triangle_profile(G, nodes=[2])
        assert set(res.keys()) == {2}, f"expected only node 2, got {sorted(res)}"
        # node 2 is in one triangle {0,1,2}; degree 3 (to 0,1,3) => 2*1/(3*2)=1/3
        _check_entry(res[2], triangles=1, degree=3, clustering=1.0 / 3.0)

    def test_nodes_subset_respected(self):
        """L2: a multi-node subset returns exactly those nodes (arg not ignored).

        A stub that ignores ``nodes`` and always profiles every node fails the
        key-set assertion here.
        """
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (0, 2), (2, 3), (3, 4)])
        res = nx.triangle_profile(G, nodes=[0, 3])
        assert set(res.keys()) == {0, 3}, f"expected {{0,3}}, got {sorted(res)}"
        _check_entry(res[0], triangles=1, degree=2, clustering=1.0)
        _check_entry(res[3], triangles=0, degree=2, clustering=0.0)

    def test_unknown_node_raises_node_not_found(self):
        """L2: a node in `nodes` absent from G raises networkx.NodeNotFound."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        with pytest.raises(nx.NodeNotFound):
            nx.triangle_profile(G, nodes=[0, 99])

    def test_directed_raises_not_implemented(self):
        """L2: a directed graph raises networkx.NetworkXNotImplemented."""
        nx = _import_networkx()
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2), (2, 0)])
        with pytest.raises(nx.NetworkXNotImplemented):
            nx.triangle_profile(G)

    def test_graph_not_mutated(self):
        """L2: the original graph G is unchanged after a call."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (0, 2), (2, 3), (3, 4), (2, 4)])
        nodes_before = set(G.nodes())
        edges_before = {tuple(sorted(e)) for e in G.edges()}
        nx.triangle_profile(G)
        nx.triangle_profile(G, nodes=[2])
        assert set(G.nodes()) == nodes_before, "nodes mutated"
        assert {tuple(sorted(e)) for e in G.edges()} == edges_before, "edges mutated"

    def test_clustering_matches_builtin_reference(self):
        """L2: clustering values agree with nx.clustering on a denser graph.

        Cross-checks the agent's formula against networkx's own clustering
        implementation (an independent oracle) on the complete-graph-minus-edge
        K4\\{2,3}, where degrees/triangles vary across nodes.
        """
        nx = _import_networkx()
        G = nx.complete_graph(4)
        G.remove_edge(2, 3)
        res = nx.triangle_profile(G)
        ref = nx.clustering(G)
        ref_tri = nx.triangles(G)
        for n in G.nodes():
            _check_entry(
                res[n],
                triangles=int(ref_tri[n]),
                degree=G.degree(n),
                clustering=float(ref[n]),
            )

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
                "networkx/algorithms/tests/test_triangle_profile.py",
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

        Exercises the public function in a clean process whose cwd is REPO_DIR,
        so a solution that only patched its own test file (without a working
        implementation) cannot pass.
        """
        driver = textwrap.dedent(
            """
            import math
            import networkx as nx
            assert nx.__file__.startswith(%r), nx.__file__

            def chk(e, t, d, c):
                assert set(e) == {"triangles", "degree", "clustering"}, e
                assert isinstance(e["triangles"], int) and not isinstance(e["triangles"], bool)
                assert isinstance(e["degree"], int) and not isinstance(e["degree"], bool)
                assert isinstance(e["clustering"], float)
                assert e["triangles"] == t, e
                assert e["degree"] == d, e
                assert math.isclose(e["clustering"], c, abs_tol=1e-9), e

            # triangle
            T = nx.Graph(); T.add_edges_from([(0,1),(1,2),(0,2)])
            rt = nx.triangle_profile(T)
            for n in (0,1,2):
                chk(rt[n], 1, 2, 1.0)

            # bowtie shared node
            B = nx.Graph()
            B.add_edges_from([(0,1),(1,2),(0,2),(2,3),(3,4),(2,4)])
            rb = nx.triangle_profile(B)
            chk(rb[2], 2, 4, 1.0/3.0)
            for n in (0,1,3,4):
                chk(rb[n], 1, 2, 1.0)

            # path internal/endpoints
            P = nx.Graph(); nx.add_path(P, [0,1,2])
            rp = nx.triangle_profile(P)
            chk(rp[1], 0, 2, 0.0)
            chk(rp[0], 0, 1, 0.0)

            # single-node query
            rs = nx.triangle_profile(T, nodes=[1])
            assert set(rs) == {1}, rs

            # directed guard
            D = nx.DiGraph(); D.add_edges_from([(0,1),(1,2),(2,0)])
            try:
                nx.triangle_profile(D)
                raise AssertionError("expected NetworkXNotImplemented")
            except nx.NetworkXNotImplemented:
                pass

            # unknown-node guard
            try:
                nx.triangle_profile(T, nodes=[99])
                raise AssertionError("expected NodeNotFound")
            except nx.NodeNotFound:
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
