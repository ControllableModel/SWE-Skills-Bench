"""Tests for the ``pandas-dataframe-patterns`` skill task (variant ext3).

The task asks the agent to create ``scripts/sensor_resample.py`` inside the
pandas repository, exposing three public functions that turn irregular sensor
readings into regular, gap-free hourly time series:

  * ``to_hourly(readings)``     -- aggregate per-event readings into a
        contiguous hourly DatetimeIndex with ``reading_count`` and
        ``mean_value`` columns; empty hours present with count 0 / NaN mean.
  * ``fill_gaps(hourly)``       -- linearly interpolate interior gaps in
        ``mean_value`` over time, back/forward-fill the edges, leaving no NaN.
  * ``rolling_average(hourly, window)`` -- trailing rolling mean of
        ``mean_value`` over ``window`` hours; first ``window-1`` rows NaN.

The agent must also add ``scripts/tests/test_sensor_resample.py``.

Verification strategy: each L2 case drives the agent's real functions through a
subprocess (so the installed/built pandas is used, not the unbuilt repo source
tree) and deep-validates numeric output, index contiguity/ordering, NaN
handling, edge cases and the "do not mutate the caller's input" contract.

A naive solution will fail. Specifically a solution that: merely creates files;
drops empty hours instead of producing a contiguous hourly index; flags empty
hours with a 0.0 mean instead of NaN; mutates the caller's frame; uses
plain ffill/bfill instead of time-proportional interpolation for interior
gaps; leaves edge NaNs after fill_gaps; or computes a leading (non-trailing)
rolling window -- all fail concrete assertions below.
"""

import json
import os
import subprocess
import tempfile
import textwrap

import pytest


class TestPandasDataframePatterns:
    REPO_DIR = "/workspace/pandas"

    MODULE_REL = os.path.join("scripts", "sensor_resample.py")
    TEST_REL = os.path.join("scripts", "tests", "test_sensor_resample.py")

    # ---- helpers ---------------------------------------------------------

    def _module_path(self):
        return os.path.join(self.REPO_DIR, self.MODULE_REL)

    def _run_driver(self, body, timeout=120):
        """Run a python snippet that imports the agent's sensor_resample module.

        The driver runs from a clean temporary cwd (NOT the repo root) so that
        ``import pandas`` resolves to the installed/built pandas instead of the
        repository source tree. The agent's ``scripts`` directory is placed on
        sys.path so ``import sensor_resample`` finds the deliverable. The
        snippet is expected to ``print`` a single JSON line as its final output.
        """
        scripts_dir = os.path.join(self.REPO_DIR, "scripts")
        assert os.path.isfile(self._module_path()), (
            "scripts/sensor_resample.py does not exist; agent did not create "
            "the deliverable module."
        )
        header = textwrap.dedent(
            f"""
            import sys, json
            sys.path.insert(0, {scripts_dir!r})
            import pandas as pd
            import numpy as np
            import sensor_resample as sr
            """
        )
        # Dedent each top-level chunk independently. Some callers concatenate a
        # flush-left SAMPLE literal with an indented body; dedenting the whole
        # string would find no common prefix and leave the body indented.
        body_src = "\n".join(textwrap.dedent(part) for part in body.split("\f"))
        src = header + body_src
        with tempfile.TemporaryDirectory() as workdir:
            script_path = os.path.join(workdir, "driver_snippet.py")
            with open(script_path, "w") as fh:
                fh.write(src)
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            proc = subprocess.run(
                ["python", script_path],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        return proc

    def _run_json(self, body, timeout=120):
        proc = self._run_driver(body, timeout=timeout)
        assert proc.returncode == 0, (
            "driver exited non-zero.\nSTDOUT:\n"
            + proc.stdout
            + "\nSTDERR:\n"
            + proc.stderr
        )
        last = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        assert last, "driver produced no stdout.\nSTDERR:\n" + proc.stderr
        try:
            return json.loads(last[-1])
        except json.JSONDecodeError as exc:  # pragma: no cover
            raise AssertionError(
                f"final stdout line was not JSON: {last[-1]!r}\nSTDERR:\n{proc.stderr}"
            ) from exc

    # A reusable sample dataset literal, defined once for driver snippets.
    # Readings span 00:10, 00:50, 02:05 -> the 01:00 bucket is empty.
    SAMPLE = textwrap.dedent(
        """
        readings = pd.DataFrame({
            'timestamp': ['2023-01-01 00:10:00',
                          '2023-01-01 00:50:00',
                          '2023-01-01 02:05:00'],
            'sensor_id': ['s1', 's1', 's2'],
            'value':     [10.0, 20.0, 5.0],
        })
        """
    )

    # ---- L1: deliverables exist & minimally well-formed ------------------

    def test_module_file_exists(self):
        """L1: scripts/sensor_resample.py must exist."""
        assert os.path.isfile(self._module_path()), (
            f"missing deliverable: {self._module_path()}"
        )

    def test_test_file_exists(self):
        """L1: scripts/tests/test_sensor_resample.py must exist."""
        assert os.path.isfile(os.path.join(self.REPO_DIR, self.TEST_REL)), (
            "missing deliverable test file scripts/tests/test_sensor_resample.py"
        )

    def test_public_functions_present(self):
        """L1: the three required public functions are importable callables."""
        out = self._run_json(
            """
            names = ['to_hourly', 'fill_gaps', 'rolling_average']
            res = {n: callable(getattr(sr, n, None)) for n in names}
            print(json.dumps(res))
            """
        )
        for name, ok in out.items():
            assert ok, f"sensor_resample.{name} is missing or not callable"

    # ---- L2: to_hourly --------------------------------------------------

    def test_to_hourly_contiguous_index_and_empty_hour(self):
        """L2: spec example -> 3 contiguous hours; empty 01:00 has count 0/NaN mean."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = sr.to_hourly(readings)
            idx = [pd.Timestamp(i).strftime('%Y-%m-%d %H:%M:%S') for i in res.index]
            counts = {pd.Timestamp(i).strftime('%H:%M'): int(c)
                      for i, c in zip(res.index, res['reading_count'])}
            means = {pd.Timestamp(i).strftime('%H:%M'):
                         (None if pd.isna(m) else float(m))
                     for i, m in zip(res.index, res['mean_value'])}
            print(json.dumps({
                'idx': idx,
                'n': int(len(res)),
                'counts': counts,
                'means': means,
                'cols': list(res.columns),
            }))
            """
        )
        # floor(earliest)=00:00 .. floor(latest)=02:00 inclusive -> 3 hourly rows
        assert out["n"] == 3, "to_hourly must produce one row per hour in the range"
        assert out["idx"] == [
            "2023-01-01 00:00:00",
            "2023-01-01 01:00:00",
            "2023-01-01 02:00:00",
        ], f"index must be a contiguous hourly range with no gaps: {out['idx']}"
        assert "reading_count" in out["cols"]
        assert "mean_value" in out["cols"]
        # 00:00 bucket has the 00:10 and 00:50 readings -> count 2, mean (10+20)/2
        assert out["counts"]["00:00"] == 2
        assert out["means"]["00:00"] == 15.0
        # 01:00 bucket is empty -> count 0, missing mean (NOT 0.0)
        assert out["counts"]["01:00"] == 0, "empty hour must have reading_count == 0"
        assert out["means"]["01:00"] is None, (
            "empty hour must have a MISSING mean_value, not 0.0"
        )
        # 02:00 bucket has the single 02:05 reading
        assert out["counts"]["02:00"] == 1
        assert out["means"]["02:00"] == 5.0

    def test_to_hourly_index_sorted_regular_and_unique(self):
        """L2: index is a sorted, strictly-1h-spaced, unique DatetimeIndex."""
        out = self._run_json(
            """
            # deliberately unsorted input spanning 00:00 .. 04:00
            readings = pd.DataFrame({
                'timestamp': ['2023-02-01 04:30:00',
                              '2023-02-01 00:15:00',
                              '2023-02-01 04:45:00'],
                'sensor_id': ['a', 'b', 'a'],
                'value':     [1.0, 2.0, 3.0],
            })
            res = sr.to_hourly(readings)
            ix = res.index
            secs = [pd.Timestamp(t).value // 10**9 for t in ix]
            diffs = [secs[i+1] - secs[i] for i in range(len(secs)-1)]
            print(json.dumps({
                'n': int(len(ix)),
                'is_datetime': bool(pd.api.types.is_datetime64_any_dtype(ix)),
                'sorted': secs == sorted(secs),
                'unique': len(secs) == len(set(secs)),
                'all_one_hour': all(d == 3600 for d in diffs),
                'first': pd.Timestamp(ix[0]).strftime('%H:%M'),
                'last': pd.Timestamp(ix[-1]).strftime('%H:%M'),
            }))
            """
        )
        # floor(00:15)=00:00 .. floor(04:45)=04:00 inclusive -> 5 hourly rows
        assert out["n"] == 5
        assert out["is_datetime"], "index must be a DatetimeIndex"
        assert out["sorted"], "index must be sorted ascending"
        assert out["unique"], "index must have one entry per hour"
        assert out["all_one_hour"], "consecutive hours must be exactly 1h apart"
        assert out["first"] == "00:00"
        assert out["last"] == "04:00"

    def test_to_hourly_mean_is_arithmetic_mean(self):
        """L2: mean_value is the true arithmetic mean of values in the bucket."""
        out = self._run_json(
            """
            readings = pd.DataFrame({
                'timestamp': ['2023-03-01 09:05:00',
                              '2023-03-01 09:25:00',
                              '2023-03-01 09:55:00'],
                'sensor_id': ['x', 'y', 'x'],
                'value':     [1.0, 2.0, 9.0],
            })
            res = sr.to_hourly(readings)
            row = res.loc[res['reading_count'] > 0].iloc[0]
            print(json.dumps({
                'count': int(row['reading_count']),
                'mean': float(row['mean_value']),
                'n_rows': int(len(res)),
            }))
            """
        )
        assert out["n_rows"] == 1, "all readings fall in the single 09:00 hour"
        assert out["count"] == 3, "reading_count must count every reading in the hour"
        # mean of [1, 2, 9] = 4.0 (not sum, not median)
        assert out["mean"] == 4.0, "mean_value must be the arithmetic mean"

    def test_to_hourly_does_not_mutate_input(self):
        """L2: the caller's readings frame must be unchanged after to_hourly."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_cols = list(readings.columns)
            before_hash = pd.util.hash_pandas_object(readings, index=True).sum()
            before_n = int(len(readings))
            _ = sr.to_hourly(readings)
            after_cols = list(readings.columns)
            after_hash = pd.util.hash_pandas_object(readings, index=True).sum()
            print(json.dumps({
                'cols_same': before_cols == after_cols,
                'hash_same': bool(before_hash == after_hash),
                'n_same': before_n == int(len(readings)),
                'ts_is_str': bool(readings['timestamp'].map(type).eq(str).all()),
            }))
            """
        )
        assert out["cols_same"], "to_hourly must not change input columns"
        assert out["hash_same"], "to_hourly must not alter input values"
        assert out["n_same"], "to_hourly must not add/drop input rows"
        assert out["ts_is_str"], (
            "to_hourly must not convert the caller's timestamp column in place"
        )

    # ---- L2: fill_gaps --------------------------------------------------

    def test_fill_gaps_interior_linear_interpolation(self):
        """L2: spec example means [10, NaN, 20] -> middle becomes 15.0."""
        out = self._run_json(
            """
            idx = pd.date_range('2023-01-01 00:00:00', periods=3, freq='h')
            hourly = pd.DataFrame(
                {'reading_count': [1, 0, 1], 'mean_value': [10.0, np.nan, 20.0]},
                index=idx,
            )
            res = sr.fill_gaps(hourly)
            means = [float(x) for x in res['mean_value'].tolist()]
            counts = [int(x) for x in res['reading_count'].tolist()]
            print(json.dumps({
                'means': means,
                'counts': counts,
                'any_na': bool(res['mean_value'].isna().any()),
            }))
            """
        )
        assert out["means"] == [10.0, 15.0, 20.0], (
            "interior gap must be the time-proportional interpolated value 15.0"
        )
        assert not out["any_na"], "fill_gaps must leave no missing mean_value"
        assert out["counts"] == [1, 0, 1], "reading_count must be left unchanged"

    def test_fill_gaps_time_proportional_uneven_gap(self):
        """L2: interpolation is time-weighted, not a naive midpoint average."""
        out = self._run_json(
            """
            # present at hour 0 (=0.0) and hour 4 (=40.0); hours 1,2,3 missing.
            # Linear-in-time fill -> 10, 20, 30. A ffill/bfill would NOT do this;
            # a single-midpoint scheme would give 20 everywhere.
            idx = pd.date_range('2023-01-01 00:00:00', periods=5, freq='h')
            hourly = pd.DataFrame(
                {'reading_count': [1, 0, 0, 0, 1],
                 'mean_value': [0.0, np.nan, np.nan, np.nan, 40.0]},
                index=idx,
            )
            res = sr.fill_gaps(hourly)
            means = [round(float(x), 6) for x in res['mean_value'].tolist()]
            print(json.dumps({'means': means}))
            """
        )
        assert out["means"] == [0.0, 10.0, 20.0, 30.0, 40.0], (
            "interior gaps must be filled by linear interpolation over time, "
            "not forward/back fill or a constant midpoint"
        )

    def test_fill_gaps_edges_back_and_forward_filled(self):
        """L2: leading gaps back-fill from first present, trailing forward-fill."""
        out = self._run_json(
            """
            # NaN at the very start and very end; one present value in the middle.
            idx = pd.date_range('2023-01-01 00:00:00', periods=5, freq='h')
            hourly = pd.DataFrame(
                {'reading_count': [0, 0, 1, 0, 0],
                 'mean_value': [np.nan, np.nan, 7.0, np.nan, np.nan]},
                index=idx,
            )
            res = sr.fill_gaps(hourly)
            means = [float(x) for x in res['mean_value'].tolist()]
            print(json.dumps({
                'means': means,
                'any_na': bool(res['mean_value'].isna().any()),
            }))
            """
        )
        # leading NaNs back-filled from 7.0, trailing NaNs forward-filled from 7.0
        assert out["means"] == [7.0, 7.0, 7.0, 7.0, 7.0], (
            "edge gaps must be back/forward-filled from the nearest present value"
        )
        assert not out["any_na"], "fill_gaps must leave no missing mean_value"

    def test_fill_gaps_does_not_mutate_input(self):
        """L2: fill_gaps must not mutate its input frame."""
        out = self._run_json(
            """
            idx = pd.date_range('2023-01-01 00:00:00', periods=3, freq='h')
            hourly = pd.DataFrame(
                {'reading_count': [1, 0, 1], 'mean_value': [10.0, np.nan, 20.0]},
                index=idx,
            )
            before = pd.util.hash_pandas_object(hourly, index=True).sum()
            na_before = int(hourly['mean_value'].isna().sum())
            _ = sr.fill_gaps(hourly)
            after = pd.util.hash_pandas_object(hourly, index=True).sum()
            na_after = int(hourly['mean_value'].isna().sum())
            print(json.dumps({
                'hash_same': bool(before == after),
                'na_before': na_before, 'na_after': na_after,
            }))
            """
        )
        assert out["hash_same"], "fill_gaps must not mutate its input"
        assert out["na_before"] == 1 and out["na_after"] == 1, (
            "the input's missing mean must remain after calling fill_gaps"
        )

    # ---- L2: rolling_average --------------------------------------------

    def test_rolling_average_trailing_window(self):
        """L2: trailing rolling mean; first window-1 rows missing (spec example)."""
        out = self._run_json(
            """
            idx = pd.date_range('2023-01-01 00:00:00', periods=4, freq='h')
            hourly = pd.DataFrame(
                {'reading_count': [1, 1, 1, 1],
                 'mean_value': [2.0, 4.0, 6.0, 8.0]},
                index=idx,
            )
            res = sr.rolling_average(hourly, 2)
            roll = [None if pd.isna(x) else float(x)
                    for x in res['rolling_mean'].tolist()]
            print(json.dumps({
                'roll': roll,
                'cols': list(res.columns),
                'mean_unchanged': [float(x) for x in res['mean_value'].tolist()],
            }))
            """
        )
        assert "rolling_mean" in out["cols"], "must add a rolling_mean column"
        # window=2 -> first row NaN; then trailing means (2+4)/2, (4+6)/2, (6+8)/2
        assert out["roll"][0] is None, "first window-1 rows must be missing"
        assert out["roll"] == [None, 3.0, 5.0, 7.0], (
            "rolling_mean must be the TRAILING mean over `window` hours"
        )
        assert out["mean_unchanged"] == [2.0, 4.0, 6.0, 8.0], (
            "rolling_average must preserve the original mean_value column"
        )

    def test_rolling_average_window_one_and_three(self):
        """L2: window=1 copies mean_value; window=3 masks first two rows."""
        out = self._run_json(
            """
            idx = pd.date_range('2023-01-01 00:00:00', periods=5, freq='h')
            hourly = pd.DataFrame(
                {'reading_count': [1]*5,
                 'mean_value': [3.0, 6.0, 9.0, 12.0, 15.0]},
                index=idx,
            )
            r1 = sr.rolling_average(hourly, 1)['rolling_mean'].tolist()
            r3 = sr.rolling_average(hourly, 3)['rolling_mean']
            r3_vals = [None if pd.isna(x) else float(x) for x in r3.tolist()]
            print(json.dumps({
                'r1': [float(x) for x in r1],
                'r3': r3_vals,
            }))
            """
        )
        # window=1 -> every value equals its own mean_value, no masking
        assert out["r1"] == [3.0, 6.0, 9.0, 12.0, 15.0]
        # window=3 -> first two rows NaN, then trailing 3-hour means
        assert out["r3"][0] is None and out["r3"][1] is None, (
            "first window-1 (=2) rows must be missing for window=3"
        )
        assert out["r3"][2] == 6.0   # (3+6+9)/3
        assert out["r3"][3] == 9.0   # (6+9+12)/3
        assert out["r3"][4] == 12.0  # (9+12+15)/3

    def test_rolling_average_does_not_mutate_input(self):
        """L2: rolling_average must not mutate its input frame."""
        out = self._run_json(
            """
            idx = pd.date_range('2023-01-01 00:00:00', periods=3, freq='h')
            hourly = pd.DataFrame(
                {'reading_count': [1, 1, 1], 'mean_value': [1.0, 2.0, 3.0]},
                index=idx,
            )
            before = pd.util.hash_pandas_object(hourly, index=True).sum()
            before_cols = list(hourly.columns)
            _ = sr.rolling_average(hourly, 2)
            after = pd.util.hash_pandas_object(hourly, index=True).sum()
            print(json.dumps({
                'hash_same': bool(before == after),
                'no_roll_col': 'rolling_mean' not in hourly.columns,
                'cols_same': before_cols == list(hourly.columns),
            }))
            """
        )
        assert out["hash_same"], "rolling_average must not mutate its input"
        assert out["no_roll_col"], "rolling_average must not add column to input"
        assert out["cols_same"], "rolling_average must not change input columns"

    # ---- L2: end-to-end pipeline integration ----------------------------

    def test_pipeline_to_hourly_then_fill_gaps(self):
        """L2: to_hourly -> fill_gaps yields a contiguous, NaN-free mean series."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            hourly = sr.to_hourly(readings)
            filled = sr.fill_gaps(hourly)
            means = [float(x) for x in filled['mean_value'].tolist()]
            n_hours = int(len(filled))
            secs = [pd.Timestamp(t).value // 10**9 for t in filled.index]
            diffs = [secs[i+1] - secs[i] for i in range(len(secs)-1)]
            print(json.dumps({
                'n': n_hours,
                'means': means,
                'any_na': bool(filled['mean_value'].isna().any()),
                'all_one_hour': all(d == 3600 for d in diffs),
            }))
            """
        )
        assert out["n"] == 3, "pipeline must preserve the contiguous hourly index"
        assert out["all_one_hour"], "hourly spacing must remain exactly 1h"
        assert not out["any_na"], "fill_gaps must remove all NaN from the pipeline"
        # 00:00 mean=15.0, 02:00 mean=5.0 present; 01:00 interpolated between -> 10.0
        assert out["means"] == [15.0, 10.0, 5.0], (
            "the empty 01:00 hour must be interpolated to 10.0 between 15.0 and 5.0"
        )

    # ---- L2: agent's own native acceptance command ----------------------

    def test_agent_native_pytest_passes(self):
        """L2: the spec's native command on the agent's own test suite passes."""
        test_file = os.path.join(self.REPO_DIR, self.TEST_REL)
        assert os.path.isfile(test_file), "agent test file missing"
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scripts/tests/test_sensor_resample.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native command `python -m pytest "
            "scripts/tests/test_sensor_resample.py -q` failed.\nSTDOUT:\n"
            + proc.stdout + "\nSTDERR:\n" + proc.stderr
        )
        # guard against a vacuous (zero-collected) pass
        assert "no tests ran" not in proc.stdout.lower(), (
            "agent test suite collected no tests"
        )
