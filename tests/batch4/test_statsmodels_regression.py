"""Tests for the ``statsmodels-regression`` skill (variant ext4).

Variant task: build an ARIMA forecast helper with a stationarity pre-check.
The deliverable is ``statsmodels/tsa/arima_forecast_helper.py`` exposing a
public function::

    forecast_series(y, steps=5, max_diff=1, alpha=0.05) -> dict

The helper runs a unit-root (ADF) stationarity test on the raw series, chooses
an integration order ``d`` (driven by the test, capped at ``max_diff``), fits an
autoregressive-integrated model, and returns a structured ``dict`` report with
keys ``d``, ``adf_pvalue``, ``forecast``, ``lower``, ``upper``, ``aic`` and
``resid_ljungbox_pvalue``. Forecast / interval arrays are on the **original**
scale of ``y`` and have length ``steps``.

Verification strategy
---------------------
L1 cases check the deliverable file exists, that ``forecast_series`` is
importable with the exact signature/defaults, and that it returns a plain dict
with the documented keys and array lengths.

L2 cases run the agent's helper in a fresh subprocess (PYTHONPATH cleared,
rooted at REPO_DIR, emitting one JSON line) and independently re-derive the
discriminating quantities from statsmodels' own machinery:

* ``adf_pvalue`` must equal ``adfuller(y)[1]`` on the *raw* series.
* ``d`` selection must respond to the data: a random-walk-like (non-stationary)
  series yields ``d == 1`` (when ``max_diff >= 1``) and a large ADF p-value; a
  stationary mean-reverting series yields ``d == 0`` and a small ADF p-value;
  ``max_diff == 0`` forces ``d == 0`` even on a trending series.
* the interval brackets the point forecast elementwise on the original scale,
  ``aic`` and ``resid_ljungbox_pvalue`` are finite probabilities/floats, and
  the helper accepts lists, ndarrays and pandas Series with identical results.

Naive / hardcoded implementations (fixed ``d``, fixed p-value, forecast left in
differenced space, or interval that does not bracket the point forecast) cannot
satisfy these checks.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/statsmodels"


# Bootstrap imported by every driver: roots the agent's module at REPO_DIR and
# brings in a reference statsmodels stack for independent verification.
_BOOTSTRAP = textwrap.dedent(
    """
    import sys, os, json
    REPO_DIR = {repo!r}
    sys.path.insert(0, REPO_DIR)
    import numpy as np
    from statsmodels.tsa.stattools import adfuller
    from statsmodels.tsa.arima_forecast_helper import forecast_series
    """
).format(repo=REPO_DIR)


def _run_driver(body, timeout=300):
    """Execute *body* (which must print one JSON object as its last stdout line)
    in a fresh interpreter rooted at REPO_DIR with PYTHONPATH cleared."""
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
        REPO_DIR, "statsmodels", "tsa", "arima_forecast_helper.py"
    )
    TEST_PATH = os.path.join(
        REPO_DIR, "statsmodels", "tsa", "tests",
        "test_arima_forecast_helper.py",
    )

    # ------------------------------------------------------------------ L1 ---
    def test_module_file_exists(self):
        """L1: the new arima_forecast_helper.py deliverable exists and is non-trivial."""
        assert os.path.isfile(self.MODULE_PATH), (
            "expected new module at " + self.MODULE_PATH
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_function_importable_with_signature(self):
        """L1: forecast_series is importable with the exact params and defaults."""
        report = _run_driver(
            """
            import inspect
            sig = inspect.signature(forecast_series)
            params = list(sig.parameters)
            defaults = {
                k: (v.default if v.default is not inspect._empty else None)
                for k, v in sig.parameters.items()
            }
            print(json.dumps({'params': params, 'defaults': defaults}))
            """
        )
        assert report["params"] == ["y", "steps", "max_diff", "alpha"], report["params"]
        assert report["defaults"]["steps"] == 5
        assert report["defaults"]["max_diff"] == 1
        assert abs(float(report["defaults"]["alpha"]) - 0.05) < 1e-12

    def test_returns_dict_with_required_keys(self):
        """L1: the helper returns a plain dict containing every documented key."""
        report = _run_driver(
            """
            rng = np.random.RandomState(0)
            y = np.cumsum(rng.normal(size=80))  # random walk
            out = forecast_series(list(y), steps=4)
            print(json.dumps({
                'is_dict': type(out).__name__ == 'dict',
                'keys': sorted(out.keys()),
            }))
            """
        )
        assert report["is_dict"] is True, "must return a plain dict"
        required = {
            "d", "adf_pvalue", "forecast", "lower", "upper",
            "aic", "resid_ljungbox_pvalue",
        }
        missing = required - set(report["keys"])
        assert not missing, "missing keys: " + str(sorted(missing))

    def test_forecast_arrays_are_ndarrays_of_length_steps(self):
        """L1: forecast/lower/upper are 1-D numpy ndarrays of length `steps`."""
        report = _run_driver(
            """
            rng = np.random.RandomState(1)
            y = np.cumsum(rng.normal(size=90))
            steps = 7
            out = forecast_series(y, steps=steps)
            f, lo, up = out['forecast'], out['lower'], out['upper']
            print(json.dumps({
                'f_type': type(f).__name__,
                'lo_type': type(lo).__name__,
                'up_type': type(up).__name__,
                'f_ndim': int(np.asarray(f).ndim),
                'lens': [int(np.asarray(f).shape[0]),
                         int(np.asarray(lo).shape[0]),
                         int(np.asarray(up).shape[0])],
                'steps': steps,
            }))
            """
        )
        assert report["f_type"] == "ndarray"
        assert report["lo_type"] == "ndarray"
        assert report["up_type"] == "ndarray"
        assert report["f_ndim"] == 1
        assert report["lens"] == [report["steps"]] * 3

    def test_d_is_int_within_bounds(self):
        """L1: `d` is an integer with 0 <= d <= max_diff."""
        report = _run_driver(
            """
            rng = np.random.RandomState(2)
            y = np.cumsum(rng.normal(size=70))
            out = forecast_series(y, steps=3, max_diff=2)
            d = out['d']
            print(json.dumps({
                'is_int': bool(float(d) == int(d)),
                'd': int(d),
            }))
            """
        )
        assert report["is_int"] is True
        assert 0 <= report["d"] <= 2

    # ------------------------------------------------------------------ L2 ---
    def test_adf_pvalue_matches_raw_adfuller(self):
        """L2: adf_pvalue equals adfuller(raw y)[1] to fp tolerance (computed on
        the original series, before any differencing)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(3)
            y = np.cumsum(rng.normal(size=120))  # non-stationary raw series
            out = forecast_series(y, steps=5)
            ref_p = float(adfuller(np.asarray(y, dtype=float))[1])
            print(json.dumps({
                'reported': float(out['adf_pvalue']),
                'ref': ref_p,
                'err': abs(float(out['adf_pvalue']) - ref_p),
                'is_prob': 0.0 <= float(out['adf_pvalue']) <= 1.0,
            }))
            """
        )
        assert report["is_prob"] is True
        assert report["err"] < 1e-8, (
            "adf_pvalue %r != adfuller(raw)[1] %r"
            % (report["reported"], report["ref"])
        )

    def test_nonstationary_series_selects_d_one(self):
        """L2: a clearly non-stationary random-walk series gives d == 1 (with
        max_diff >= 1) and a large ADF p-value (not rejecting the unit root)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(4)
            y = np.cumsum(rng.normal(scale=1.0, size=200))  # I(1) random walk
            out = forecast_series(y, steps=5, max_diff=1)
            print(json.dumps({
                'd': int(out['d']),
                'adf_pvalue': float(out['adf_pvalue']),
            }))
            """
        )
        assert report["adf_pvalue"] > 0.10, report
        assert report["d"] == 1, report

    def test_stationary_series_selects_d_zero(self):
        """L2: a stationary mean-reverting (AR(1), |phi|<1) series gives d == 0
        and a small ADF p-value (rejecting the unit root)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(5)
            n = 300
            phi = 0.4
            e = rng.normal(scale=1.0, size=n)
            y = np.zeros(n)
            for t in range(1, n):
                y[t] = phi * y[t-1] + e[t]   # mean-reverting, stationary
            out = forecast_series(y, steps=5, max_diff=1)
            print(json.dumps({
                'd': int(out['d']),
                'adf_pvalue': float(out['adf_pvalue']),
            }))
            """
        )
        assert report["adf_pvalue"] < 0.05, report
        assert report["d"] == 0, report

    def test_max_diff_zero_forces_d_zero(self):
        """L2: even on a trending non-stationary series, max_diff=0 caps the
        integration order at 0 (d never exceeds max_diff)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(6)
            y = np.cumsum(rng.normal(size=150))  # non-stationary
            out = forecast_series(y, steps=4, max_diff=0)
            print(json.dumps({'d': int(out['d'])}))
            """
        )
        assert report["d"] == 0, report

    def test_interval_brackets_forecast_elementwise(self):
        """L2: lower[i] <= forecast[i] <= upper[i] at every horizon, the bounds
        are strictly ordered (lower < upper), and all are finite."""
        report = _run_driver(
            """
            rng = np.random.RandomState(7)
            y = np.cumsum(rng.normal(size=140))
            out = forecast_series(y, steps=6, alpha=0.05)
            f = np.asarray(out['forecast'], dtype=float)
            lo = np.asarray(out['lower'], dtype=float)
            up = np.asarray(out['upper'], dtype=float)
            print(json.dumps({
                'lo_le_f': bool(np.all(lo <= f + 1e-9)),
                'f_le_up': bool(np.all(f <= up + 1e-9)),
                'lo_lt_up': bool(np.all(lo < up)),
                'finite': bool(np.all(np.isfinite(f)) and np.all(np.isfinite(lo))
                               and np.all(np.isfinite(up))),
            }))
            """
        )
        assert report["finite"] is True
        assert report["lo_le_f"] is True
        assert report["f_le_up"] is True
        assert report["lo_lt_up"] is True

    def test_forecast_on_original_scale_for_random_walk(self):
        """L2: for a random walk the d==1 point forecast must be on the ORIGINAL
        scale (near the last observed level), not in differenced space. A helper
        that forgets to undo differencing would forecast near 0; this fails it."""
        report = _run_driver(
            """
            rng = np.random.RandomState(8)
            steps = np.random.RandomState(0)  # unused; keep determinism explicit
            drift = 0.5
            n = 250
            y = np.cumsum(drift + rng.normal(scale=0.5, size=n))  # strong upward trend
            last = float(y[-1])
            out = forecast_series(y, steps=5, max_diff=1)
            f = np.asarray(out['forecast'], dtype=float)
            print(json.dumps({
                'd': int(out['d']),
                'last': last,
                'first_fc': float(f[0]),
                'mean_level_of_y': float(np.mean(y)),
            }))
            """
        )
        # d should be 1 for this trending series
        assert report["d"] == 1, report
        # original-scale forecast must stay near the last LEVEL (hundreds), far
        # from 0 / from the differenced mean (~drift). Differenced-space output
        # would be ~0.5, which is nowhere near `last`.
        last = report["last"]
        first_fc = report["first_fc"]
        assert abs(first_fc - last) < 0.5 * abs(last) + 5.0, report
        assert abs(first_fc) > 5.0, report  # not collapsed to differenced scale

    def test_aic_and_ljungbox_are_floats_in_range(self):
        """L2: aic is a finite float and resid_ljungbox_pvalue is a valid
        probability in [0, 1]."""
        report = _run_driver(
            """
            rng = np.random.RandomState(9)
            y = np.cumsum(rng.normal(size=180))
            out = forecast_series(y, steps=5)
            aic = float(out['aic'])
            lb = float(out['resid_ljungbox_pvalue'])
            print(json.dumps({
                'aic_finite': bool(np.isfinite(aic)),
                'lb': lb,
                'lb_is_prob': 0.0 <= lb <= 1.0,
            }))
            """
        )
        assert report["aic_finite"] is True
        assert report["lb_is_prob"] is True, report

    def test_accepts_list_array_and_series_identically(self):
        """L2: list, ndarray and pandas Series inputs produce the same d,
        adf_pvalue and forecast (the helper must not depend on container type)."""
        report = _run_driver(
            """
            import pandas as pd
            rng = np.random.RandomState(10)
            arr = np.cumsum(rng.normal(size=160))
            out_arr = forecast_series(arr, steps=5)
            out_list = forecast_series(list(arr), steps=5)
            out_ser = forecast_series(pd.Series(arr), steps=5)

            def fc(o):
                return np.asarray(o['forecast'], dtype=float)

            print(json.dumps({
                'd_equal': int(out_arr['d']) == int(out_list['d']) == int(out_ser['d']),
                'p_err_list': abs(float(out_arr['adf_pvalue']) - float(out_list['adf_pvalue'])),
                'p_err_ser': abs(float(out_arr['adf_pvalue']) - float(out_ser['adf_pvalue'])),
                'fc_err_list': float(np.max(np.abs(fc(out_arr) - fc(out_list)))),
                'fc_err_ser': float(np.max(np.abs(fc(out_arr) - fc(out_ser)))),
            }))
            """
        )
        assert report["d_equal"] is True, report
        assert report["p_err_list"] < 1e-9, report
        assert report["p_err_ser"] < 1e-9, report
        assert report["fc_err_list"] < 1e-6, report
        assert report["fc_err_ser"] < 1e-6, report

    def test_steps_parameter_controls_horizon_length(self):
        """L2: changing `steps` changes all three array lengths accordingly
        (output length is data-driven by the argument, not hardcoded to 5)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(11)
            y = np.cumsum(rng.normal(size=130))
            lens = {}
            for s in (1, 3, 9):
                out = forecast_series(y, steps=s)
                lens[str(s)] = [
                    int(np.asarray(out['forecast']).shape[0]),
                    int(np.asarray(out['lower']).shape[0]),
                    int(np.asarray(out['upper']).shape[0]),
                ]
            print(json.dumps(lens))
            """
        )
        assert report["1"] == [1, 1, 1], report
        assert report["3"] == [3, 3, 3], report
        assert report["9"] == [9, 9, 9], report

    def test_native_pytest_passes(self):
        """L2: the acceptance command for the deliverable's own unit tests passes
        (pytest statsmodels/tsa/tests/test_arima_forecast_helper.py)."""
        if not os.path.isfile(self.TEST_PATH):
            pytest.skip("deliverable test module not present: " + self.TEST_PATH)
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                os.path.join(
                    "statsmodels", "tsa", "tests",
                    "test_arima_forecast_helper.py",
                ),
                "-q",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=900,
            env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
        )
        assert proc.returncode == 0, (
            "native pytest failed\nSTDOUT:\n"
            + proc.stdout[-4000:]
            + "\nSTDERR:\n"
            + proc.stderr[-2000:]
        )
