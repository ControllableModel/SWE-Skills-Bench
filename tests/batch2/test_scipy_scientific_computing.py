"""
Test for the 'scipy-scientific-computing' skill (variant ext2).

Verifies the agent added a robust nonlinear decay-curve fitter to
``scipy/optimize`` as a new private module ``scipy/optimize/_decayfit.py``
exposing ``fit_decay(t, y, *, p0=None, bounds=None)``.

The model is the fixed three-parameter exponential-decay-plus-offset
``f(t) = a * exp(-b * t) + c`` with ``b > 0``. ``fit_decay`` must return a dict
with exactly the keys ``"params"`` (length-3 float array ``(a, b, c)``),
``"residual_rms"`` (non-negative RMS of the residuals) and ``"r_squared"``
(coefficient of determination, <= 1.0).

These tests do not trust the agent's own test file or string-match the source.
Instead they exercise the real ``fit_decay`` function inside the built SciPy
(running each scenario in a fresh ``python`` subprocess with cwd=REPO_DIR,
exactly the environment the acceptance command uses) and deep-validate the
numeric / structural contract:

  * parameters are recovered from synthetic clean data within a tight
    tolerance and ``r_squared`` ~= 1.0;
  * ``residual_rms`` equals the recomputed RMS of ``y - f(t; params)``
    (self-consistency) and ``r_squared`` is consistent with ``1 - SS_res/SS_tot``;
  * a genuinely poor fit yields a much lower ``r_squared``;
  * automatic ``p0`` produces convergence without a user-supplied guess;
  * supplied ``bounds`` clamp every returned parameter into ``[lower, upper]``;
  * the caller's ``t`` / ``y`` arrays are not mutated;
  * every documented invalid-input case raises the documented exception
    (``ValueError`` for bad shapes/order/bounds).

A naive implementation (always returning ``p0``, fitting a straight line, or
ignoring ``bounds``) fails these tests.
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/scipy"

# Common preamble used by every driver subprocess. It loads ``fit_decay``
# preferring the official package import path required by the task, and falling
# back to loading the source file directly (its own ``from scipy.optimize ...``
# imports still resolve through the installed SciPy) so that the behavioural
# tests can run even if the editable rebuild has not re-registered the module
# under the package namespace yet.
_LOADER = r"""
import json, sys, importlib.util, os
import numpy as np

def _load_fit_decay():
    try:
        from scipy.optimize._decayfit import fit_decay as fd
        return fd
    except Exception:
        pass
    src = os.path.join(REPO_DIR, "scipy", "optimize", "_decayfit.py")
    spec = importlib.util.spec_from_file_location("_decayfit_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.fit_decay

REPO_DIR = %r
fit_decay = _load_fit_decay()

def model(t, a, b, c):
    return a * np.exp(-b * np.asarray(t, dtype=float)) + c
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
    """Validate the fit_decay exponential-decay curve fitter."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """scipy/optimize/_decayfit.py must exist."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "optimize", "_decayfit.py")
        assert os.path.isfile(fpath), "_decayfit.py not found at %s" % fpath

    def test_test_file_exists(self):
        """scipy/optimize/tests/test_decayfit.py must exist."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "optimize", "tests", "test_decayfit.py"
        )
        assert os.path.isfile(fpath), "test_decayfit.py not found at %s" % fpath

    def test_meson_registers_module(self):
        """scipy/optimize/meson.build must list _decayfit.py for installation."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "optimize", "meson.build")
        assert os.path.isfile(fpath), "optimize meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "_decayfit.py" in content, (
            "_decayfit.py was not added to scipy/optimize/meson.build install_sources"
        )

    def test_meson_registers_test(self):
        """scipy/optimize/tests/meson.build must list test_decayfit.py."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "optimize", "tests", "meson.build"
        )
        assert os.path.isfile(fpath), "tests meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "test_decayfit.py" in content, (
            "test_decayfit.py was not added to tests/meson.build install_sources"
        )

    def test_function_importable_and_keys(self):
        """fit_decay must be importable and return a dict with exactly three keys."""
        res = _run_driver(
            r"""
            import numpy as np
            t = np.linspace(0.0, 10.0, 60)
            y = model(t, 3.0, 0.5, 1.0)
            out = fit_decay(t, y)
            assert isinstance(out, dict), "return value must be a dict"
            params = np.asarray(out["params"], dtype=float)
            print(json.dumps({"keys": sorted(out.keys()), "nparams": int(params.size)}))
            """
        )
        assert res["keys"] == ["params", "r_squared", "residual_rms"], (
            "fit_decay must return exactly keys "
            "{'params','residual_rms','r_squared'}, got %r" % res["keys"]
        )
        assert res["nparams"] == 3, (
            "'params' must be a length-3 array (a, b, c), got length %r" % res["nparams"]
        )

    # ------------------------------------------------------------------
    # L2 — dynamic execution / deep behavioural validation
    # ------------------------------------------------------------------

    def test_recovers_known_params_clean_data(self):
        """Clean data from a=3,b=0.5,c=1 -> params ~= [3.0, 0.5, 1.0]."""
        res = _run_driver(
            r"""
            import numpy as np
            t = np.linspace(0.0, 10.0, 80)
            y = model(t, 3.0, 0.5, 1.0)
            out = fit_decay(t, y)
            params = [float(v) for v in np.asarray(out["params"], dtype=float)]
            print(json.dumps({"params": params, "r2": float(out["r_squared"])}))
            """
        )
        a, b, c = res["params"]
        assert abs(a - 3.0) < 1e-2, "a should be ~3.0, got %r" % a
        assert abs(b - 0.5) < 1e-2, "b should be ~0.5, got %r" % b
        assert abs(c - 1.0) < 1e-2, "c should be ~1.0, got %r" % c
        assert res["r2"] > 0.999, (
            "r_squared on clean data should be ~1.0, got %r "
            "(a straight-line or hardcoded fit fails here)" % res["r2"]
        )

    def test_recovers_params_with_small_noise(self):
        """Small deterministic noise still recovers params within tolerance."""
        res = _run_driver(
            r"""
            import numpy as np
            t = np.linspace(0.0, 10.0, 200)
            clean = model(t, 3.0, 0.5, 1.0)
            # deterministic, seeded noise — no global randomness leaks
            rng = np.random.default_rng(12345)
            noise = 0.01 * rng.standard_normal(t.size)
            y = clean + noise
            out = fit_decay(t, y)
            params = [float(v) for v in np.asarray(out["params"], dtype=float)]
            print(json.dumps({"params": params, "r2": float(out["r_squared"])}))
            """
        )
        a, b, c = res["params"]
        assert abs(a - 3.0) < 0.1, "a should be ~3.0 under small noise, got %r" % a
        assert abs(b - 0.5) < 0.05, "b should be ~0.5 under small noise, got %r" % b
        assert abs(c - 1.0) < 0.1, "c should be ~1.0 under small noise, got %r" % c
        assert res["r2"] > 0.99, (
            "r_squared with tiny noise should be near 1.0, got %r" % res["r2"]
        )

    def test_b_is_positive(self):
        """The recovered decay rate b must be positive for decaying data."""
        res = _run_driver(
            r"""
            import numpy as np
            t = np.linspace(0.0, 8.0, 100)
            y = model(t, 2.5, 0.8, 0.3)
            out = fit_decay(t, y)
            b = float(np.asarray(out["params"], dtype=float)[1])
            print(json.dumps({"b": b}))
            """
        )
        assert res["b"] > 0.0, "decay rate b must be > 0, got %r" % res["b"]
        assert abs(res["b"] - 0.8) < 0.05, "b should recover ~0.8, got %r" % res["b"]

    def test_residual_rms_self_consistent(self):
        """residual_rms must equal RMS of y - f(t; returned params)."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.default_rng(7)
            t = np.linspace(0.0, 10.0, 150)
            y = model(t, 3.0, 0.5, 1.0) + 0.05 * rng.standard_normal(150)
            out = fit_decay(t, y)
            a, b, c = [float(v) for v in np.asarray(out["params"], dtype=float)]
            pred = model(t, a, b, c)
            recomputed = float(np.sqrt(np.mean((y - pred) ** 2)))
            reported = float(out["residual_rms"])
            print(json.dumps({"reported": reported, "recomputed": recomputed}))
            """
        )
        reported, recomputed = res["reported"], res["recomputed"]
        assert reported >= 0.0, "residual_rms must be non-negative, got %r" % reported
        assert abs(reported - recomputed) < 1e-6, (
            "residual_rms (%r) must equal RMS of actual residuals (%r); "
            "a stub that hardcodes 0.0 fails this" % (reported, recomputed)
        )

    def test_r_squared_consistent_with_definition(self):
        """r_squared must match 1 - SS_res/SS_tot for the returned params."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.default_rng(99)
            t = np.linspace(0.0, 10.0, 120)
            y = model(t, 3.0, 0.5, 1.0) + 0.08 * rng.standard_normal(120)
            out = fit_decay(t, y)
            a, b, c = [float(v) for v in np.asarray(out["params"], dtype=float)]
            pred = model(t, a, b, c)
            ss_res = float(np.sum((y - pred) ** 2))
            ss_tot = float(np.sum((y - np.mean(y)) ** 2))
            r2_def = 1.0 - ss_res / ss_tot
            print(json.dumps({"reported": float(out["r_squared"]), "computed": r2_def}))
            """
        )
        assert abs(res["reported"] - res["computed"]) < 1e-6, (
            "r_squared (%r) must equal 1 - SS_res/SS_tot (%r)"
            % (res["reported"], res["computed"])
        )

    def test_poor_fit_has_low_r_squared(self):
        """Non-decay data (a noisy line) yields r_squared well below 1.0."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.default_rng(3)
            t = np.linspace(0.0, 10.0, 100)
            # data that does NOT follow a*exp(-b t)+c at all: heavy noise around 0
            y = rng.standard_normal(100)
            try:
                out = fit_decay(t, y)
                r2 = float(out["r_squared"])
                ok = True
            except Exception:
                # a non-convergence RuntimeError is also acceptable for junk data
                r2 = None
                ok = True
            print(json.dumps({"ok": ok, "r2": r2}))
            """
        )
        # Either it raised (acceptable) or it returned a low r_squared.
        if res["r2"] is not None:
            assert res["r2"] < 0.5, (
                "r_squared on pure-noise data should be far below 1.0, got %r "
                "(an impl that hardcodes r_squared=1 fails here)" % res["r2"]
            )

    def test_flat_signal(self):
        """A flat constant signal y=c -> residual_rms ~= 0, r_squared high."""
        res = _run_driver(
            r"""
            import numpy as np
            t = np.linspace(0.0, 10.0, 50)
            y = np.full_like(t, 2.0)
            out = fit_decay(t, y)
            a, b, c = [float(v) for v in np.asarray(out["params"], dtype=float)]
            pred = model(t, a, b, c)
            rms = float(np.sqrt(np.mean((y - pred) ** 2)))
            print(json.dumps({"rms": rms, "reported_rms": float(out["residual_rms"])}))
            """
        )
        assert res["reported_rms"] < 1e-3, (
            "flat constant signal should fit with ~0 residual_rms, got %r"
            % res["reported_rms"]
        )
        assert abs(res["rms"] - res["reported_rms"]) < 1e-6, (
            "reported residual_rms must match recomputed residuals on flat signal"
        )

    def test_auto_p0_converges(self):
        """Automatic p0 (no user guess) must converge for well-conditioned data."""
        res = _run_driver(
            r"""
            import numpy as np
            t = np.linspace(0.0, 12.0, 90)
            y = model(t, 5.0, 0.3, 2.0)
            # explicitly pass p0=None and let the impl form its own guess
            out = fit_decay(t, y, p0=None)
            params = [float(v) for v in np.asarray(out["params"], dtype=float)]
            print(json.dumps({"params": params, "r2": float(out["r_squared"])}))
            """
        )
        a, b, c = res["params"]
        assert abs(a - 5.0) < 0.1, "auto-p0 fit: a should be ~5.0, got %r" % a
        assert abs(b - 0.3) < 0.05, "auto-p0 fit: b should be ~0.3, got %r" % b
        assert abs(c - 2.0) < 0.1, "auto-p0 fit: c should be ~2.0, got %r" % c
        assert res["r2"] > 0.999, (
            "auto-p0 fit must converge to a near-perfect fit, r2=%r" % res["r2"]
        )

    def test_bounds_are_respected(self):
        """Supplied bounds must clamp every returned parameter into range."""
        res = _run_driver(
            r"""
            import numpy as np
            t = np.linspace(0.0, 10.0, 100)
            # true a=3 lies above the upper bound 2.0 for a -> fit must clamp.
            y = model(t, 3.0, 0.5, 1.0)
            lower = [0.0, 0.0, 0.0]
            upper = [2.0, 1.0, 5.0]
            out = fit_decay(t, y, bounds=(lower, upper))
            params = [float(v) for v in np.asarray(out["params"], dtype=float)]
            inside = all(lo - 1e-9 <= p <= hi + 1e-9
                         for p, lo, hi in zip(params, lower, upper))
            print(json.dumps({"params": params, "inside": bool(inside)}))
            """
        )
        assert res["inside"] is True, (
            "every returned parameter must lie within the supplied bounds; "
            "got params=%r (an impl that ignores bounds fails here)" % res["params"]
        )
        a = res["params"][0]
        assert a <= 2.0 + 1e-6, (
            "parameter a must be clamped to its upper bound 2.0, got %r "
            "(true a=3.0 exceeds the bound, so ignoring bounds is detectable)" % a
        )

    def test_input_not_mutated(self):
        """fit_decay must not mutate the caller's t or y arrays."""
        res = _run_driver(
            r"""
            import numpy as np
            t = np.linspace(0.0, 10.0, 60)
            y = model(t, 3.0, 0.5, 1.0)
            t_before = t.copy()
            y_before = y.copy()
            _ = fit_decay(t, y)
            print(json.dumps({
                "t_unchanged": bool(np.array_equal(t, t_before)),
                "y_unchanged": bool(np.array_equal(y, y_before)),
            }))
            """
        )
        assert res["t_unchanged"] is True, "fit_decay must not mutate t"
        assert res["y_unchanged"] is True, "fit_decay must not mutate y"

    def test_invalid_inputs_raise(self):
        """Each documented invalid-input case must raise ValueError."""
        res = _run_driver(
            r"""
            import numpy as np
            t = np.linspace(0.0, 10.0, 20)
            y = model(t, 3.0, 0.5, 1.0)

            def raises_value_error(fn):
                try:
                    fn()
                except ValueError:
                    return True
                except Exception:
                    return False
                return False

            results = {}
            # t and y different lengths
            results["len_mismatch"] = raises_value_error(
                lambda: fit_decay(t, y[:-1]))
            # fewer than 4 samples
            results["too_few"] = raises_value_error(
                lambda: fit_decay(t[:3], y[:3]))
            # t not strictly increasing (duplicate / non-monotone)
            t_bad = t.copy(); t_bad[5] = t_bad[4]
            results["not_increasing"] = raises_value_error(
                lambda: fit_decay(t_bad, y))
            t_dec = t[::-1].copy()
            results["decreasing"] = raises_value_error(
                lambda: fit_decay(t_dec, y))
            # bounds not a pair of length-3 vectors
            results["bounds_badlen"] = raises_value_error(
                lambda: fit_decay(t, y, bounds=([0, 0], [1, 1])))
            # bounds with lower > upper
            results["bounds_order"] = raises_value_error(
                lambda: fit_decay(t, y, bounds=([5, 0, 0], [1, 1, 1])))
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
             "scipy/optimize/tests/test_decayfit.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=900,
        )
        assert proc.returncode == 0, (
            "acceptance command failed\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
            % (proc.stdout[-4000:], proc.stderr[-2000:])
        )
