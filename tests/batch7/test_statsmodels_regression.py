"""Tests for the ``statsmodels-regression`` skill (variant ext7).

Variant task: build a *residual autocorrelation diagnostics* helper. The
deliverable is a new module ``statsmodels/tsa/resid_autocorr.py`` exposing a
single public function::

    def autocorrelation_report(resid, lags=10, alpha=0.05, model_df=0): ...

It takes a 1-D residual series and returns a plain ``dict`` with at least the
keys ``acf`` (ndarray of lags 0..lags, lag-0 == 1.0), ``durbin_watson`` (float
in [0, 4]), ``ljungbox_stat`` (float portmanteau stat at lag ``lags``, adjusted
for ``model_df``), ``ljungbox_pvalue`` (float), ``autocorrelated`` (bool, True
iff p-value < alpha) and ``first_significant_lag`` (int >= 1 of the first lag in
1..lags whose |acf| exceeds 1.96/sqrt(n), else None).

Verification strategy: every reported quantity is independently re-derived from
statsmodels' OWN machinery -- ``statsmodels.tsa.stattools.acf``,
``statsmodels.stats.stattools.durbin_watson`` and
``statsmodels.stats.diagnostic.acorr_ljungbox`` (with ``model_df`` passed
through) -- and compared to floating-point tolerance. The boolean / first-lag
semantics are checked on deliberately constructed white-noise and strongly
positively-autocorrelated series, where a naive or hardcoded implementation
(fixed dict, ignoring ``model_df``, ignoring ``alpha``, hardcoding DW or the
significance band) cannot satisfy the cases.

L1 cases check the deliverable file exists and the function is importable with
the right signature and returns the documented keys/types. L2 cases run the
agent's function in a subprocess that emits JSON (robust to PYTHONPATH being
cleared and to import-time side effects), then compare against an independent
statsmodels computation done in the same subprocess. The final case drives the
native acceptance command ``pytest
statsmodels/tsa/tests/test_resid_autocorr.py -q``.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/statsmodels"


# Bootstrap that imports the agent's module from REPO_DIR and exposes both the
# helper under test and the reference statsmodels machinery. Each driver script
# below prepends this so it can run from anywhere with PYTHONPATH cleared.
_BOOTSTRAP = textwrap.dedent(
    """
    import sys, os, json
    REPO_DIR = {repo!r}
    sys.path.insert(0, REPO_DIR)
    import numpy as np
    from statsmodels.tsa.stattools import acf as _ref_acf
    from statsmodels.stats.stattools import durbin_watson as _ref_dw
    from statsmodels.stats.diagnostic import acorr_ljungbox as _ref_lb
    from statsmodels.tsa.resid_autocorr import autocorrelation_report


    def _ar1_series(n, phi, seed):
        rng = np.random.RandomState(seed)
        e = rng.normal(size=n)
        x = np.empty(n)
        x[0] = e[0]
        for i in range(1, n):
            x[i] = phi * x[i - 1] + e[i]
        return x
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
        REPO_DIR, "statsmodels", "tsa", "resid_autocorr.py"
    )
    TEST_PATH = os.path.join(
        REPO_DIR, "statsmodels", "tsa", "tests", "test_resid_autocorr.py"
    )

    # ------------------------------------------------------------------ L1 ---
    def test_module_file_exists(self):
        """L1: the new resid_autocorr.py deliverable exists and is non-trivial."""
        assert os.path.isfile(self.MODULE_PATH), (
            "expected new module at " + self.MODULE_PATH
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_function_importable_with_signature(self):
        """L1: autocorrelation_report is importable with the documented params
        and the right defaults (lags=10, alpha=0.05, model_df=0)."""
        report = _run_driver(
            """
            import inspect
            sig = inspect.signature(autocorrelation_report)
            params = list(sig.parameters)
            defaults = {
                k: (v.default if v.default is not inspect._empty else '__req__')
                for k, v in sig.parameters.items()
            }
            print(json.dumps({'params': params, 'defaults': defaults}))
            """
        )
        assert report["params"][0] == "resid", report["params"]
        for name in ("lags", "alpha", "model_df"):
            assert name in report["params"], name
        assert report["defaults"]["lags"] == 10
        assert abs(float(report["defaults"]["alpha"]) - 0.05) < 1e-12
        assert int(report["defaults"]["model_df"]) == 0

    def test_returns_dict_with_required_keys(self):
        """L1: the helper returns a plain dict containing every documented key."""
        report = _run_driver(
            """
            x = _ar1_series(120, 0.0, seed=1)
            out = autocorrelation_report(list(x), lags=8)
            print(json.dumps({
                'is_dict': type(out).__name__ == 'dict',
                'keys': sorted(out.keys()),
            }))
            """
        )
        assert report["is_dict"] is True, "must return a plain dict"
        required = {
            "acf", "durbin_watson", "ljungbox_stat", "ljungbox_pvalue",
            "autocorrelated", "first_significant_lag",
        }
        missing = required - set(report["keys"])
        assert not missing, "missing keys: " + str(sorted(missing))

    def test_acf_shape_and_types(self):
        """L1: acf has length lags+1 with lag-0 == 1.0, and the scalar fields are
        of the documented Python types (float / bool / int-or-None)."""
        report = _run_driver(
            """
            x = _ar1_series(100, 0.0, seed=2)
            lags = 7
            out = autocorrelation_report(x, lags=lags)
            acf = np.asarray(out['acf'], dtype=float)
            fsl = out['first_significant_lag']
            print(json.dumps({
                'len': int(acf.shape[0]),
                'lag0': float(acf[0]),
                'dw_is_float': isinstance(out['durbin_watson'], float),
                'stat_is_float': isinstance(out['ljungbox_stat'], float),
                'p_is_float': isinstance(out['ljungbox_pvalue'], float),
                'ac_is_bool': isinstance(out['autocorrelated'], bool),
                'fsl_ok': (fsl is None) or isinstance(fsl, int),
            }))
            """
        )
        assert report["len"] == 8  # lags + 1
        assert abs(report["lag0"] - 1.0) < 1e-12
        assert report["dw_is_float"] is True
        assert report["stat_is_float"] is True
        assert report["p_is_float"] is True
        assert report["ac_is_bool"] is True
        assert report["fsl_ok"] is True

    # ------------------------------------------------------------------ L2 ---
    def test_acf_matches_statsmodels(self):
        """L2: the full acf vector matches statsmodels.tsa.stattools.acf for the
        same series and lag count (a hardcoded / approximate acf cannot pass)."""
        report = _run_driver(
            """
            x = _ar1_series(200, 0.6, seed=3)
            lags = 12
            out = autocorrelation_report(x, lags=lags)
            got = np.asarray(out['acf'], dtype=float)
            ref = _ref_acf(np.asarray(x, float), nlags=lags, fft=True)
            print(json.dumps({
                'len_got': int(got.shape[0]),
                'len_ref': int(ref.shape[0]),
                'max_abs_err': float(np.max(np.abs(got - ref))),
            }))
            """
        )
        assert report["len_got"] == report["len_ref"] == 13
        assert report["max_abs_err"] < 1e-9, report

    def test_durbin_watson_matches_and_in_range(self):
        """L2: durbin_watson equals statsmodels.stats.stattools.durbin_watson on
        the raw residuals and lies in [0, 4]."""
        report = _run_driver(
            """
            x = _ar1_series(150, 0.4, seed=4)
            out = autocorrelation_report(x, lags=10)
            dw = float(out['durbin_watson'])
            ref = float(_ref_dw(np.asarray(x, float)))
            print(json.dumps({
                'dw': dw, 'ref': ref,
                'err': abs(dw - ref),
                'in_range': 0.0 <= dw <= 4.0,
            }))
            """
        )
        assert report["in_range"] is True
        assert report["err"] < 1e-9, report

    def test_ljungbox_matches_statsmodels_no_modeldf(self):
        """L2: ljungbox_stat / ljungbox_pvalue equal acorr_ljungbox's lb_stat /
        lb_pvalue at lag == lags when model_df is 0."""
        report = _run_driver(
            """
            x = _ar1_series(180, 0.5, seed=5)
            lags = 10
            out = autocorrelation_report(x, lags=lags, model_df=0)
            ref = _ref_lb(np.asarray(x, float), lags=[lags], model_df=0,
                          return_df=True)
            ref_stat = float(ref['lb_stat'].iloc[-1])
            ref_p = float(ref['lb_pvalue'].iloc[-1])
            print(json.dumps({
                'stat': float(out['ljungbox_stat']),
                'p': float(out['ljungbox_pvalue']),
                'ref_stat': ref_stat,
                'ref_p': ref_p,
                'is_prob': 0.0 <= float(out['ljungbox_pvalue']) <= 1.0,
            }))
            """
        )
        assert report["is_prob"] is True
        assert abs(report["stat"] - report["ref_stat"]) < 1e-7, report
        assert abs(report["p"] - report["ref_p"]) < 1e-9, report

    def test_model_df_is_passed_through(self):
        """L2: model_df must reach the portmanteau computation. With model_df>0
        the reported p-value matches acorr_ljungbox(..., model_df=k) and DIFFERS
        from the model_df=0 result -- an implementation that ignores model_df
        fails this discrimination."""
        report = _run_driver(
            """
            x = _ar1_series(200, 0.45, seed=6)
            lags, k = 12, 3
            out = autocorrelation_report(x, lags=lags, model_df=k)
            ref = _ref_lb(np.asarray(x, float), lags=[lags], model_df=k,
                          return_df=True)
            ref0 = _ref_lb(np.asarray(x, float), lags=[lags], model_df=0,
                           return_df=True)
            print(json.dumps({
                'p': float(out['ljungbox_pvalue']),
                'stat': float(out['ljungbox_stat']),
                'ref_p_k': float(ref['lb_pvalue'].iloc[-1]),
                'ref_p_0': float(ref0['lb_pvalue'].iloc[-1]),
            }))
            """
        )
        # the statistic is unchanged by model_df but the p-value reflects the
        # reduced degrees of freedom; matching the k>0 reference proves the
        # parameter was threaded through.
        assert abs(report["p"] - report["ref_p_k"]) < 1e-9, report
        # and the k>0 p-value must genuinely differ from the k=0 one.
        assert abs(report["ref_p_k"] - report["ref_p_0"]) > 1e-6
        assert abs(report["p"] - report["ref_p_0"]) > 1e-6, (
            "model_df appears to be ignored: %r" % report
        )

    def test_white_noise_branch(self):
        """L2: on white-noise-like residuals -> DW near 2, large Ljung-Box
        p-value, autocorrelated False, first_significant_lag None."""
        report = _run_driver(
            """
            x = _ar1_series(400, 0.0, seed=7)
            out = autocorrelation_report(x, lags=10, alpha=0.05)
            print(json.dumps({
                'dw': float(out['durbin_watson']),
                'p': float(out['ljungbox_pvalue']),
                'autocorr': bool(out['autocorrelated']),
                'fsl': out['first_significant_lag'],
            }))
            """
        )
        assert abs(report["dw"] - 2.0) < 0.3, report
        assert report["p"] > 0.05, report
        assert report["autocorr"] is False, report
        assert report["fsl"] is None, report

    def test_autocorrelated_branch(self):
        """L2: on strongly positively-autocorrelated residuals -> DW well below
        2, tiny Ljung-Box p-value, autocorrelated True, and first_significant_lag
        is a small integer (typically 1)."""
        report = _run_driver(
            """
            x = _ar1_series(300, 0.8, seed=8)
            out = autocorrelation_report(x, lags=10, alpha=0.05)
            print(json.dumps({
                'dw': float(out['durbin_watson']),
                'p': float(out['ljungbox_pvalue']),
                'autocorr': bool(out['autocorrelated']),
                'fsl': out['first_significant_lag'],
            }))
            """
        )
        assert report["dw"] < 1.5, report
        assert report["p"] < 0.01, report
        assert report["autocorr"] is True, report
        assert isinstance(report["fsl"], int) and report["fsl"] >= 1, report
        assert report["fsl"] == 1, report

    def test_autocorrelated_flag_respects_alpha(self):
        """L2: the autocorrelated flag is exactly (ljungbox_pvalue < alpha). We
        pick a series and two alphas straddling its p-value and assert the flag
        flips accordingly -- a hardcoded boolean cannot satisfy both calls."""
        report = _run_driver(
            """
            # mild autocorrelation so the p-value lands strictly inside (0, 1)
            x = _ar1_series(60, 0.25, seed=9)
            base = autocorrelation_report(x, lags=10)
            p = float(base['ljungbox_pvalue'])
            assert 1e-6 < p < 1.0 - 1e-6, p
            lo = max(p / 2.0, 1e-9)          # alpha below p  -> flag False
            hi = min(p + (1.0 - p) / 2.0, 1.0 - 1e-9)  # alpha above p -> True
            out_lo = autocorrelation_report(x, lags=10, alpha=lo)
            out_hi = autocorrelation_report(x, lags=10, alpha=hi)
            print(json.dumps({
                'p': p,
                'flag_lo': bool(out_lo['autocorrelated']),
                'flag_hi': bool(out_hi['autocorrelated']),
            }))
            """
        )
        assert report["flag_lo"] is False, report
        assert report["flag_hi"] is True, report

    def test_first_significant_lag_definition(self):
        """L2: first_significant_lag is the first lag in 1..lags whose |acf|
        exceeds 1.96/sqrt(n); recompute it independently from the reference acf
        and require an exact integer match (None when nothing exceeds)."""
        report = _run_driver(
            """
            results = []
            for phi, seed in [(0.0, 21), (0.85, 22), (0.6, 23)]:
                lags = 10
                x = _ar1_series(250, phi, seed)
                n = x.shape[0]
                out = autocorrelation_report(x, lags=lags)
                ref_acf = _ref_acf(np.asarray(x, float), nlags=lags, fft=True)
                band = 1.96 / np.sqrt(n)
                expected = None
                for k in range(1, lags + 1):
                    if abs(ref_acf[k]) > band:
                        expected = k
                        break
                results.append({'phi': phi,
                                'got': out['first_significant_lag'],
                                'expected': expected})
            print(json.dumps(results))
            """
        )
        for row in report:
            assert row["got"] == row["expected"], row

    def test_accepts_list_array_and_series_equivalently(self):
        """L2: a list, an ndarray and a pandas Series carrying the same residuals
        produce identical numeric reports (input-type robustness)."""
        report = _run_driver(
            """
            import pandas as pd
            x = _ar1_series(140, 0.5, seed=10)
            lags = 9
            o_arr = autocorrelation_report(np.asarray(x, float), lags=lags)
            o_lst = autocorrelation_report(list(x), lags=lags)
            o_ser = autocorrelation_report(pd.Series(x), lags=lags)

            def acf_err(a, b):
                return float(np.max(np.abs(
                    np.asarray(a['acf'], float) - np.asarray(b['acf'], float))))

            print(json.dumps({
                'acf_err_lst': acf_err(o_arr, o_lst),
                'acf_err_ser': acf_err(o_arr, o_ser),
                'dw_err_lst': abs(float(o_arr['durbin_watson']) - float(o_lst['durbin_watson'])),
                'dw_err_ser': abs(float(o_arr['durbin_watson']) - float(o_ser['durbin_watson'])),
                'p_err_lst': abs(float(o_arr['ljungbox_pvalue']) - float(o_lst['ljungbox_pvalue'])),
                'p_err_ser': abs(float(o_arr['ljungbox_pvalue']) - float(o_ser['ljungbox_pvalue'])),
                'fsl_same': (o_arr['first_significant_lag'] == o_lst['first_significant_lag']
                             == o_ser['first_significant_lag']),
            }))
            """
        )
        assert report["acf_err_lst"] < 1e-12, report
        assert report["acf_err_ser"] < 1e-12, report
        assert report["dw_err_lst"] < 1e-12, report
        assert report["dw_err_ser"] < 1e-12, report
        assert report["p_err_lst"] < 1e-12, report
        assert report["p_err_ser"] < 1e-12, report
        assert report["fsl_same"] is True, report

    def test_native_pytest_passes(self):
        """L2: the acceptance command for the deliverable's own unit tests passes
        (pytest statsmodels/tsa/tests/test_resid_autocorr.py)."""
        if not os.path.isfile(self.TEST_PATH):
            pytest.skip("deliverable test module not present: " + self.TEST_PATH)
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                os.path.join(
                    "statsmodels", "tsa", "tests",
                    "test_resid_autocorr.py",
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
