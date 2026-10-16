"""
Test for the 'scipy-scientific-computing' skill  (variant: ext8).

Verifies the agent added a constrained budget-allocation optimizer to
``scipy/optimize`` as a new private module ``scipy/optimize/_allocate.py``
exposing::

    allocate_budget(gains, budget, *, caps=None)

which maximizes the concave diminishing-returns payoff
``sum_i gains[i] * sqrt(x_i)`` over a non-negative allocation ``x`` subject to
the total-spend equality ``sum_i x_i == budget`` and optional per-activity caps
``x_i <= caps[i]``.  It returns a dict with exactly the keys
``{"x", "payoff", "success"}``.

The tests do not trust the agent's own test file or string-match the source.
Instead they exercise the real ``allocate_budget`` function (running each
scenario in a fresh ``python`` subprocess with cwd=REPO_DIR — exactly the
environment the acceptance command uses) and deep-validate the numeric /
structural contract:

  * the returned ``"x"`` sums to ``budget`` (tight tolerance), is non-negative,
    and respects ``caps`` when supplied;
  * the uncapped optimum equals the closed-form solution
    (``x_i`` proportional to ``gains[i]**2``);
  * ``"payoff"`` strictly beats an equal-split baseline, proving a genuine
    maximization rather than an arbitrary feasible point;
  * binding caps saturate exactly and the remaining budget redistributes among
    unsaturated activities;
  * ``"success"`` is True on solvable problems;
  * inputs are not mutated;
  * every invalid-input case raises ``ValueError``.

A naive implementation (even split regardless of ``gains``, ignoring ``caps``,
or returning a hardcoded/arbitrary feasible point) fails these tests.

Native acceptance command (driven by the final test):

    python -m pytest scipy/optimize/tests/test_allocate.py -v
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/scipy"

# Common preamble for every driver subprocess. It loads ``allocate_budget``
# preferring the official package import path required by the task, and falling
# back to loading the source file directly (its own ``from scipy.optimize ...``
# imports still resolve through the installed SciPy) so the behavioural tests
# run even if the editable rebuild has not re-registered the module under the
# package namespace yet.
_LOADER = r"""
import json, sys, importlib.util, os
import numpy as np

def _load_allocate_budget():
    try:
        from scipy.optimize._allocate import allocate_budget as ab
        return ab
    except Exception:
        pass
    src = os.path.join(REPO_DIR, "scipy", "optimize", "_allocate.py")
    spec = importlib.util.spec_from_file_location("_allocate_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.allocate_budget

REPO_DIR = %r
allocate_budget = _load_allocate_budget()
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
    """Validate the allocate_budget constrained optimizer."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """scipy/optimize/_allocate.py must exist."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "optimize", "_allocate.py")
        assert os.path.isfile(fpath), "_allocate.py not found at %s" % fpath

    def test_test_file_exists(self):
        """scipy/optimize/tests/test_allocate.py must exist."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "optimize", "tests", "test_allocate.py"
        )
        assert os.path.isfile(fpath), "test_allocate.py not found at %s" % fpath

    def test_meson_registers_module(self):
        """scipy/optimize/meson.build must list _allocate.py for installation."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "optimize", "meson.build")
        assert os.path.isfile(fpath), "optimize meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "_allocate.py" in content, (
            "_allocate.py was not added to scipy/optimize/meson.build install_sources"
        )

    def test_meson_registers_test(self):
        """scipy/optimize/tests/meson.build must list test_allocate.py."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "optimize", "tests", "meson.build"
        )
        assert os.path.isfile(fpath), "optimize/tests meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "test_allocate.py" in content, (
            "test_allocate.py was not added to tests/meson.build install_sources"
        )

    def test_function_importable_and_return_keys(self):
        """allocate_budget must be importable and return a dict with exactly the three keys."""
        res = _run_driver(
            r"""
            out = allocate_budget([1.0, 1.0], 10.0)
            assert isinstance(out, dict), "return value must be a dict"
            keys = sorted(out.keys())
            print(json.dumps(keys))
            """
        )
        assert res == ["payoff", "success", "x"], (
            "allocate_budget must return exactly keys {'x','payoff','success'}, got %r"
            % res
        )

    def test_return_value_types(self):
        """'x' is a length-n float array, 'payoff' a float, 'success' a bool."""
        res = _run_driver(
            r"""
            out = allocate_budget([2.0, 1.0, 3.0], 6.0)
            x = np.asarray(out["x"], dtype=float)
            print(json.dumps({
                "n": int(x.size),
                "ndim": int(x.ndim),
                "payoff_is_num": isinstance(out["payoff"], (int, float, np.floating)),
                "success_is_bool": isinstance(out["success"], (bool, np.bool_)),
            }))
            """
        )
        assert res["n"] == 3, "'x' must have length n (=3), got %r" % res["n"]
        assert res["ndim"] == 1, "'x' must be 1-D, got ndim=%r" % res["ndim"]
        assert res["payoff_is_num"] is True, "'payoff' must be a float"
        assert res["success_is_bool"] is True, "'success' must be a bool"

    # ------------------------------------------------------------------
    # L2 — dynamic execution / deep behavioural validation
    # ------------------------------------------------------------------

    def test_symmetric_optimum(self):
        """gains=[1,1], budget=10 -> x ~= [5,5] and payoff == analytic max."""
        res = _run_driver(
            r"""
            out = allocate_budget([1.0, 1.0], 10.0)
            x = np.asarray(out["x"], dtype=float)
            payoff = float(out["payoff"])
            print(json.dumps({
                "x": x.tolist(),
                "payoff": payoff,
                "total": float(x.sum()),
            }))
            """
        )
        x = res["x"]
        assert abs(res["total"] - 10.0) < 1e-4, (
            "allocation must sum to budget=10, got sum=%r" % res["total"]
        )
        assert abs(x[0] - 5.0) < 1e-3 and abs(x[1] - 5.0) < 1e-3, (
            "symmetric problem optimum must be [5,5], got %r" % x
        )
        # Analytic max payoff: 1*sqrt(5) + 1*sqrt(5) = 2*sqrt(5).
        import math
        assert abs(res["payoff"] - 2.0 * math.sqrt(5.0)) < 1e-3, (
            "payoff must equal analytic maximum 2*sqrt(5), got %r" % res["payoff"]
        )

    def test_uncapped_matches_analytic_proportion(self):
        """Uncapped optimum: x_i proportional to gains_i**2 (here gains=[2,1])."""
        res = _run_driver(
            r"""
            gains = np.array([2.0, 1.0])
            budget = 5.0
            out = allocate_budget(gains, budget)
            x = np.asarray(out["x"], dtype=float)
            # analytic: x_i = budget * gains_i**2 / sum(gains**2)
            w = gains**2
            x_star = budget * w / w.sum()
            print(json.dumps({
                "x": x.tolist(),
                "x_star": x_star.tolist(),
                "total": float(x.sum()),
            }))
            """
        )
        x, x_star = res["x"], res["x_star"]
        assert abs(res["total"] - 5.0) < 1e-4, (
            "allocation must sum to budget=5, got %r" % res["total"]
        )
        # gains=[2,1] -> weights [4,1] -> x_star = [4,1] (sum 5).
        assert abs(x[0] - x_star[0]) < 1e-2 and abs(x[1] - x_star[1]) < 1e-2, (
            "uncapped optimum must match gains**2 proportion %r, got %r "
            "(an even split [2.5,2.5] fails here)" % (x_star, x)
        )
        # Skew must be real: activity 0 gets strictly more than activity 1.
        assert x[0] > x[1] + 1.0, (
            "allocation must skew toward higher-gain activity, got %r" % x
        )

    def test_uncapped_three_way_analytic(self):
        """gains=[3,2,1], budget=14 -> x proportional to [9,4,1]."""
        res = _run_driver(
            r"""
            gains = np.array([3.0, 2.0, 1.0])
            budget = 14.0
            out = allocate_budget(gains, budget)
            x = np.asarray(out["x"], dtype=float)
            w = gains**2
            x_star = budget * w / w.sum()
            print(json.dumps({"x": x.tolist(), "x_star": x_star.tolist()}))
            """
        )
        x, x_star = res["x"], res["x_star"]
        # weights [9,4,1] sum 14 -> x_star = [9,4,1] exactly.
        for i, (xi, xs) in enumerate(zip(x, x_star)):
            assert abs(xi - xs) < 2e-2, (
                "component %d: expected %r (gains**2 proportion), got %r" % (i, xs, xi)
            )

    def test_payoff_beats_equal_split(self):
        """Achieved payoff must strictly exceed an equal-split baseline."""
        res = _run_driver(
            r"""
            gains = np.array([3.0, 1.0, 0.5])
            budget = 12.0
            out = allocate_budget(gains, budget)
            x = np.asarray(out["x"], dtype=float)
            achieved = float(out["payoff"])
            # achieved payoff recomputed independently from x
            recomputed = float(np.sum(gains * np.sqrt(np.clip(x, 0, None))))
            # equal-split baseline
            eq = np.full(gains.size, budget / gains.size)
            eq_payoff = float(np.sum(gains * np.sqrt(eq)))
            print(json.dumps({
                "achieved": achieved,
                "recomputed": recomputed,
                "eq_payoff": eq_payoff,
            }))
            """
        )
        # The reported payoff must actually correspond to the returned x.
        assert abs(res["achieved"] - res["recomputed"]) < 1e-3, (
            "reported 'payoff' (%r) must equal payoff evaluated at returned 'x' (%r)"
            % (res["achieved"], res["recomputed"])
        )
        # And it must genuinely beat the equal-split feasible baseline.
        assert res["achieved"] > res["eq_payoff"] + 1e-3, (
            "optimized payoff (%r) must beat equal-split baseline (%r); "
            "a naive even-split impl ties the baseline and fails"
            % (res["achieved"], res["eq_payoff"])
        )

    def test_non_negative_and_sums_to_budget(self):
        """For an asymmetric problem x is non-negative and sums to budget."""
        res = _run_driver(
            r"""
            gains = np.array([5.0, 0.1, 2.0, 0.3])
            budget = 7.5
            out = allocate_budget(gains, budget)
            x = np.asarray(out["x"], dtype=float)
            print(json.dumps({
                "total": float(x.sum()),
                "min": float(x.min()),
            }))
            """
        )
        assert abs(res["total"] - 7.5) < 1e-4, (
            "allocation must sum to budget=7.5, got %r" % res["total"]
        )
        assert res["min"] >= -1e-8, (
            "allocation must be non-negative, min component was %r" % res["min"]
        )

    def test_binding_cap_saturates_and_redistributes(self):
        """gains=[1,1,1], budget=9, caps=[2,100,100] -> x0 pinned at 2, rest split."""
        res = _run_driver(
            r"""
            out = allocate_budget([1.0, 1.0, 1.0], 9.0, caps=[2.0, 100.0, 100.0])
            x = np.asarray(out["x"], dtype=float)
            print(json.dumps({
                "x": x.tolist(),
                "total": float(x.sum()),
            }))
            """
        )
        x = res["x"]
        assert abs(res["total"] - 9.0) < 1e-4, (
            "capped allocation must still sum to budget=9, got %r" % res["total"]
        )
        # Activity 0 saturates exactly at its cap of 2.
        assert abs(x[0] - 2.0) < 1e-3, (
            "saturated activity 0 must sit exactly at its cap 2.0, got %r "
            "(an impl ignoring caps fails)" % x[0]
        )
        # Remaining 7 split evenly between symmetric activities 1 and 2.
        assert abs(x[1] - 3.5) < 1e-2 and abs(x[2] - 3.5) < 1e-2, (
            "remaining budget (7) must redistribute evenly to [3.5, 3.5], got %r"
            % x[1:]
        )

    def test_cap_respected_everywhere(self):
        """No component may exceed its cap when caps bind on multiple activities."""
        res = _run_driver(
            r"""
            gains = np.array([4.0, 1.0, 1.0])
            caps = np.array([1.0, 2.0, 100.0])
            budget = 6.0
            out = allocate_budget(gains, budget, caps=caps)
            x = np.asarray(out["x"], dtype=float)
            print(json.dumps({
                "x": x.tolist(),
                "viol": float(np.max(x - caps)),
                "total": float(x.sum()),
            }))
            """
        )
        x = res["x"]
        assert abs(res["total"] - 6.0) < 1e-4, (
            "capped allocation must sum to budget=6, got %r" % res["total"]
        )
        assert res["viol"] <= 1e-6, (
            "no component may exceed its cap; max violation was %r (x=%r)"
            % (res["viol"], x)
        )
        # High-gain activity 0 wants more but is capped at 1.0 -> saturates.
        assert abs(x[0] - 1.0) < 1e-2, (
            "high-gain capped activity 0 must saturate at 1.0, got %r" % x[0]
        )

    def test_success_true_on_solvable(self):
        """'success' must be True for a well-posed solvable problem."""
        res = _run_driver(
            r"""
            out = allocate_budget([2.0, 3.0, 1.0], 8.0, caps=[10.0, 10.0, 10.0])
            print(json.dumps({"success": bool(out["success"])}))
            """
        )
        assert res["success"] is True, (
            "'success' must be True on a solvable problem"
        )

    def test_input_not_mutated(self):
        """allocate_budget must not mutate gains or caps passed by the caller."""
        res = _run_driver(
            r"""
            gains = np.array([2.0, 1.0, 3.0])
            caps = np.array([10.0, 10.0, 10.0])
            g_before = gains.copy()
            c_before = caps.copy()
            _ = allocate_budget(gains, 6.0, caps=caps)
            print(json.dumps({
                "gains_unchanged": bool(np.array_equal(gains, g_before)),
                "caps_unchanged": bool(np.array_equal(caps, c_before)),
            }))
            """
        )
        assert res["gains_unchanged"] is True, "gains array must not be mutated"
        assert res["caps_unchanged"] is True, "caps array must not be mutated"

    def test_optimality_vs_random_feasible(self):
        """Achieved payoff must dominate many random feasible allocations."""
        res = _run_driver(
            r"""
            gains = np.array([3.0, 1.5, 0.7, 2.0])
            budget = 10.0
            out = allocate_budget(gains, budget)
            achieved = float(out["payoff"])
            rng = np.random.RandomState(0)   # deterministic
            best_rand = -1.0
            for _ in range(2000):
                w = rng.rand(gains.size)
                pt = budget * w / w.sum()      # feasible: sums to budget, >=0
                p = float(np.sum(gains * np.sqrt(pt)))
                if p > best_rand:
                    best_rand = p
            print(json.dumps({"achieved": achieved, "best_rand": best_rand}))
            """
        )
        assert res["achieved"] >= res["best_rand"] - 1e-3, (
            "optimized payoff (%r) must dominate the best of 2000 random feasible "
            "allocations (%r); an arbitrary feasible point fails"
            % (res["achieved"], res["best_rand"])
        )

    def test_invalid_inputs_raise_value_error(self):
        """Each invalid-input case must raise ValueError."""
        res = _run_driver(
            r"""
            def raises_value_error(fn):
                try:
                    fn()
                except ValueError:
                    return True
                except Exception:
                    return False
                return False

            results = {}
            # gains empty
            results["gains_empty"] = raises_value_error(
                lambda: allocate_budget([], 5.0))
            # gains not 1-D
            results["gains_2d"] = raises_value_error(
                lambda: allocate_budget([[1.0, 2.0], [3.0, 4.0]], 5.0))
            # gains has a non-positive entry
            results["gains_zero"] = raises_value_error(
                lambda: allocate_budget([1.0, 0.0], 5.0))
            results["gains_neg"] = raises_value_error(
                lambda: allocate_budget([1.0, -2.0], 5.0))
            # budget <= 0
            results["budget_zero"] = raises_value_error(
                lambda: allocate_budget([1.0, 1.0], 0.0))
            results["budget_neg"] = raises_value_error(
                lambda: allocate_budget([1.0, 1.0], -3.0))
            # caps wrong length
            results["caps_len"] = raises_value_error(
                lambda: allocate_budget([1.0, 1.0], 5.0, caps=[3.0]))
            # caps negative entry
            results["caps_neg"] = raises_value_error(
                lambda: allocate_budget([1.0, 1.0], 5.0, caps=[3.0, -1.0]))
            # total cap < budget -> infeasible equality
            results["caps_infeasible"] = raises_value_error(
                lambda: allocate_budget([1.0, 1.0], 10.0, caps=[2.0, 3.0]))
            print(json.dumps(results))
            """
        )
        for case, ok in res.items():
            assert ok is True, "invalid-input case %r did not raise ValueError" % case

    def test_acceptance_pytest_command(self):
        """The agent's own test file passes via the native acceptance command."""
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scipy/optimize/tests/test_allocate.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command failed\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
            % (proc.stdout[-4000:], proc.stderr[-2000:])
        )
