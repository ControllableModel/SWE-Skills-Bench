"""Tests for the `polars-dataframe` skill task (variant ext9): a Data-Cleaning
and Bucketing Module.

Verifies the deliverable `examples/data_clean/clean.py` inside the polars
repository (REPO_DIR=/workspace/polars). The four public functions
(`impute_temperature`, `parse_counts`, `bucket_temperature`, `group_health`)
are exercised dynamically: a focused driver script is written into REPO_DIR,
imports the agent's module + polars, runs it on controlled in-memory
DataFrames, and emits JSON that is deep-validated here.

L1 cases check the deliverable files exist and the public functions are
importable. L2 cases drive real polars behavior so a naive / hardcoded
solution fails:
  * impute_temperature fills nulls with the per-group mean of non-null
    temperatures, leaves nulls where no group mean exists, preserves all
    original columns, and keeps the original (non-imputed) temperature intact.
  * parse_counts maps null AND empty-string count_str to null, parses valid
    integer strings, and never raises.
  * bucket_temperature applies the exact band boundaries (null->unknown,
    <0->cold, [0,25)->mild, >=25->hot) from the ORIGINAL temperature.
  * group_health counts rows and null temperatures per group with the null
    group sorted last.
  * every function returns a correctly-shaped empty DataFrame on empty input.

The final L2 case drives the doc's native acceptance command:
    python -m pytest examples/data_clean/test_clean.py -q
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/polars"
PKG_DIR = os.path.join(REPO_DIR, "examples", "data_clean")
CLEAN_PY = os.path.join(PKG_DIR, "clean.py")


# ---------------------------------------------------------------------------
# Driver harness: run a python snippet from REPO_DIR with the agent's module
# importable, capturing a single JSON object printed on the LAST stdout line.
# This is an INDEPENDENT verification harness (we do not trust the agent's own
# tests for the behavioral L2 assertions below).
# ---------------------------------------------------------------------------

_PREAMBLE = textwrap.dedent(
    """
    import json, sys, os
    import polars as pl
    sys.path.insert(0, os.path.join(os.getcwd(), "examples"))
    from data_clean import clean as C

    def _df_to_records(df):
        cols = list(df.columns)
        dtypes = [str(df.schema[c]) for c in cols]
        rows = df.rows()
        out = []
        for r in rows:
            rec = {}
            for c, v in zip(cols, r):
                if isinstance(v, float) and v != v:  # NaN
                    rec[c] = "__NAN__"
                else:
                    rec[c] = v
            out.append(rec)
        return {"columns": cols, "dtypes": dtypes, "rows": out}
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


# Shared raw fixture builder embedded inside drivers ------------------------
#
#   id  group  temperature  count_str
#   1   A      10.0         "10"
#   2   A      30.0         "30"      -> group A non-null mean = (10+30)/2 = 20.0
#   3   A      null         ""        -> filled = 20.0, count = null, band unknown
#   4   B      null         null      -> group B all-null temp -> filled null
#   5   B      null         "7"       -> filled null, count 7
#   6   null   -3.0         "0"       -> band cold, count 0
#   7   C      0.0          "abc"-ish? we keep valid ints only
#
# We keep count_str well-formed except where we intentionally test null/empty.

_BUILD_RAW = """
    raw = pl.DataFrame(
        {
            "id": [3, 1, 2, 5, 4, 6, 7],
            "group": ["A", "A", "A", "B", "B", None, "C"],
            "temperature": [None, 10.0, 30.0, None, None, -3.0, 0.0],
            "count_str": ["", "10", "30", "7", None, "0", "25"],
        },
        schema={
            "id": pl.Int64,
            "group": pl.String,
            "temperature": pl.Float64,
            "count_str": pl.String,
        },
    )
"""


class TestPolarsDataframe:
    REPO_DIR = "/workspace/polars"

    # ------------------------------------------------------------------ L1

    def test_package_marker_exists(self):
        """L1: the package marker __init__.py is present."""
        assert os.path.isfile(
            os.path.join(PKG_DIR, "__init__.py")
        ), "examples/data_clean/__init__.py missing"

    def test_clean_module_exists(self):
        """L1: clean.py deliverable exists and is non-trivial."""
        assert os.path.isfile(CLEAN_PY), "examples/data_clean/clean.py missing"
        assert os.path.getsize(CLEAN_PY) > 200, "clean.py is suspiciously small"

    def test_native_test_file_exists(self):
        """L1: the agent's pytest suite deliverable exists."""
        assert os.path.isfile(
            os.path.join(PKG_DIR, "test_clean.py")
        ), "examples/data_clean/test_clean.py missing"

    def test_public_functions_importable(self):
        """L1: the four public functions are importable and callable."""
        result = _run_driver(
            """
            names = ["impute_temperature", "parse_counts",
                     "bucket_temperature", "group_health"]
            out = {n: callable(getattr(C, n, None)) for n in names}
            print(json.dumps(out))
            """
        )
        for name, ok in result.items():
            assert ok, "%s missing or not callable in clean.py" % name

    # ------------------------------------------------------------------ L2

    def test_impute_preserves_columns_and_sort(self):
        """L2: impute_temperature preserves all originals, adds temperature_filled,
        and sorts by id ascending."""
        result = _run_driver(
            _BUILD_RAW
            + """
            df = C.impute_temperature(raw)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        for c in ["id", "group", "temperature", "count_str", "temperature_filled"]:
            assert c in cols, "missing column %s in impute output: %s" % (c, cols)
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["temperature_filled"].lower().startswith("float"), (
            "temperature_filled must be Float64, got %s"
            % dtype_map["temperature_filled"]
        )
        ids = [r["id"] for r in result["rows"]]
        assert ids == sorted(ids), "rows must be sorted by id ascending"
        assert ids == [1, 2, 3, 4, 5, 6, 7]
        # original temperature column must be untouched (row id=3 still null)
        by_id = {r["id"]: r for r in result["rows"]}
        assert by_id[3]["temperature"] is None, (
            "original temperature must remain null (not overwritten)"
        )

    def test_impute_group_mean_fill(self):
        """L2: a null temperature in group A is filled with the group's non-null
        mean (20.0), while a group with all-null temps stays null."""
        result = _run_driver(
            _BUILD_RAW
            + """
            df = C.impute_temperature(raw)
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_id = {r["id"]: r for r in result["rows"]}
        # group A: temps 10,30 -> mean 20; row id=3 null -> filled 20.0
        assert by_id[3]["temperature_filled"] == pytest.approx(20.0), (
            "null temp in group A must be filled with group mean 20.0, got %r"
            % by_id[3]["temperature_filled"]
        )
        # non-null rows keep their own value
        assert by_id[1]["temperature_filled"] == pytest.approx(10.0)
        assert by_id[2]["temperature_filled"] == pytest.approx(30.0)
        # group B: all temps null -> filled stays null for both rows
        assert by_id[4]["temperature_filled"] is None, (
            "all-null group must leave filled null, got %r"
            % by_id[4]["temperature_filled"]
        )
        assert by_id[5]["temperature_filled"] is None
        # null-group row id=6 had a real temperature -> kept as-is
        assert by_id[6]["temperature_filled"] == pytest.approx(-3.0)

    def test_impute_uses_per_group_not_global_mean(self):
        """L2: discriminative — a naive global-mean fill (or copy of temperature)
        must fail. Two groups with distinct means fill differently."""
        result = _run_driver(
            """
            raw = pl.DataFrame(
                {
                    "id": [1, 2, 3, 4, 5, 6],
                    "group": ["X", "X", "X", "Y", "Y", "Y"],
                    "temperature": [100.0, 200.0, None, 1.0, 3.0, None],
                    "count_str": ["1", "2", "3", "4", "5", "6"],
                },
                schema={"id": pl.Int64, "group": pl.String,
                        "temperature": pl.Float64, "count_str": pl.String},
            )
            df = C.impute_temperature(raw)
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_id = {r["id"]: r for r in result["rows"]}
        # X group mean = 150, Y group mean = 2.0; global mean would be 61.0
        assert by_id[3]["temperature_filled"] == pytest.approx(150.0), (
            "group X null must fill with 150 (per-group), got %r"
            % by_id[3]["temperature_filled"]
        )
        assert by_id[6]["temperature_filled"] == pytest.approx(2.0), (
            "group Y null must fill with 2.0 (per-group), got %r"
            % by_id[6]["temperature_filled"]
        )

    def test_parse_counts_null_and_empty_and_valid(self):
        """L2: parse_counts maps null and empty string to null, parses valid
        integers, preserves originals, sorts by id, and never raises."""
        result = _run_driver(
            _BUILD_RAW
            + """
            df = C.parse_counts(raw)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        assert "count" in cols, "parse_counts must add a `count` column: %s" % cols
        for c in ["id", "group", "temperature", "count_str"]:
            assert c in cols, "original column %s dropped" % c
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["count"].lower() in ("int64",), (
            "count must be Int64, got %s" % dtype_map["count"]
        )
        ids = [r["id"] for r in result["rows"]]
        assert ids == [1, 2, 3, 4, 5, 6, 7], "rows must be sorted by id ascending"
        by_id = {r["id"]: r for r in result["rows"]}
        # id=1 "10" -> 10 ; id=2 "30" -> 30
        assert by_id[1]["count"] == 10
        assert by_id[2]["count"] == 30
        # id=3 "" (empty) -> null
        assert by_id[3]["count"] is None, "empty count_str must yield null"
        # id=4 null -> null
        assert by_id[4]["count"] is None, "null count_str must yield null"
        # id=5 "7" -> 7 ; id=6 "0" -> 0 ; id=7 "25" -> 25
        assert by_id[5]["count"] == 7
        assert by_id[6]["count"] == 0, "zero string must parse to 0, not null"
        assert by_id[7]["count"] == 25

    def test_bucket_temperature_band_boundaries(self):
        """L2: bands assigned by exact boundaries from the ORIGINAL temperature;
        0.0 -> mild, 25.0 -> hot, negative -> cold, null -> unknown."""
        result = _run_driver(
            """
            raw = pl.DataFrame(
                {
                    "id": [1, 2, 3, 4, 5, 6],
                    "group": ["A", "A", "A", "A", "A", "A"],
                    "temperature": [-3.0, 0.0, 24.999, 25.0, 40.0, None],
                    "count_str": ["1", "2", "3", "4", "5", "6"],
                },
                schema={"id": pl.Int64, "group": pl.String,
                        "temperature": pl.Float64, "count_str": pl.String},
            )
            df = C.bucket_temperature(raw)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        assert "band" in cols, "bucket_temperature must add a `band` column: %s" % cols
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["band"].lower().startswith("str"), (
            "band must be String, got %s" % dtype_map["band"]
        )
        ids = [r["id"] for r in result["rows"]]
        assert ids == [1, 2, 3, 4, 5, 6], "rows must be sorted by id ascending"
        by_id = {r["id"]: r for r in result["rows"]}
        assert by_id[1]["band"] == "cold", "-3.0 must be cold"
        assert by_id[2]["band"] == "mild", "exactly 0.0 must be mild"
        assert by_id[3]["band"] == "mild", "24.999 must be mild"
        assert by_id[4]["band"] == "hot", "exactly 25.0 must be hot"
        assert by_id[5]["band"] == "hot", "40.0 must be hot"
        assert by_id[6]["band"] == "unknown", "null temperature must be unknown"

    def test_bucket_uses_original_not_imputed_temperature(self):
        """L2: discriminative — band must come from the ORIGINAL temperature.
        A null-temp row keeps band 'unknown' even though its group has a mean."""
        result = _run_driver(
            _BUILD_RAW
            + """
            df = C.bucket_temperature(raw)
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_id = {r["id"]: r for r in result["rows"]}
        # id=3 is in group A (mean 20 -> would be 'mild' if imputed) but its
        # original temperature is null, so band MUST be 'unknown'.
        assert by_id[3]["band"] == "unknown", (
            "null-temp row must be 'unknown' (band from original temp), got %r"
            % by_id[3]["band"]
        )
        assert by_id[6]["band"] == "cold", "id=6 original temp -3.0 -> cold"

    def test_group_health_counts(self):
        """L2: group_health reports rows and null_temp per group with exact
        columns and ordering (null group last)."""
        result = _run_driver(
            _BUILD_RAW
            + """
            df = C.group_health(raw)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["group", "rows", "null_temp"], (
            "group_health columns must be exactly [group, rows, null_temp]: %s"
            % result["columns"]
        )
        rows = result["rows"]
        groups = [r["group"] for r in rows]
        # distinct groups in raw: A, B, C, and null
        assert set(g for g in groups if g is not None) == {"A", "B", "C"}, (
            "unexpected group set: %s" % groups
        )
        assert None in groups, "null group must appear as its own row"
        # null group must be sorted LAST
        assert groups[-1] is None, "null group must be sorted last: %s" % groups
        # non-null groups ascending among themselves
        non_null = [g for g in groups if g is not None]
        assert non_null == sorted(non_null), "non-null groups must be ascending"
        by_group = {r["group"]: r for r in rows}
        # group A: ids 1,2,3 -> 3 rows, 1 null temp (id=3)
        assert by_group["A"]["rows"] == 3
        assert by_group["A"]["null_temp"] == 1
        # group B: ids 4,5 -> 2 rows, 2 null temps
        assert by_group["B"]["rows"] == 2
        assert by_group["B"]["null_temp"] == 2
        # group C: id 7 -> 1 row, 0 null
        assert by_group["C"]["rows"] == 1
        assert by_group["C"]["null_temp"] == 0
        # null group: id 6 -> 1 row, 0 null temp
        assert by_group[None]["rows"] == 1
        assert by_group[None]["null_temp"] == 0

    def test_group_health_null_group_sorted_last_even_when_alpha_late(self):
        """L2: discriminative — even with a group name like 'Z', the null group
        is still placed last (not naive lexicographic with null first)."""
        result = _run_driver(
            """
            raw = pl.DataFrame(
                {
                    "id": [1, 2, 3],
                    "group": [None, "Z", "A"],
                    "temperature": [None, 5.0, None],
                    "count_str": ["1", "2", "3"],
                },
                schema={"id": pl.Int64, "group": pl.String,
                        "temperature": pl.Float64, "count_str": pl.String},
            )
            df = C.group_health(raw)
            print(json.dumps(_df_to_records(df)))
            """
        )
        groups = [r["group"] for r in result["rows"]]
        assert groups == ["A", "Z", None], (
            "null group must sort last after Z: %s" % groups
        )
        by_group = {r["group"]: r for r in result["rows"]}
        assert by_group[None]["null_temp"] == 1
        assert by_group["A"]["null_temp"] == 1
        assert by_group["Z"]["null_temp"] == 0

    def test_empty_input_shapes_all_functions(self):
        """L2: every function returns an empty DataFrame with correct columns and
        dtypes on empty input, never raising."""
        result = _run_driver(
            """
            raw = pl.DataFrame(
                schema={"id": pl.Int64, "group": pl.String,
                        "temperature": pl.Float64, "count_str": pl.String},
            )
            out = {}
            it = C.impute_temperature(raw)
            out["impute"] = {"cols": list(it.columns), "h": it.height,
                             "dtypes": [str(it.schema[c]) for c in it.columns]}
            pc = C.parse_counts(raw)
            out["parse"] = {"cols": list(pc.columns), "h": pc.height,
                            "dtypes": [str(pc.schema[c]) for c in pc.columns]}
            bt = C.bucket_temperature(raw)
            out["bucket"] = {"cols": list(bt.columns), "h": bt.height}
            gh = C.group_health(raw)
            out["group_health"] = {"cols": list(gh.columns), "h": gh.height}
            print(json.dumps(out))
            """
        )
        it = result["impute"]
        assert it["h"] == 0, "impute_temperature must be empty on empty input"
        assert "temperature_filled" in it["cols"], (
            "impute empty must keep temperature_filled column: %s" % it["cols"]
        )
        ft = dict(zip(it["cols"], it["dtypes"]))["temperature_filled"]
        assert ft.lower().startswith("float"), (
            "temperature_filled dtype must be Float64 even when empty, got %s" % ft
        )
        pc = result["parse"]
        assert pc["h"] == 0
        assert "count" in pc["cols"], "parse empty must keep count column"
        ct = dict(zip(pc["cols"], pc["dtypes"]))["count"]
        assert ct.lower() == "int64", "count dtype must be Int64 even when empty, got %s" % ct
        bt = result["bucket"]
        assert bt["h"] == 0
        assert "band" in bt["cols"], "bucket empty must keep band column"
        gh = result["group_health"]
        assert gh["h"] == 0
        assert gh["cols"] == ["group", "rows", "null_temp"], (
            "group_health empty cols: %s" % gh["cols"]
        )

    def test_functions_do_not_mutate_input(self):
        """L2: calling the functions must not mutate the caller's `raw` DataFrame
        (no extra columns leak back, height unchanged)."""
        result = _run_driver(
            _BUILD_RAW
            + """
            before_cols = list(raw.columns)
            before_h = raw.height
            _ = C.impute_temperature(raw)
            _ = C.parse_counts(raw)
            _ = C.bucket_temperature(raw)
            _ = C.group_health(raw)
            after_cols = list(raw.columns)
            after_h = raw.height
            print(json.dumps({
                "before_cols": before_cols, "after_cols": after_cols,
                "before_h": before_h, "after_h": after_h,
            }))
            """
        )
        assert result["before_cols"] == result["after_cols"], (
            "input DataFrame columns must not be mutated: %s -> %s"
            % (result["before_cols"], result["after_cols"])
        )
        assert result["before_h"] == result["after_h"], "input height must not change"

    def test_native_pytest_suite_passes(self):
        """L2: the agent's own pytest suite for the module passes
        (doc's native acceptance command)."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "examples/data_clean/test_clean.py", "-q"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=420,
        )
        assert proc.returncode == 0, (
            "native pytest suite failed (rc=%s)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:])
        )
