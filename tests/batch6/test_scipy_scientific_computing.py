"""
Test for the 'scipy-scientific-computing' skill (variant ext6).

Verifies the agent added a damped-oscillator ODE simulator to
``scipy/integrate`` as a new private module ``scipy/integrate/_oscillator.py``
exposing::

    simulate_oscillator(omega, zeta, y0, t_span, *, n_eval=200, forcing=None)

modelling ``x'' + 2*zeta*omega*x' + omega**2 * x = forcing(t)`` as a
first-order system, and returning a dict with keys ``"t"``, ``"x"``, ``"v"``,
``"energy"``.

Verification strategy
---------------------
The tests do NOT trust the agent's own test file and do NOT string-match the
source. Instead each scenario exercises the real ``simulate_oscillator``
function inside the built SciPy (running in a fresh ``python`` subprocess with
cwd=REPO_DIR, exactly the environment the acceptance command uses) and
deep-validates the numeric / structural contract:

  * return dict has EXACTLY the four keys, each a 1-D float array of length
    ``n_eval``; ``"t"`` is ascending and spans ``t_span`` (endpoints included);
  * undamped unforced motion matches the analytic
    ``x0*cos(omega t) + (v0/omega)*sin(omega t)`` to tight tolerance and
    conserves the reported mechanical energy ``0.5*v**2 + 0.5*omega**2*x**2``;
  * underdamped motion (0<zeta<1) decays in amplitude and the reported energy
    is monotonically non-increasing;
  * overdamped motion from rest displaced approaches 0 with NO sign change
    (no overshoot through zero);
  * a forcing callable changes the steady-state response (driven case differs
    from the unforced case and matches the analytic forced steady state);
  * the caller's ``y0`` is not mutated;
  * every invalid-input case raises ``ValueError``.

A naive implementation (e.g. emitting a fixed cosine regardless of damping, or
a one-step Euler scheme that leaks energy in the conservative case, or one that
ignores ``forcing``) fails these tests. Finally the agent's own test file is
driven via the native acceptance command::

    python -m pytest scipy/integrate/tests/test_oscillator.py -v
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/scipy"

# Common preamble used by every driver subprocess. It loads
# ``simulate_oscillator`` preferring the official package import path required
# by the task, and falling back to loading the source file directly (its own
# ``from scipy.integrate ...`` imports still resolve through the installed
# SciPy) so the behavioural tests can run even if an editable rebuild has not
# re-registered the module under the package namespace yet.
_LOADER = r"""
import json, sys, importlib.util, os
import numpy as np

REPO_DIR = %r

def _load_simulate_oscillator():
    try:
        from scipy.integrate._oscillator import simulate_oscillator as so
        return so
    except Exception:
        pass
    src = os.path.join(REPO_DIR, "scipy", "integrate", "_oscillator.py")
    spec = importlib.util.spec_from_file_location("_oscillator_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.simulate_oscillator

simulate_oscillator = _load_simulate_oscillator()
""" % REPO_DIR


def _run_driver(body, timeout=300):
    """Run ``_LOADER + body`` as a python subprocess in REPO_DIR.

    ``body`` must ``print(json.dumps(...))`` its result on the final line.
    Returns the parsed JSON object. Raises AssertionError with captured output
    on failure.
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
    """Validate the simulate_oscillator damped-oscillator simulator."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """scipy/integrate/_oscillator.py must exist."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "integrate", "_oscillator.py")
        assert os.path.isfile(fpath), "_oscillator.py not found at %s" % fpath

    def test_test_file_exists(self):
        """scipy/integrate/tests/test_oscillator.py must exist."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "integrate", "tests", "test_oscillator.py"
        )
        assert os.path.isfile(fpath), "test_oscillator.py not found at %s" % fpath

    def test_meson_registers_module(self):
        """scipy/integrate/meson.build must list _oscillator.py for installation."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "integrate", "meson.build")
        assert os.path.isfile(fpath), "integrate meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "_oscillator.py" in content, (
            "_oscillator.py was not added to scipy/integrate/meson.build "
            "install_sources"
        )

    def test_meson_registers_test(self):
        """scipy/integrate/tests/meson.build must list test_oscillator.py."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "integrate", "tests", "meson.build"
        )
        assert os.path.isfile(fpath), "tests meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "test_oscillator.py" in content, (
            "test_oscillator.py was not added to tests/meson.build install_sources"
        )

    def test_return_keys_and_shapes(self):
        """Return value is a dict with exactly t/x/v/energy, each 1-D len n_eval."""
        res = _run_driver(
            r"""
            import numpy as np
            n_eval = 137
            out = simulate_oscillator(2.0, 0.0, (1.0, 0.0), (0.0, 3.0),
                                      n_eval=n_eval)
            assert isinstance(out, dict), "return value must be a dict"
            info = {"keys": sorted(out.keys())}
            shapes = {}
            ndims = {}
            for k in ("t", "x", "v", "energy"):
                a = np.asarray(out[k], dtype=float)
                shapes[k] = int(a.size)
                ndims[k] = int(a.ndim)
            info["shapes"] = shapes
            info["ndims"] = ndims
            info["n_eval"] = n_eval
            print(json.dumps(info))
            """
        )
        assert res["keys"] == ["energy", "t", "v", "x"], (
            "simulate_oscillator must return exactly keys "
            "{'t','x','v','energy'}, got %r" % res["keys"]
        )
        for k in ("t", "x", "v", "energy"):
            assert res["ndims"][k] == 1, "'%s' must be 1-D, got ndim=%r" % (
                k, res["ndims"][k])
            assert res["shapes"][k] == res["n_eval"], (
                "'%s' must have length n_eval=%r, got %r"
                % (k, res["n_eval"], res["shapes"][k])
            )

    # ------------------------------------------------------------------
    # L2 — dynamic execution / deep behavioural validation
    # ------------------------------------------------------------------

    def test_time_grid_spans_and_ascending(self):
        """'t' is ascending, equally spaced, and spans t_span endpoints."""
        res = _run_driver(
            r"""
            import numpy as np
            t0, t1 = -1.5, 4.0
            n_eval = 200
            out = simulate_oscillator(1.3, 0.05, (0.2, -0.4), (t0, t1),
                                      n_eval=n_eval)
            t = np.asarray(out["t"], dtype=float)
            diffs = np.diff(t)
            print(json.dumps({
                "t_first": float(t[0]),
                "t_last": float(t[-1]),
                "monotone": bool(np.all(diffs > 0)),
                "uniform": bool(np.allclose(diffs, diffs[0], rtol=1e-6, atol=1e-9)),
                "t0": t0, "t1": t1,
            }))
            """
        )
        assert res["monotone"] is True, "'t' must be strictly ascending"
        assert res["uniform"] is True, "'t' must be equally spaced"
        assert abs(res["t_first"] - res["t0"]) < 1e-9, (
            "'t' must start at t0=%r, got %r" % (res["t0"], res["t_first"]))
        assert abs(res["t_last"] - res["t1"]) < 1e-9, (
            "'t' must end at t1=%r, got %r" % (res["t1"], res["t_last"]))

    def test_undamped_matches_analytic_cosine(self):
        """zeta=0, y0=(1,0), omega=2 -> x(t) ~= cos(2 t) to tight tolerance."""
        res = _run_driver(
            r"""
            import numpy as np
            omega = 2.0
            out = simulate_oscillator(omega, 0.0, (1.0, 0.0), (0.0, 4.0),
                                      n_eval=300)
            t = np.asarray(out["t"], dtype=float)
            x = np.asarray(out["x"], dtype=float)
            v = np.asarray(out["v"], dtype=float)
            x_exact = np.cos(omega * t)              # x0*cos + (v0/omega)*sin
            v_exact = -omega * np.sin(omega * t)
            print(json.dumps({
                "max_x_err": float(np.max(np.abs(x - x_exact))),
                "max_v_err": float(np.max(np.abs(v - v_exact))),
            }))
            """
        )
        assert res["max_x_err"] < 1e-4, (
            "undamped x(t) must match analytic cos(2 t); max abs err %r "
            "(an Euler scheme or hardcoded curve fails)" % res["max_x_err"]
        )
        assert res["max_v_err"] < 1e-3, (
            "undamped v(t) must match analytic -2 sin(2 t); max abs err %r"
            % res["max_v_err"]
        )

    def test_undamped_general_initial_velocity(self):
        """zeta=0, nonzero v0 -> x ~= x0 cos + (v0/omega) sin (not just cosine)."""
        res = _run_driver(
            r"""
            import numpy as np
            omega = 1.7
            x0, v0 = 0.5, 1.3
            out = simulate_oscillator(omega, 0.0, (x0, v0), (0.0, 5.0),
                                      n_eval=400)
            t = np.asarray(out["t"], dtype=float)
            x = np.asarray(out["x"], dtype=float)
            x_exact = x0*np.cos(omega*t) + (v0/omega)*np.sin(omega*t)
            x_cos_only = x0*np.cos(omega*t)   # what a "fixed cosine" impl gives
            print(json.dumps({
                "max_err": float(np.max(np.abs(x - x_exact))),
                "cos_only_err": float(np.max(np.abs(x - x_cos_only))),
            }))
            """
        )
        assert res["max_err"] < 1e-4, (
            "undamped x(t) must include the sine term from v0; max err %r"
            % res["max_err"]
        )
        # A naive cosine-only implementation would be far off here.
        assert res["cos_only_err"] > 0.1, (
            "sanity: with v0!=0 the solution must differ from a pure cosine "
            "(distance %r) — guards against a hardcoded-cosine stub passing"
            % res["cos_only_err"]
        )

    def test_undamped_energy_conserved(self):
        """zeta=0 -> reported 'energy' is constant across 't'."""
        res = _run_driver(
            r"""
            import numpy as np
            omega = 2.0
            out = simulate_oscillator(omega, 0.0, (1.0, 0.0), (0.0, 6.0),
                                      n_eval=500)
            x = np.asarray(out["x"], dtype=float)
            v = np.asarray(out["v"], dtype=float)
            e = np.asarray(out["energy"], dtype=float)
            e_def = 0.5*v**2 + 0.5*omega**2*x**2     # contract definition
            e0 = 0.5*(1.0)*omega**2                   # initial energy
            print(json.dumps({
                "spread": float(np.max(e) - np.min(e)),
                "e0": float(e0),
                "max_def_err": float(np.max(np.abs(e - e_def))),
            }))
            """
        )
        # 'energy' must equal the contract definition 0.5 v^2 + 0.5 omega^2 x^2.
        assert res["max_def_err"] < 1e-6, (
            "'energy' must equal 0.5*v**2 + 0.5*omega**2*x**2; max dev %r"
            % res["max_def_err"]
        )
        # Conservative case: energy must be (numerically) constant.
        assert res["spread"] < 1e-3 * res["e0"], (
            "undamped energy must be conserved; spread %r vs E0 %r "
            "(an Euler integrator that leaks energy fails)"
            % (res["spread"], res["e0"])
        )

    def test_underdamped_amplitude_decays(self):
        """0<zeta<1 -> oscillation amplitude decays over time."""
        res = _run_driver(
            r"""
            import numpy as np
            out = simulate_oscillator(1.0, 0.1, (1.0, 0.0), (0.0, 30.0),
                                      n_eval=600)
            t = np.asarray(out["t"], dtype=float)
            x = np.asarray(out["x"], dtype=float)
            n = x.size
            early = float(np.max(np.abs(x[: n//4])))
            late = float(np.max(np.abs(x[3*n//4 :])))
            print(json.dumps({"early": early, "late": late}))
            """
        )
        assert res["late"] < 0.5 * res["early"], (
            "underdamped amplitude must decay: early peak %r, late peak %r "
            "(a fixed cosine that never decays fails)"
            % (res["early"], res["late"])
        )

    def test_underdamped_energy_non_increasing(self):
        """0<zeta<1 -> reported 'energy' is monotonically non-increasing."""
        res = _run_driver(
            r"""
            import numpy as np
            out = simulate_oscillator(1.0, 0.1, (1.0, 0.0), (0.0, 30.0),
                                      n_eval=600)
            e = np.asarray(out["energy"], dtype=float)
            de = np.diff(e)
            tol = 1e-6 * float(max(abs(e[0]), 1.0))
            print(json.dumps({
                "max_increase": float(np.max(de)),
                "tol": tol,
                "e_first": float(e[0]),
                "e_last": float(e[-1]),
            }))
            """
        )
        assert res["max_increase"] <= res["tol"], (
            "underdamped energy must be non-increasing; largest step-up %r "
            "exceeds tolerance %r" % (res["max_increase"], res["tol"])
        )
        assert res["e_last"] < res["e_first"], (
            "underdamped energy must actually decay overall; first %r last %r"
            % (res["e_first"], res["e_last"])
        )

    def test_overdamped_no_overshoot(self):
        """zeta>1 from rest displaced -> x stays one-signed and tends to 0."""
        res = _run_driver(
            r"""
            import numpy as np
            out = simulate_oscillator(1.0, 2.0, (1.0, 0.0), (0.0, 20.0),
                                      n_eval=500)
            t = np.asarray(out["t"], dtype=float)
            x = np.asarray(out["x"], dtype=float)
            min_x = float(np.min(x))
            print(json.dumps({
                "min_x": min_x,
                "x0": float(x[0]),
                "x_end": float(x[-1]),
            }))
            """
        )
        # started at x0=+1; overdamped -> never crosses below ~0 (no overshoot).
        assert res["min_x"] > -1e-3, (
            "overdamped trajectory must not overshoot through zero; min(x)=%r "
            "(an underdamped/hardcoded oscillation fails)" % res["min_x"]
        )
        assert abs(res["x_end"]) < 0.2 * abs(res["x0"]), (
            "overdamped trajectory must decay toward 0; x_end=%r vs x0=%r"
            % (res["x_end"], res["x0"])
        )

    def test_forcing_changes_steady_state(self):
        """A forcing callable changes the response vs the unforced case."""
        res = _run_driver(
            r"""
            import numpy as np
            omega, zeta = 2.0, 0.3
            drive = 3.0
            # constant forcing f(t)=drive: steady state x_ss = drive/omega**2
            forced = simulate_oscillator(omega, zeta, (0.0, 0.0), (0.0, 40.0),
                                         n_eval=800,
                                         forcing=lambda tt: drive)
            unforced = simulate_oscillator(omega, zeta, (0.0, 0.0), (0.0, 40.0),
                                           n_eval=800, forcing=None)
            xf = np.asarray(forced["x"], dtype=float)
            xu = np.asarray(unforced["x"], dtype=float)
            x_ss = drive / omega**2
            tail = xf[-50:]
            print(json.dumps({
                "forced_tail_mean": float(np.mean(tail)),
                "x_ss": float(x_ss),
                "unforced_max_abs": float(np.max(np.abs(xu))),
                "diff_max": float(np.max(np.abs(xf - xu))),
            }))
            """
        )
        # Unforced from rest at origin stays ~0.
        assert res["unforced_max_abs"] < 1e-6, (
            "unforced response from y0=(0,0) must stay at the origin, got %r"
            % res["unforced_max_abs"]
        )
        # Forced steady state must approach drive/omega^2 (=0.75 here).
        assert abs(res["forced_tail_mean"] - res["x_ss"]) < 0.05, (
            "constant forcing must drive x toward drive/omega**2=%r; tail mean %r "
            "(an impl that ignores 'forcing' fails)"
            % (res["x_ss"], res["forced_tail_mean"])
        )
        assert res["diff_max"] > 0.1, (
            "forced and unforced responses must differ materially; max diff %r"
            % res["diff_max"]
        )

    def test_y0_not_mutated(self):
        """simulate_oscillator must not mutate the caller's y0."""
        res = _run_driver(
            r"""
            import numpy as np
            y0 = np.array([1.0, -2.0])
            before = y0.copy()
            _ = simulate_oscillator(1.5, 0.2, y0, (0.0, 5.0), n_eval=100)
            unchanged = bool(np.array_equal(y0, before))
            print(json.dumps({"unchanged": unchanged,
                              "y0": [float(v) for v in y0]}))
            """
        )
        assert res["unchanged"] is True, (
            "simulate_oscillator must not mutate its y0 argument; y0 became %r"
            % res["y0"]
        )

    def test_n_eval_endpoints_included(self):
        """n_eval output times include both endpoints; small n_eval still valid."""
        res = _run_driver(
            r"""
            import numpy as np
            out = simulate_oscillator(1.0, 0.0, (1.0, 0.0), (0.0, 1.0), n_eval=2)
            t = np.asarray(out["t"], dtype=float)
            x = np.asarray(out["x"], dtype=float)
            print(json.dumps({
                "n": int(t.size),
                "t0": float(t[0]), "t1": float(t[-1]),
                "x0": float(x[0]),
            }))
            """
        )
        assert res["n"] == 2, "n_eval=2 must yield 2 output points, got %r" % res["n"]
        assert abs(res["t0"] - 0.0) < 1e-12 and abs(res["t1"] - 1.0) < 1e-12, (
            "endpoints must be included for n_eval=2, got t0=%r t1=%r"
            % (res["t0"], res["t1"])
        )
        assert abs(res["x0"] - 1.0) < 1e-9, (
            "x at t0 must equal x0 from y0, got %r" % res["x0"]
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
            # omega <= 0
            results["omega_zero"] = raises_value_error(
                lambda: simulate_oscillator(0.0, 0.1, (1.0, 0.0), (0.0, 1.0)))
            results["omega_neg"] = raises_value_error(
                lambda: simulate_oscillator(-1.0, 0.1, (1.0, 0.0), (0.0, 1.0)))
            # zeta < 0
            results["zeta_neg"] = raises_value_error(
                lambda: simulate_oscillator(1.0, -0.1, (1.0, 0.0), (0.0, 1.0)))
            # y0 not a length-2 pair
            results["y0_len1"] = raises_value_error(
                lambda: simulate_oscillator(1.0, 0.1, (1.0,), (0.0, 1.0)))
            results["y0_len3"] = raises_value_error(
                lambda: simulate_oscillator(1.0, 0.1, (1.0, 0.0, 0.0), (0.0, 1.0)))
            # y0 non-finite
            results["y0_nan"] = raises_value_error(
                lambda: simulate_oscillator(1.0, 0.1, (np.nan, 0.0), (0.0, 1.0)))
            results["y0_inf"] = raises_value_error(
                lambda: simulate_oscillator(1.0, 0.1, (1.0, np.inf), (0.0, 1.0)))
            # t_span not t0 < t1
            results["tspan_eq"] = raises_value_error(
                lambda: simulate_oscillator(1.0, 0.1, (1.0, 0.0), (1.0, 1.0)))
            results["tspan_rev"] = raises_value_error(
                lambda: simulate_oscillator(1.0, 0.1, (1.0, 0.0), (2.0, 1.0)))
            # n_eval < 2
            results["neval_1"] = raises_value_error(
                lambda: simulate_oscillator(1.0, 0.1, (1.0, 0.0), (0.0, 1.0),
                                            n_eval=1))
            results["neval_0"] = raises_value_error(
                lambda: simulate_oscillator(1.0, 0.1, (1.0, 0.0), (0.0, 1.0),
                                            n_eval=0))
            print(json.dumps(results))
            """
        )
        for case, ok in res.items():
            assert ok is True, (
                "invalid-input case %r did not raise ValueError" % case
            )

    def test_acceptance_pytest_command(self):
        """The agent's own test file passes via the native acceptance command."""
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scipy/integrate/tests/test_oscillator.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command failed\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
            % (proc.stdout[-4000:], proc.stderr[-2000:])
        )
