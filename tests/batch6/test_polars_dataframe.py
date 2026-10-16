"""Tests for the `polars-dataframe` skill task (ext6): a Sensor Time-Series
Resampling Module.

Verifies the deliverable `examples/sensor_series/series.py` inside the polars
repository (REPO_DIR=/workspace/polars). The three public functions
(`hourly_mean`, `add_gap_seconds`, `daily_value_range`) are exercised
dynamically: a focused driver script is written into REPO_DIR, imports the
agent's module + polars, runs it on controlled in-memory DataFrames, and emits
JSON that is deep-validated here.

L1 cases check the deliverable files exist and the public functions are
importable/callable. L2 cases drive real polars behavior with our OWN
independent harness (top-of-hour bucketing per sensor, per-bucket mean + count,
per-sensor whole-second gaps independent of input row order with null for each
sensor's first reading, per-sensor-day value range, strict cross-sensor
isolation, single-reading edge cases, and correctly-shaped empty results) so
that a naive or hardcoded implementation fails. A final case runs the variant's
native acceptance command:

    python -m pytest examples/sensor_series/test_series.py -q
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/polars"
PKG_DIR = os.path.join(REPO_DIR, "examples", "sensor_series")
SERIES_PY = os.path.join(PKG_DIR, "series.py")
NATIVE_TEST_PY = os.path.join(PKG_DIR, "test_series.py")


# ---------------------------------------------------------------------------
# Driver harness: run a python snippet from REPO_DIR with the agent's module
# importable, capturing a single JSON object printed on the LAST stdout line.
# ---------------------------------------------------------------------------

_PREAMBLE = textwrap.dedent(
    """
    import json, sys, os
    from datetime import datetime, date
    import polars as pl
    sys.path.insert(0, os.path.join(os.getcwd(), "examples"))
    from sensor_series import series as S

    def _norm(v):
        # JSON-serialise polars row values deterministically.
        if isinstance(v, float) and v != v:  # NaN
            return "__NAN__"
        if isinstance(v, datetime):
            return "DT:" + v.isoformat()
        if isinstance(v, date):
            return "D:" + v.isoformat()
        return v

    def _df_to_records(df):
        cols = list(df.columns)
        dtypes = [str(df.schema[c]) for c in cols]
        rows = df.rows()
        out = []
        for r in rows:
            rec = {}
            for c, v in zip(cols, r):
                rec[c] = _norm(v)
            out.append(rec)
        return {"columns": cols, "dtypes": dtypes, "rows": out, "height": df.height}
    """
)


def _run_driver(body, timeout=180):
    """Write `body` (which must `print(json.dumps(result))`) and run it.

    Returns the parsed JSON from the last non-empty stdout line.
    """
    script = _PREAMBLE + "\n" + textwrap.dedent(body)
    driver_path = os.path.join(REPO_DIR, "_skilltest_driver.py")
    with open(driver_path, "w") as fh:
        fh.write(script)
    try:
        proc = subprocess.run(
            ["python", "_skilltest_driver.py"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    finally:
        try:
            os.remove(driver_path)
        except OSError:
            pass
    if proc.returncode != 0:
        raise AssertionError(
            "driver failed (rc=%s)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-3000:])
        )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, "driver produced no stdout\nSTDERR:\n%s" % proc.stderr[-2000:]
    return json.loads(lines[-1])


# Shared fixture builder embedded inside drivers. Deliberately UNSORTED input
# (mixed sensors, out-of-order timestamps) so a naive impl that trusts row
# order or skips per-sensor isolation fails.
_BUILD_READINGS = """
    readings = pl.DataFrame(
        {
            "ts": [
                datetime(2023, 1, 1, 11, 1, 0),   # s1 -> 11:00 bucket
                datetime(2023, 1, 1, 10, 50, 0),  # s1 -> 10:00 bucket
                datetime(2023, 1, 1, 10, 5, 0),   # s1 -> 10:00 bucket
                datetime(2023, 1, 1, 10, 30, 0),  # s2 -> 10:00 bucket
                datetime(2023, 1, 2, 9, 0, 0),    # s1 -> next day
            ],
            "sensor": ["s1", "s1", "s1", "s2", "s1"],
            "value": [7.0, 4.0, 2.0, 100.0, 9.0],
        },
        schema={"ts": pl.Datetime, "sensor": pl.String, "value": pl.Float64},
    )
"""


class TestPolarsDataframe:
    REPO_DIR = "/workspace/polars"

    # ------------------------------------------------------------------ L1

    def test_package_marker_exists(self):
        """L1: the package marker __init__.py is present."""
        assert os.path.isfile(
            os.path.join(PKG_DIR, "__init__.py")
        ), "examples/sensor_series/__init__.py missing"

    def test_series_module_exists(self):
        """L1: series.py deliverable exists and is non-trivial."""
        assert os.path.isfile(SERIES_PY), "examples/sensor_series/series.py missing"
        assert os.path.getsize(SERIES_PY) > 200, "series.py is suspiciously small"

    def test_native_test_file_exists(self):
        """L1: the module's own pytest suite file is present."""
        assert os.path.isfile(
            NATIVE_TEST_PY
        ), "examples/sensor_series/test_series.py missing"

    def test_public_functions_importable(self):
        """L1: the three public functions are importable and callable."""
        result = _run_driver(
            """
            names = ["hourly_mean", "add_gap_seconds", "daily_value_range"]
            out = {n: callable(getattr(S, n, None)) for n in names}
            print(json.dumps(out))
            """
        )
        for name, ok in result.items():
            assert ok, "%s missing or not callable in series.py" % name

    # ------------------------------------------------------------------ L2

    def test_hourly_mean_columns_dtypes_and_order(self):
        """L2: hourly_mean returns exact column names/order, sorted sensor then bucket."""
        result = _run_driver(
            _BUILD_READINGS
            + """
            df = S.hourly_mean(readings)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["sensor", "bucket", "mean_value", "n"], (
            "unexpected columns/order: %s" % result["columns"]
        )
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert "Datetime" in dtype_map["bucket"], (
            "bucket must be Datetime, got %s" % dtype_map["bucket"]
        )
        assert dtype_map["mean_value"].startswith("Float"), (
            "mean_value must be Float64, got %s" % dtype_map["mean_value"]
        )
        assert dtype_map["n"].startswith("Int") or dtype_map["n"].startswith("UInt"), (
            "n must be an integer count dtype, got %s" % dtype_map["n"]
        )
        keys = [(r["sensor"], r["bucket"]) for r in result["rows"]]
        assert keys == sorted(keys), "rows must be sorted by sensor then bucket asc"

    def test_hourly_mean_top_of_hour_bucketing_and_counts(self):
        """L2: readings bucket to the hour start; per-bucket mean + count are correct."""
        result = _run_driver(
            _BUILD_READINGS
            + """
            df = S.hourly_mean(readings)
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_key = {(r["sensor"], r["bucket"]): r for r in result["rows"]}
        # s1 10:00 bucket: readings at 10:05 (2.0) and 10:50 (4.0) -> mean 3.0, n=2
        k = ("s1", "DT:2023-01-01T10:00:00")
        assert k in by_key, "s1 10:00 bucket missing; got %s" % list(by_key)
        assert by_key[k]["mean_value"] == pytest.approx(3.0)
        assert by_key[k]["n"] == 2
        # s1 11:00 bucket: reading at 11:01 (7.0) -> mean 7.0, n=1
        k = ("s1", "DT:2023-01-01T11:00:00")
        assert k in by_key, "s1 11:00 bucket missing"
        assert by_key[k]["mean_value"] == pytest.approx(7.0)
        assert by_key[k]["n"] == 1
        # s1 next-day 09:00 bucket: reading 9.0 -> mean 9.0, n=1
        k = ("s1", "DT:2023-01-02T09:00:00")
        assert k in by_key, "s1 next-day 09:00 bucket missing"
        assert by_key[k]["mean_value"] == pytest.approx(9.0)
        assert by_key[k]["n"] == 1

    def test_hourly_mean_no_cross_sensor_leakage(self):
        """L2: sensors do not contaminate each other's buckets."""
        result = _run_driver(
            _BUILD_READINGS
            + """
            df = S.hourly_mean(readings)
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_key = {(r["sensor"], r["bucket"]): r for r in result["rows"]}
        # s2 has exactly one reading at 10:30 (value 100) -> its own 10:00 bucket
        k = ("s2", "DT:2023-01-01T10:00:00")
        assert k in by_key, "s2 10:00 bucket missing"
        assert by_key[k]["mean_value"] == pytest.approx(100.0), (
            "s2 bucket polluted by s1 values: %s" % by_key[k]
        )
        assert by_key[k]["n"] == 1, "s2 bucket count must not include s1 rows"
        # s1's 10:00 bucket stays at mean 3.0 / n 2 (unaffected by s2's 100)
        s1 = by_key[("s1", "DT:2023-01-01T10:00:00")]
        assert s1["mean_value"] == pytest.approx(3.0)
        assert s1["n"] == 2

    def test_hourly_mean_omits_empty_buckets(self):
        """L2: only buckets that actually contain a reading appear (no gap-filling)."""
        result = _run_driver(
            """
            readings = pl.DataFrame(
                {
                    "ts": [
                        datetime(2023, 5, 1, 8, 10, 0),
                        datetime(2023, 5, 1, 12, 45, 0),
                    ],
                    "sensor": ["a", "a"],
                    "value": [1.0, 3.0],
                },
                schema={"ts": pl.Datetime, "sensor": pl.String, "value": pl.Float64},
            )
            df = S.hourly_mean(readings)
            print(json.dumps(_df_to_records(df)))
            """
        )
        buckets = [r["bucket"] for r in result["rows"]]
        # 08:00 and 12:00 only; the empty 09/10/11 hours must NOT be materialised
        assert buckets == [
            "DT:2023-05-01T08:00:00",
            "DT:2023-05-01T12:00:00",
        ], "empty intermediate buckets must be omitted; got %s" % buckets
        assert result["height"] == 2

    def test_add_gap_seconds_per_sensor_and_first_is_null(self):
        """L2: gap_s is per-sensor whole-second delta in ts order; first reading null."""
        result = _run_driver(
            _BUILD_READINGS
            + """
            df = S.add_gap_seconds(readings)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        # original columns preserved
        for c in ["ts", "sensor", "value"]:
            assert c in result["columns"], "original column %s dropped" % c
        assert "gap_s" in result["columns"], "gap_s column missing"
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["gap_s"].startswith("Int"), (
            "gap_s must be Int64, got %s" % dtype_map["gap_s"]
        )
        # sorted by sensor asc then ts asc
        keys = [(r["sensor"], r["ts"]) for r in result["rows"]]
        assert keys == sorted(keys), "rows must be sorted by sensor then ts asc"

        gaps = {(r["sensor"], r["ts"]): r["gap_s"] for r in result["rows"]}
        # s1 ordered ts: 10:05, 10:50, 11:01, next-day 09:00
        assert gaps[("s1", "DT:2023-01-01T10:05:00")] is None, "s1 first gap must be null"
        # 10:05 -> 10:50 = 45 min = 2700 s
        assert gaps[("s1", "DT:2023-01-01T10:50:00")] == 2700
        # 10:50 -> 11:01 = 11 min = 660 s
        assert gaps[("s1", "DT:2023-01-01T11:01:00")] == 660
        # 11:01 -> next day 09:00. delta = (24h - 11:01) + 9h
        # from 2023-01-01 11:01:00 to 2023-01-02 09:00:00 = 21h 59m = 79140 s
        assert gaps[("s1", "DT:2023-01-02T09:00:00")] == 79140
        # s2 has a single reading -> null
        assert gaps[("s2", "DT:2023-01-01T10:30:00")] is None, "s2 only reading must be null"

    def test_add_gap_seconds_ignores_input_row_order(self):
        """L2: gaps computed in ts order even when input rows are shuffled per sensor."""
        result = _run_driver(
            """
            readings = pl.DataFrame(
                {
                    "ts": [
                        datetime(2023, 3, 1, 0, 0, 30),  # +30s from first
                        datetime(2023, 3, 1, 0, 0, 0),   # earliest
                        datetime(2023, 3, 1, 0, 0, 10),  # +10s from first
                    ],
                    "sensor": ["x", "x", "x"],
                    "value": [3.0, 1.0, 2.0],
                },
                schema={"ts": pl.Datetime, "sensor": pl.String, "value": pl.Float64},
            )
            df = S.add_gap_seconds(readings)
            print(json.dumps(_df_to_records(df)))
            """
        )
        rows = result["rows"]
        # must come out in ts order regardless of the shuffled input
        ts_order = [r["ts"] for r in rows]
        assert ts_order == [
            "DT:2023-03-01T00:00:00",
            "DT:2023-03-01T00:00:10",
            "DT:2023-03-01T00:00:30",
        ], "output must be ts-sorted; got %s" % ts_order
        gaps = [r["gap_s"] for r in rows]
        # first null, then 10s, then 20s (00:10 -> 00:30)
        assert gaps == [None, 10, 20], "gaps must be per-pair second deltas; got %s" % gaps

    def test_add_gap_seconds_whole_seconds_truncation(self):
        """L2: gap is WHOLE seconds; sub-second remainders are not rounded up."""
        result = _run_driver(
            """
            readings = pl.DataFrame(
                {
                    "ts": [
                        datetime(2023, 4, 1, 0, 0, 0, 0),
                        datetime(2023, 4, 1, 0, 0, 1, 900000),  # 1.9 s later
                    ],
                    "sensor": ["k", "k"],
                    "value": [1.0, 2.0],
                },
                schema={"ts": pl.Datetime, "sensor": pl.String, "value": pl.Float64},
            )
            df = S.add_gap_seconds(readings)
            print(json.dumps(_df_to_records(df)))
            """
        )
        gaps = [r["gap_s"] for r in result["rows"]]
        assert gaps[0] is None
        # 1.9s of separation -> 1 whole second (truncation), never 2
        assert gaps[1] == 1, "1.9s gap must be 1 whole second, got %r" % gaps[1]

    def test_daily_value_range_columns_and_values(self):
        """L2: daily_value_range gives per-sensor-day max-minus-min in correct shape."""
        result = _run_driver(
            _BUILD_READINGS
            + """
            df = S.daily_value_range(readings)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["sensor", "day", "value_range"], (
            "unexpected columns/order: %s" % result["columns"]
        )
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["day"] == "Date", "day must be pl.Date, got %s" % dtype_map["day"]
        assert dtype_map["value_range"].startswith("Float"), (
            "value_range must be Float64, got %s" % dtype_map["value_range"]
        )
        keys = [(r["sensor"], r["day"]) for r in result["rows"]]
        assert keys == sorted(keys), "rows must be sorted by sensor then day asc"
        by_key = {(r["sensor"], r["day"]): r for r in result["rows"]}
        # s1 day 2023-01-01 values: 2.0, 4.0, 7.0 -> range 7-2 = 5.0
        k = ("s1", "D:2023-01-01")
        assert k in by_key, "s1 2023-01-01 day missing"
        assert by_key[k]["value_range"] == pytest.approx(5.0)
        # s1 day 2023-01-02 single value 9.0 -> range 0.0
        k = ("s1", "D:2023-01-02")
        assert k in by_key, "s1 2023-01-02 day missing"
        assert by_key[k]["value_range"] == pytest.approx(0.0)
        # s2 day 2023-01-01 single value 100.0 -> range 0.0
        k = ("s2", "D:2023-01-01")
        assert k in by_key, "s2 2023-01-01 day missing"
        assert by_key[k]["value_range"] == pytest.approx(0.0)

    def test_daily_value_range_single_reading_is_zero(self):
        """L2: a sensor-day with exactly one reading yields value_range 0.0, not null."""
        result = _run_driver(
            """
            readings = pl.DataFrame(
                {
                    "ts": [datetime(2023, 6, 6, 14, 0, 0)],
                    "sensor": ["solo"],
                    "value": [42.5],
                },
                schema={"ts": pl.Datetime, "sensor": pl.String, "value": pl.Float64},
            )
            df = S.daily_value_range(readings)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["height"] == 1
        row = result["rows"][0]
        assert row["sensor"] == "solo"
        assert row["day"] == "D:2023-06-06"
        assert row["value_range"] == pytest.approx(0.0), (
            "single-reading day must be 0.0, got %r" % row["value_range"]
        )

    def test_daily_value_range_no_cross_sensor_or_cross_day_leak(self):
        """L2: ranges are isolated per sensor AND per calendar day."""
        result = _run_driver(
            """
            readings = pl.DataFrame(
                {
                    "ts": [
                        datetime(2023, 7, 1, 1, 0, 0),
                        datetime(2023, 7, 1, 23, 0, 0),
                        datetime(2023, 7, 2, 5, 0, 0),
                        datetime(2023, 7, 1, 6, 0, 0),
                    ],
                    "sensor": ["a", "a", "a", "b"],
                    "value": [10.0, 30.0, 1000.0, 5.0],
                },
                schema={"ts": pl.Datetime, "sensor": pl.String, "value": pl.Float64},
            )
            df = S.daily_value_range(readings)
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_key = {(r["sensor"], r["day"]): r for r in result["rows"]}
        # a / 2023-07-01: values 10,30 -> range 20 (the 1000 is on day 2)
        assert by_key[("a", "D:2023-07-01")]["value_range"] == pytest.approx(20.0), (
            "day-2 value must not leak into day-1 range"
        )
        # a / 2023-07-02: single 1000 -> 0.0
        assert by_key[("a", "D:2023-07-02")]["value_range"] == pytest.approx(0.0)
        # b / 2023-07-01: single 5 -> 0.0, isolated from sensor a
        assert by_key[("b", "D:2023-07-01")]["value_range"] == pytest.approx(0.0)
        assert ("b", "D:2023-07-01") in by_key

    def test_empty_input_shapes_all_functions(self):
        """L2: every function returns an empty DataFrame with correct columns/dtypes."""
        result = _run_driver(
            """
            readings = pl.DataFrame(
                schema={"ts": pl.Datetime, "sensor": pl.String, "value": pl.Float64},
            )
            out = {}
            hm = S.hourly_mean(readings)
            out["hourly_mean"] = {
                "cols": list(hm.columns), "h": hm.height,
                "dtypes": [str(hm.schema[c]) for c in hm.columns],
            }
            gs = S.add_gap_seconds(readings)
            out["add_gap_seconds"] = {
                "cols": list(gs.columns), "h": gs.height,
                "dtypes": [str(gs.schema[c]) for c in gs.columns],
            }
            dv = S.daily_value_range(readings)
            out["daily_value_range"] = {
                "cols": list(dv.columns), "h": dv.height,
                "dtypes": [str(dv.schema[c]) for c in dv.columns],
            }
            print(json.dumps(out))
            """
        )
        hm = result["hourly_mean"]
        assert hm["h"] == 0, "hourly_mean must be empty on empty input"
        assert hm["cols"] == ["sensor", "bucket", "mean_value", "n"], (
            "hourly_mean empty cols: %s" % hm["cols"]
        )
        hm_dt = dict(zip(hm["cols"], hm["dtypes"]))
        assert "Datetime" in hm_dt["bucket"], "empty bucket dtype: %s" % hm_dt["bucket"]
        assert hm_dt["mean_value"].startswith("Float"), hm_dt["mean_value"]

        gs = result["add_gap_seconds"]
        assert gs["h"] == 0, "add_gap_seconds must be empty on empty input"
        for c in ["ts", "sensor", "value", "gap_s"]:
            assert c in gs["cols"], "add_gap_seconds empty missing %s: %s" % (c, gs["cols"])
        gs_dt = dict(zip(gs["cols"], gs["dtypes"]))
        assert gs_dt["gap_s"].startswith("Int"), "empty gap_s dtype: %s" % gs_dt["gap_s"]

        dv = result["daily_value_range"]
        assert dv["h"] == 0, "daily_value_range must be empty on empty input"
        assert dv["cols"] == ["sensor", "day", "value_range"], (
            "daily_value_range empty cols: %s" % dv["cols"]
        )
        dv_dt = dict(zip(dv["cols"], dv["dtypes"]))
        assert dv_dt["day"] == "Date", "empty day dtype: %s" % dv_dt["day"]

    def test_native_pytest_suite_passes(self):
        """L2: the module's own pytest suite passes (variant native acceptance command)."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "examples/sensor_series/test_series.py", "-q"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=420,
        )
        assert proc.returncode == 0, (
            "native pytest suite failed (rc=%s)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:])
        )
