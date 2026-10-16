"""Tests for skill: networkx-graph-algorithms (variant ext2).

Task: add a *Hub-Set Mediation Scorer* to networkx that exposes
``nx.hub_set_mediation(G, hubs, weight=None)``. For a designated *set* ``S`` of
nodes treated as a single gateway, the function measures the fraction of
all-pairs shortest-path traffic among the **outside** nodes (nodes not in ``S``)
that is routed through ``S`` as an *interior* node. The result is a single
``float`` in ``[0.0, 1.0]``:

    sum over valid outside pairs (s, t) of  sigma_S(s, t) / sigma(s, t)
    -------------------------------------------------------------------
                  number of valid ordered pairs (s, t)

where ``sigma(s, t)`` counts distinct shortest paths and ``sigma_S(s, t)``
counts those passing through at least one node of ``S`` as an interior node.
For undirected graphs each unordered outside pair is counted once.

Deliverables under verification (per the variant requirement doc):
  * networkx/algorithms/centrality/hub_mediation.py            (new module)
  * networkx/algorithms/centrality/__init__.py                 (import wiring)
  * networkx/algorithms/centrality/tests/test_hub_mediation.py (unit tests)

Verification strategy: these tests reach into REPO_DIR = /workspace/networkx,
import that networkx build directly (so the agent's edited module is exercised),
and dynamically validate the public function's numeric output, fractional
multi-path mediation, edge cases (empty hub set / full coverage / disconnected),
error handling (NodeNotFound), graph immutability, the [0, 1] bound, and
directed/weighted behavior. Each unambiguous scenario in the doc maps to a
concrete float assertion; the contradictory path-graph 0.4 figure is verified
only via the agent's own native pytest command rather than hard-coded here.
Substring/keyword matching on source is deliberately avoided -- the new behavior
is exercised end-to-end. A stub that returns a constant, ignores ``hubs`` or
``weight``, or fails to divide by sigma cannot pass these cases.
"""

import importlib
import itertools
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


class TestNetworkxGraphAlgorithms:
    REPO_DIR = "/workspace/networkx"

    # ---------------------------------------------------------------- L1 ----
    def test_module_file_exists(self):
        """L1: the new hub_mediation module file is present and non-empty."""
        path = os.path.join(
            REPO_DIR, "networkx", "algorithms", "centrality", "hub_mediation.py"
        )
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 0, "hub_mediation.py is empty"

    def test_unit_test_file_exists(self):
        """L1: the deliverable unit-test file is present and non-empty."""
        path = os.path.join(
            REPO_DIR,
            "networkx",
            "algorithms",
            "centrality",
            "tests",
            "test_hub_mediation.py",
        )
        assert os.path.isfile(path), f"missing test file: {path}"
        assert os.path.getsize(path) > 0, "test_hub_mediation.py is empty"

    def test_public_name_resolves(self):
        """L1: nx.hub_set_mediation is wired through the package and callable."""
        nx = _import_networkx()
        assert hasattr(nx, "hub_set_mediation"), "nx.hub_set_mediation not exposed"
        assert callable(nx.hub_set_mediation)

    # ---------------------------------------------------------------- L2 ----
    def test_star_all_traffic_through_center(self):
        """L2: star with center c, leaves a/b/d, hubs={c} -> score 1.0.

        Every leaf-to-leaf shortest path is forced through the single center,
        so the mediated fraction is exactly 1.0 (doc Expected Functionality).
        """
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([("c", "a"), ("c", "b"), ("c", "d")])
        score = nx.hub_set_mediation(G, {"c"})
        assert isinstance(score, float), f"score type {type(score)!r}"
        assert score == 1.0, f"expected 1.0, got {score!r}"

    def test_triangle_direct_edge_bypasses_hub(self):
        """L2: triangle 0-1-2 with hubs={2} -> score 0.0.

        The only outside pair (0,1) has a direct edge whose shortest path never
        uses node 2, so the mediated fraction is 0.0 (doc Expected Functionality).
        """
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (0, 2)])
        score = nx.hub_set_mediation(G, {2})
        assert isinstance(score, float), f"score type {type(score)!r}"
        assert score == 0.0, f"expected 0.0, got {score!r}"

    def test_fractional_mediation_with_tied_shortest_paths(self):
        """L2: a single interior hub on ONE of two tied shortest paths.

        Square 0-1-3-2-0 with hubs={1}. Outside = {0, 2, 3}; undirected pairs:
          (0,2): direct edge          -> 0 mediated
          (2,3): direct edge          -> 0 mediated
          (0,3): two shortest paths [0,1,3] and [0,2,3]; exactly one passes
                 through hub 1 as interior -> sigma_S/sigma = 1/2 = 0.5
        Score = (0 + 0 + 0.5) / 3 = 1/6. This pins the sigma_S/sigma division: a
        naive "passes through?" boolean (0 or 1) would yield 1/3 instead.
        """
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 3), (0, 2), (2, 3)])
        score = nx.hub_set_mediation(G, {1})
        assert math.isclose(score, 1.0 / 6.0, rel_tol=0, abs_tol=1e-9), (
            f"expected 1/6 (tied-path fractional mediation), got {score!r}"
        )

    def test_empty_hub_set_returns_zero(self):
        """L2: an empty hubs iterable returns 0.0 regardless of the graph."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([("c", "a"), ("c", "b"), ("c", "d")])
        for empty in ([], set(), tuple()):
            score = nx.hub_set_mediation(G, empty)
            assert score == 0.0, f"empty hubs {empty!r} -> {score!r}, expected 0.0"
            assert isinstance(score, float)

    def test_hubs_cover_everything_returns_zero(self):
        """L2: when every node is a hub there are no outside pairs -> 0.0."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2)])
        score = nx.hub_set_mediation(G, {0, 1, 2})
        assert score == 0.0, f"full coverage -> {score!r}, expected 0.0"
        assert isinstance(score, float)

    def test_no_reachable_outside_pairs_returns_zero(self):
        """L2: outside nodes that cannot reach each other -> 0.0 (no valid pairs).

        Two disjoint hub-anchored stars: outside leaves live in different
        components, so no outside ordered pair is connected.
        """
        nx = _import_networkx()
        # Isolate a single outside leaf in each of two disjoint components so the
        # only outside pair spans components and is therefore unreachable.
        H = nx.Graph()
        H.add_edge("hA", "a1")  # only outside node a1 in comp A
        H.add_edge("hB", "b1")  # only outside node b1 in comp B
        score = nx.hub_set_mediation(H, {"hA", "hB"})
        # outside = {a1, b1}; the single pair (a1,b1) is unreachable -> 0 valid
        assert score == 0.0, f"no reachable outside pairs -> {score!r}, expected 0.0"

    def test_unknown_hub_raises_node_not_found(self):
        """L2: a hub element absent from G raises NodeNotFound."""
        nx = _import_networkx()
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        with pytest.raises(nx.NodeNotFound):
            nx.hub_set_mediation(G, {99})
        with pytest.raises(nx.NodeNotFound):
            nx.hub_set_mediation(G, {1, 99})  # one valid, one bogus

    def test_weighted_routes_through_hub(self):
        """L2: weight=None vs a named attribute change which path is shortest.

        Triangle: 0-1 (c=1), 1-2 (c=1), 0-2 (c=5). hubs={1}, outside={0,2}.
          * weighted by 'c': cost(0-1-2)=2 < cost(0-2)=5, so the shortest path
            runs THROUGH hub 1 -> score 1.0.
          * unweighted (hop count): direct edge 0-2 is shortest (1 hop) and never
            touches the hub -> score 0.0.
        A solution that ignores ``weight`` cannot satisfy both.
        """
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edge(0, 1, c=1)
        G.add_edge(1, 2, c=1)
        G.add_edge(0, 2, c=5)
        assert nx.hub_set_mediation(G, {1}, weight="c") == 1.0, "weighted should be 1.0"
        assert nx.hub_set_mediation(G, {1}) == 0.0, "unweighted should be 0.0"

    def test_directed_respects_orientation(self):
        """L2: directed traffic only counts pairs reachable along edge direction.

        Chain 0->1->2 (DiGraph), hubs={1}, outside={0,2}. Ordered pairs:
          (0,2): reachable via hub 1 -> mediated; (2,0): no directed path.
        One valid pair, fully mediated -> score 1.0. An undirected reading would
        also include (2,0) as the same connection and still give 1.0, so we add
        a second graph where orientation actually changes the count.
        """
        nx = _import_networkx()
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2)])
        assert nx.hub_set_mediation(G, {1}) == 1.0, "directed chain via hub -> 1.0"

        # Orientation matters: add a direct shortcut 0->2 (1 hop) so the only
        # shortest 0->2 path bypasses the hub -> 0.0, even though 0-1-2 exists.
        G2 = nx.DiGraph()
        G2.add_edges_from([(0, 1), (1, 2), (0, 2)])
        assert nx.hub_set_mediation(G2, {1}) == 0.0, "direct 0->2 shortcut -> 0.0"

    def test_score_within_unit_interval(self):
        """L2: the score always lies in the closed interval [0.0, 1.0]."""
        nx = _import_networkx()
        graphs = []
        g1 = nx.Graph()
        g1.add_edges_from([("c", "a"), ("c", "b"), ("c", "d")])
        graphs.append((g1, {"c"}))
        g2 = nx.Graph()
        g2.add_edges_from([(0, 1), (1, 3), (0, 2), (2, 3)])
        graphs.append((g2, {1}))
        g3 = nx.Graph()
        nx.add_path(g3, [0, 1, 2, 3, 4])
        graphs.append((g3, {2}))
        g4 = nx.DiGraph()
        g4.add_edges_from([(0, 1), (1, 2), (2, 0)])
        graphs.append((g4, {1}))
        for G, hubs in graphs:
            s = nx.hub_set_mediation(G, hubs)
            assert isinstance(s, float), f"score type {type(s)!r} for hubs {hubs!r}"
            assert 0.0 <= s <= 1.0, f"score {s!r} out of [0,1] for hubs {hubs!r}"

    def test_graph_not_mutated(self):
        """L2: G (nodes, edges, attributes) is unchanged after a call."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edge(0, 1, c=1)
        G.add_edge(1, 2, c=1)
        G.add_edge(0, 2, c=5)
        nodes_before = set(G.nodes())
        edges_before = {tuple(sorted(e)) for e in G.edges()}
        attrs_before = {tuple(sorted(e)): G.edges[e]["c"] for e in G.edges()}
        nx.hub_set_mediation(G, {1}, weight="c")
        assert set(G.nodes()) == nodes_before, "nodes mutated"
        assert {tuple(sorted(e)) for e in G.edges()} == edges_before, "edges mutated"
        attrs_after = {tuple(sorted(e)): G.edges[e]["c"] for e in G.edges()}
        assert attrs_after == attrs_before, "edge attributes mutated"

    def test_ignores_constant_stub_via_distinct_values(self):
        """L2: distinct graphs must yield distinct scores (anti-constant guard).

        A stub returning a fixed float would collide on at least one of these.
        star -> 1.0, triangle -> 0.0, square-hub1 -> 1/6 are mutually distinct.
        """
        nx = _import_networkx()
        star = nx.Graph()
        star.add_edges_from([("c", "a"), ("c", "b"), ("c", "d")])
        tri = nx.Graph()
        tri.add_edges_from([(0, 1), (1, 2), (0, 2)])
        sq = nx.Graph()
        sq.add_edges_from([(0, 1), (1, 3), (0, 2), (2, 3)])
        s_star = nx.hub_set_mediation(star, {"c"})
        s_tri = nx.hub_set_mediation(tri, {2})
        s_sq = nx.hub_set_mediation(sq, {1})
        vals = {round(s_star, 9), round(s_tri, 9), round(s_sq, 9)}
        assert len(vals) == 3, f"scores not distinct -> likely constant stub: {vals}"
        assert s_star == 1.0 and s_tri == 0.0
        assert math.isclose(s_sq, 1.0 / 6.0, abs_tol=1e-9)

    def test_native_pytest_passes(self):
        """L2: the deliverable test command passes from the repo root.

        Runs the agent's own committed unit tests via the native toolchain,
        exactly as specified in the Acceptance Criteria:
            python -m pytest networkx/algorithms/centrality/tests/test_hub_mediation.py -q
        """
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "networkx/algorithms/centrality/tests/test_hub_mediation.py",
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
        implementation) cannot pass. Recomputes the fractional, weighted and
        directed reference values independently.
        """
        driver = textwrap.dedent(
            """
            import math, sys
            import networkx as nx
            assert nx.__file__.startswith(%r), nx.__file__

            # star -> 1.0
            S = nx.Graph()
            S.add_edges_from([("c","a"),("c","b"),("c","d")])
            assert nx.hub_set_mediation(S, {"c"}) == 1.0

            # triangle -> 0.0
            T = nx.Graph(); T.add_edges_from([(0,1),(1,2),(0,2)])
            assert nx.hub_set_mediation(T, {2}) == 0.0

            # tied shortest paths -> 1/6 (sigma_S/sigma division)
            Q = nx.Graph(); Q.add_edges_from([(0,1),(1,3),(0,2),(2,3)])
            assert math.isclose(nx.hub_set_mediation(Q, {1}), 1.0/6.0, abs_tol=1e-9)

            # weighted vs unweighted divergence
            W = nx.Graph()
            W.add_edge(0,1,c=1); W.add_edge(1,2,c=1); W.add_edge(0,2,c=5)
            assert nx.hub_set_mediation(W, {1}, weight="c") == 1.0
            assert nx.hub_set_mediation(W, {1}) == 0.0

            # directed orientation
            D = nx.DiGraph(); D.add_edges_from([(0,1),(1,2)])
            assert nx.hub_set_mediation(D, {1}) == 1.0

            # NodeNotFound
            try:
                nx.hub_set_mediation(T, {999}); raise SystemExit("no raise")
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
