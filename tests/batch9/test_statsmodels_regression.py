"""Tests for the ``statsmodels-regression`` skill (variant ext9).

Variant task: build a weighted-least-squares convenience helper.  The agent must
create ``statsmodels/regression/wls_helper.py`` exposing a public

    weighted_fit(endog, exog, weights=None, add_intercept=True)

that returns a plain ``dict`` report.  With explicit ``weights`` it must produce
exactly what ``statsmodels``' own WLS estimator gives on the same
intercept-augmented design and weights; with ``weights=None`` it must derive
weights itself (inversely proportional to a fitted-value-driven variance
estimate so high-variance observations get *smaller* weight), set
``derived_weights=True`` and report the *weighted* fit.  A non-positive supplied
weight must raise ``ValueError``; an existing constant column must not be
duplicated; lists and a 1-D ``exog`` must be accepted.

Verification strategy.  Every reported quantity is independently re-derived in a
fresh subprocess (PYTHONPATH cleared, rooted at REPO_DIR) from
``statsmodels.api``'s own ``WLS`` / ``OLS`` / ``add_constant`` machinery and
compared to floating-point tolerance — no source-text or keyword matching.
Discriminative cases plant a known heteroskedastic pattern and assert the
derived weights actually down-weight the high-variance rows (a stub that returns
uniform weights, ignores ``weights``, hardcodes ``derived_weights``, or fits OLS
instead of WLS fails).  L1 cases check the deliverable's existence, signature and
documented keys/types; L2 cases run real fits and compare numbers.  The final
case drives the doc's native acceptance command,
``pytest statsmodels/regression/tests/test_wls_helper.py -q``.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/statsmodels"


# Bootstrap: import the agent's helper from REPO_DIR alongside a reference
# statsmodels implementation.  Prepended to every driver so it runs from
# anywhere with PYTHONPATH cleared.
_BOOTSTRAP = textwrap.dedent(
    """
    import sys, os, json
    REPO_DIR = {repo!r}
    sys.path.insert(0, REPO_DIR)
    import numpy as np
    import statsmodels.api as sm
    from statsmodels.regression.wls_helper import weighted_fit
    """
).format(repo=REPO_DIR)


def _run_driver(body, timeout=300):
    """Execute *body* (which must print one JSON object) in a fresh interpreter
    rooted at REPO_DIR with PYTHONPATH cleared.  Returns the parsed dict."""
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
        REPO_DIR, "statsmodels", "regression", "wls_helper.py"
    )
    TEST_PATH = os.path.join(
        REPO_DIR, "statsmodels", "regression", "tests", "test_wls_helper.py"
    )

    # ------------------------------------------------------------------ L1 ---
    def test_module_file_exists(self):
        """L1: the new wls_helper.py deliverable exists and is non-trivial."""
        assert os.path.isfile(self.MODULE_PATH), (
            "expected new module at " + self.MODULE_PATH
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_function_importable_with_signature(self):
        """L1: weighted_fit is importable and has the documented parameters and
        defaults (weights=None, add_intercept=True)."""
        report = _run_driver(
            """
            import inspect
            sig = inspect.signature(weighted_fit)
            params = list(sig.parameters)
            w_def = (sig.parameters['weights'].default
                     if 'weights' in sig.parameters else 'MISSING')
            ai_def = (sig.parameters['add_intercept'].default
                      if 'add_intercept' in sig.parameters else 'MISSING')
            print(json.dumps({
                'params': params,
                'weights_default_none': w_def is None,
                'add_intercept_default': ai_def is True,
            }))
            """
        )
        assert report["params"][:2] == ["endog", "exog"], report["params"]
        assert "weights" in report["params"]
        assert "add_intercept" in report["params"]
        assert report["weights_default_none"] is True
        assert report["add_intercept_default"] is True

    def test_returns_dict_with_required_keys(self):
        """L1: weighted_fit returns a plain dict containing every documented key."""
        report = _run_driver(
            """
            x = np.linspace(0, 10, 30)
            y = 1.0 + 2.0 * x
            out = weighted_fit(list(y), list(x))
            print(json.dumps({
                'is_dict': type(out).__name__ == 'dict',
                'keys': sorted(out.keys()),
            }))
            """
        )
        assert report["is_dict"] is True, "must return a plain dict"
        required = {
            "params", "bse", "weights", "rsquared",
            "derived_weights", "nobs",
        }
        missing = required - set(report["keys"])
        assert not missing, "missing keys: " + str(sorted(missing))

    def test_key_types_and_shapes(self):
        """L1: params/bse/weights are 1-D ndarrays, derived_weights is a bool,
        nobs is an int and weights has length nobs and is strictly positive."""
        report = _run_driver(
            """
            rng = np.random.RandomState(0)
            n = 25
            x = np.linspace(0, 5, n)
            y = 0.5 + 1.5 * x + rng.normal(scale=0.3, size=n)
            w = np.linspace(1.0, 3.0, n)
            out = weighted_fit(y, x, weights=w)
            params = np.asarray(out['params'])
            bse = np.asarray(out['bse'])
            weights = np.asarray(out['weights'], dtype=float)
            print(json.dumps({
                'params_1d': params.ndim == 1,
                'bse_1d': bse.ndim == 1,
                'weights_1d': weights.ndim == 1,
                'weights_len': int(weights.shape[0]),
                'weights_all_pos': bool(np.all(weights > 0)),
                'dw_is_bool': type(out['derived_weights']).__name__ == 'bool',
                'nobs_is_int': float(out['nobs']) == int(out['nobs']),
                'nobs': int(out['nobs']),
                'rsq_is_float': isinstance(out['rsquared'], float)
                                or float(out['rsquared']) == float(out['rsquared']),
            }))
            """
        )
        assert report["params_1d"] and report["bse_1d"] and report["weights_1d"]
        assert report["nobs"] == 25
        assert report["weights_len"] == 25
        assert report["weights_all_pos"] is True
        assert report["dw_is_bool"] is True
        assert report["nobs_is_int"] is True
        assert report["rsq_is_float"] is True

    # ------------------------------------------------------------------ L2 ---
    def test_explicit_weights_match_statsmodels_wls(self):
        """L2: with explicit weights and an intercept, params/bse/rsquared match a
        direct statsmodels WLS on the intercept-augmented design to fp tolerance,
        and params[0] is the intercept (an OLS-instead-of-WLS stub fails)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(3)
            n = 60
            x1 = rng.normal(size=n)
            x2 = rng.uniform(-2, 2, size=n)
            X = np.column_stack([x1, x2])
            y = 1.3 - 2.0 * x1 + 0.7 * x2 + rng.normal(scale=0.5, size=n)
            w = np.linspace(0.5, 4.0, n)

            out = weighted_fit(y, X, weights=w, add_intercept=True)

            Xc = sm.add_constant(X)
            ref = sm.WLS(y, Xc, weights=w).fit()
            ref_ols = sm.OLS(y, Xc).fit()

            params = np.asarray(out['params'], dtype=float)
            bse = np.asarray(out['bse'], dtype=float)
            print(json.dumps({
                'param_max_abs_err': float(np.max(np.abs(params - ref.params))),
                'bse_max_abs_err': float(np.max(np.abs(bse - ref.bse))),
                'rsq_err': abs(float(out['rsquared']) - float(ref.rsquared)),
                'first_is_intercept': bool(abs(params[0] - ref.params[0]) < 1e-8),
                'differs_from_ols': float(np.max(np.abs(params - ref_ols.params))),
                'nparams': int(params.shape[0]),
            }))
            """
        )
        assert report["nparams"] == 3  # intercept + 2 columns
        assert report["param_max_abs_err"] < 1e-7
        assert report["bse_max_abs_err"] < 1e-7
        assert report["rsq_err"] < 1e-9
        assert report["first_is_intercept"] is True
        # WLS with non-uniform weights must differ from plain OLS -> not a stub.
        assert report["differs_from_ols"] > 1e-3, report

    def test_explicit_weights_derived_flag_false_and_echoed(self):
        """L2: supplying weights -> derived_weights is False and the reported
        'weights' equals the supplied array element-for-element."""
        report = _run_driver(
            """
            rng = np.random.RandomState(9)
            n = 40
            x = np.linspace(0, 8, n)
            y = 2.0 + 1.1 * x + rng.normal(scale=0.5, size=n)
            w = np.linspace(1.0, 5.0, n)
            out = weighted_fit(y, x, weights=w)
            rep_w = np.asarray(out['weights'], dtype=float)
            print(json.dumps({
                'derived': bool(out['derived_weights']),
                'weights_max_abs_err': float(np.max(np.abs(rep_w - w))),
            }))
            """
        )
        assert report["derived"] is False
        assert report["weights_max_abs_err"] < 1e-12

    def test_uniform_weights_equal_ols(self):
        """L2: explicit uniform (constant) weights reproduce the OLS fit exactly,
        confirming the weighting actually enters the normal equations."""
        report = _run_driver(
            """
            rng = np.random.RandomState(2)
            n = 50
            x = rng.normal(size=n)
            y = 0.7 + 2.5 * x + rng.normal(scale=0.4, size=n)
            w = np.ones(n) * 3.0
            out = weighted_fit(y, x, weights=w)
            Xc = sm.add_constant(x)
            ref = sm.OLS(y, Xc).fit()
            params = np.asarray(out['params'], dtype=float)
            print(json.dumps({
                'param_err': float(np.max(np.abs(params - ref.params))),
                'rsq_err': abs(float(out['rsquared']) - float(ref.rsquared)),
            }))
            """
        )
        assert report["param_err"] < 1e-8
        assert report["rsq_err"] < 1e-9

    def test_nonpositive_weight_raises_valueerror(self):
        """L2: a supplied weights array containing a zero or a negative value
        raises ValueError (boundary/error case)."""
        report = _run_driver(
            """
            n = 20
            x = np.linspace(0, 5, n)
            y = 1.0 + 2.0 * x
            results = {}
            for label, badval in [('zero', 0.0), ('neg', -1.0)]:
                w = np.linspace(1.0, 2.0, n)
                w[5] = badval
                try:
                    weighted_fit(y, x, weights=w)
                    results[label] = 'no_error'
                except ValueError:
                    results[label] = 'value_error'
                except Exception as exc:
                    results[label] = 'other:' + type(exc).__name__
            # a fully-positive control must succeed
            ok = True
            try:
                weighted_fit(y, x, weights=np.linspace(1.0, 2.0, n))
            except Exception:
                ok = False
            results['control_ok'] = ok
            print(json.dumps(results))
            """
        )
        assert report["zero"] == "value_error", report
        assert report["neg"] == "value_error", report
        assert report["control_ok"] is True

    def test_derived_weights_downweight_high_variance(self):
        """L2: with weights=None on heteroskedastic data whose error spread grows
        with the fitted value, derived_weights is True and the derived weights are
        strictly smaller for the high-variance tail than for the low-variance head
        (a uniform-weight stub fails this ordering check)."""
        report = _run_driver(
            """
            n = 200
            x = np.linspace(1.0, 20.0, n)
            rng = np.random.RandomState(5)
            # variance grows strongly with x (and hence with the fitted value)
            y = 1.0 + 2.0 * x + rng.normal(scale=0.05 + 0.9 * x, size=n)
            out = weighted_fit(y, x, weights=None)
            w = np.asarray(out['weights'], dtype=float)
            k = 25
            low_var_w = float(np.mean(w[:k]))     # small fitted value -> low var
            high_var_w = float(np.mean(w[-k:]))   # large fitted value -> high var
            print(json.dumps({
                'derived': bool(out['derived_weights']),
                'all_pos': bool(np.all(w > 0)),
                'low_var_w': low_var_w,
                'high_var_w': high_var_w,
                'spread': float(w.max() / w.min()),
            }))
            """
        )
        assert report["derived"] is True
        assert report["all_pos"] is True
        # high-variance observations must receive smaller weight
        assert report["high_var_w"] < report["low_var_w"], report
        # the weights must be genuinely non-uniform, not a token perturbation
        assert report["spread"] > 1.5, report

    def test_derived_fit_is_weighted_not_ols(self):
        """L2: when weights are derived, the reported params/bse/rsquared equal a
        direct statsmodels WLS using those exact derived weights, and differ from
        a plain OLS fit -> the reported fit is the weighted one."""
        report = _run_driver(
            """
            n = 160
            x = np.linspace(1.0, 15.0, n)
            rng = np.random.RandomState(11)
            y = 0.5 + 1.7 * x + rng.normal(scale=0.1 + 0.8 * x, size=n)
            out = weighted_fit(y, x, weights=None, add_intercept=True)
            w = np.asarray(out['weights'], dtype=float)
            params = np.asarray(out['params'], dtype=float)
            bse = np.asarray(out['bse'], dtype=float)

            Xc = sm.add_constant(x)
            ref_wls = sm.WLS(y, Xc, weights=w).fit()
            ref_ols = sm.OLS(y, Xc).fit()
            print(json.dumps({
                'param_vs_wls': float(np.max(np.abs(params - ref_wls.params))),
                'bse_vs_wls': float(np.max(np.abs(bse - ref_wls.bse))),
                'rsq_vs_wls': abs(float(out['rsquared']) - float(ref_wls.rsquared)),
                'param_vs_ols': float(np.max(np.abs(params - ref_ols.params))),
            }))
            """
        )
        assert report["param_vs_wls"] < 1e-7, report
        assert report["bse_vs_wls"] < 1e-7, report
        assert report["rsq_vs_wls"] < 1e-9, report
        # the derived-weight fit must be meaningfully different from OLS
        assert report["param_vs_ols"] > 1e-4, report

    def test_existing_constant_column_not_duplicated(self):
        """L2: add_intercept=True with an exog that already has a constant column
        must not add a duplicate constant; params count equals supplied columns,
        the design stays full-rank, and the WLS fit matches has_constant='skip'."""
        report = _run_driver(
            """
            rng = np.random.RandomState(7)
            n = 60
            ones = np.ones(n)
            x = rng.normal(size=n)
            X = np.column_stack([ones, x])  # already contains a constant column
            y = 2.0 + 3.0 * x + rng.normal(scale=0.4, size=n)
            w = np.linspace(0.5, 3.0, n)

            out = weighted_fit(y, X, weights=w, add_intercept=True)
            params = np.asarray(out['params'], dtype=float)

            Xc = sm.add_constant(X, has_constant='skip')
            ref = sm.WLS(y, Xc, weights=w).fit()
            rank = int(np.linalg.matrix_rank(Xc))
            print(json.dumps({
                'nparams': int(params.shape[0]),
                'ncols': int(X.shape[1]),
                'full_rank': rank == X.shape[1],
                'has_nan': bool(np.any(np.isnan(params))),
                'rsq': float(out['rsquared']),
                'ref_rsq': float(ref.rsquared),
                'param_err': float(np.max(np.abs(np.sort(params) - np.sort(ref.params)))),
            }))
            """
        )
        assert report["nparams"] == report["ncols"], (
            "duplicate constant was added: %d params for %d supplied columns"
            % (report["nparams"], report["ncols"])
        )
        assert report["full_rank"] is True
        assert report["has_nan"] is False
        assert abs(report["rsq"] - report["ref_rsq"]) < 1e-9
        assert report["param_err"] < 1e-7

    def test_accepts_lists_and_1d_exog(self):
        """L2: plain Python lists and a 1-D exog (single column) are accepted and
        produce the same numeric report as the equivalent ndarray 2-D call."""
        report = _run_driver(
            """
            rng = np.random.RandomState(8)
            x = list(np.linspace(0, 3, 30))
            y = list(0.4 + 1.1 * np.asarray(x) + rng.normal(scale=0.2, size=30))
            w = list(np.linspace(1.0, 2.0, 30))

            out_list = weighted_fit(y, x, weights=w, add_intercept=True)
            out_arr = weighted_fit(
                np.asarray(y), np.asarray(x).reshape(-1, 1),
                weights=np.asarray(w), add_intercept=True)

            pl = np.asarray(out_list['params'], dtype=float)
            pa = np.asarray(out_arr['params'], dtype=float)
            print(json.dumps({
                'list_nparams': int(pl.shape[0]),
                'param_err': float(np.max(np.abs(pl - pa))),
                'rsq_err': abs(float(out_list['rsquared']) - float(out_arr['rsquared'])),
                'nobs': int(out_list['nobs']),
            }))
            """
        )
        assert report["list_nparams"] == 2  # intercept + single column
        assert report["nobs"] == 30
        assert report["param_err"] < 1e-12
        assert report["rsq_err"] < 1e-12

    def test_no_intercept_param_count(self):
        """L2: add_intercept=False on a single predictor with explicit weights ->
        len(params)==1 and the coefficient matches a no-constant statsmodels WLS."""
        report = _run_driver(
            """
            rng = np.random.RandomState(4)
            n = 30
            x = np.linspace(1, 6, n)
            y = 2.7 * x + rng.normal(scale=0.4, size=n)
            w = np.linspace(0.5, 2.0, n)
            out = weighted_fit(y, x, weights=w, add_intercept=False)
            ref = sm.WLS(y, np.asarray(x, float).reshape(-1, 1), weights=w).fit()
            params = np.asarray(out['params'], dtype=float)
            print(json.dumps({
                'nparams': int(params.shape[0]),
                'nobs': int(out['nobs']),
                'param0': float(params[0]),
                'ref_param0': float(ref.params[0]),
            }))
            """
        )
        assert report["nparams"] == 1
        assert report["nobs"] == 30
        assert abs(report["param0"] - report["ref_param0"]) < 1e-8

    def test_native_pytest_passes(self):
        """L2: the doc's native acceptance command for the deliverable's own unit
        tests passes (pytest statsmodels/regression/tests/test_wls_helper.py)."""
        if not os.path.isfile(self.TEST_PATH):
            pytest.skip("deliverable test module not present: " + self.TEST_PATH)
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                os.path.join(
                    "statsmodels", "regression", "tests",
                    "test_wls_helper.py",
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
