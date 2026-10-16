"""Tests for skill: networkx-graph-algorithms (variant ext5).

Task: add a weighted adjacency-CSV reader and writer to networkx under
``networkx/readwrite/weighted_csv.py`` and wire them so they resolve as
``nx.write_weighted_csv(G, path, weight="weight", default=1.0)`` and
``nx.read_weighted_csv(path, weight="weight", create_using=None)``.

Writer contract: first line is exactly ``source,target,weight``; each edge is
serialized as ``u,v,w`` (str(node) labels, the named weight attribute or
``default`` when absent), in ``G.edges()`` order. Reader contract: node labels
are read back as **strings** (no type inference), the third column is parsed as
``float`` under the ``weight`` attribute name; ``create_using`` follows NetworkX
convention. A malformed (non-3-field) data line raises ``networkx.NetworkXError``;
an empty graph round-trips to a header-only file.

Verification strategy: import the agent's edited networkx build directly from
REPO_DIR and dynamically exercise the two public functions — header bytes, body
rows, round-trip edge/weight reproduction, stringified labels, default-weight
fill, directed direction preservation, malformed-line errors and the empty-graph
case. A naive stub (hardcoded header, ignored weights, int labels on read, no
error on malformed input) must fail. The deliverable native pytest command and an
independent in-process driver are both run to defeat test-only patches.
"""

import importlib
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/networkx"

# Front-load REPO_DIR so the agent's edited tree is imported in preference to any
# site-packages networkx. Importing networkx is expensive for the dev build, so
# import exactly ONCE and cache it.
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
        """L1: the new weighted_csv module file is present and non-empty."""
        path = os.path.join(REPO_DIR, "networkx", "readwrite", "weighted_csv.py")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 0, "weighted_csv.py is empty"

    def test_test_file_exists(self):
        """L1: the deliverable unit-test file is present and non-empty."""
        path = os.path.join(
            REPO_DIR, "networkx", "readwrite", "tests", "test_weighted_csv.py"
        )
        assert os.path.isfile(path), f"missing test file: {path}"
        assert os.path.getsize(path) > 0, "test_weighted_csv.py is empty"

    def test_public_names_resolve(self):
        """L1: nx.write_weighted_csv / nx.read_weighted_csv are wired and callable."""
        nx = _import_networkx()
        assert hasattr(nx, "write_weighted_csv"), "nx.write_weighted_csv not exposed"
        assert hasattr(nx, "read_weighted_csv"), "nx.read_weighted_csv not exposed"
        assert callable(nx.write_weighted_csv)
        assert callable(nx.read_weighted_csv)

    # ---------------------------------------------------------------- L2 ----
    def test_header_line_is_exact(self, tmp_path):
        """L2: the first line of the written file is exactly 'source,target,weight'."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edge("a", "b", weight=2.5)
        p = tmp_path / "g.csv"
        nx.write_weighted_csv(G, os.fspath(p))
        lines = p.read_text().splitlines()
        assert lines, "written file is empty"
        assert lines[0] == "source,target,weight", f"bad header: {lines[0]!r}"

    def test_body_rows_match_edges_and_weights(self, tmp_path):
        """L2: edges serialize as 'u,v,w'; named weight used, default fills gaps."""
        nx = _import_networkx()
        G = nx.Graph()
        # Insertion order is preserved by G.edges(): (a,b) then (b,c).
        G.add_edge("a", "b", weight=2.5)
        G.add_edge("b", "c")  # no weight -> default 1.0
        p = tmp_path / "g.csv"
        nx.write_weighted_csv(G, os.fspath(p))
        lines = p.read_text().splitlines()
        assert lines[0] == "source,target,weight"
        body = lines[1:]
        assert len(body) == 2, f"expected 2 data rows, got {body!r}"
        # Parse each row and compare structurally (tolerate 1.0 vs 1 etc).
        parsed = []
        for row in body:
            fields = row.split(",")
            assert len(fields) == 3, f"row not 3 fields: {row!r}"
            u, v, w = fields[0], fields[1], float(fields[2])
            parsed.append((u, v, w))
        assert parsed[0] == ("a", "b", 2.5), f"first row wrong: {parsed[0]!r}"
        assert parsed[1] == ("b", "c", 1.0), f"second row wrong: {parsed[1]!r}"

    def test_round_trip_reproduces_edges_and_float_weights(self, tmp_path):
        """L2: write-then-read reproduces the edge set with float weights."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edge("a", "b", weight=2.5)
        G.add_edge("b", "c")  # default 1.0
        p = tmp_path / "g.csv"
        nx.write_weighted_csv(G, os.fspath(p))
        H = nx.read_weighted_csv(os.fspath(p))
        assert isinstance(H, nx.Graph) and not H.is_directed()
        assert set(map(frozenset, H.edges())) == {
            frozenset(("a", "b")),
            frozenset(("b", "c")),
        }, f"edge set wrong: {list(H.edges())}"
        w_ab = H.edges["a", "b"]["weight"]
        w_bc = H.edges["b", "c"]["weight"]
        assert w_ab == 2.5 and isinstance(w_ab, float), f"weight a-b={w_ab!r}"
        assert w_bc == 1.0 and isinstance(w_bc, float), f"weight b-c={w_bc!r}"

    def test_integer_labels_round_trip_as_strings(self, tmp_path):
        """L2: writer uses str(node); reader returns STRING labels (no inference)."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edge(1, 2, weight=3.0)
        p = tmp_path / "g.csv"
        nx.write_weighted_csv(G, os.fspath(p))
        H = nx.read_weighted_csv(os.fspath(p))
        assert set(H.nodes()) == {"1", "2"}, f"nodes not stringified: {set(H.nodes())}"
        # The integer node must NOT survive as an int.
        assert 1 not in H.nodes() and 2 not in H.nodes(), "int labels leaked through"
        assert H.edges["1", "2"]["weight"] == 3.0

    def test_custom_weight_attribute_name(self, tmp_path):
        """L2: a non-default weight attr name is honored on write and read."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edge("x", "y", cost=7.5)
        G.add_edge("y", "z")  # no 'cost' -> default
        p = tmp_path / "g.csv"
        nx.write_weighted_csv(G, os.fspath(p), weight="cost", default=4.0)
        lines = p.read_text().splitlines()
        # default must be applied for the missing 'cost' edge.
        parsed = {(r.split(",")[0], r.split(",")[1]): float(r.split(",")[2])
                  for r in lines[1:]}
        assert parsed[("x", "y")] == 7.5, f"x-y cost wrong: {parsed!r}"
        assert parsed[("y", "z")] == 4.0, f"y-z default wrong: {parsed!r}"
        # Read back storing under 'cost'.
        H = nx.read_weighted_csv(os.fspath(p), weight="cost")
        assert H.edges["x", "y"]["cost"] == 7.5
        assert H.edges["y", "z"]["cost"] == 4.0

    def test_directed_round_trip_preserves_direction(self, tmp_path):
        """L2: DiGraph written and read with create_using=nx.DiGraph keeps direction."""
        nx = _import_networkx()
        G = nx.DiGraph()
        G.add_edge("a", "b", weight=1.0)
        G.add_edge("b", "c", weight=2.0)
        p = tmp_path / "d.csv"
        nx.write_weighted_csv(G, os.fspath(p))
        H = nx.read_weighted_csv(os.fspath(p), create_using=nx.DiGraph)
        assert H.is_directed(), "create_using=nx.DiGraph did not yield a DiGraph"
        assert set(H.edges()) == {("a", "b"), ("b", "c")}, f"edges: {list(H.edges())}"
        # Direction is real: reverse edges must be absent.
        assert not H.has_edge("b", "a"), "spurious reverse edge b->a"
        assert not H.has_edge("c", "b"), "spurious reverse edge c->b"

    def test_default_create_using_is_undirected(self, tmp_path):
        """L2: create_using=None yields an undirected Graph."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edge("a", "b", weight=1.0)
        p = tmp_path / "g.csv"
        nx.write_weighted_csv(G, os.fspath(p))
        H = nx.read_weighted_csv(os.fspath(p))
        assert not H.is_directed(), "default reader should produce undirected Graph"
        # Undirected: both orientations resolve to the same edge.
        assert H.has_edge("a", "b") and H.has_edge("b", "a")

    def test_malformed_line_raises_networkx_error(self, tmp_path):
        """L2: a non-header data line without exactly 3 fields raises NetworkXError."""
        nx = _import_networkx()
        p = tmp_path / "bad.csv"
        # Header is well-formed; the data line has only 2 fields.
        p.write_text("source,target,weight\na,b\n")
        with pytest.raises(nx.NetworkXError):
            nx.read_weighted_csv(os.fspath(p))

    def test_malformed_too_many_fields_raises(self, tmp_path):
        """L2: a data line with four comma fields also raises NetworkXError."""
        nx = _import_networkx()
        p = tmp_path / "bad2.csv"
        p.write_text("source,target,weight\na,b,1.0,extra\n")
        with pytest.raises(nx.NetworkXError):
            nx.read_weighted_csv(os.fspath(p))

    def test_empty_graph_round_trip(self, tmp_path):
        """L2: writing an edgeless graph yields a header-only file; read gives no edges."""
        nx = _import_networkx()
        G = nx.Graph()
        p = tmp_path / "empty.csv"
        nx.write_weighted_csv(G, os.fspath(p))
        lines = p.read_text().splitlines()
        assert lines == ["source,target,weight"], f"empty file body: {lines!r}"
        H = nx.read_weighted_csv(os.fspath(p))
        assert H.number_of_edges() == 0, f"expected no edges, got {list(H.edges())}"

    def test_pathlike_argument_accepted(self, tmp_path):
        """L2: write/read accept os.PathLike (a pathlib.Path), not just str."""
        nx = _import_networkx()
        G = nx.Graph()
        G.add_edge("p", "q", weight=9.0)
        p = tmp_path / "pl.csv"
        nx.write_weighted_csv(G, p)  # pass Path directly
        H = nx.read_weighted_csv(p)  # pass Path directly
        assert H.edges["p", "q"]["weight"] == 9.0

    def test_native_pytest_passes(self):
        """L2: the deliverable native test command passes from the repo root."""
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "networkx/readwrite/tests/test_weighted_csv.py",
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

    def test_independent_driver_against_native_python(self, tmp_path):
        """L2: a fresh driver process under REPO_DIR exercises the public API.

        A solution that only patched its own test file (without a working
        implementation) cannot pass this, since the driver imports networkx and
        round-trips a graph in a clean interpreter.
        """
        out_path = tmp_path / "driver.csv"
        driver = textwrap.dedent(
            """
            import os, sys
            import networkx as nx
            assert nx.__file__.startswith(%r), nx.__file__

            path = %r

            # weighted undirected round trip with default fill
            G = nx.Graph()
            G.add_edge("a", "b", weight=2.5)
            G.add_edge("b", "c")
            nx.write_weighted_csv(G, path)

            with open(path) as fh:
                lines = fh.read().splitlines()
            assert lines[0] == "source,target,weight", lines[0]

            H = nx.read_weighted_csv(path)
            assert not H.is_directed()
            assert set(map(frozenset, H.edges())) == {
                frozenset(("a", "b")), frozenset(("b", "c"))
            }, list(H.edges())
            wab = H.edges["a", "b"]["weight"]
            wbc = H.edges["b", "c"]["weight"]
            assert wab == 2.5 and isinstance(wab, float), wab
            assert wbc == 1.0 and isinstance(wbc, float), wbc

            # integer labels -> strings
            Gi = nx.Graph(); Gi.add_edge(1, 2, weight=3.0)
            nx.write_weighted_csv(Gi, path)
            Hi = nx.read_weighted_csv(path)
            assert set(Hi.nodes()) == {"1", "2"}, set(Hi.nodes())

            # directed preserves direction
            D = nx.DiGraph(); D.add_edge("a", "b", weight=1.0)
            nx.write_weighted_csv(D, path)
            Hd = nx.read_weighted_csv(path, create_using=nx.DiGraph)
            assert Hd.is_directed() and not Hd.has_edge("b", "a"), list(Hd.edges())

            print("DRIVER_OK")
            """
            % (os.path.realpath(REPO_DIR), os.fspath(out_path))
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
