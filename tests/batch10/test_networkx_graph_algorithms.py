"""Tests for skill: networkx-graph-algorithms (variant ext10).

Task: add an Attribute-Filtered Ego Subgraph Extractor to networkx exposing
``nx.filtered_ego_graph(G, center, radius=1, node_filter=None)``. The function
extracts the neighborhood within ``radius`` hops of ``center`` (honoring edge
direction on DiGraphs) and keeps only nodes whose attributes satisfy a caller
supplied predicate ``node_filter(node, attrs) -> bool``. ``center`` is always
kept (exempt from the filter). The result is an INDEPENDENT induced subgraph of
the same graph type, preserving node/edge attributes; ``G`` is never mutated;
a missing center raises ``networkx.NodeNotFound``.

Verification strategy: these tests reach into REPO_DIR = /workspace/networkx,
import that networkx build directly (so the agent's edited module is
exercised), and dynamically validate node sets, edge sets, attribute carry
over, graph-type, the radius-0 / center-exempt / induced-edge / directed edge
cases, copy independence (mutating the result must not touch G), and error
handling. Each scenario from the requirement doc maps to a concrete assertion.
A naive stub (e.g. ignoring node_filter, returning G unchanged, sharing
mutable state with G, or dropping the center) is designed to fail. Source-text
keyword matching is deliberately avoided; the native deliverable test command
is also driven via subprocess, plus an independent in-process driver.
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
# dev build, so we import exactly ONCE and cache it.
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


def _edgeset_undirected(G):
    return {frozenset(e) for e in G.edges()}


class TestNetworkxGraphAlgorithms:
    REPO_DIR = "/workspace/networkx"

    # ---------------------------------------------------------------- L1 ----
    def test_module_file_exists(self):
        """L1: the new ego_filtered module file is present and non-empty."""
        path = os.path.join(REPO_DIR, "networkx", "algorithms", "ego_filtered.py")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 0, "ego_filtered.py is empty"

    def test_test_file_exists(self):
        """L1: the deliverable unit-test file is present and non-empty."""
        path = os.path.join(
            REPO_DIR, "networkx", "algorithms", "tests", "test_ego_filtered.py"
        )
        assert os.path.isfile(path), f"missing test file: {path}"
        assert os.path.getsize(path) > 0, "test_ego_filtered.py is empty"

    def test_public_name_resolves(self):
        """L1: nx.filtered_ego_graph is wired through the package and callable."""
        nx = _import_networkx()
        assert hasattr(nx, "filtered_ego_graph"), "nx.filtered_ego_graph not exposed"
        assert callable(nx.filtered_ego_graph)

    # ---------------------------------------------------------------- L2 ----
    def test_star_filter_keeps_matching_nodes_and_induced_edges(self):
        """L2: star with team attrs, filter team=='A' keeps {c,x,z} and c-x,c-z."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_node("c", team="A")
        G.add_node("x", team="A")
        G.add_node("y", team="B")
        G.add_node("z", team="A")
        G.add_edges_from([("c", "x"), ("c", "y"), ("c", "z")])
        H = nx.filtered_ego_graph(
            G, "c", radius=1, node_filter=lambda n, d: d.get("team") == "A"
        )
        assert set(H.nodes()) == {"c", "x", "z"}, f"nodes={set(H.nodes())}"
        assert _edgeset_undirected(H) == {
            frozenset(("c", "x")),
            frozenset(("c", "z")),
        }, f"edges={_edgeset_undirected(H)}"
        # node y must be excluded entirely, taking edge c-y with it
        assert "y" not in H

    def test_node_and_edge_attributes_preserved(self):
        """L2: node attrs and edge attrs survive into the returned subgraph."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_node("c", team="A", rank=1)
        G.add_node("x", team="A", rank=7)
        G.add_edge("c", "x", weight=3.5, label="link")
        H = nx.filtered_ego_graph(
            G, "c", radius=1, node_filter=lambda n, d: d.get("team") == "A"
        )
        assert H.nodes["x"]["rank"] == 7, f"node attr lost: {H.nodes['x']}"
        assert H.nodes["c"]["team"] == "A"
        assert H.edges["c", "x"]["weight"] == 3.5, f"edge attr lost: {H.edges['c','x']}"
        assert H.edges["c", "x"]["label"] == "link"

    def test_path_radius_two_no_filter(self):
        """L2: path 0-1-2-3, center 0, radius 2, no filter -> {0,1,2}, 0-1,1-2."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3])
        H = nx.filtered_ego_graph(G, 0, radius=2, node_filter=None)
        assert set(H.nodes()) == {0, 1, 2}, f"nodes={set(H.nodes())}"
        assert _edgeset_undirected(H) == {
            frozenset((0, 1)),
            frozenset((1, 2)),
        }, f"edges={_edgeset_undirected(H)}"
        assert 3 not in H, "node 3 is out of radius and must be excluded"

    def test_radius_zero_returns_only_center(self):
        """L2: radius 0 returns a single-node graph holding only center (no edges)."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3])
        G.add_node(0, color="red")
        H = nx.filtered_ego_graph(G, 0, radius=0)
        assert set(H.nodes()) == {0}, f"nodes={set(H.nodes())}"
        assert H.number_of_edges() == 0, "radius-0 result must have no edges"
        assert H.nodes[0].get("color") == "red", "center attrs must be preserved"

    def test_center_kept_even_when_filter_rejects_it(self):
        """L2: center is exempt from node_filter and remains in the result."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_node("c", team="B")  # filter below rejects team B
        G.add_node("x", team="A")
        G.add_edge("c", "x")
        H = nx.filtered_ego_graph(
            G, "c", radius=1, node_filter=lambda n, d: d.get("team") == "A"
        )
        assert "c" in H.nodes(), "center must be kept despite failing the filter"
        assert set(H.nodes()) == {"c", "x"}, f"nodes={set(H.nodes())}"
        assert _edgeset_undirected(H) == {frozenset(("c", "x"))}

    def test_induced_edges_only(self):
        """L2: an edge survives iff BOTH endpoints survive filtering and range."""
        nx = _import_networkx()
        # center c connects to a (kept) and b (dropped); a-b edge must vanish too.
        G = nx.Graph()
        G.add_node("c", keep=True)
        G.add_node("a", keep=True)
        G.add_node("b", keep=False)
        G.add_edges_from([("c", "a"), ("c", "b"), ("a", "b")])
        H = nx.filtered_ego_graph(
            G, "c", radius=1, node_filter=lambda n, d: d.get("keep") is True
        )
        assert set(H.nodes()) == {"c", "a"}, f"nodes={set(H.nodes())}"
        # only c-a remains; c-b and a-b both reference dropped node b
        assert _edgeset_undirected(H) == {frozenset(("c", "a"))}, _edgeset_undirected(H)

    def test_directed_respects_edge_direction(self):
        """L2: directed chain 0->1->2, center 0, radius 2 keeps {0,1,2} forward only."""
        nx = _import_networkx()
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2)])
        H = nx.filtered_ego_graph(G, 0, radius=2)
        assert isinstance(H, nx.DiGraph), f"result type {type(H).__name__}"
        assert set(H.nodes()) == {0, 1, 2}, f"nodes={set(H.nodes())}"
        assert set(H.edges()) == {(0, 1), (1, 2)}, f"edges={set(H.edges())}"
        # the reverse direction is never present
        assert (1, 0) not in H.edges() and (2, 1) not in H.edges()

    def test_directed_does_not_reach_against_orientation(self):
        """L2: a predecessor of center is out of a directed ego ball."""
        nx = _import_networkx()
        # 9 -> 0 -> 1 : from center 0, node 9 is upstream and unreachable forward.
        G = nx.DiGraph()
        G.add_edges_from([(9, 0), (0, 1)])
        H = nx.filtered_ego_graph(G, 0, radius=5)
        assert 9 not in H.nodes(), "upstream predecessor must not appear (directed)"
        assert set(H.nodes()) == {0, 1}, f"nodes={set(H.nodes())}"

    def test_result_is_independent_copy(self):
        """L2: mutating the returned graph must not affect G (independent copy)."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_node("c")
        G.add_node("x", team="A")
        G.add_edge("c", "x", weight=1)
        H = nx.filtered_ego_graph(G, "c", radius=1)
        # mutate H heavily
        H.add_node("INTRUDER")
        H.add_edge("c", "INTRUDER")
        H.nodes["x"]["team"] = "MUTATED"
        H.edges["c", "x"]["weight"] = 999
        assert "INTRUDER" not in G.nodes(), "node mutation leaked into G"
        assert ("c", "INTRUDER") not in G.edges(), "edge mutation leaked into G"
        assert G.nodes["x"]["team"] == "A", "node-attr mutation leaked into G"
        assert G.edges["c", "x"]["weight"] == 1, "edge-attr mutation leaked into G"

    def test_graph_not_mutated(self):
        """L2: the original graph G is unchanged after the call."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_node("c", team="A")
        G.add_node("x", team="A")
        G.add_node("y", team="B")
        G.add_edges_from([("c", "x"), ("c", "y")])
        nodes_before = set(G.nodes())
        edges_before = _edgeset_undirected(G)
        nx.filtered_ego_graph(
            G, "c", radius=1, node_filter=lambda n, d: d.get("team") == "A"
        )
        assert set(G.nodes()) == nodes_before, "G nodes mutated"
        assert _edgeset_undirected(G) == edges_before, "G edges mutated"
        assert G.nodes["y"]["team"] == "B", "G node attrs mutated"

    def test_missing_center_raises_node_not_found(self):
        """L2: a center absent from G raises networkx.NodeNotFound."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        with pytest.raises(nx.NodeNotFound):
            nx.filtered_ego_graph(G, 99, radius=1)

    def test_returns_same_graph_type(self):
        """L2: undirected input -> Graph (not DiGraph) result of correct type."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        H = nx.filtered_ego_graph(G, 0, radius=1)
        assert isinstance(H, nx.Graph) and not isinstance(H, nx.DiGraph), (
            f"undirected input produced {type(H).__name__}"
        )

    def test_filter_receives_node_and_attrs(self):
        """L2: node_filter is invoked with (node_id, attr_dict) and honored."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_node("c")
        G.add_node("a", score=10)
        G.add_node("b", score=1)
        G.add_edges_from([("c", "a"), ("c", "b")])
        seen = {}

        def filt(n, d):
            seen[n] = d
            return d.get("score", 0) >= 5

        H = nx.filtered_ego_graph(G, "c", radius=1, node_filter=filt)
        # a and b were both candidates; both must have been offered to the filter
        assert "a" in seen and "b" in seen, f"filter not called for all: {seen}"
        assert seen["a"].get("score") == 10, "attrs dict not passed to filter"
        assert set(H.nodes()) == {"c", "a"}, f"nodes={set(H.nodes())}"

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
                "networkx/algorithms/tests/test_ego_filtered.py",
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
            import sys
            import networkx as nx
            assert nx.__file__.startswith(%r), nx.__file__

            def es(G):
                return {frozenset(e) for e in G.edges()}

            # star + team filter
            G = nx.Graph()
            G.add_node("c", team="A"); G.add_node("x", team="A")
            G.add_node("y", team="B"); G.add_node("z", team="A")
            G.add_edges_from([("c","x"),("c","y"),("c","z")])
            H = nx.filtered_ego_graph(G, "c", radius=1,
                                      node_filter=lambda n,d: d.get("team")=="A")
            assert set(H.nodes()) == {"c","x","z"}, set(H.nodes())
            assert es(H) == {frozenset(("c","x")), frozenset(("c","z"))}, es(H)

            # radius 0
            P = nx.Graph(); nx.add_path(P, [0,1,2,3])
            R0 = nx.filtered_ego_graph(P, 0, radius=0)
            assert set(R0.nodes()) == {0} and R0.number_of_edges() == 0

            # directed forward-only
            D = nx.DiGraph(); D.add_edges_from([(0,1),(1,2)])
            HD = nx.filtered_ego_graph(D, 0, radius=2)
            assert isinstance(HD, nx.DiGraph)
            assert set(HD.edges()) == {(0,1),(1,2)}, set(HD.edges())

            # independence
            H.add_node("INTRUDER")
            assert "INTRUDER" not in G.nodes()

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
