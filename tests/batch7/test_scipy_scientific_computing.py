"""
Test for the 'scipy-scientific-computing' skill (variant ext7).

Verifies the agent added a sparse grid-graph Laplacian builder/solver to
``scipy/sparse`` as a new private module ``scipy/sparse/_gridlaplace.py``
exposing::

    grid_laplacian(nx, ny)
    solve_steady_state(nx, ny, source, *, fixed=None)

The tests do NOT trust the agent's own test file and do NOT string-match the
source. Instead each scenario is run in a fresh ``python`` subprocess with
cwd=REPO_DIR (exactly the environment the acceptance command uses), exercising
the real functions and deep-validating the structural / numeric contract:

  * ``grid_laplacian`` is a *sparse* CSR matrix of shape (nx*ny, nx*ny) that is
    symmetric, has zero row sums, degree-2 corners / degree-3 edges /
    degree-4 interior, and an off-diagonal sparsity pattern that matches grid
    adjacency exactly (no spurious nonzeros);
  * ``nnz`` equals the analytic edge count (2 * #edges) + diagonal;
  * ``solve_steady_state`` pins ``fixed`` nodes to their values EXACTLY and the
    solved potentials satisfy the discrete balance at non-anchored nodes with a
    round-off ``residual``;
  * the returned object is the dict with exactly {"u","residual","nnz"};
  * inputs are not mutated;
  * every invalid-input case raises ``ValueError``.

A naive implementation (a dense identity, a wrong stencil, ignoring ``fixed``,
or densifying the matrix) fails these tests. The L2 acceptance driver finally
runs the repo's native command::

    python -m pytest scipy/sparse/tests/test_gridlaplace.py -v
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/scipy"

# Common preamble used by every driver subprocess. It loads the two functions
# preferring the official package import path required by the task, falling back
# to loading the source file directly (its own ``from scipy.sparse ...`` imports
# still resolve through the installed SciPy) so the behavioural tests can run
# even if the editable rebuild has not re-registered the module under the
# package namespace yet.
_LOADER = r"""
import json, sys, importlib.util, os
import numpy as np

REPO_DIR = %r

def _load():
    try:
        from scipy.sparse._gridlaplace import grid_laplacian, solve_steady_state
        return grid_laplacian, solve_steady_state
    except Exception:
        pass
    src = os.path.join(REPO_DIR, "scipy", "sparse", "_gridlaplace.py")
    spec = importlib.util.spec_from_file_location("_gridlaplace_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.grid_laplacian, mod.solve_steady_state

grid_laplacian, solve_steady_state = _load()
""" % REPO_DIR


def _run_driver(body, timeout=300):
    """Run ``_LOADER + body`` as a python subprocess in REPO_DIR.

    ``body`` is expected to ``print(json.dumps(...))`` its result on the final
    line. Returns the parsed JSON object. Raises AssertionError with captured
    output on failure.
    """
    script = _LOADER + "\n" + textwrap.dedent(body)
    proc = subprocess.run(
        ["python", "-c", script],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert proc.returncode == 0, (
        "driver subprocess failed (rc=%d)\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
        % (proc.returncode, proc.stdout, proc.stderr)
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, "driver produced no stdout\nSTDERR:\n%s" % proc.stderr
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise AssertionError(
            "could not parse driver JSON output: %s\nLAST LINE: %r\nFULL STDOUT:\n%s"
            % (exc, lines[-1], proc.stdout)
        )


class TestScipyScientificComputing:
    """Validate the grid-graph Laplacian builder/solver."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """scipy/sparse/_gridlaplace.py must exist."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "sparse", "_gridlaplace.py")
        assert os.path.isfile(fpath), "_gridlaplace.py not found at %s" % fpath

    def test_test_file_exists(self):
        """scipy/sparse/tests/test_gridlaplace.py must exist."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "sparse", "tests", "test_gridlaplace.py"
        )
        assert os.path.isfile(fpath), "test_gridlaplace.py not found at %s" % fpath

    def test_meson_registers_module(self):
        """scipy/sparse/meson.build must list _gridlaplace.py for installation."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "sparse", "meson.build")
        assert os.path.isfile(fpath), "sparse meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "_gridlaplace.py" in content, (
            "_gridlaplace.py was not added to scipy/sparse/meson.build "
            "install_sources"
        )

    def test_meson_registers_test(self):
        """scipy/sparse/tests/meson.build must list test_gridlaplace.py."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "sparse", "tests", "meson.build"
        )
        assert os.path.isfile(fpath), "tests meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "test_gridlaplace.py" in content, (
            "test_gridlaplace.py was not added to tests/meson.build "
            "install_sources"
        )

    def test_functions_importable_and_return_contract(self):
        """grid_laplacian returns a 2-D matrix; solve_steady_state returns the
        dict with exactly {'u','residual','nnz'}."""
        res = _run_driver(
            r"""
            import numpy as np
            L = grid_laplacian(3, 3)
            shape = list(L.shape)
            ndim = int(getattr(L, "ndim", 2))
            src = np.zeros(9); src[0] = 1.0; src[8] = -1.0
            out = solve_steady_state(3, 3, src, fixed={8: 0.0})
            keys = sorted(out.keys())
            print(json.dumps({"shape": shape, "ndim": ndim, "keys": keys}))
            """
        )
        assert res["shape"] == [9, 9], (
            "grid_laplacian(3,3) must be 9x9, got %r" % res["shape"]
        )
        assert res["keys"] == ["nnz", "residual", "u"], (
            "solve_steady_state must return exactly keys "
            "{'u','residual','nnz'}, got %r" % res["keys"]
        )

    # ------------------------------------------------------------------
    # L2 — dynamic execution / deep behavioural validation
    # ------------------------------------------------------------------

    def test_laplacian_is_sparse_type(self):
        """grid_laplacian must return a sparse matrix/array, not a dense one."""
        res = _run_driver(
            r"""
            import numpy as np
            from scipy import sparse as sp
            L = grid_laplacian(4, 5)
            is_sparse = bool(sp.issparse(L))
            # CSR specifically requested by the contract.
            fmt = getattr(L, "format", None)
            print(json.dumps({"is_sparse": is_sparse, "format": fmt}))
            """
        )
        assert res["is_sparse"] is True, (
            "grid_laplacian must return a SciPy sparse type, not a dense array "
            "(a dense implementation fails the must-not-densify contract)"
        )
        assert res["format"] == "csr", (
            "grid_laplacian must be stored as CSR, got format=%r" % res["format"]
        )

    def test_symmetric_and_zero_row_sums(self):
        """Laplacian is symmetric and every row sums to zero."""
        res = _run_driver(
            r"""
            import numpy as np
            L = grid_laplacian(4, 6).toarray()
            asym = float(np.max(np.abs(L - L.T)))
            rowsums = np.asarray(L.sum(axis=1)).ravel()
            max_rowsum = float(np.max(np.abs(rowsums)))
            print(json.dumps({"asym": asym, "max_rowsum": max_rowsum}))
            """
        )
        assert res["asym"] < 1e-12, (
            "Laplacian must be symmetric, max |L - L.T| = %r" % res["asym"]
        )
        assert res["max_rowsum"] < 1e-12, (
            "every Laplacian row must sum to zero, max |rowsum| = %r"
            % res["max_rowsum"]
        )

    def test_node_degrees_corner_edge_interior(self):
        """Diagonal degrees: corners=2, edges=3, interior=4 on a 3x3 grid."""
        res = _run_driver(
            r"""
            import numpy as np
            nx, ny = 3, 3
            L = grid_laplacian(nx, ny).toarray()
            diag = np.diag(L).astype(float).tolist()
            # row-major flat indices for a 3x3 grid:
            # corners: 0,2,6,8 ; edges: 1,3,5,7 ; center: 4
            print(json.dumps({"diag": diag}))
            """
        )
        diag = res["diag"]
        corners = [0, 2, 6, 8]
        edges = [1, 3, 5, 7]
        center = 4
        for c in corners:
            assert abs(diag[c] - 2.0) < 1e-12, (
                "corner node %d must have degree 2, got %r" % (c, diag[c])
            )
        for e in edges:
            assert abs(diag[e] - 3.0) < 1e-12, (
                "edge node %d must have degree 3, got %r" % (e, diag[e])
            )
        assert abs(diag[center] - 4.0) < 1e-12, (
            "center node must have degree 4, got %r" % diag[center]
        )

    def test_adjacency_pattern_exact_no_spurious_nonzeros(self):
        """Off-diagonals are -1 exactly on the 4-neighbour grid adjacency and
        zero everywhere else (no spurious nonzeros / wrong stencil)."""
        res = _run_driver(
            r"""
            import numpy as np
            nx, ny = 4, 3   # 12 nodes, row-major node = r*nx + c
            L = grid_laplacian(nx, ny).toarray()
            N = nx * ny
            # Build the reference adjacency independently.
            wrong = []
            for a in range(N):
                ra, ca = divmod(a, nx)
                for b in range(N):
                    if a == b:
                        continue
                    rb, cb = divmod(b, nx)
                    adjacent = (abs(ra - rb) + abs(ca - cb)) == 1
                    val = float(L[a, b])
                    if adjacent:
                        if abs(val - (-1.0)) > 1e-12:
                            wrong.append([a, b, val, "expected -1"])
                    else:
                        if abs(val) > 1e-12:
                            wrong.append([a, b, val, "expected 0"])
            print(json.dumps({"wrong": wrong[:20], "n_wrong": len(wrong)}))
            """
        )
        assert res["n_wrong"] == 0, (
            "off-diagonal structure must be exactly the 5-point grid stencil "
            "(-1 for orthogonal neighbours, 0 otherwise); mismatches: %r"
            % res["wrong"]
        )

    def test_nnz_matches_analytic_edge_count(self):
        """'nnz' equals 2*#edges + #diagonal entries for the grid."""
        res = _run_driver(
            r"""
            import numpy as np
            results = {}
            for nx, ny in [(3, 3), (5, 4), (1, 6), (7, 1)]:
                N = nx * ny
                # number of undirected grid edges
                n_edges = (nx - 1) * ny + (ny - 1) * nx
                # diagonal entries: degree>0 nodes -> here every node has a
                # nonzero diagonal unless the grid is a single isolated node.
                expected = 2 * n_edges + (N if N > 1 else 0)
                # for a 1x1 grid the single node has degree 0; allow diag 0 or absent
                L = grid_laplacian(nx, ny)
                src = np.zeros(N)
                if N > 1:
                    src[0] = 1.0; src[-1] = -1.0
                    out = solve_steady_state(nx, ny, src, fixed={N - 1: 0.0})
                else:
                    out = solve_steady_state(nx, ny, src, fixed={0: 0.0})
                results["%dx%d" % (nx, ny)] = {
                    "nnz": int(out["nnz"]),
                    "expected": int(expected),
                    "Lnnz": int(L.nnz),
                }
            print(json.dumps(results))
            """
        )
        for key, d in res.items():
            assert d["nnz"] == d["expected"], (
                "nnz for %s must equal 2*edges+diagonal=%d, got %d"
                % (key, d["expected"], d["nnz"])
            )
            assert d["Lnnz"] == d["expected"], (
                "the stored Laplacian for %s must have %d nonzeros, got %d"
                % (key, d["expected"], d["Lnnz"])
            )

    def test_solution_satisfies_discrete_balance(self):
        """Single source/sink with the sink anchored to 0 -> residual ~ 0 and the
        discrete balance L u = source holds at non-anchored nodes."""
        res = _run_driver(
            r"""
            import numpy as np
            nx, ny = 5, 5
            N = nx * ny
            corner_a = 0
            corner_b = N - 1
            src = np.zeros(N)
            src[corner_a] = 1.0
            src[corner_b] = -1.0
            out = solve_steady_state(nx, ny, src, fixed={corner_b: 0.0})
            u = np.asarray(out["u"], dtype=float)
            # Independently recompute the residual at non-anchored nodes.
            L = grid_laplacian(nx, ny).toarray()
            r = L @ u - src
            free = [i for i in range(N) if i != corner_b]
            indep_resid = float(np.max(np.abs(r[free])))
            print(json.dumps({
                "residual": float(out["residual"]),
                "indep_resid": indep_resid,
                "len_u": int(u.size),
            }))
            """
        )
        assert res["len_u"] == 25, "u must be length nx*ny=25, got %r" % res["len_u"]
        assert res["residual"] >= 0.0, (
            "residual must be non-negative, got %r" % res["residual"]
        )
        assert res["residual"] < 1e-8, (
            "reported residual must be at round-off level, got %r" % res["residual"]
        )
        assert res["indep_resid"] < 1e-8, (
            "independently computed balance residual at free nodes must be ~0, "
            "got %r (a wrong-stencil or non-solving impl fails here)"
            % res["indep_resid"]
        )

    def test_anchored_nodes_exact(self):
        """fixed nodes must equal their prescribed values exactly in 'u'."""
        res = _run_driver(
            r"""
            import numpy as np
            nx, ny = 6, 4
            N = nx * ny
            src = np.zeros(N)
            src[2] = 1.5
            src[10] = -1.5
            fixed = {0: 3.25, 10: 0.0, N - 1: -2.0}
            out = solve_steady_state(nx, ny, src, fixed=fixed)
            u = np.asarray(out["u"], dtype=float)
            got = {str(k): float(u[k]) for k in fixed}
            print(json.dumps({"got": got, "want": {str(k): v for k, v in fixed.items()}}))
            """
        )
        for k, want in res["want"].items():
            got = res["got"][k]
            assert abs(got - want) < 1e-12, (
                "anchored node %s must equal its fixed value %r exactly, got %r "
                "(an impl that ignores `fixed` fails here)" % (k, want, got)
            )

    def test_anchored_value_changes_solution(self):
        """Changing an anchor's value shifts the solution -> `fixed` is honoured,
        not ignored."""
        res = _run_driver(
            r"""
            import numpy as np
            nx, ny = 4, 4
            N = nx * ny
            src = np.zeros(N)
            src[0] = 1.0
            src[N - 1] = -1.0
            u_zero = np.asarray(
                solve_steady_state(nx, ny, src, fixed={N - 1: 0.0})["u"], float)
            u_five = np.asarray(
                solve_steady_state(nx, ny, src, fixed={N - 1: 5.0})["u"], float)
            # Anchoring to 5 instead of 0 should shift the whole field by +5
            # (Laplacian is invariant to a constant offset).
            diff = u_five - u_zero
            max_dev = float(np.max(np.abs(diff - 5.0)))
            print(json.dumps({"max_dev": max_dev}))
            """
        )
        assert res["max_dev"] < 1e-6, (
            "changing the anchor value by +5 must shift the whole solution by +5 "
            "(constant-offset invariance); max deviation %r" % res["max_dev"]
        )

    def test_input_not_mutated(self):
        """solve_steady_state must not mutate the caller's source/fixed inputs."""
        res = _run_driver(
            r"""
            import numpy as np
            nx, ny = 5, 5
            N = nx * ny
            src = np.zeros(N)
            src[0] = 1.0
            src[N - 1] = -1.0
            src_before = src.copy()
            fixed = {N - 1: 0.0}
            fixed_before = dict(fixed)
            _ = solve_steady_state(nx, ny, src, fixed=fixed)
            print(json.dumps({
                "src_unchanged": bool(np.array_equal(src, src_before)),
                "fixed_unchanged": bool(fixed == fixed_before),
            }))
            """
        )
        assert res["src_unchanged"] is True, (
            "solve_steady_state must not mutate the source array"
        )
        assert res["fixed_unchanged"] is True, (
            "solve_steady_state must not mutate the fixed dict"
        )

    def test_invalid_inputs_raise_value_error(self):
        """Each invalid-input case must raise ValueError."""
        res = _run_driver(
            r"""
            import numpy as np

            def raises_value_error(fn):
                try:
                    fn()
                except ValueError:
                    return True
                except Exception:
                    return False
                return False

            results = {}
            # nx < 1
            results["nx_zero"] = raises_value_error(lambda: grid_laplacian(0, 3))
            results["ny_zero"] = raises_value_error(lambda: grid_laplacian(3, 0))
            results["nx_neg"] = raises_value_error(lambda: grid_laplacian(-2, 3))
            # source length mismatch
            results["src_len"] = raises_value_error(
                lambda: solve_steady_state(3, 3, np.zeros(8), fixed={8: 0.0}))
            # fixed index out of range
            results["fixed_oob_hi"] = raises_value_error(
                lambda: solve_steady_state(
                    3, 3, np.zeros(9), fixed={9: 0.0}))
            results["fixed_oob_neg"] = raises_value_error(
                lambda: solve_steady_state(
                    3, 3, np.zeros(9), fixed={-1: 0.0}))
            # singular system with no anchor and nonzero net source
            src = np.zeros(9); src[0] = 1.0   # net source != 0, no sink, no anchor
            results["singular_no_anchor"] = raises_value_error(
                lambda: solve_steady_state(3, 3, src, fixed=None))
            print(json.dumps(results))
            """
        )
        for case, ok in res.items():
            assert ok is True, (
                "invalid-input case %r did not raise ValueError" % case
            )

    def test_solution_not_via_dense_solve_on_large_grid(self):
        """A moderately large grid solves quickly via sparse machinery; a dense
        densify-and-solve would still produce correct numbers, so we only assert
        correctness + sparse storage here on a 20x20 grid."""
        res = _run_driver(
            r"""
            import numpy as np
            from scipy import sparse as sp
            nx, ny = 20, 20
            N = nx * ny
            src = np.zeros(N)
            src[0] = 1.0
            src[N - 1] = -1.0
            L = grid_laplacian(nx, ny)
            out = solve_steady_state(nx, ny, src, fixed={N - 1: 0.0})
            u = np.asarray(out["u"], dtype=float)
            r = (L @ u) - src
            free = [i for i in range(N) if i != (N - 1)]
            indep_resid = float(np.max(np.abs(r[free])))
            print(json.dumps({
                "is_sparse": bool(sp.issparse(L)),
                "indep_resid": indep_resid,
                "anchor": float(u[N - 1]),
            }))
            """,
            timeout=300,
        )
        assert res["is_sparse"] is True, "Laplacian must be sparse on a 20x20 grid"
        assert res["indep_resid"] < 1e-6, (
            "balance residual on a 20x20 grid must be ~0, got %r"
            % res["indep_resid"]
        )
        assert abs(res["anchor"]) < 1e-12, "anchored node must remain 0 exactly"

    def test_acceptance_pytest_command(self):
        """The agent's own test file passes via the native acceptance command."""
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scipy/sparse/tests/test_gridlaplace.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command failed\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
            % (proc.stdout[-4000:], proc.stderr[-2000:])
        )
