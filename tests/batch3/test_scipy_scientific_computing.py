"""
Test for the 'scipy-scientific-computing' skill (variant: ext3).

Verifies the agent added a tridiagonal boundary-value-problem solver to
``scipy/linalg`` as a new private module ``scipy/linalg/_tridiag_bvp.py``
exposing::

    solve_poisson_1d(rhs, *, domain=(0.0, 1.0), bc=(0.0, 0.0))

which solves the 1-D Poisson equation ``-u'' = g`` on ``[x0, x1]`` with
Dirichlet boundary conditions using the standard symmetric tridiagonal
3-point finite-difference Laplacian, and returns a dict with keys
``"x"`` (grid, length N+2), ``"u"`` (solution, length N+2) and
``"residual"`` (max |-u'' - g| at interior nodes).

The tests do NOT trust the agent's own test file or string-match the source.
They exercise the real ``solve_poisson_1d`` function inside the built SciPy
(each scenario in a fresh ``python`` subprocess with cwd=REPO_DIR, exactly the
environment the acceptance command uses) and deep-validate the numeric /
structural contract:

  * the sinusoidal problem ``-u'' = pi^2 sin(pi x)`` converges to ``sin(pi x)``
    and the error shrinks as N grows (a naive linear interpolant fails);
  * the harmonic problem ``-u'' = 0`` with ``bc=(1,3)`` reproduces the straight
    line to round-off, and ``residual`` is ~0;
  * the parabola problem ``-u'' = 2`` matches ``x(1-x)`` to round-off;
  * boundary nodes equal the prescribed values EXACTLY;
  * grid ``x`` is ascending, uniform and length N+2;
  * ``rhs`` as an array and as a callable give identical results;
  * the discrete ``residual`` is at the round-off level for solved systems;
  * the caller's input array is not mutated;
  * every invalid-input case raises ``ValueError``.

A naive implementation (linear interpolation between the boundary values, an
implementation ignoring ``rhs``, or one returning a constant/hardcoded array)
fails these tests.

Acceptance command driven by L2:
    python -m pytest scipy/linalg/tests/test_tridiag_bvp.py -v
"""

import json
import os
import subprocess
import textwrap


REPO_DIR = "/workspace/scipy"

# Common preamble used by every driver subprocess. It loads ``solve_poisson_1d``
# preferring the official package import path required by the task, and falling
# back to loading the source file directly (its own ``from scipy ...`` imports
# still resolve through the installed SciPy) so the behavioural tests can run
# even if the editable rebuild has not re-registered the module under the
# package namespace yet.
_LOADER = r"""
import json, sys, importlib.util, os
import numpy as np

REPO_DIR = %r

def _load_solver():
    try:
        from scipy.linalg._tridiag_bvp import solve_poisson_1d as fn
        return fn
    except Exception:
        pass
    src = os.path.join(REPO_DIR, "scipy", "linalg", "_tridiag_bvp.py")
    spec = importlib.util.spec_from_file_location("_tridiag_bvp_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.solve_poisson_1d

solve_poisson_1d = _load_solver()
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
    """Validate the solve_poisson_1d tridiagonal BVP solver."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """scipy/linalg/_tridiag_bvp.py must exist."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "linalg", "_tridiag_bvp.py")
        assert os.path.isfile(fpath), "_tridiag_bvp.py not found at %s" % fpath

    def test_test_file_exists(self):
        """scipy/linalg/tests/test_tridiag_bvp.py must exist."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "linalg", "tests", "test_tridiag_bvp.py"
        )
        assert os.path.isfile(fpath), "test_tridiag_bvp.py not found at %s" % fpath

    def test_meson_registers_module(self):
        """scipy/linalg/meson.build must list _tridiag_bvp.py for installation."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "linalg", "meson.build")
        assert os.path.isfile(fpath), "linalg meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "_tridiag_bvp.py" in content, (
            "_tridiag_bvp.py was not added to scipy/linalg/meson.build install_sources"
        )

    def test_meson_registers_test(self):
        """scipy/linalg/tests/meson.build must list test_tridiag_bvp.py."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "linalg", "tests", "meson.build"
        )
        assert os.path.isfile(fpath), "tests meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "test_tridiag_bvp.py" in content, (
            "test_tridiag_bvp.py was not added to tests/meson.build install_sources"
        )

    def test_function_importable_and_return_contract(self):
        """solve_poisson_1d must return a dict with exactly keys x, u, residual."""
        res = _run_driver(
            r"""
            import numpy as np
            N = 20
            x0, x1 = 0.0, 1.0
            xi = np.linspace(x0, x1, N + 2)[1:-1]
            g = np.full(N, 2.0)
            out = solve_poisson_1d(g, domain=(x0, x1), bc=(0.0, 0.0))
            assert isinstance(out, dict), "return value must be a dict"
            keys = sorted(out.keys())
            x = np.asarray(out["x"], dtype=float)
            u = np.asarray(out["u"], dtype=float)
            print(json.dumps({
                "keys": keys,
                "len_x": int(x.size),
                "len_u": int(u.size),
                "N": N,
            }))
            """
        )
        assert res["keys"] == ["residual", "u", "x"], (
            "solve_poisson_1d must return exactly keys {'x','u','residual'}, got %r"
            % res["keys"]
        )
        assert res["len_x"] == res["N"] + 2, (
            "'x' must have length N+2=%d, got %d" % (res["N"] + 2, res["len_x"])
        )
        assert res["len_u"] == res["N"] + 2, (
            "'u' must have length N+2=%d, got %d" % (res["N"] + 2, res["len_u"])
        )

    def test_grid_is_ascending_and_uniform(self):
        """'x' must include both boundaries, be ascending and uniformly spaced."""
        res = _run_driver(
            r"""
            import numpy as np
            N = 25
            x0, x1 = -1.0, 2.0
            g = np.zeros(N)
            out = solve_poisson_1d(g, domain=(x0, x1), bc=(0.0, 0.0))
            x = np.asarray(out["x"], dtype=float)
            dx = np.diff(x)
            print(json.dumps({
                "first": float(x[0]),
                "last": float(x[-1]),
                "ascending": bool(np.all(dx > 0)),
                "spacing_spread": float(np.max(dx) - np.min(dx)),
                "expected_dx": float((x1 - x0) / (N + 1)),
                "mean_dx": float(np.mean(dx)),
            }))
            """
        )
        assert abs(res["first"] - (-1.0)) < 1e-12, "x[0] must equal x0, got %r" % res["first"]
        assert abs(res["last"] - 2.0) < 1e-12, "x[-1] must equal x1, got %r" % res["last"]
        assert res["ascending"] is True, "grid must be strictly ascending"
        assert res["spacing_spread"] < 1e-9, (
            "grid must be uniformly spaced, spacing spread was %r" % res["spacing_spread"]
        )
        assert abs(res["mean_dx"] - res["expected_dx"]) < 1e-9, (
            "uniform spacing must be (x1-x0)/(N+1); got mean dx %r vs expected %r"
            % (res["mean_dx"], res["expected_dx"])
        )

    # ------------------------------------------------------------------
    # L2 — dynamic execution / deep behavioural validation
    # ------------------------------------------------------------------

    def test_boundary_values_honored_exactly(self):
        """u[0] and u[-1] must equal the supplied boundary values exactly."""
        res = _run_driver(
            r"""
            import numpy as np
            N = 17
            x0, x1 = 0.0, 1.0
            xi = np.linspace(x0, x1, N + 2)[1:-1]
            g = np.pi**2 * np.sin(np.pi * xi)
            bc = (-0.7, 1.3)
            out = solve_poisson_1d(g, domain=(x0, x1), bc=bc)
            u = np.asarray(out["u"], dtype=float)
            print(json.dumps({
                "u0": float(u[0]),
                "uN": float(u[-1]),
                "bc": list(bc),
            }))
            """
        )
        assert res["u0"] == res["bc"][0], (
            "u[0] must equal bc[0]=%r exactly, got %r" % (res["bc"][0], res["u0"])
        )
        assert res["uN"] == res["bc"][1], (
            "u[-1] must equal bc[1]=%r exactly, got %r" % (res["bc"][1], res["uN"])
        )

    def test_linear_harmonic_recovered_to_roundoff(self):
        """-u''=0 with bc=(1,3) -> u is the straight line, exact to round-off."""
        res = _run_driver(
            r"""
            import numpy as np
            N = 31
            x0, x1 = 0.0, 1.0
            g = np.zeros(N)
            out = solve_poisson_1d(g, domain=(x0, x1), bc=(1.0, 3.0))
            x = np.asarray(out["x"], dtype=float)
            u = np.asarray(out["u"], dtype=float)
            exact = 1.0 + 2.0 * (x - x0) / (x1 - x0)   # line from 1 to 3
            max_err = float(np.max(np.abs(u - exact)))
            print(json.dumps({"max_err": max_err}))
            """
        )
        assert res["max_err"] < 1e-9, (
            "harmonic problem (-u''=0) must reproduce the straight line to "
            "round-off; max error was %r (an impl ignoring the discrete "
            "operator fails)" % res["max_err"]
        )

    def test_parabola_matches_analytic(self):
        """-u''=2 with bc=(0,0) on [0,1] -> u ~= x(1-x), exact to round-off."""
        res = _run_driver(
            r"""
            import numpy as np
            N = 41
            x0, x1 = 0.0, 1.0
            g = np.full(N, 2.0)
            out = solve_poisson_1d(g, domain=(x0, x1), bc=(0.0, 0.0))
            x = np.asarray(out["x"], dtype=float)
            u = np.asarray(out["u"], dtype=float)
            exact = x * (1.0 - x)
            max_err = float(np.max(np.abs(u - exact)))
            peak = float(np.max(u))
            print(json.dumps({"max_err": max_err, "peak": peak}))
            """
        )
        # The 3-point stencil is EXACT for quadratics, so error is round-off.
        assert res["max_err"] < 1e-8, (
            "parabola -u''=2 must match x(1-x) to round-off; max error %r "
            "(a linear-interpolation stub returns a flat 0 here and fails)"
            % res["max_err"]
        )
        # The analytic peak of x(1-x) on [0,1] is 0.25; a stub returning the
        # boundary line (all zeros) would give peak 0.0.
        assert abs(res["peak"] - 0.25) < 1e-6, (
            "interior solution must bow up to ~0.25; got peak %r" % res["peak"]
        )

    def test_sinusoid_converges_with_refinement(self):
        """-u''=pi^2 sin(pi x): error to sin(pi x) shrinks as N grows."""
        res = _run_driver(
            r"""
            import numpy as np
            x0, x1 = 0.0, 1.0
            def err_for(N):
                xi = np.linspace(x0, x1, N + 2)[1:-1]
                g = np.pi**2 * np.sin(np.pi * xi)
                out = solve_poisson_1d(g, domain=(x0, x1), bc=(0.0, 0.0))
                x = np.asarray(out["x"], dtype=float)
                u = np.asarray(out["u"], dtype=float)
                exact = np.sin(np.pi * x)
                return float(np.max(np.abs(u - exact)))
            e_coarse = err_for(10)
            e_fine = err_for(80)
            print(json.dumps({"coarse": e_coarse, "fine": e_fine}))
            """
        )
        # Second-order scheme: an 8x refinement should cut error ~64x.
        assert res["fine"] < res["coarse"], (
            "refining the grid must reduce the error (coarse=%r fine=%r); a "
            "stub that ignores N/rhs fails" % (res["coarse"], res["fine"])
        )
        assert res["fine"] < res["coarse"] / 10.0, (
            "expected ~2nd-order convergence (8x refine -> >>10x smaller error); "
            "coarse=%r fine=%r" % (res["coarse"], res["fine"])
        )
        assert res["fine"] < 1e-2, (
            "fine-grid solution must be close to sin(pi x); max error %r" % res["fine"]
        )

    def test_residual_is_roundoff_for_solved_system(self):
        """'residual' (max |-u'' - g|) must be at round-off for a solved system."""
        res = _run_driver(
            r"""
            import numpy as np
            N = 50
            x0, x1 = 0.0, 1.0
            xi = np.linspace(x0, x1, N + 2)[1:-1]
            g = np.pi**2 * np.sin(np.pi * xi)
            out = solve_poisson_1d(g, domain=(x0, x1), bc=(0.0, 0.0))
            r = float(out["residual"])
            print(json.dumps({"residual": r}))
            """
        )
        assert res["residual"] >= 0.0, (
            "residual must be non-negative, got %r" % res["residual"]
        )
        assert res["residual"] < 1e-8, (
            "the discrete residual of a properly solved tridiagonal system must "
            "be round-off (~0); got %r (a hardcoded/linear stub leaves a large "
            "residual)" % res["residual"]
        )

    def test_rhs_callable_matches_array(self):
        """rhs as a callable g(x) must give identical results to the sampled array."""
        res = _run_driver(
            r"""
            import numpy as np
            N = 33
            x0, x1 = 0.0, 1.0
            xi = np.linspace(x0, x1, N + 2)[1:-1]
            g_arr = np.pi**2 * np.sin(np.pi * xi)
            out_arr = solve_poisson_1d(g_arr, domain=(x0, x1), bc=(0.0, 0.0))
            out_cb = solve_poisson_1d(lambda x: np.pi**2 * np.sin(np.pi * x),
                                      domain=(x0, x1), bc=(0.0, 0.0))
            u_arr = np.asarray(out_arr["u"], dtype=float)
            u_cb = np.asarray(out_cb["u"], dtype=float)
            max_diff = float(np.max(np.abs(u_arr - u_cb)))
            print(json.dumps({
                "max_diff": max_diff,
                "len_cb": int(u_cb.size),
                "n_expected": N + 2,
            }))
            """
        )
        assert res["len_cb"] == res["n_expected"], (
            "callable rhs path must produce u of length N+2=%d, got %d"
            % (res["n_expected"], res["len_cb"])
        )
        assert res["max_diff"] < 1e-12, (
            "array-rhs and callable-rhs must give identical solutions; "
            "max diff was %r (an impl that ignores the callable fails)"
            % res["max_diff"]
        )

    def test_solution_is_rhs_dependent(self):
        """Different rhs must yield different interior solutions (not hardcoded)."""
        res = _run_driver(
            r"""
            import numpy as np
            N = 30
            x0, x1 = 0.0, 1.0
            out_zero = solve_poisson_1d(np.zeros(N), domain=(x0, x1), bc=(0.0, 0.0))
            out_two = solve_poisson_1d(np.full(N, 2.0), domain=(x0, x1), bc=(0.0, 0.0))
            u0 = np.asarray(out_zero["u"], dtype=float)
            u2 = np.asarray(out_two["u"], dtype=float)
            # With bc=(0,0): zero rhs -> all zeros; rhs=2 -> bowed parabola.
            print(json.dumps({
                "zero_peak": float(np.max(np.abs(u0))),
                "two_peak": float(np.max(np.abs(u2))),
            }))
            """
        )
        assert res["zero_peak"] < 1e-9, (
            "with rhs=0 and bc=(0,0) the solution must be ~0 everywhere; got "
            "peak %r" % res["zero_peak"]
        )
        assert res["two_peak"] > 0.2, (
            "with rhs=2 the interior must bow up (~0.25); got peak %r. A stub "
            "ignoring rhs would return the same (zero) field for both."
            % res["two_peak"]
        )

    def test_input_array_not_mutated(self):
        """solve_poisson_1d must not mutate the caller-supplied rhs array."""
        res = _run_driver(
            r"""
            import numpy as np
            N = 20
            x0, x1 = 0.0, 1.0
            xi = np.linspace(x0, x1, N + 2)[1:-1]
            g = np.pi**2 * np.sin(np.pi * xi)
            before = g.copy()
            _ = solve_poisson_1d(g, domain=(x0, x1), bc=(0.5, -0.5))
            unchanged = bool(np.array_equal(g, before))
            print(json.dumps({"unchanged": unchanged}))
            """
        )
        assert res["unchanged"] is True, (
            "solve_poisson_1d must not mutate its caller-supplied rhs array"
        )

    def test_nonzero_bc_with_source_superposition(self):
        """Combined nonzero bc + source: solution = parabola + boundary line."""
        res = _run_driver(
            r"""
            import numpy as np
            N = 45
            x0, x1 = 0.0, 1.0
            g = np.full(N, 2.0)            # -u'' = 2 -> particular x(1-x)
            bc = (1.0, 4.0)
            out = solve_poisson_1d(g, domain=(x0, x1), bc=bc)
            x = np.asarray(out["x"], dtype=float)
            u = np.asarray(out["u"], dtype=float)
            # exact: x(1-x) + line through bc
            line = bc[0] + (bc[1] - bc[0]) * (x - x0) / (x1 - x0)
            exact = x * (1.0 - x) + line
            max_err = float(np.max(np.abs(u - exact)))
            print(json.dumps({"max_err": max_err}))
            """
        )
        assert res["max_err"] < 1e-8, (
            "solver must correctly superpose source response and inhomogeneous "
            "boundary line; max error %r (a stub solving only one part fails)"
            % res["max_err"]
        )

    def test_nonunit_domain_scaling(self):
        """-u''=2 on [0,L] with bc=(0,0) -> u = x(L-x); spacing scales with L."""
        res = _run_driver(
            r"""
            import numpy as np
            N = 40
            x0, x1 = 0.0, 4.0
            g = np.full(N, 2.0)
            out = solve_poisson_1d(g, domain=(x0, x1), bc=(0.0, 0.0))
            x = np.asarray(out["x"], dtype=float)
            u = np.asarray(out["u"], dtype=float)
            exact = x * (x1 - x)
            max_err = float(np.max(np.abs(u - exact)))
            print(json.dumps({"max_err": max_err, "peak": float(np.max(u))}))
            """
        )
        # Quadratic exact for the stencil; checks the grid spacing (dx) entered
        # the operator (a solver that used dx=1 ignoring the domain would fail).
        assert res["max_err"] < 1e-7, (
            "solver must scale the discrete Laplacian by the true grid spacing "
            "on [0,4]; expected u=x(4-x) but max error was %r" % res["max_err"]
        )
        assert abs(res["peak"] - 4.0) < 1e-4, (
            "peak of x(4-x) on [0,4] is 4.0; got %r (wrong dx scaling fails this)"
            % res["peak"]
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

            good = np.full(10, 2.0)
            results = {}
            # rhs not 1-D
            results["rhs_2d"] = raises_value_error(
                lambda: solve_poisson_1d(np.ones((3, 3)), domain=(0.0, 1.0), bc=(0.0, 0.0)))
            # rhs has zero interior points
            results["rhs_empty"] = raises_value_error(
                lambda: solve_poisson_1d(np.array([]), domain=(0.0, 1.0), bc=(0.0, 0.0)))
            # domain not x0 < x1 (equal)
            results["domain_equal"] = raises_value_error(
                lambda: solve_poisson_1d(good, domain=(1.0, 1.0), bc=(0.0, 0.0)))
            # domain reversed
            results["domain_reversed"] = raises_value_error(
                lambda: solve_poisson_1d(good, domain=(1.0, 0.0), bc=(0.0, 0.0)))
            # bc wrong length
            results["bc_len"] = raises_value_error(
                lambda: solve_poisson_1d(good, domain=(0.0, 1.0), bc=(0.0,)))
            results["bc_len3"] = raises_value_error(
                lambda: solve_poisson_1d(good, domain=(0.0, 1.0), bc=(0.0, 1.0, 2.0)))
            # bc not finite
            results["bc_nan"] = raises_value_error(
                lambda: solve_poisson_1d(good, domain=(0.0, 1.0), bc=(0.0, float("nan"))))
            results["bc_inf"] = raises_value_error(
                lambda: solve_poisson_1d(good, domain=(0.0, 1.0), bc=(float("inf"), 0.0)))
            print(json.dumps(results))
            """
        )
        for case, ok in res.items():
            assert ok is True, (
                "invalid-input case %r did not raise ValueError" % case
            )

    def test_acceptance_pytest_command(self):
        """The agent's own test file passes via the acceptance command."""
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scipy/linalg/tests/test_tridiag_bvp.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command failed\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
            % (proc.stdout[-4000:], proc.stderr[-2000:])
        )
