"""
Test for the 'scipy-scientific-computing' skill (variant ext5).

Verifies the agent added a *monotone resampling interpolator* to
``scipy.interpolate`` as a new private module
``scipy/interpolate/_monoresample.py`` exposing::

    resample_monotone(x, y, x_new, *, extrapolate=False)

The function resamples a strictly-increasing calibration curve onto a new
abscissa, preserving monotonicity, and returns a dict with keys
``"y_new"`` (1-D float, non-decreasing for sorted queries), ``"in_range"``
(1-D bool), and ``"n_extrapolated"`` (int count of out-of-range queries).

The tests do not trust the agent's own test file and do not string-match the
source.  Instead they exercise the real ``resample_monotone`` function inside
the built SciPy (running each scenario in a fresh ``python`` subprocess with
cwd=REPO_DIR, the same environment the acceptance command uses) and
deep-validate the numeric / structural contract:

  * exact reproduction at the source nodes (interpolation, not smoothing);
  * a linear calibration ``y = 2x + 1`` is recovered to machine precision on a
    dense query, with all ``in_range`` True and ``n_extrapolated == 0``;
  * a sorted dense query on a non-decreasing curve yields a non-decreasing
    ``y_new`` with no overshoot beyond the bracketing samples;
  * ``in_range`` and ``n_extrapolated`` are correct for mixed in/out queries;
  * ``extrapolate=False`` raises on any out-of-range query, ``extrapolate=True``
    fills and counts them;
  * the caller's ``x``, ``y``, ``x_new`` arrays are not mutated;
  * every invalid-input case raises ``ValueError``.

A naive implementation -- nearest-neighbor lookup (fails exact-node /
linear-recovery / monotone checks), an unconstrained high-order interpolant
that overshoots (fails the no-overshoot / monotonicity checks), or one that
ignores the range check (fails the in_range / n_extrapolated / raising checks)
-- must fail these tests.  The final test drives the doc's native acceptance
command on the agent's own test suite.
"""

import json
import os
import subprocess
import textwrap


REPO_DIR = "/workspace/scipy"

# Common preamble used by every driver subprocess.  It loads
# ``resample_monotone`` preferring the official package import path required by
# the task, and falling back to loading the source file directly (its own
# ``from scipy ...`` imports still resolve through the installed SciPy) so the
# behavioural tests can run even if the editable rebuild has not re-registered
# the module under the package namespace yet.
_LOADER = r"""
import json, sys, importlib.util, os
import numpy as np

REPO_DIR = %r

def _load_resample_monotone():
    try:
        from scipy.interpolate._monoresample import resample_monotone as rm
        return rm
    except Exception:
        pass
    src = os.path.join(REPO_DIR, "scipy", "interpolate", "_monoresample.py")
    spec = importlib.util.spec_from_file_location("_monoresample_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.resample_monotone

resample_monotone = _load_resample_monotone()
""" % REPO_DIR


def _run_driver(body, timeout=300):
    """Run ``_LOADER + body`` as a python subprocess in REPO_DIR.

    ``body`` is expected to ``print(json.dumps(...))`` its result on the final
    line.  Returns the parsed JSON object.  Raises AssertionError with captured
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
    """Validate the resample_monotone monotone resampling interpolator."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 -- deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """scipy/interpolate/_monoresample.py must exist."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "interpolate", "_monoresample.py"
        )
        assert os.path.isfile(fpath), "_monoresample.py not found at %s" % fpath

    def test_test_file_exists(self):
        """scipy/interpolate/tests/test_monoresample.py must exist."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "interpolate", "tests", "test_monoresample.py"
        )
        assert os.path.isfile(fpath), "test_monoresample.py not found at %s" % fpath

    def test_meson_registers_module(self):
        """scipy/interpolate/meson.build must list _monoresample.py for install."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "interpolate", "meson.build"
        )
        assert os.path.isfile(fpath), "interpolate meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "_monoresample.py" in content, (
            "_monoresample.py was not added to scipy/interpolate/meson.build "
            "install_sources"
        )

    def test_meson_registers_test(self):
        """scipy/interpolate/tests/meson.build must list test_monoresample.py."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "interpolate", "tests", "meson.build"
        )
        assert os.path.isfile(fpath), "tests meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "test_monoresample.py" in content, (
            "test_monoresample.py was not added to tests/meson.build install_sources"
        )

    def test_function_importable_and_returns_three_keys(self):
        """resample_monotone must import and return a dict with the 3 keys."""
        res = _run_driver(
            r"""
            import numpy as np
            x = np.array([0.0, 1.0, 2.0, 3.0])
            y = np.array([0.0, 2.0, 4.0, 6.0])
            x_new = np.array([0.5, 1.5, 2.5])
            out = resample_monotone(x, y, x_new)
            assert isinstance(out, dict), "return value must be a dict"
            print(json.dumps(sorted(out.keys())))
            """
        )
        assert res == ["in_range", "n_extrapolated", "y_new"], (
            "resample_monotone must return exactly keys "
            "{'y_new','in_range','n_extrapolated'}, got %r" % res
        )

    # ------------------------------------------------------------------
    # L2 -- dynamic execution / deep behavioural validation
    # ------------------------------------------------------------------

    def test_exact_reproduction_at_source_nodes(self):
        """Querying the original x returns y exactly (interpolation, not smoothing)."""
        res = _run_driver(
            r"""
            import numpy as np
            x = np.array([0.0, 1.0, 2.5, 4.0, 7.0])
            y = np.array([1.0, 3.0, 8.0, 9.0, 20.0])
            out = resample_monotone(x, y, x)   # query the nodes themselves
            y_new = np.asarray(out["y_new"], dtype=float)
            max_err = float(np.max(np.abs(y_new - y)))
            print(json.dumps({"max_err": max_err,
                              "all_in": bool(np.all(np.asarray(out["in_range"]))),
                              "n_extrap": int(out["n_extrapolated"])}))
            """
        )
        assert res["max_err"] < 1e-9, (
            "resample_monotone must reproduce source samples exactly at the "
            "original nodes; max error was %r (a nearest-neighbor / smoothing "
            "impl fails here)" % res["max_err"]
        )
        assert res["all_in"] is True, "the nodes themselves must all be in_range"
        assert res["n_extrap"] == 0, "no node query is out of range"

    def test_linear_calibration_recovered(self):
        """y = 2x + 1 sampled coarsely, queried densely -> y_new ~= 2*x_new + 1."""
        res = _run_driver(
            r"""
            import numpy as np
            x = np.array([0.0, 2.0, 4.0, 6.0, 8.0, 10.0])
            y = 2.0 * x + 1.0
            x_new = np.linspace(0.0, 10.0, 51)
            out = resample_monotone(x, y, x_new)
            y_new = np.asarray(out["y_new"], dtype=float)
            expected = 2.0 * x_new + 1.0
            max_err = float(np.max(np.abs(y_new - expected)))
            print(json.dumps({"max_err": max_err,
                              "all_in": bool(np.all(np.asarray(out["in_range"]))),
                              "n_extrap": int(out["n_extrapolated"])}))
            """
        )
        assert res["max_err"] < 1e-9, (
            "a linear calibration y=2x+1 must be recovered exactly; max error "
            "was %r (a nearest-neighbor impl produces staircase error >> 0)"
            % res["max_err"]
        )
        assert res["all_in"] is True, (
            "all queries lie inside [x0, x-1]; in_range must be all True"
        )
        assert res["n_extrap"] == 0, "no in-range query may be counted as extrapolated"

    def test_y_new_non_decreasing_no_overshoot(self):
        """Sorted dense query on a non-decreasing curve -> y_new non-decreasing,
        with no overshoot below/above the bracketing samples."""
        res = _run_driver(
            r"""
            import numpy as np
            # strictly increasing x; non-decreasing y with a flat then steep region
            x = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
            y = np.array([0.0, 0.0, 0.1, 0.2, 5.0, 5.0])   # a "step"-like rise
            x_new = np.linspace(0.0, 5.0, 201)
            out = resample_monotone(x, y, x_new)
            y_new = np.asarray(out["y_new"], dtype=float)
            diffs = np.diff(y_new)
            min_diff = float(np.min(diffs))
            ymin = float(y_new.min())
            ymax = float(y_new.max())
            print(json.dumps({"min_diff": min_diff, "ymin": ymin, "ymax": ymax,
                              "lo": float(y.min()), "hi": float(y.max())}))
            """
        )
        # Non-decreasing: no negative step (small tolerance for fp noise).
        assert res["min_diff"] >= -1e-9, (
            "y_new must be non-decreasing for a sorted query on monotone data; "
            "found a decreasing step of %r (an unconstrained high-order "
            "interpolant that oscillates fails here)" % res["min_diff"]
        )
        # No overshoot beyond the global sample range.
        assert res["ymin"] >= res["lo"] - 1e-9, (
            "y_new undershoots below the data minimum (%r < %r): overshoot"
            % (res["ymin"], res["lo"])
        )
        assert res["ymax"] <= res["hi"] + 1e-9, (
            "y_new overshoots above the data maximum (%r > %r): overshoot"
            % (res["ymax"], res["hi"])
        )

    def test_midpoints_bracketed_by_neighbors(self):
        """Each interior query lies between its bracketing sample values
        (monotone bracketing, the core no-overshoot guarantee)."""
        res = _run_driver(
            r"""
            import numpy as np
            x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
            y = np.array([0.0, 1.0, 4.0, 9.0, 16.0])   # convex monotone (x**2)
            # query the midpoints of each interval
            mids = 0.5 * (x[:-1] + x[1:])
            out = resample_monotone(x, y, mids)
            y_new = np.asarray(out["y_new"], dtype=float)
            lo = np.minimum(y[:-1], y[1:])
            hi = np.maximum(y[:-1], y[1:])
            below = float(np.min(y_new - lo))   # >= 0 required
            above = float(np.max(y_new - hi))   # <= 0 required
            print(json.dumps({"below": below, "above": above,
                              "y_new": [float(v) for v in y_new],
                              "lo": [float(v) for v in lo],
                              "hi": [float(v) for v in hi]}))
            """
        )
        assert res["below"] >= -1e-9, (
            "an interior query fell below its bracketing samples "
            "(y_new=%r, lo=%r): overshoot" % (res["y_new"], res["lo"])
        )
        assert res["above"] <= 1e-9, (
            "an interior query rose above its bracketing samples "
            "(y_new=%r, hi=%r): overshoot" % (res["y_new"], res["hi"])
        )
        # Midpoints must be strictly inside the brackets, not pinned to a node
        # value (which is what a nearest-neighbor lookup would do).
        assert res["below"] > 1e-6, (
            "interior queries equal a neighbouring node value -> looks like "
            "nearest-neighbor, not interpolation (min gap above lo=%r)"
            % res["below"]
        )

    def test_in_range_and_n_extrapolated_mixed(self):
        """Mixed in/out queries: in_range mask and n_extrapolated are correct."""
        res = _run_driver(
            r"""
            import numpy as np
            x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
            y = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
            # two below x0, three inside, one above x[-1]
            x_new = np.array([-2.0, -0.5, 0.0, 1.5, 4.0, 9.0])
            out = resample_monotone(x, y, x_new, extrapolate=True)
            in_range = [bool(v) for v in np.asarray(out["in_range"])]
            print(json.dumps({"in_range": in_range,
                              "n_extrap": int(out["n_extrapolated"]),
                              "len": int(np.asarray(out["in_range"]).size)}))
            """
        )
        # boundary values x0 and x[-1] are inside [x0, x[-1]] (inclusive).
        assert res["in_range"] == [False, False, True, True, True, False], (
            "in_range mask incorrect: got %r (boundaries 0.0 and 4.0 are "
            "in-range; -2,-0.5,9 are out)" % res["in_range"]
        )
        assert res["n_extrap"] == 3, (
            "n_extrapolated must count exactly the 3 out-of-range queries, got %r"
            % res["n_extrap"]
        )
        assert res["len"] == 6, "in_range must be the same length as x_new"

    def test_extrapolate_false_raises_on_out_of_range(self):
        """extrapolate=False must raise on any out-of-range query."""
        res = _run_driver(
            r"""
            import numpy as np
            x = np.array([0.0, 1.0, 2.0, 3.0])
            y = np.array([0.0, 1.0, 2.0, 3.0])
            def raises_ve(fn):
                try:
                    fn()
                except ValueError:
                    return True
                except Exception:
                    return False
                return False
            below = raises_ve(lambda: resample_monotone(x, y, np.array([-0.1, 1.0])))
            above = raises_ve(lambda: resample_monotone(x, y, np.array([1.0, 3.1])))
            # a fully in-range query must NOT raise
            ok_inrange = True
            try:
                resample_monotone(x, y, np.array([0.0, 1.5, 3.0]))
            except Exception:
                ok_inrange = False
            print(json.dumps({"below": below, "above": above,
                              "ok_inrange": ok_inrange}))
            """
        )
        assert res["below"] is True, (
            "extrapolate=False with a query below x0 must raise ValueError"
        )
        assert res["above"] is True, (
            "extrapolate=False with a query above x[-1] must raise ValueError"
        )
        assert res["ok_inrange"] is True, (
            "extrapolate=False with an all-in-range query must NOT raise"
        )

    def test_extrapolate_true_fills_and_counts(self):
        """extrapolate=True fills out-of-range entries and counts them; in-range
        entries match the non-extrapolated result."""
        res = _run_driver(
            r"""
            import numpy as np
            x = np.array([0.0, 2.0, 4.0, 6.0])
            y = 3.0 * x - 1.0            # linear: continues cleanly past the ends
            x_new = np.array([-2.0, 1.0, 3.0, 8.0])
            out = resample_monotone(x, y, x_new, extrapolate=True)
            y_new = np.asarray(out["y_new"], dtype=float)
            in_range = [bool(v) for v in np.asarray(out["in_range"])]
            # interior linear value must be exact
            mid_err = float(abs(y_new[1] - (3.0*1.0 - 1.0)))
            print(json.dumps({"y_new": [float(v) for v in y_new],
                              "in_range": in_range,
                              "n_extrap": int(out["n_extrapolated"]),
                              "mid_err": mid_err,
                              "finite": bool(np.all(np.isfinite(y_new)))}))
            """
        )
        assert res["in_range"] == [False, True, True, False], (
            "in_range mask wrong with extrapolate=True: %r" % res["in_range"]
        )
        assert res["n_extrap"] == 2, (
            "n_extrapolated must be 2 for the two out-of-range queries, got %r"
            % res["n_extrap"]
        )
        assert res["finite"] is True, (
            "extrapolated entries must be filled with finite values, got %r"
            % res["y_new"]
        )
        assert res["mid_err"] < 1e-9, (
            "an in-range linear query must still be exact under extrapolate=True"
        )

    def test_inputs_not_mutated(self):
        """resample_monotone must not mutate x, y, or x_new."""
        res = _run_driver(
            r"""
            import numpy as np
            x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
            y = np.array([0.0, 0.5, 2.0, 4.5, 8.0])
            x_new = np.array([0.25, 1.75, 3.5, 4.0])
            xb, yb, xnb = x.copy(), y.copy(), x_new.copy()
            _ = resample_monotone(x, y, x_new, extrapolate=True)
            print(json.dumps({
                "x_ok": bool(np.array_equal(x, xb)),
                "y_ok": bool(np.array_equal(y, yb)),
                "xnew_ok": bool(np.array_equal(x_new, xnb)),
            }))
            """
        )
        assert res["x_ok"] is True, "resample_monotone mutated x"
        assert res["y_ok"] is True, "resample_monotone mutated y"
        assert res["xnew_ok"] is True, "resample_monotone mutated x_new"

    def test_return_types_and_shapes(self):
        """y_new is float 1-D, in_range is bool 1-D, n_extrapolated is an int;
        all aligned with x_new length."""
        res = _run_driver(
            r"""
            import numpy as np
            x = np.array([0.0, 1.0, 2.0, 3.0])
            y = np.array([0.0, 1.0, 2.0, 3.0])
            x_new = np.array([-1.0, 0.5, 1.5, 2.5, 5.0])
            out = resample_monotone(x, y, x_new, extrapolate=True)
            y_new = np.asarray(out["y_new"])
            in_range = np.asarray(out["in_range"])
            print(json.dumps({
                "y_ndim": int(y_new.ndim),
                "y_is_float": bool(np.issubdtype(y_new.dtype, np.floating)),
                "y_len": int(y_new.size),
                "ir_ndim": int(in_range.ndim),
                "ir_is_bool": bool(in_range.dtype == np.bool_),
                "ir_len": int(in_range.size),
                "n_is_int": bool(isinstance(out["n_extrapolated"], int)
                                 or np.issubdtype(type(out["n_extrapolated"]), np.integer)),
                "xnew_len": int(x_new.size),
            }))
            """
        )
        assert res["y_ndim"] == 1, "y_new must be 1-D"
        assert res["y_is_float"] is True, "y_new must be a float array"
        assert res["ir_ndim"] == 1, "in_range must be 1-D"
        assert res["ir_is_bool"] is True, "in_range must be a boolean array"
        assert res["n_is_int"] is True, "n_extrapolated must be an int"
        assert res["y_len"] == res["xnew_len"], "y_new length must match x_new"
        assert res["ir_len"] == res["xnew_len"], "in_range length must match x_new"

    def test_n_extrapolated_consistent_with_in_range(self):
        """n_extrapolated must equal the number of False entries in in_range."""
        res = _run_driver(
            r"""
            import numpy as np
            x = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
            y = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
            x_new = np.array([-3.0, -1.0, 0.0, 2.0, 5.0, 6.0, 12.0])
            out = resample_monotone(x, y, x_new, extrapolate=True)
            in_range = np.asarray(out["in_range"])
            n_false = int(np.count_nonzero(~in_range))
            print(json.dumps({"n_false": n_false,
                              "n_extrap": int(out["n_extrapolated"])}))
            """
        )
        assert res["n_extrap"] == res["n_false"], (
            "n_extrapolated (%r) must equal count of out-of-range entries (%r)"
            % (res["n_extrap"], res["n_false"])
        )
        assert res["n_extrap"] == 4, (
            "expected 4 out-of-range queries (-3,-1,6,12), got %r" % res["n_extrap"]
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

            good_x = np.array([0.0, 1.0, 2.0, 3.0])
            good_y = np.array([0.0, 1.0, 2.0, 3.0])
            xn = np.array([0.5, 1.5])

            results = {}
            # x and y differ in length
            results["len_mismatch"] = raises_value_error(
                lambda: resample_monotone(np.array([0.0, 1.0, 2.0]),
                                          np.array([0.0, 1.0]), xn))
            # fewer than 2 samples
            results["too_few"] = raises_value_error(
                lambda: resample_monotone(np.array([0.0]),
                                          np.array([0.0]), xn))
            # x not strictly increasing (duplicate)
            results["x_not_strict"] = raises_value_error(
                lambda: resample_monotone(np.array([0.0, 1.0, 1.0, 2.0]),
                                          np.array([0.0, 1.0, 2.0, 3.0]), xn))
            # x decreasing
            results["x_decreasing"] = raises_value_error(
                lambda: resample_monotone(np.array([3.0, 2.0, 1.0, 0.0]),
                                          good_y, xn))
            # y not monotonically non-decreasing
            results["y_not_monotone"] = raises_value_error(
                lambda: resample_monotone(good_x,
                                          np.array([0.0, 2.0, 1.0, 3.0]), xn))
            # extrapolate False, x_new out of range (below)
            results["oor_below"] = raises_value_error(
                lambda: resample_monotone(good_x, good_y,
                                          np.array([-0.5, 1.0]),
                                          extrapolate=False))
            # extrapolate False, x_new out of range (above)
            results["oor_above"] = raises_value_error(
                lambda: resample_monotone(good_x, good_y,
                                          np.array([1.0, 3.5]),
                                          extrapolate=False))
            print(json.dumps(results))
            """
        )
        for case, ok in res.items():
            assert ok is True, (
                "invalid-input case %r did not raise ValueError" % case
            )

    def test_acceptance_pytest_command(self):
        """The agent's own test file passes via the doc's native acceptance command."""
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scipy/interpolate/tests/test_monoresample.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command failed\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
            % (proc.stdout[-4000:], proc.stderr[-2000:])
        )
