"""Tests for the ``statsmodels-regression`` skill (variant ext10).

Variant task: build an *outlier-robust conditional-quantile fit helper* at
``statsmodels/regression/quantile_compare.py`` exposing a single public
function::

    compare_mean_vs_quantile(endog, exog, q=0.5, add_intercept=True)

It must fit BOTH an ordinary mean (OLS) model and a conditional-quantile
(QuantReg) model of ``endog`` on ``exog`` from raw arrays, and return a plain
``dict`` report with keys: ``ols_params``, ``quantile_params``, ``q``,
``slope_diff``, ``ols_resid``, ``quantile_resid`` and
``quantile_below_fraction``.

Verification strategy
---------------------
Every reported quantity is independently re-derived in the SAME subprocess from
statsmodels' own ``sm.OLS`` and ``sm.QuantReg`` estimators on the equivalent
intercept-augmented design, and asserted to agree to floating-point tolerance.
A naive/stub implementation cannot pass because:
  * ``ols_params`` must equal a real OLS fit (not a hardcoded vector);
  * ``quantile_params`` must equal a real QuantReg fit at the supplied ``q``
    (so ignoring ``q``, or returning the OLS params, fails);
  * ``slope_diff`` must be the elementwise difference of the two;
  * ``quantile_below_fraction`` must reflect the actual quantile residual sign
    split (near ``q``), so a fixed constant fails;
  * a planted-outlier scenario requires the quantile slope to be genuinely more
    robust than the OLS slope (mean-vs-median discrimination);
  * ``q`` outside ``(0, 1)`` must raise ``ValueError``.

L1 cases check the deliverable file exists and the function is importable with
the correct signature/keys/types. L2 cases drive dynamic numeric verification
through a subprocess that prints a single JSON object (robust to PYTHONPATH
being cleared), plus the doc's native acceptance command (pytest on the
deliverable's own test module).
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/statsmodels"


# Bootstrap importing the agent's module plus reference statsmodels estimators.
# Prepended to every driver script so it runs from anywhere with PYTHONPATH
# cleared.
_BOOTSTRAP = textwrap.dedent(
    """
    import sys, os, json
    REPO_DIR = {repo!r}
    sys.path.insert(0, REPO_DIR)
    import numpy as np
    import statsmodels.api as sm
    from statsmodels.regression.quantile_regression import QuantReg
    from statsmodels.regression.quantile_compare import compare_mean_vs_quantile
    """
).format(repo=REPO_DIR)


def _run_driver(body, timeout=300):
    """Execute *body* (which must print a single JSON object on its last line)
    in a fresh interpreter rooted at REPO_DIR. Returns the parsed JSON dict."""
    script = _BOOTSTRAP + textwrap.dedent(body)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
    )
    assert proc.returncode == 0, (
        "driver failed\nSTDOUT:\n"
        + proc.stdout[-4000:]
        + "\nSTDERR:\n"
        + proc.stderr[-4000:]
    )
    out = proc.stdout.strip().splitlines()
    assert out, "driver produced no stdout:\n" + proc.stderr[-2000:]
    return json.loads(out[-1])


class TestStatsmodelsRegression:
    REPO_DIR = "/workspace/statsmodels"

    MODULE_PATH = os.path.join(
        REPO_DIR, "statsmodels", "regression", "quantile_compare.py"
    )
    TEST_PATH = os.path.join(
        REPO_DIR,
        "statsmodels",
        "regression",
        "tests",
        "test_quantile_compare.py",
    )

    # ------------------------------------------------------------------ L1 ---
    def test_module_file_exists(self):
        """L1: the new quantile_compare.py deliverable exists and is non-trivial."""
        assert os.path.isfile(self.MODULE_PATH), (
            "expected new module at " + self.MODULE_PATH
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_function_importable_with_signature(self):
        """L1: compare_mean_vs_quantile is importable and has the required
        parameters with the documented defaults (q=0.5, add_intercept=True)."""
        report = _run_driver(
            """
            import inspect
            sig = inspect.signature(compare_mean_vs_quantile)
            params = list(sig.parameters)
            q_default = (
                sig.parameters['q'].default if 'q' in sig.parameters else None
            )
            ai_default = (
                sig.parameters['add_intercept'].default
                if 'add_intercept' in sig.parameters else None
            )
            print(json.dumps({
                'params': params,
                'q_default': q_default,
                'add_intercept_default': ai_default,
            }))
            """
        )
        assert report["params"][:2] == ["endog", "exog"], report["params"]
        assert "q" in report["params"]
        assert "add_intercept" in report["params"]
        assert report["q_default"] == 0.5
        assert report["add_intercept_default"] is True

    def test_returns_dict_with_required_keys(self):
        """L1: the helper returns a plain dict containing every documented key."""
        report = _run_driver(
            """
            x = np.linspace(0, 10, 30)
            y = 1.0 + 2.0 * x
            out = compare_mean_vs_quantile(list(y), list(x))
            print(json.dumps({
                'is_dict': type(out).__name__ == 'dict',
                'keys': sorted(out.keys()),
            }))
            """
        )
        assert report["is_dict"] is True, "must return a plain dict"
        required = {
            "ols_params", "quantile_params", "q", "slope_diff",
            "ols_resid", "quantile_resid", "quantile_below_fraction",
        }
        missing = required - set(report["keys"])
        assert not missing, "missing keys: " + str(sorted(missing))

    def test_value_types_and_lengths_well_formed(self):
        """L1: array-valued keys are 1-D arrays, param vectors share a length,
        residual vectors have length n, q is a float, and below-fraction is a
        float in [0, 1]."""
        report = _run_driver(
            """
            rng = np.random.RandomState(0)
            n = 25
            x = np.linspace(0, 5, n)
            y = 0.5 + 1.5 * x + rng.normal(scale=0.3, size=n)
            out = compare_mean_vs_quantile(y, x, q=0.5)
            op = np.asarray(out['ols_params'])
            qp = np.asarray(out['quantile_params'])
            sd = np.asarray(out['slope_diff'])
            orr = np.asarray(out['ols_resid'])
            qrr = np.asarray(out['quantile_resid'])
            qbf = float(out['quantile_below_fraction'])
            print(json.dumps({
                'op_ndim': int(op.ndim),
                'qp_ndim': int(qp.ndim),
                'sd_ndim': int(sd.ndim),
                'same_param_len': op.shape == qp.shape == sd.shape,
                'resid_len_op': int(orr.shape[0]),
                'resid_len_qp': int(qrr.shape[0]),
                'n': n,
                'q_is_float': isinstance(out['q'], float),
                'q_val': float(out['q']),
                'qbf': qbf,
                'qbf_in_unit': 0.0 <= qbf <= 1.0,
            }))
            """
        )
        assert report["op_ndim"] == 1
        assert report["qp_ndim"] == 1
        assert report["sd_ndim"] == 1
        assert report["same_param_len"] is True
        assert report["resid_len_op"] == report["n"]
        assert report["resid_len_qp"] == report["n"]
        assert report["q_is_float"] is True
        assert report["q_val"] == 0.5
        assert report["qbf_in_unit"] is True

    # ------------------------------------------------------------------ L2 ---
    def test_ols_params_match_statsmodels_ols(self):
        """L2: with an intercept, ols_params equals a direct sm.OLS fit on the
        constant-augmented design (intercept first), and ols_resid matches its
        residuals to fp tolerance."""
        report = _run_driver(
            """
            rng = np.random.RandomState(3)
            n = 60
            x1 = rng.normal(size=n)
            x2 = rng.uniform(-2, 2, size=n)
            X = np.column_stack([x1, x2])
            y = 1.3 - 2.0 * x1 + 0.7 * x2 + rng.normal(scale=0.5, size=n)

            out = compare_mean_vs_quantile(y, X, q=0.5, add_intercept=True)

            Xc = sm.add_constant(X)
            ref = sm.OLS(y, Xc).fit()

            op = np.asarray(out['ols_params'], dtype=float)
            orr = np.asarray(out['ols_resid'], dtype=float)
            print(json.dumps({
                'param_max_abs_err': float(np.max(np.abs(op - ref.params))),
                'first_is_intercept': bool(abs(op[0] - ref.params[0]) < 1e-8),
                'nparams': int(op.shape[0]),
                'resid_max_abs_err': float(np.max(np.abs(orr - ref.resid))),
                'resid_len': int(orr.shape[0]),
                'n': n,
            }))
            """
        )
        assert report["nparams"] == 3  # intercept + 2 columns
        assert report["param_max_abs_err"] < 1e-8
        assert report["first_is_intercept"] is True
        assert report["resid_len"] == report["n"]
        assert report["resid_max_abs_err"] < 1e-8

    def test_quantile_params_match_statsmodels_quantreg(self):
        """L2: quantile_params equals a direct sm.QuantReg fit at the supplied q
        on the same intercept-augmented design, and quantile_resid matches its
        residuals. A stub returning OLS params (or ignoring q) fails."""
        report = _run_driver(
            """
            rng = np.random.RandomState(11)
            n = 80
            x = rng.uniform(-3, 3, size=n)
            y = 0.7 + 1.4 * x + rng.normal(scale=0.6, size=n)
            q = 0.3

            out = compare_mean_vs_quantile(y, x, q=q, add_intercept=True)

            Xc = sm.add_constant(x)
            qref = QuantReg(y, Xc).fit(q=q)

            qp = np.asarray(out['quantile_params'], dtype=float)
            qrr = np.asarray(out['quantile_resid'], dtype=float)
            ols_ref = sm.OLS(y, Xc).fit()
            print(json.dumps({
                'qparam_max_abs_err': float(np.max(np.abs(qp - qref.params))),
                'qresid_max_abs_err': float(np.max(np.abs(qrr - qref.resid))),
                'nparams': int(qp.shape[0]),
                # distance from the OLS params: must be non-trivial so that a
                # stub returning OLS params would be detectable here.
                'dist_from_ols': float(np.max(np.abs(qp - ols_ref.params))),
                'q_echo': float(out['q']),
            }))
            """
        )
        assert report["nparams"] == 2
        assert report["qparam_max_abs_err"] < 1e-6
        assert report["qresid_max_abs_err"] < 1e-6
        assert report["q_echo"] == 0.3

    def test_slope_diff_is_elementwise_difference(self):
        """L2: slope_diff equals quantile_params - ols_params elementwise and has
        the same length as the parameter vectors."""
        report = _run_driver(
            """
            rng = np.random.RandomState(4)
            n = 70
            x = rng.normal(size=n)
            y = -0.5 + 2.2 * x + rng.normal(scale=0.5, size=n)
            out = compare_mean_vs_quantile(y, x, q=0.4, add_intercept=True)
            op = np.asarray(out['ols_params'], dtype=float)
            qp = np.asarray(out['quantile_params'], dtype=float)
            sd = np.asarray(out['slope_diff'], dtype=float)
            print(json.dumps({
                'len_ok': sd.shape == op.shape,
                'max_err': float(np.max(np.abs(sd - (qp - op)))),
            }))
            """
        )
        assert report["len_ok"] is True
        assert report["max_err"] < 1e-12

    def test_median_and_mean_agree_on_clean_symmetric_data(self):
        """L2: on clean, symmetric-error data with q=0.5 the median and mean fits
        nearly agree, so slope_diff entries are small in magnitude."""
        report = _run_driver(
            """
            rng = np.random.RandomState(20)
            n = 400
            x = np.linspace(-5, 5, n)
            y = 2.0 + 1.5 * x + rng.normal(scale=0.5, size=n)  # symmetric noise
            out = compare_mean_vs_quantile(y, x, q=0.5, add_intercept=True)
            sd = np.asarray(out['slope_diff'], dtype=float)
            print(json.dumps({
                'max_abs_slope_diff': float(np.max(np.abs(sd))),
                'slope_entry_diff': float(abs(sd[1])),
            }))
            """
        )
        # mean and median nearly coincide for symmetric noise
        assert report["max_abs_slope_diff"] < 0.3, report
        assert report["slope_entry_diff"] < 0.2, report

    def test_quantile_slope_more_robust_to_outliers(self):
        """L2: with a few extreme endog outliers and q=0.5, the conditional-
        quantile slope stays closer to the clean-data slope than the mean-model
        slope does (mean-vs-median robustness discrimination)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(30)
            n = 200
            x = np.linspace(0, 10, n)
            true_slope = 1.5
            y_clean = 3.0 + true_slope * x + rng.normal(scale=0.4, size=n)

            # clean fit to define the target slope
            base = compare_mean_vs_quantile(y_clean, x, q=0.5)
            clean_ols_slope = float(np.asarray(base['ols_params'])[1])
            clean_q_slope = float(np.asarray(base['quantile_params'])[1])

            # contaminate a handful of points with large positive jumps
            y_out = y_clean.copy()
            for idx in (10, 55, 120, 170):
                y_out[idx] += 120.0

            out = compare_mean_vs_quantile(y_out, x, q=0.5)
            ols_slope = float(np.asarray(out['ols_params'])[1])
            q_slope = float(np.asarray(out['quantile_params'])[1])

            ols_dev = abs(ols_slope - clean_ols_slope)
            q_dev = abs(q_slope - clean_q_slope)
            sd1 = float(abs(np.asarray(out['slope_diff'])[1]))
            print(json.dumps({
                'ols_dev': ols_dev,
                'q_dev': q_dev,
                'q_more_robust': q_dev < ols_dev,
                'slope_diff_nonnegligible': sd1,
                'true_slope': true_slope,
                'q_slope': q_slope,
            }))
            """
        )
        # quantile (median) slope is perturbed less by the outliers
        assert report["q_more_robust"] is True, report
        # the perturbation to the mean slope makes slope_diff non-negligible
        assert report["slope_diff_nonnegligible"] > 0.1, report
        # median slope stays near the true slope despite contamination
        assert abs(report["q_slope"] - report["true_slope"]) < 0.5, report

    def test_below_fraction_matches_quantile_residual_sign_split(self):
        """L2: quantile_below_fraction equals the fraction of observations whose
        endog lies strictly below its quantile fitted value, i.e. the fraction of
        strictly-positive quantile residuals (matching the QuantReg fit), and is
        close to q for a reasonable fit."""
        report = _run_driver(
            """
            rng = np.random.RandomState(41)
            n = 500
            x = rng.uniform(-2, 2, size=n)
            y = 1.0 + 0.8 * x + rng.normal(scale=0.7, size=n)
            q = 0.65

            out = compare_mean_vs_quantile(y, x, q=q, add_intercept=True)
            qbf = float(out['quantile_below_fraction'])

            # independent reference: strictly-positive residuals from QuantReg
            Xc = sm.add_constant(x)
            qref = QuantReg(y, Xc).fit(q=q)
            ref_frac = float(np.mean(qref.resid > 0))
            print(json.dumps({
                'qbf': qbf,
                'ref_frac': ref_frac,
                'matches_ref': abs(qbf - ref_frac) < 1e-6,
                'near_q': abs(qbf - q) < 0.06,
                'q': q,
            }))
            """
        )
        assert report["matches_ref"], (
            "quantile_below_fraction %r != residual sign split %r"
            % (report["qbf"], report["ref_frac"])
        )
        assert report["near_q"], report

    def test_below_fraction_tracks_q(self):
        """L2: changing q changes quantile_below_fraction monotonically (a higher
        target quantile leaves a larger fraction below the fitted line). A stub
        returning a constant cannot satisfy both checks."""
        report = _run_driver(
            """
            rng = np.random.RandomState(42)
            n = 600
            x = rng.uniform(0, 5, size=n)
            y = 2.0 + 1.0 * x + rng.normal(scale=0.9, size=n)
            f_lo = float(compare_mean_vs_quantile(y, x, q=0.2)['quantile_below_fraction'])
            f_hi = float(compare_mean_vs_quantile(y, x, q=0.8)['quantile_below_fraction'])
            print(json.dumps({
                'f_lo': f_lo, 'f_hi': f_hi,
                'monotone': f_hi > f_lo,
                'lo_near': abs(f_lo - 0.2) < 0.07,
                'hi_near': abs(f_hi - 0.8) < 0.07,
            }))
            """
        )
        assert report["monotone"] is True, report
        assert report["lo_near"] is True, report
        assert report["hi_near"] is True, report

    def test_no_intercept_param_count(self):
        """L2: add_intercept=False on a single predictor -> both param vectors
        have length 1, and they match the no-constant OLS / QuantReg fits."""
        report = _run_driver(
            """
            rng = np.random.RandomState(2)
            x = np.linspace(1, 6, 40)
            y = 2.7 * x + rng.normal(scale=0.4, size=40)
            out = compare_mean_vs_quantile(y, x, q=0.5, add_intercept=False)

            Xr = np.asarray(x, float).reshape(-1, 1)
            ols_ref = sm.OLS(np.asarray(y, float), Xr).fit()
            q_ref = QuantReg(np.asarray(y, float), Xr).fit(q=0.5)

            op = np.asarray(out['ols_params'], dtype=float)
            qp = np.asarray(out['quantile_params'], dtype=float)
            print(json.dumps({
                'op_len': int(op.shape[0]),
                'qp_len': int(qp.shape[0]),
                'ols_err': float(abs(op[0] - ols_ref.params[0])),
                'q_err': float(abs(qp[0] - q_ref.params[0])),
            }))
            """
        )
        assert report["op_len"] == 1
        assert report["qp_len"] == 1
        assert report["ols_err"] < 1e-8
        assert report["q_err"] < 1e-6

    def test_existing_constant_column_not_duplicated(self):
        """L2: add_intercept=True with an exog that already contains a constant
        column must not add a duplicate constant; param count equals the supplied
        columns and the OLS params match has_constant='skip'."""
        report = _run_driver(
            """
            rng = np.random.RandomState(7)
            n = 60
            ones = np.ones(n)
            x = rng.normal(size=n)
            X = np.column_stack([ones, x])  # already has a constant column
            y = 2.0 + 3.0 * x + rng.normal(scale=0.4, size=n)

            out = compare_mean_vs_quantile(y, X, q=0.5, add_intercept=True)
            op = np.asarray(out['ols_params'], dtype=float)
            qp = np.asarray(out['quantile_params'], dtype=float)

            Xc = sm.add_constant(X, has_constant='skip')
            ref = sm.OLS(y, Xc).fit()
            print(json.dumps({
                'ols_nparams': int(op.shape[0]),
                'q_nparams': int(qp.shape[0]),
                'ncols': int(X.shape[1]),
                'has_nan': bool(np.any(np.isnan(op)) or np.any(np.isnan(qp))),
                'ols_param_err': float(np.max(np.abs(np.sort(op) - np.sort(ref.params)))),
            }))
            """
        )
        assert report["ols_nparams"] == report["ncols"], (
            "duplicate constant was added: %d OLS params for %d supplied columns"
            % (report["ols_nparams"], report["ncols"])
        )
        assert report["q_nparams"] == report["ncols"]
        assert report["has_nan"] is False
        assert report["ols_param_err"] < 1e-8

    def test_invalid_q_raises_value_error(self):
        """L2: q outside the open interval (0, 1) raises ValueError (both q=0 and
        q=1.5), while a valid interior q does not raise."""
        report = _run_driver(
            """
            x = np.linspace(0, 5, 20)
            y = 1.0 + 2.0 * x

            def raised(qv):
                try:
                    compare_mean_vs_quantile(y, x, q=qv)
                    return False
                except ValueError:
                    return True
                except Exception:
                    return 'wrong-exc'

            ok = True
            try:
                compare_mean_vs_quantile(y, x, q=0.5)
            except Exception:
                ok = False
            print(json.dumps({
                'q0': raised(0),
                'q1_5': raised(1.5),
                'q1': raised(1.0),
                'q_neg': raised(-0.2),
                'valid_ok': ok,
            }))
            """
        )
        assert report["q0"] is True, "q=0 must raise ValueError"
        assert report["q1_5"] is True, "q=1.5 must raise ValueError"
        assert report["q1"] is True, "q=1 must raise ValueError"
        assert report["q_neg"] is True, "q<0 must raise ValueError"
        assert report["valid_ok"] is True, "valid interior q must not raise"

    def test_accepts_lists_and_1d_exog(self):
        """L2: plain Python lists and a 1-D exog (single column) are accepted and
        produce the same numeric report as the equivalent ndarray 2-D call."""
        report = _run_driver(
            """
            rng = np.random.RandomState(8)
            x = list(np.linspace(0, 3, 50))
            y = list(0.4 + 1.1 * np.asarray(x) + rng.normal(scale=0.2, size=50))

            out_list = compare_mean_vs_quantile(y, x, q=0.5, add_intercept=True)
            out_arr = compare_mean_vs_quantile(
                np.asarray(y), np.asarray(x).reshape(-1, 1),
                q=0.5, add_intercept=True)

            opl = np.asarray(out_list['ols_params'], dtype=float)
            opa = np.asarray(out_arr['ols_params'], dtype=float)
            qpl = np.asarray(out_list['quantile_params'], dtype=float)
            qpa = np.asarray(out_arr['quantile_params'], dtype=float)
            print(json.dumps({
                'list_nparams': int(opl.shape[0]),
                'ols_param_err': float(np.max(np.abs(opl - opa))),
                'q_param_err': float(np.max(np.abs(qpl - qpa))),
            }))
            """
        )
        assert report["list_nparams"] == 2  # intercept + single column
        assert report["ols_param_err"] < 1e-10
        assert report["q_param_err"] < 1e-6

    def test_native_pytest_passes(self):
        """L2: the doc's native acceptance command for the deliverable's own unit
        tests passes (pytest statsmodels/regression/tests/test_quantile_compare.py)."""
        if not os.path.isfile(self.TEST_PATH):
            pytest.skip("deliverable test module not present: " + self.TEST_PATH)
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                os.path.join(
                    "statsmodels", "regression", "tests",
                    "test_quantile_compare.py",
                ),
                "-q",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
        )
        assert proc.returncode == 0, (
            "native pytest failed\nSTDOUT:\n"
            + proc.stdout[-4000:]
            + "\nSTDERR:\n"
            + proc.stderr[-2000:]
        )
