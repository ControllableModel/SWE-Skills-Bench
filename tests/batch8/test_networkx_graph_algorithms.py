"""Tests for skill: networkx-graph-algorithms (variant ext8).

Task: add a Degree-Histogram Structural Fingerprint module to networkx that
exposes two label/order-independent helpers:

    nx.structural_fingerprint(G) -> {
        "n_nodes": int, "n_edges": int,
        "degree_histogram": tuple[int, ...],   # trimmed; () for empty graph
        "n_triangles": int,
    }
    nx.same_fingerprint(G, H) -> bool   # True iff the two dicts are equal

These tests reach into REPO_DIR = /workspace/networkx, import that networkx
build directly (so the agent's edited module is exercised), and dynamically
validate the fingerprint dict's exact keys/values, isomorphic relabeling
equality, order independence, triangle counts, directed-input rejection
(NetworkXNotImplemented), empty-graph behavior, and graph immutability. Each
scenario in the requirement doc maps to a concrete numeric/structural
assertion. Substring/keyword matching on the source is deliberately avoided;
the new behavior is exercised end-to-end, including via an independent driver
process and the deliverable's native pytest command.

Verification strategy / discriminative power:
- A stub that returns a fixed dict, ignores node labels, leaves the
  degree_histogram untrimmed, miscounts triangles, double-counts edges, or
  mutates its input will fail at least one L2 case.
- The native acceptance command is driven exactly:
    python -m pytest networkx/algorithms/tests/test_structural_fingerprint.py -q
"""

import importlib
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


class TestNetworkxGraphAlgorithms:
    REPO_DIR = "/workspace/networkx"

    # ---------------------------------------------------------------- L1 ----
    def test_module_file_exists(self):
        """L1: the new structural_fingerprint module file is present."""
        path = os.path.join(
            REPO_DIR, "networkx", "algorithms", "structural_fingerprint.py"
        )
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 0, "structural_fingerprint.py is empty"

    def test_test_file_exists(self):
        """L1: the deliverable unit-test file is present and non-empty."""
        path = os.path.join(
            REPO_DIR,
            "networkx",
            "algorithms",
            "tests",
            "test_structural_fingerprint.py",
        )
        assert os.path.isfile(path), f"missing test file: {path}"
        assert os.path.getsize(path) > 0, "test_structural_fingerprint.py is empty"

    def test_public_names_resolve(self):
        """L1: nx.structural_fingerprint and nx.same_fingerprint are wired up."""
        nx = _import_networkx()
        assert hasattr(nx, "structural_fingerprint"), "structural_fingerprint missing"
        assert hasattr(nx, "same_fingerprint"), "same_fingerprint missing"
        assert callable(nx.structural_fingerprint)
        assert callable(nx.same_fingerprint)

    # ---------------------------------------------------------------- L2 ----
    def test_fingerprint_exact_keys(self):
        """L2: returns a dict with EXACTLY the four specified keys."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (2, 0)])
        fp = nx.structural_fingerprint(G)
        assert isinstance(fp, dict), f"expected dict, got {type(fp)}"
        assert set(fp.keys()) == {
            "n_nodes",
            "n_edges",
            "degree_histogram",
            "n_triangles",
        }, f"unexpected keys: {sorted(fp.keys())}"

    def test_triangle_fingerprint_values(self):
        """L2: a triangle has the exact documented fingerprint."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (2, 0)])
        fp = nx.structural_fingerprint(G)
        assert fp["n_nodes"] == 3, fp
        assert fp["n_edges"] == 3, fp
        assert fp["degree_histogram"] == (0, 0, 3), fp
        assert isinstance(fp["degree_histogram"], tuple), "degree_histogram not a tuple"
        assert fp["n_triangles"] == 1, fp
        # types are concrete ints (not numpy / not bool)
        assert type(fp["n_nodes"]) is int and type(fp["n_edges"]) is int
        assert type(fp["n_triangles"]) is int
        assert all(type(c) is int for c in fp["degree_histogram"])

    def test_four_cycle_fingerprint_values(self):
        """L2: 4-cycle 0-1-2-3-0 => degree_histogram=(0,0,4), n_triangles=0."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 0)])
        fp = nx.structural_fingerprint(G)
        assert fp["n_nodes"] == 4, fp
        assert fp["n_edges"] == 4, fp
        assert fp["degree_histogram"] == (0, 0, 4), fp
        assert fp["n_triangles"] == 0, fp

    def test_path_p3_fingerprint_values(self):
        """L2: path 0-1-2 => 2 edges, degree_histogram=(0,2,1), no triangles."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        fp = nx.structural_fingerprint(G)
        assert fp["n_nodes"] == 3, fp
        assert fp["n_edges"] == 2, fp
        # two degree-1 endpoints, one degree-2 center; trimmed at last nonzero
        assert fp["degree_histogram"] == (0, 2, 1), fp
        assert fp["n_triangles"] == 0, fp

    def test_empty_graph_fingerprint(self):
        """L2: empty graph yields the documented all-zero / empty-tuple dict."""
        nx = _import_networkx()
        G = nx.Graph()
        fp = nx.structural_fingerprint(G)
        assert fp == {
            "n_nodes": 0,
            "n_edges": 0,
            "degree_histogram": (),
            "n_triangles": 0,
        }, fp
        assert fp["degree_histogram"] == (), "empty graph must give empty tuple"

    def test_degree_histogram_is_trimmed(self):
        """L2: trailing zero-count degrees are trimmed (last element non-zero).

        Star K_{1,3}: center degree 3, three leaves degree 1 -> histogram
        (0, 3, 0, 1). A naive non-trimming impl that pads to max-degree+1 with
        a trailing zero (e.g. extra index) would still end in 1 here, so we use
        a graph whose true max degree leaves no trailing zeros and separately
        assert there is never a trailing zero element.
        """
        nx = _import_networkx()
        G = nx.star_graph(3)  # nodes 0..3, center 0 degree 3, leaves degree 1
        fp = nx.structural_fingerprint(G)
        assert fp["n_nodes"] == 4, fp
        assert fp["n_edges"] == 3, fp
        assert fp["degree_histogram"] == (0, 3, 0, 1), fp
        hist = fp["degree_histogram"]
        assert hist == () or hist[-1] != 0, f"histogram not trimmed: {hist}"

    def test_isolated_node_in_histogram(self):
        """L2: a degree-0 node contributes to index 0 of the histogram."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1)])
        G.add_node(99)  # isolated
        fp = nx.structural_fingerprint(G)
        assert fp["n_nodes"] == 3, fp
        assert fp["n_edges"] == 1, fp
        # one degree-0 node, two degree-1 nodes
        assert fp["degree_histogram"] == (1, 2), fp
        assert fp["n_triangles"] == 0, fp

    def test_label_independence_isomorphic_equal(self):
        """L2: relabeled isomorphic triangles produce EQUAL fingerprints."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (2, 0)])
        H = nx.Graph()
        H.add_edges_from([("a", "b"), ("b", "c"), ("c", "a")])
        assert nx.structural_fingerprint(G) == nx.structural_fingerprint(H)
        assert nx.same_fingerprint(G, H) is True

    def test_insertion_order_independence(self):
        """L2: edge/node insertion order does not change the fingerprint."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 0), (0, 2)])
        H = nx.Graph()
        # same graph, reversed/shuffled insertion order and reversed endpoints
        H.add_edges_from([(2, 0), (0, 3), (3, 2), (2, 1), (1, 0)])
        assert nx.structural_fingerprint(G) == nx.structural_fingerprint(H)
        assert nx.same_fingerprint(G, H) is True

    def test_same_fingerprint_false_for_distinct(self):
        """L2: triangle vs path-on-3 differ (3 vs 2 edges) => same_fingerprint False."""
        nx = _import_networkx()
        tri = nx.Graph()
        tri.add_edges_from([(0, 1), (1, 2), (2, 0)])
        path = nx.Graph()
        nx.add_path(path, [0, 1, 2])
        assert nx.structural_fingerprint(tri) != nx.structural_fingerprint(path)
        assert nx.same_fingerprint(tri, path) is False
        # and equal for two relabeled triangles
        tri2 = nx.Graph()
        tri2.add_edges_from([("x", "y"), ("y", "z"), ("z", "x")])
        assert nx.same_fingerprint(tri, tri2) is True

    def test_same_fingerprint_distinguishes_triangle_count(self):
        """L2: same n_nodes/n_edges/degree dist but different triangle counts.

        K4 (4 nodes, 6 edges, all degree 3, 4 triangles) vs the 3-prism /
        complete-bipartite-like graph that also has 4 nodes... we instead build
        two 6-node 3-regular graphs: K_{3,3} (0 triangles) vs the triangular
        prism (2 triangles). Both have 6 nodes, 9 edges, histogram (0,0,0,6),
        so only n_triangles distinguishes them.
        """
        nx = _import_networkx()
        k33 = nx.complete_bipartite_graph(3, 3)
        prism = nx.Graph()
        # two triangles 0-1-2 and 3-4-5 joined 0-3,1-4,2-5
        prism.add_edges_from(
            [(0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (0, 3), (1, 4), (2, 5)]
        )
        fp_k = nx.structural_fingerprint(k33)
        fp_p = nx.structural_fingerprint(prism)
        assert fp_k["n_nodes"] == fp_p["n_nodes"] == 6
        assert fp_k["n_edges"] == fp_p["n_edges"] == 9
        assert fp_k["degree_histogram"] == fp_p["degree_histogram"] == (0, 0, 0, 6)
        assert fp_k["n_triangles"] == 0, fp_k
        assert fp_p["n_triangles"] == 2, fp_p
        assert nx.same_fingerprint(k33, prism) is False

    def test_directed_input_raises_not_implemented(self):
        """L2: directed input to either function raises NetworkXNotImplemented."""
        nx = _import_networkx()
        D = nx.DiGraph()
        D.add_edges_from([(0, 1), (1, 2)])
        with pytest.raises(nx.NetworkXNotImplemented):
            nx.structural_fingerprint(D)
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        with pytest.raises(nx.NetworkXNotImplemented):
            nx.same_fingerprint(D, G)
        with pytest.raises(nx.NetworkXNotImplemented):
            nx.same_fingerprint(G, D)

    def test_graph_not_mutated(self):
        """L2: neither structural_fingerprint nor same_fingerprint mutates input."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (2, 0)])
        G.add_node(7)
        nodes_before = set(G.nodes())
        edges_before = {tuple(sorted(e)) for e in G.edges()}
        H = nx.Graph()
        H.add_edges_from([("a", "b"), ("b", "c"), ("c", "a")])
        h_nodes_before = set(H.nodes())
        h_edges_before = {tuple(sorted(e, key=str)) for e in H.edges()}
        nx.structural_fingerprint(G)
        nx.same_fingerprint(G, H)
        assert set(G.nodes()) == nodes_before, "G nodes mutated"
        assert {tuple(sorted(e)) for e in G.edges()} == edges_before, "G edges mutated"
        assert set(H.nodes()) == h_nodes_before, "H nodes mutated"
        assert {tuple(sorted(e, key=str)) for e in H.edges()} == h_edges_before, (
            "H edges mutated"
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
                "networkx/algorithms/tests/test_structural_fingerprint.py",
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

        Exercises the public functions in a clean process whose cwd is
        REPO_DIR, so a solution that only patched its own test file (without a
        working implementation) cannot pass.
        """
        driver = textwrap.dedent(
            """
            import sys
            import networkx as nx
            assert nx.__file__.startswith(%r), nx.__file__

            # triangle exact fingerprint
            T = nx.Graph(); T.add_edges_from([(0,1),(1,2),(2,0)])
            fp = nx.structural_fingerprint(T)
            assert fp == {"n_nodes": 3, "n_edges": 3,
                          "degree_histogram": (0, 0, 3), "n_triangles": 1}, fp

            # 4-cycle: no triangles, four degree-2 nodes
            C = nx.Graph(); C.add_edges_from([(0,1),(1,2),(2,3),(3,0)])
            fc = nx.structural_fingerprint(C)
            assert fc["degree_histogram"] == (0, 0, 4) and fc["n_triangles"] == 0, fc

            # empty graph
            assert nx.structural_fingerprint(nx.Graph()) == {
                "n_nodes": 0, "n_edges": 0,
                "degree_histogram": (), "n_triangles": 0}

            # relabel invariance
            H = nx.Graph(); H.add_edges_from([("a","b"),("b","c"),("c","a")])
            assert nx.same_fingerprint(T, H) is True

            # distinct graphs differ
            P = nx.Graph(); nx.add_path(P, [0,1,2])
            assert nx.same_fingerprint(T, P) is False

            # directed rejection
            D = nx.DiGraph(); D.add_edges_from([(0,1),(1,2)])
            try:
                nx.structural_fingerprint(D); raise AssertionError("no raise")
            except nx.NetworkXNotImplemented:
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
