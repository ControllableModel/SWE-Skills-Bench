"""Tests for the `polars-dataframe` skill task (ext10): a Nutrition Dataset
Analytics Module.

Verifies the deliverable `examples/nutrition_report/report.py` inside the polars
repository (REPO_DIR=/workspace/polars). Three public functions are exercised:

  * ``load_foods(paths) -> pl.DataFrame`` — read + row-stack CSVs (4 columns,
    file-list order, empty list -> empty 4-col frame).
  * ``category_summary(paths) -> pl.DataFrame`` — per-category count / mean
    calories / summed sugars / max fats, sorted by category.
  * ``write_summary(summary, out_path) -> None`` — round-trippable CSV write.

Verification strategy: an independent driver script is written into REPO_DIR
that imports the agent's module plus polars, writes its OWN controlled CSVs to a
temp directory, calls the agent's functions on REAL on-disk files, and prints a
single JSON object that is deep-validated here. This sidesteps the agent's own
test file for behavioral checks, so a naive/stub implementation (in-memory only,
ignored paths, hardcoded summary, no real file write) fails. L1 cases check the
deliverable files exist / are importable; L2 cases assert concrete numeric
aggregates, column order, ordering, and the on-disk round trip. A final L2 case
drives the doc's native acceptance command
(``python -m pytest examples/nutrition_report/test_report.py -q``).
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/polars"
PKG_DIR = os.path.join(REPO_DIR, "examples", "nutrition_report")
REPORT_PY = os.path.join(PKG_DIR, "report.py")


# ---------------------------------------------------------------------------
# Driver harness: run a python snippet from REPO_DIR with the agent's module
# importable, capturing a single JSON object printed on the LAST stdout line.
# The snippet has `tmp` (a fresh temp dir) and helpers available.
# ---------------------------------------------------------------------------

_PREAMBLE = textwrap.dedent(
    """
    import json, sys, os, tempfile, shutil
    import polars as pl
    sys.path.insert(0, os.path.join(os.getcwd(), "examples"))
    from nutrition_report import report as R

    tmp = tempfile.mkdtemp(prefix="nut_skilltest_")

    def _write_csv(name, text):
        p = os.path.join(tmp, name)
        with open(p, "w") as fh:
            fh.write(text)
        return p

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
        return {"columns": cols, "dtypes": dtypes, "rows": out, "height": df.height}
    """
)


def _run_driver(body, timeout=180):
    """Write `body` (which must `print(json.dumps(result))`) and run it.

    Returns the parsed JSON from the last non-empty stdout line.
    """
    script = _PREAMBLE + "\n" + textwrap.dedent(body) + "\nshutil.rmtree(tmp, ignore_errors=True)\n"
    driver_path = os.path.join(REPO_DIR, "_nut_skilltest_driver.py")
    with open(driver_path, "w") as fh:
        fh.write(script)
    try:
        proc = subprocess.run(
            ["python", "_nut_skilltest_driver.py"],
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


# A controlled two-file dataset embedded in drivers. File 1 has three "fruit"
# rows so n_items/mean/sum/max are all non-degenerate and order matters.
_BUILD_TWO_FILES = """
    f1 = _write_csv(
        "a.csv",
        "category,calories,fats_g,sugars_g\\n"
        "fruit,60,0.0,11.0\\n"
        "meat,100,5.0,0.0\\n"
        "fruit,30,4.0,5.0\\n"
        "veg,20,0.0,2.0\\n"
        "fruit,90,1.0,8.0\\n",
    )
    f2 = _write_csv(
        "b.csv",
        "category,calories,fats_g,sugars_g\\n"
        "meat,200,10.0,1.0\\n"
        "veg,40,0.5,3.0\\n",
    )
"""


class TestPolarsDataframe:
    REPO_DIR = "/workspace/polars"

    # ------------------------------------------------------------------ L1

    def test_package_marker_exists(self):
        """L1: the package marker __init__.py is present."""
        assert os.path.isfile(
            os.path.join(PKG_DIR, "__init__.py")
        ), "examples/nutrition_report/__init__.py missing"

    def test_report_module_exists(self):
        """L1: report.py deliverable exists and is non-trivial."""
        assert os.path.isfile(REPORT_PY), "examples/nutrition_report/report.py missing"
        assert os.path.getsize(REPORT_PY) > 200, "report.py is suspiciously small"

    def test_public_functions_importable(self):
        """L1: load_foods, category_summary, write_summary are callable."""
        result = _run_driver(
            """
            names = ["load_foods", "category_summary", "write_summary"]
            out = {n: callable(getattr(R, n, None)) for n in names}
            print(json.dumps(out))
            """
        )
        for name, ok in result.items():
            assert ok, "%s missing or not callable in report.py" % name

    # ------------------------------------------------------------------ L2

    def test_load_foods_columns_and_dtypes(self):
        """L2: load_foods returns the four columns in order with correct dtypes."""
        result = _run_driver(
            _BUILD_TWO_FILES
            + """
            df = R.load_foods([f1, f2])
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == [
            "category",
            "calories",
            "fats_g",
            "sugars_g",
        ], "unexpected columns/order: %s" % result["columns"]
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["category"] == "String", dtype_map
        assert dtype_map["calories"] == "Int64", dtype_map
        assert dtype_map["fats_g"] == "Float64", dtype_map
        assert dtype_map["sugars_g"] == "Float64", dtype_map

    def test_load_foods_row_stacking_and_order(self):
        """L2: load_foods stacks all rows of all files preserving file-list order."""
        result = _run_driver(
            _BUILD_TWO_FILES
            + """
            df = R.load_foods([f1, f2])
            print(json.dumps(_df_to_records(df)))
            """
        )
        rows = result["rows"]
        assert result["height"] == 7, "expected 5+2=7 stacked rows, got %s" % result["height"]
        # File 1 rows first (in file order), then file 2 rows.
        cats = [r["category"] for r in rows]
        assert cats == ["fruit", "meat", "fruit", "veg", "fruit", "meat", "veg"], (
            "rows not in file-list + internal order: %s" % cats
        )
        # First row exact values come from file 1's first line.
        assert rows[0]["calories"] == 60
        assert rows[0]["sugars_g"] == pytest.approx(11.0)
        # Last row comes from file 2's last line.
        assert rows[6]["category"] == "veg"
        assert rows[6]["calories"] == 40
        assert rows[6]["fats_g"] == pytest.approx(0.5)

    def test_load_foods_reversed_order_changes_result(self):
        """L2: swapping the paths order swaps the row order (paths are honored)."""
        result = _run_driver(
            _BUILD_TWO_FILES
            + """
            df = R.load_foods([f2, f1])
            print(json.dumps(_df_to_records(df)))
            """
        )
        rows = result["rows"]
        assert result["height"] == 7
        cats = [r["category"] for r in rows]
        # File 2 first now.
        assert cats == ["meat", "veg", "fruit", "meat", "fruit", "veg", "fruit"], (
            "reversed file order not reflected: %s" % cats
        )
        assert rows[0]["calories"] == 200, "first row must be file 2's first line"

    def test_load_foods_empty_paths(self):
        """L2: an empty paths list yields an empty four-column frame, no exception."""
        result = _run_driver(
            """
            df = R.load_foods([])
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["height"] == 0, "empty paths must give 0 rows"
        assert result["columns"] == [
            "category",
            "calories",
            "fats_g",
            "sugars_g",
        ], "empty-list columns wrong: %s" % result["columns"]
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["calories"] == "Int64"
        assert dtype_map["fats_g"] == "Float64"
        assert dtype_map["sugars_g"] == "Float64"

    def test_category_summary_columns_and_sorted(self):
        """L2: category_summary has the exact 5 columns in order, sorted by category."""
        result = _run_driver(
            _BUILD_TWO_FILES
            + """
            df = R.category_summary([f1, f2])
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == [
            "category",
            "n_items",
            "avg_calories",
            "total_sugars",
            "max_fats",
        ], "unexpected summary columns/order: %s" % result["columns"]
        cats = [r["category"] for r in result["rows"]]
        assert cats == sorted(cats), "rows must be sorted by category ascending"
        assert cats == ["fruit", "meat", "veg"], "distinct categories wrong: %s" % cats

    def test_category_summary_aggregate_values(self):
        """L2: per-category count, mean calories, summed sugars, max fats are exact."""
        result = _run_driver(
            _BUILD_TWO_FILES
            + """
            df = R.category_summary([f1, f2])
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_cat = {r["category"]: r for r in result["rows"]}
        # fruit: rows (60,0,11),(30,4,5),(90,1,8) -> n=3, avg=180/3=60, sugars=24, max_fats=4
        fr = by_cat["fruit"]
        assert fr["n_items"] == 3, "fruit n_items must be 3, got %s" % fr["n_items"]
        assert fr["avg_calories"] == pytest.approx(60.0)
        assert fr["total_sugars"] == pytest.approx(24.0)
        assert fr["max_fats"] == pytest.approx(4.0)
        # meat: (100,5,0),(200,10,1) -> n=2, avg=150, sugars=1, max_fats=10
        me = by_cat["meat"]
        assert me["n_items"] == 2
        assert me["avg_calories"] == pytest.approx(150.0)
        assert me["total_sugars"] == pytest.approx(1.0)
        assert me["max_fats"] == pytest.approx(10.0)
        # veg: (20,0,2),(40,0.5,3) -> n=2, avg=30, sugars=5, max_fats=0.5
        ve = by_cat["veg"]
        assert ve["n_items"] == 2
        assert ve["avg_calories"] == pytest.approx(30.0)
        assert ve["total_sugars"] == pytest.approx(5.0)
        assert ve["max_fats"] == pytest.approx(0.5)

    def test_category_summary_value_dtypes(self):
        """L2: avg_calories/total_sugars/max_fats are Float64, n_items integer."""
        result = _run_driver(
            _BUILD_TWO_FILES
            + """
            df = R.category_summary([f1, f2])
            print(json.dumps(_df_to_records(df)))
            """
        )
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["avg_calories"] == "Float64", dtype_map
        assert dtype_map["total_sugars"] == "Float64", dtype_map
        assert dtype_map["max_fats"] == "Float64", dtype_map
        assert dtype_map["n_items"] in ("Int64", "UInt32", "UInt64", "Int32"), (
            "n_items must be an integer count dtype, got %s" % dtype_map["n_items"]
        )

    def test_write_summary_roundtrip(self):
        """L2: write_summary writes a header CSV that reads back to identical data."""
        result = _run_driver(
            _BUILD_TWO_FILES
            + """
            summary = R.category_summary([f1, f2])
            out_path = os.path.join(tmp, "summary_out.csv")
            ret = R.write_summary(summary, out_path)
            file_exists = os.path.isfile(out_path)
            # first byte line must be a header (column names, not data)
            with open(out_path) as fh:
                first_line = fh.readline().strip()
            back = pl.read_csv(out_path)
            out = {
                "ret_is_none": ret is None,
                "file_exists": file_exists,
                "header": first_line,
                "orig_cols": list(summary.columns),
                "back": _df_to_records(back),
                "orig_height": summary.height,
            }
            print(json.dumps(out))
            """
        )
        assert result["ret_is_none"] is True, "write_summary must return None"
        assert result["file_exists"] is True, "output CSV file was not written to disk"
        assert result["header"] == "category,n_items,avg_calories,total_sugars,max_fats", (
            "CSV header row missing/wrong: %r" % result["header"]
        )
        back = result["back"]
        assert back["columns"] == result["orig_cols"], (
            "round-trip columns changed: %s vs %s" % (back["columns"], result["orig_cols"])
        )
        assert back["height"] == result["orig_height"] == 3, (
            "round-trip row count mismatch: %s" % back["height"]
        )
        by_cat = {r["category"]: r for r in back["rows"]}
        # Re-derive the same expected aggregates after the disk round trip.
        assert by_cat["fruit"]["n_items"] == 3
        assert by_cat["fruit"]["avg_calories"] == pytest.approx(60.0)
        assert by_cat["fruit"]["total_sugars"] == pytest.approx(24.0)
        assert by_cat["fruit"]["max_fats"] == pytest.approx(4.0)
        assert by_cat["meat"]["avg_calories"] == pytest.approx(150.0)
        assert by_cat["veg"]["max_fats"] == pytest.approx(0.5)

    def test_write_summary_real_disk_not_stub(self):
        """L2: write_summary actually writes the *given* frame (not a hardcoded one).

        A naive impl that ignores `summary` and dumps a fixed table would fail:
        we feed a single-category custom summary-shaped frame and demand it back.
        """
        result = _run_driver(
            """
            summary = pl.DataFrame(
                {
                    "category": ["zebra"],
                    "n_items": [7],
                    "avg_calories": [123.5],
                    "total_sugars": [9.0],
                    "max_fats": [42.0],
                },
                schema={
                    "category": pl.String,
                    "n_items": pl.Int64,
                    "avg_calories": pl.Float64,
                    "total_sugars": pl.Float64,
                    "max_fats": pl.Float64,
                },
            )
            out_path = os.path.join(tmp, "custom.csv")
            R.write_summary(summary, out_path)
            back = pl.read_csv(out_path)
            print(json.dumps(_df_to_records(back)))
            """
        )
        assert result["height"] == 1, "must write exactly the one given row"
        row = result["rows"][0]
        assert row["category"] == "zebra", "summary content must come from the argument"
        assert row["n_items"] == 7
        assert row["avg_calories"] == pytest.approx(123.5)
        assert row["total_sugars"] == pytest.approx(9.0)
        assert row["max_fats"] == pytest.approx(42.0)

    def test_uses_repo_bundled_foods_csv(self):
        """L2: functions read a real on-disk CSV (the repo's own foods1.csv)."""
        result = _run_driver(
            """
            src = os.path.join(os.getcwd(), "examples", "datasets", "foods1.csv")
            assert os.path.isfile(src), "repo dataset foods1.csv missing: " + src
            loaded = R.load_foods([src])
            summary = R.category_summary([src])
            # cross-check the agent's aggregates against an independent polars compute
            raw = pl.read_csv(src)
            indep = (
                raw.group_by("category")
                .agg(
                    pl.len().alias("n_items"),
                    pl.col("calories").mean().alias("avg_calories"),
                    pl.col("sugars_g").sum().alias("total_sugars"),
                    pl.col("fats_g").max().alias("max_fats"),
                )
                .sort("category")
            )
            out = {
                "loaded_height": loaded.height,
                "raw_height": raw.height,
                "summary": _df_to_records(summary),
                "indep": _df_to_records(indep),
            }
            print(json.dumps(out))
            """,
            timeout=240,
        )
        assert result["loaded_height"] == result["raw_height"], (
            "load_foods did not return all rows of foods1.csv"
        )
        agent = {r["category"]: r for r in result["summary"]["rows"]}
        indep = {r["category"]: r for r in result["indep"]["rows"]}
        assert set(agent) == set(indep), (
            "category set mismatch: %s vs %s" % (sorted(agent), sorted(indep))
        )
        # category order must match the independently sorted reference
        assert [r["category"] for r in result["summary"]["rows"]] == [
            r["category"] for r in result["indep"]["rows"]
        ], "summary not sorted by category like the reference"
        for cat, ref in indep.items():
            a = agent[cat]
            assert a["n_items"] == ref["n_items"], "n_items[%s]" % cat
            assert a["avg_calories"] == pytest.approx(ref["avg_calories"]), "avg[%s]" % cat
            assert a["total_sugars"] == pytest.approx(ref["total_sugars"]), "sugars[%s]" % cat
            assert a["max_fats"] == pytest.approx(ref["max_fats"]), "maxfats[%s]" % cat

    def test_native_pytest_suite_passes(self):
        """L2: the agent's own pytest suite passes (doc's native acceptance command)."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "examples/nutrition_report/test_report.py", "-q"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=420,
        )
        assert proc.returncode == 0, (
            "native pytest suite failed (rc=%s)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:])
        )
