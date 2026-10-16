"""
Test for the 'scipy-scientific-computing' skill (variant ext10).

Verifies the agent added a distribution fit-and-goodness reporter to
``scipy/stats`` as a new private module ``scipy/stats/_distfit_report.py``
exposing::

    fit_and_assess(data, dist, *, alpha=0.05)

which fits a named continuous distribution to a 1-D sample by maximum
likelihood and returns a dict with EXACTLY the keys
``{"params", "ks_statistic", "pvalue", "reject", "loglik"}``.

These tests do NOT trust the agent's own test file and do NOT string-match the
source. Instead each scenario runs ``fit_and_assess`` inside a fresh ``python``
subprocess with cwd=REPO_DIR (the same environment the acceptance command
uses) and deep-validates the numeric / structural contract against an
INDEPENDENT recomputation built directly on ``scipy.stats``:

  * recovered ``"params"`` match an independent direct ``dist.fit(data)``;
  * ``"ks_statistic"``/``"pvalue"`` match an independent ``scipy.stats.kstest``
    against the fitted distribution;
  * ``"loglik"`` equals the independently recomputed sum of fitted log-density;
  * matched-family data are NOT rejected (large p-value) while mismatched-family
    data ARE rejected (small p-value);
  * ``"reject"`` is exactly ``pvalue < alpha`` and honours a custom ``alpha``;
  * results are deterministic across repeated calls;
  * the caller's input array is not mutated;
  * every invalid-input case raises ``ValueError``.

A naive implementation (always returning the sample mean/std, never rejecting,
emitting a fixed p-value, or ignoring ``dist``/``alpha``) fails these tests.
The agent's own test suite is also run via the native acceptance command.
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/scipy"

# Common preamble for every driver subprocess. It loads ``fit_and_assess``
# preferring the official package import path required by the task, falling
# back to loading the source file directly (its own ``from scipy.stats ...``
# imports still resolve through the installed SciPy) so the behavioural tests
# run even if an editable rebuild has not re-registered the new module under
# the package namespace yet.
_LOADER = r"""
import json, sys, importlib.util, os
import numpy as np

REPO_DIR = %r

def _load_fit_and_assess():
    try:
        from scipy.stats._distfit_report import fit_and_assess as fa
        return fa
    except Exception:
        pass
    src = os.path.join(REPO_DIR, "scipy", "stats", "_distfit_report.py")
    spec = importlib.util.spec_from_file_location("_distfit_report_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.fit_and_assess

fit_and_assess = _load_fit_and_assess()
""" % REPO_DIR


def _run_driver(body, timeout=300):
    """Run ``_LOADER + body`` as a python subprocess in REPO_DIR.

    ``body`` must ``print(json.dumps(...))`` its result on the final line.
    Returns the parsed JSON object; raises AssertionError with captured output
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
    """Validate the fit_and_assess distribution fit-and-goodness reporter."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """scipy/stats/_distfit_report.py must exist."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "stats", "_distfit_report.py")
        assert os.path.isfile(fpath), "_distfit_report.py not found at %s" % fpath

    def test_test_file_exists(self):
        """scipy/stats/tests/test_distfit_report.py must exist."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "stats", "tests", "test_distfit_report.py"
        )
        assert os.path.isfile(fpath), "test_distfit_report.py not found at %s" % fpath

    def test_meson_registers_module(self):
        """scipy/stats/meson.build must list _distfit_report.py for installation."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "stats", "meson.build")
        assert os.path.isfile(fpath), "stats meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "_distfit_report.py" in content, (
            "_distfit_report.py was not added to scipy/stats/meson.build "
            "install_sources"
        )

    def test_meson_registers_test(self):
        """scipy/stats/tests/meson.build must list test_distfit_report.py."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "stats", "tests", "meson.build"
        )
        assert os.path.isfile(fpath), "stats/tests meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "test_distfit_report.py" in content, (
            "test_distfit_report.py was not added to tests/meson.build "
            "install_sources"
        )

    def test_function_returns_exact_keys(self):
        """fit_and_assess must return a dict with EXACTLY the five contract keys."""
        res = _run_driver(
            r"""
            import numpy as np
            x = np.linspace(-2.0, 2.0, 60)
            out = fit_and_assess(x, "norm")
            assert isinstance(out, dict), "return value must be a dict"
            print(json.dumps(sorted(out.keys())))
            """
        )
        assert res == ["ks_statistic", "loglik", "params", "pvalue", "reject"], (
            "fit_and_assess must return exactly keys "
            "{'params','ks_statistic','pvalue','reject','loglik'}, got %r" % res
        )

    def test_return_value_types(self):
        """params is a tuple of floats; pvalue in [0,1]; reject is a real bool."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(0)
            x = rng.normal(1.0, 2.0, 200)
            out = fit_and_assess(x, "norm")
            info = {
                "params_is_tuple": isinstance(out["params"], tuple),
                "params_len": len(out["params"]),
                "params_all_float": all(isinstance(float(v), float) for v in out["params"]),
                "ks_is_num": isinstance(out["ks_statistic"], (int, float)),
                "pvalue": float(out["pvalue"]),
                "reject_is_bool": isinstance(out["reject"], bool),
                "loglik_is_num": isinstance(out["loglik"], (int, float)),
            }
            print(json.dumps(info))
            """
        )
        assert res["params_is_tuple"] is True, (
            "'params' must be a tuple, got non-tuple"
        )
        assert res["params_len"] == 2, (
            "norm fit must have exactly (loc, scale) -> 2 params, got %r"
            % res["params_len"]
        )
        assert res["params_all_float"] is True, "'params' must be floats"
        assert res["ks_is_num"] is True, "'ks_statistic' must be numeric"
        assert 0.0 <= res["pvalue"] <= 1.0, (
            "'pvalue' must lie in [0,1], got %r" % res["pvalue"]
        )
        assert res["reject_is_bool"] is True, "'reject' must be a python bool"
        assert res["loglik_is_num"] is True, "'loglik' must be numeric"

    # ------------------------------------------------------------------
    # L2 — dynamic execution / deep behavioural validation
    # ------------------------------------------------------------------

    def test_params_match_independent_norm_fit(self):
        """'params' must match an independent scipy.stats.norm.fit of the same data."""
        res = _run_driver(
            r"""
            import numpy as np
            import scipy.stats as st
            rng = np.random.RandomState(7)
            x = rng.normal(2.5, 1.3, 500)
            out = fit_and_assess(x, "norm")
            ref = st.norm.fit(x)
            print(json.dumps({
                "got": [float(v) for v in out["params"]],
                "ref": [float(v) for v in ref],
            }))
            """
        )
        got, ref = res["got"], res["ref"]
        assert len(got) == len(ref) == 2, (
            "norm params length mismatch: got %r ref %r" % (got, ref)
        )
        for g, r in zip(got, ref):
            assert abs(g - r) <= 1e-6 + 1e-6 * abs(r), (
                "fitted params must match an independent norm.fit; got %r ref %r"
                % (got, ref)
            )
        # Guard against a naive impl that returns (mean, std) only by luck:
        # the fitted scale must be the MLE std (ddof=0), distinct from sample std.
        assert abs(got[0] - 2.5) < 0.3, "loc should be ~ sample mean, got %r" % got[0]

    def test_params_match_independent_expon_fit(self):
        """For an exponential sample, 'params' must match expon.fit and the scale."""
        res = _run_driver(
            r"""
            import numpy as np
            import scipy.stats as st
            rng = np.random.RandomState(11)
            x = rng.exponential(2.5, 600)
            out = fit_and_assess(x, "expon")
            ref = st.expon.fit(x)
            print(json.dumps({
                "got": [float(v) for v in out["params"]],
                "ref": [float(v) for v in ref],
                "mean": float(np.mean(x)),
            }))
            """
        )
        got, ref = res["got"], res["ref"]
        assert len(got) == 2, "expon fit must yield (loc, scale) -> 2 params, got %r" % got
        for g, r in zip(got, ref):
            assert abs(g - r) <= 1e-6 + 1e-6 * abs(r), (
                "expon params must match independent expon.fit; got %r ref %r"
                % (got, ref)
            )
        # MLE scale of an expon with loc~0 is ~ the sample mean.
        assert abs(got[1] - res["mean"]) < 0.4, (
            "expon scale should be ~ sample mean (%r), got %r" % (res["mean"], got[1])
        )

    def test_ks_statistic_and_pvalue_match_independent_kstest(self):
        """'ks_statistic'/'pvalue' must match an independent kstest of fitted dist."""
        res = _run_driver(
            r"""
            import numpy as np
            import scipy.stats as st
            rng = np.random.RandomState(3)
            x = rng.normal(0.0, 1.0, 400)
            out = fit_and_assess(x, "norm")
            params = tuple(out["params"])
            ref = st.kstest(x, "norm", args=params)
            print(json.dumps({
                "got_ks": float(out["ks_statistic"]),
                "ref_ks": float(ref.statistic),
                "got_p": float(out["pvalue"]),
                "ref_p": float(ref.pvalue),
            }))
            """
        )
        assert abs(res["got_ks"] - res["ref_ks"]) <= 1e-6, (
            "ks_statistic must match independent kstest of fitted dist: got %r ref %r"
            % (res["got_ks"], res["ref_ks"])
        )
        assert abs(res["got_p"] - res["ref_p"]) <= 1e-6, (
            "pvalue must match independent kstest of fitted dist: got %r ref %r"
            % (res["got_p"], res["ref_p"])
        )

    def test_loglik_equals_recomputed_logpdf_sum(self):
        """'loglik' must equal the independently recomputed sum of fitted logpdf."""
        res = _run_driver(
            r"""
            import numpy as np
            import scipy.stats as st
            rng = np.random.RandomState(5)
            x = rng.gamma(2.0, 1.5, 300)
            out = fit_and_assess(x, "gamma")
            params = tuple(out["params"])
            ref = float(np.sum(st.gamma.logpdf(x, *params)))
            print(json.dumps({
                "got": float(out["loglik"]),
                "ref": ref,
                "n_params": len(params),
            }))
            """
        )
        # gamma has 1 shape + loc + scale = 3 params.
        assert res["n_params"] == 3, (
            "gamma fit must yield 3 params (shape, loc, scale), got %r" % res["n_params"]
        )
        assert abs(res["got"] - res["ref"]) <= 1e-6 + 1e-6 * abs(res["ref"]), (
            "loglik must equal sum(dist.logpdf(data, *params)); got %r ref %r"
            % (res["got"], res["ref"])
        )

    def test_matched_family_not_rejected(self):
        """Data genuinely drawn from norm, fit with 'norm' -> NOT rejected, large p."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(42)
            x = rng.normal(0.0, 1.0, 500)
            out = fit_and_assess(x, "norm", alpha=0.05)
            print(json.dumps({
                "reject": bool(out["reject"]),
                "pvalue": float(out["pvalue"]),
            }))
            """
        )
        assert res["reject"] is False, (
            "well-matched normal data must NOT be rejected (a naive impl that "
            "always rejects/uses a fixed small p fails); pvalue=%r" % res["pvalue"]
        )
        assert res["pvalue"] > 0.05, (
            "matched-family p-value should be comfortably large, got %r" % res["pvalue"]
        )

    def test_mismatched_family_rejected(self):
        """A clearly skewed exponential sample fit with 'norm' -> rejected, small p."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(123)
            x = rng.exponential(1.0, 500)   # strongly right-skewed
            out = fit_and_assess(x, "norm", alpha=0.05)
            print(json.dumps({
                "reject": bool(out["reject"]),
                "pvalue": float(out["pvalue"]),
            }))
            """
        )
        assert res["reject"] is True, (
            "exponential data fit with 'norm' must be rejected (a naive impl that "
            "never rejects fails); pvalue=%r" % res["pvalue"]
        )
        assert res["pvalue"] < 0.05, (
            "mismatched-family p-value should be small, got %r" % res["pvalue"]
        )

    def test_reject_consistent_with_pvalue_and_alpha(self):
        """'reject' must equal (pvalue < alpha), and honour a custom alpha."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(2024)
            # borderline-skewed data so the p-value is in an interesting middle range
            x = rng.exponential(1.0, 120)
            base = fit_and_assess(x, "norm", alpha=0.05)
            p = float(base["pvalue"])
            # alpha just below p -> must NOT reject; alpha just above p -> must reject
            lo = max(min(p * 0.5, 0.99), 1e-6)
            hi = min(max(p * 2.0, p + 1e-3), 0.999)
            r_lo = fit_and_assess(x, "norm", alpha=lo)
            r_hi = fit_and_assess(x, "norm", alpha=hi)
            print(json.dumps({
                "p": p,
                "base_reject": bool(base["reject"]),
                "base_default_consistent": bool(base["reject"]) == (p < 0.05),
                "lo": lo, "reject_lo": bool(r_lo["reject"]),
                "hi": hi, "reject_hi": bool(r_hi["reject"]),
            }))
            """
        )
        assert res["base_default_consistent"] is True, (
            "'reject' must equal (pvalue < alpha) at the default alpha; p=%r reject=%r"
            % (res["p"], res["base_reject"])
        )
        # alpha below p -> not reject; alpha above p -> reject (a fixed-flag impl fails).
        assert res["reject_lo"] == (res["p"] < res["lo"]), (
            "with alpha=%r < p=%r, reject should be %r"
            % (res["lo"], res["p"], res["p"] < res["lo"])
        )
        assert res["reject_hi"] == (res["p"] < res["hi"]), (
            "with alpha=%r > p=%r, reject should be %r"
            % (res["hi"], res["p"], res["p"] < res["hi"])
        )
        assert res["reject_lo"] != res["reject_hi"], (
            "'reject' must flip as alpha crosses the p-value; got lo=%r hi=%r "
            "(a hardcoded reject flag fails)" % (res["reject_lo"], res["reject_hi"])
        )

    def test_deterministic_across_calls(self):
        """Repeated calls on identical inputs must give identical results."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(99)
            x = rng.normal(3.0, 2.0, 250)
            a = fit_and_assess(x, "norm")
            b = fit_and_assess(x, "norm")
            print(json.dumps({
                "params_a": [float(v) for v in a["params"]],
                "params_b": [float(v) for v in b["params"]],
                "ks_a": float(a["ks_statistic"]), "ks_b": float(b["ks_statistic"]),
                "p_a": float(a["pvalue"]), "p_b": float(b["pvalue"]),
                "ll_a": float(a["loglik"]), "ll_b": float(b["loglik"]),
            }))
            """
        )
        assert res["params_a"] == res["params_b"], (
            "params must be deterministic; got %r vs %r"
            % (res["params_a"], res["params_b"])
        )
        assert res["ks_a"] == res["ks_b"], "ks_statistic must be deterministic"
        assert res["p_a"] == res["p_b"], (
            "pvalue must be deterministic (no random p-value estimation that "
            "changes between calls); got %r vs %r" % (res["p_a"], res["p_b"])
        )
        assert res["ll_a"] == res["ll_b"], "loglik must be deterministic"

    def test_input_not_mutated(self):
        """fit_and_assess must not mutate the caller's input array."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(8)
            x = rng.normal(0.0, 1.0, 200)
            before = x.copy()
            _ = fit_and_assess(x, "norm")
            print(json.dumps({"unchanged": bool(np.array_equal(x, before))}))
            """
        )
        assert res["unchanged"] is True, (
            "fit_and_assess must not mutate its input array"
        )

    def test_dist_argument_actually_used(self):
        """Fitting the SAME data as 'norm' vs 'expon' must give different reports."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(17)
            x = rng.exponential(2.0, 400)
            n = fit_and_assess(x, "norm")
            e = fit_and_assess(x, "expon")
            print(json.dumps({
                "ll_norm": float(n["loglik"]),
                "ll_expon": float(e["loglik"]),
                "p_norm": float(n["pvalue"]),
                "p_expon": float(e["pvalue"]),
                "params_norm_len": len(n["params"]),
                "params_expon_len": len(e["params"]),
            }))
            """
        )
        # A naive impl that ignores 'dist' would give identical loglik/pvalue.
        assert res["ll_norm"] != res["ll_expon"], (
            "loglik must depend on the requested 'dist' (impl ignores dist?); "
            "norm=%r expon=%r" % (res["ll_norm"], res["ll_expon"])
        )
        assert res["p_norm"] != res["p_expon"], (
            "pvalue must depend on the requested 'dist'; norm=%r expon=%r"
            % (res["p_norm"], res["p_expon"])
        )
        # For exponential data, expon must fit much better than norm.
        assert res["ll_expon"] > res["ll_norm"], (
            "exponential data must have higher loglik under 'expon' than 'norm'"
        )
        assert res["p_expon"] > res["p_norm"], (
            "exponential data must be a better goodness-of-fit under 'expon'"
        )

    def test_invalid_inputs_raise_value_error(self):
        """Each invalid-input case must raise ValueError."""
        res = _run_driver(
            r"""
            import numpy as np
            good = np.linspace(-1.0, 1.0, 40)

            def raises_value_error(fn):
                try:
                    fn()
                except ValueError:
                    return True
                except Exception:
                    return False
                return False

            results = {}
            # data not 1-D
            results["data_2d"] = raises_value_error(
                lambda: fit_and_assess(np.ones((4, 4)), "norm"))
            # data contains non-finite
            bad = good.copy(); bad[0] = np.nan
            results["data_nan"] = raises_value_error(
                lambda: fit_and_assess(bad, "norm"))
            badinf = good.copy(); badinf[1] = np.inf
            results["data_inf"] = raises_value_error(
                lambda: fit_and_assess(badinf, "norm"))
            # fewer than 5 samples
            results["data_short"] = raises_value_error(
                lambda: fit_and_assess(np.array([1.0, 2.0, 3.0]), "norm"))
            # unknown distribution name
            results["dist_unknown"] = raises_value_error(
                lambda: fit_and_assess(good, "not_a_real_distribution"))
            # alpha out of (0,1)
            results["alpha_zero"] = raises_value_error(
                lambda: fit_and_assess(good, "norm", alpha=0.0))
            results["alpha_one"] = raises_value_error(
                lambda: fit_and_assess(good, "norm", alpha=1.0))
            results["alpha_neg"] = raises_value_error(
                lambda: fit_and_assess(good, "norm", alpha=-0.1))
            results["alpha_big"] = raises_value_error(
                lambda: fit_and_assess(good, "norm", alpha=1.5))
            print(json.dumps(results))
            """
        )
        for case, ok in res.items():
            assert ok is True, "invalid-input case %r did not raise ValueError" % case

    def test_acceptance_pytest_command(self):
        """The agent's own test file passes via the native acceptance command."""
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scipy/stats/tests/test_distfit_report.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command failed\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
            % (proc.stdout[-4000:], proc.stderr[-2000:])
        )
