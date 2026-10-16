"""Tests for the `polars-dataframe` skill task: a Sales Performance Reporting Module.

Verifies the deliverable `examples/sales_pipeline/report.py` inside the polars
repository (REPO_DIR=/workspace/polars). The four public functions
(`store_summary`, `top_employee_per_store`, `category_pivot`,
`flag_outlier_transactions`) are exercised dynamically: a focused driver script
is written into REPO_DIR, imports the agent's module + polars, runs it on
controlled in-memory DataFrames, and emits JSON that is deep-validated here.

L1 cases check the deliverable files exist and are importable. L2 cases drive
real polars behavior (null-aware sums/averages, join-based name resolution,
tie-breaking, alphabetical pivot columns, strict per-store outlier flagging,
empty-input shapes) so that a naive or hardcoded solution fails.
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/polars"
PKG_DIR = os.path.join(REPO_DIR, "examples", "sales_pipeline")
REPORT_PY = os.path.join(PKG_DIR, "report.py")


# ---------------------------------------------------------------------------
# Driver harness: run a python snippet from REPO_DIR with the agent's module
# importable, capturing a single JSON object printed on the LAST stdout line.
# ---------------------------------------------------------------------------

_PREAMBLE = textwrap.dedent(
    """
    import json, sys, os
    import polars as pl
    sys.path.insert(0, os.path.join(os.getcwd(), "examples"))
    from sales_pipeline import report as R

    def _df_to_records(df):
        # ordered list of column names + list-of-rows (python-native) + dtypes
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


# Shared fixture data builders embedded inside drivers ----------------------

_BUILD_TXNS = """
    transactions = pl.DataFrame(
        {
            "txn_id": [1, 2, 3, 4, 5, 6],
            "store": ["A", "A", "A", "B", "B", "A"],
            "employee_id": [10, 11, 10, 20, 20, 11],
            "category": ["food", "drink", "food", "food", "misc", "drink"],
            "amount": [100.0, 50.0, None, 80.0, None, 50.0],
        },
        schema={
            "txn_id": pl.Int64,
            "store": pl.String,
            "employee_id": pl.Int64,
            "category": pl.String,
            "amount": pl.Float64,
        },
    )
"""

_BUILD_EMP = """
    employees = pl.DataFrame(
        {
            "employee_id": [10, 11, 20],
            "name": ["Ann", "Bob", "Cara"],
            "store": ["A", "A", "B"],
        },
        schema={"employee_id": pl.Int64, "name": pl.String, "store": pl.String},
    )
"""


class TestPolarsDataframe:
    REPO_DIR = "/workspace/polars"

    # ------------------------------------------------------------------ L1

    def test_package_marker_exists(self):
        """L1: the package marker __init__.py is present."""
        assert os.path.isfile(
            os.path.join(PKG_DIR, "__init__.py")
        ), "examples/sales_pipeline/__init__.py missing"

    def test_report_module_exists(self):
        """L1: report.py deliverable exists and is non-trivial."""
        assert os.path.isfile(REPORT_PY), "examples/sales_pipeline/report.py missing"
        assert os.path.getsize(REPORT_PY) > 200, "report.py is suspiciously small"

    def test_public_functions_importable(self):
        """L1: the four public functions are importable and callable."""
        result = _run_driver(
            """
            names = ["store_summary", "top_employee_per_store",
                     "category_pivot", "flag_outlier_transactions"]
            out = {n: callable(getattr(R, n, None)) for n in names}
            print(json.dumps(out))
            """
        )
        for name, ok in result.items():
            assert ok, "%s missing or not callable in report.py" % name

    # ------------------------------------------------------------------ L2

    def test_store_summary_columns_and_order(self):
        """L2: store_summary returns the exact columns in order, sorted by store."""
        result = _run_driver(
            _BUILD_TXNS
            + """
            df = R.store_summary(transactions)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == [
            "store",
            "total_amount",
            "txn_count",
            "valid_txn_count",
            "avg_valid_amount",
        ], "unexpected column set/order: %s" % result["columns"]
        stores = [r["store"] for r in result["rows"]]
        assert stores == sorted(stores), "rows must be sorted by store ascending"
        assert stores == ["A", "B"]

    def test_store_summary_null_aware_aggregates(self):
        """L2: sums treat null as 0; txn_count counts all; valid_txn_count excludes nulls."""
        result = _run_driver(
            _BUILD_TXNS
            + """
            df = R.store_summary(transactions).sort("store")
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_store = {r["store"]: r for r in result["rows"]}
        # Store A: amounts 100,50,null,50 -> total 200, 4 txns, 3 valid, avg 200/3
        a = by_store["A"]
        assert a["total_amount"] == pytest.approx(200.0)
        assert a["txn_count"] == 4
        assert a["valid_txn_count"] == 3
        assert a["avg_valid_amount"] == pytest.approx(200.0 / 3.0)
        # Store B: amounts 80,null -> total 80, 2 txns, 1 valid, avg 80
        b = by_store["B"]
        assert b["total_amount"] == pytest.approx(80.0)
        assert b["txn_count"] == 2
        assert b["valid_txn_count"] == 1
        assert b["avg_valid_amount"] == pytest.approx(80.0)

    def test_store_summary_all_null_store(self):
        """L2: a store with every amount null -> total 0.0 and avg null (not 0/NaN)."""
        result = _run_driver(
            """
            transactions = pl.DataFrame(
                {
                    "txn_id": [1, 2, 3],
                    "store": ["A", "Z", "Z"],
                    "employee_id": [1, 2, 2],
                    "category": ["food", "food", "drink"],
                    "amount": [10.0, None, None],
                },
                schema={"txn_id": pl.Int64, "store": pl.String,
                        "employee_id": pl.Int64, "category": pl.String,
                        "amount": pl.Float64},
            )
            df = R.store_summary(transactions).sort("store")
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_store = {r["store"]: r for r in result["rows"]}
        assert "Z" in by_store, "all-null store must still appear as a row"
        z = by_store["Z"]
        assert z["total_amount"] == pytest.approx(0.0)
        assert z["txn_count"] == 2
        assert z["valid_txn_count"] == 0
        assert z["avg_valid_amount"] is None, (
            "all-null store avg must be null, got %r" % z["avg_valid_amount"]
        )

    def test_top_employee_basic_and_grouping_by_txn_store(self):
        """L2: top employee per store by summed non-null amount, grouped by txn store."""
        result = _run_driver(
            _BUILD_TXNS
            + _BUILD_EMP
            + """
            df = R.top_employee_per_store(transactions, employees)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == [
            "store",
            "employee_id",
            "name",
            "employee_total",
        ], "unexpected columns: %s" % result["columns"]
        by_store = {r["store"]: r for r in result["rows"]}
        assert sorted(by_store) == ["A", "B"]
        # Store A: emp10 -> 100 (+null), emp11 -> 50+50=100 -> tie -> smaller id 10 wins
        a = by_store["A"]
        assert a["employee_id"] == 10
        assert a["name"] == "Ann"
        assert a["employee_total"] == pytest.approx(100.0)
        # Store B: only emp20 -> 80 (+null)
        b = by_store["B"]
        assert b["employee_id"] == 20
        assert b["name"] == "Cara"
        assert b["employee_total"] == pytest.approx(80.0)

    def test_top_employee_tie_breaks_to_smaller_id(self):
        """L2: when two employees tie on total, the smaller employee_id is chosen."""
        result = _run_driver(
            """
            transactions = pl.DataFrame(
                {
                    "txn_id": [1, 2, 3, 4],
                    "store": ["A", "A", "A", "A"],
                    "employee_id": [7, 7, 3, 3],
                    "category": ["food", "food", "food", "food"],
                    "amount": [40.0, 30.0, 35.0, 35.0],
                },
                schema={"txn_id": pl.Int64, "store": pl.String,
                        "employee_id": pl.Int64, "category": pl.String,
                        "amount": pl.Float64},
            )
            employees = pl.DataFrame(
                {"employee_id": [3, 7], "name": ["Eve", "Sam"], "store": ["A", "A"]},
                schema={"employee_id": pl.Int64, "name": pl.String, "store": pl.String},
            )
            df = R.top_employee_per_store(transactions, employees)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert len(result["rows"]) == 1
        row = result["rows"][0]
        # both total 70 -> tie -> smaller id 3 (Eve)
        assert row["employee_total"] == pytest.approx(70.0)
        assert row["employee_id"] == 3, "tie must break to smaller employee_id"
        assert row["name"] == "Eve"

    def test_top_employee_unknown_id_gets_null_name(self):
        """L2: an employee in transactions but absent from employees -> name null."""
        result = _run_driver(
            """
            transactions = pl.DataFrame(
                {
                    "txn_id": [1, 2],
                    "store": ["A", "A"],
                    "employee_id": [99, 5],
                    "category": ["food", "food"],
                    "amount": [200.0, 10.0],
                },
                schema={"txn_id": pl.Int64, "store": pl.String,
                        "employee_id": pl.Int64, "category": pl.String,
                        "amount": pl.Float64},
            )
            employees = pl.DataFrame(
                {"employee_id": [5], "name": ["Liz"], "store": ["A"]},
                schema={"employee_id": pl.Int64, "name": pl.String, "store": pl.String},
            )
            df = R.top_employee_per_store(transactions, employees)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert len(result["rows"]) == 1
        row = result["rows"][0]
        assert row["employee_id"] == 99, "top seller (unknown id) must win"
        assert row["employee_total"] == pytest.approx(200.0)
        assert row["name"] is None, "unknown employee_id must resolve to null name"

    def test_category_pivot_alphabetical_columns_and_zero_fill(self):
        """L2: pivot has store + alphabetically ordered category columns, 0.0 fills."""
        result = _run_driver(
            _BUILD_TXNS
            + """
            df = R.category_pivot(transactions)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        assert cols[0] == "store", "first column must be store"
        cat_cols = cols[1:]
        assert cat_cols == sorted(cat_cols), "category columns must be alphabetical"
        assert cat_cols == ["drink", "food", "misc"], "unexpected category columns: %s" % cat_cols
        by_store = {r["store"]: r for r in result["rows"]}
        assert [r["store"] for r in result["rows"]] == ["A", "B"]
        # Store A: food = 100 (+null) = 100; drink = 50+50 = 100; misc = 0.0
        a = by_store["A"]
        assert a["food"] == pytest.approx(100.0)
        assert a["drink"] == pytest.approx(100.0)
        assert a["misc"] == pytest.approx(0.0), "absent (store,cat) combo must be 0.0"
        # Store B: food = 80; drink = 0.0; misc = 0.0 (amount null)
        b = by_store["B"]
        assert b["food"] == pytest.approx(80.0)
        assert b["drink"] == pytest.approx(0.0)
        assert b["misc"] == pytest.approx(0.0)

    def test_category_pivot_column_exists_even_if_unsold_in_some_store(self):
        """L2: a category sold only somewhere still yields a column with 0.0 elsewhere."""
        result = _run_driver(
            """
            transactions = pl.DataFrame(
                {
                    "txn_id": [1, 2],
                    "store": ["A", "B"],
                    "employee_id": [1, 2],
                    "category": ["food", "drink"],
                    "amount": [10.0, 20.0],
                },
                schema={"txn_id": pl.Int64, "store": pl.String,
                        "employee_id": pl.Int64, "category": pl.String,
                        "amount": pl.Float64},
            )
            df = R.category_pivot(transactions)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        assert cols == ["store", "drink", "food"], "cols: %s" % cols
        by_store = {r["store"]: r for r in result["rows"]}
        # store A never sold drink -> 0.0
        assert by_store["A"]["drink"] == pytest.approx(0.0)
        assert by_store["A"]["food"] == pytest.approx(10.0)
        # store B never sold food -> 0.0
        assert by_store["B"]["food"] == pytest.approx(0.0)
        assert by_store["B"]["drink"] == pytest.approx(20.0)

    def test_flag_outlier_preserves_rows_and_order(self):
        """L2: flag_outlier preserves txn_id order/count and adds a Boolean column."""
        result = _run_driver(
            _BUILD_TXNS
            + """
            df = R.flag_outlier_transactions(transactions)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        assert "above_store_avg" in cols, "new boolean column missing"
        assert cols[-1] == "above_store_avg" or "above_store_avg" in cols
        # dtype check: boolean
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["above_store_avg"].lower().startswith("bool"), (
            "above_store_avg must be Boolean, got %s" % dtype_map["above_store_avg"]
        )
        txn_ids = [r["txn_id"] for r in result["rows"]]
        assert txn_ids == [1, 2, 3, 4, 5, 6], "row order/count must be preserved"
        # original columns retained
        for c in ["txn_id", "store", "employee_id", "category", "amount"]:
            assert c in cols, "original column %s dropped" % c

    def test_flag_outlier_strict_per_store_average(self):
        """L2: above_store_avg uses per-store non-null avg, strict >, null -> False."""
        result = _run_driver(
            _BUILD_TXNS
            + """
            df = R.flag_outlier_transactions(transactions)
            print(json.dumps(_df_to_records(df)))
            """
        )
        flags = {r["txn_id"]: r["above_store_avg"] for r in result["rows"]}
        # Store A non-null amounts: 100,50,50 -> avg 200/3 ~= 66.67
        #   txn1 amount 100 > 66.67 -> True
        #   txn2 amount 50  -> False
        #   txn3 amount null -> False
        #   txn6 amount 50  -> False
        assert flags[1] is True
        assert flags[2] is False
        assert flags[3] is False, "null amount must be False"
        assert flags[6] is False
        # Store B non-null amounts: 80 -> avg 80
        #   txn4 amount 80 -> NOT strictly greater than 80 -> False
        #   txn5 amount null -> False
        assert flags[4] is False, "amount equal to store avg must NOT be flagged"
        assert flags[5] is False

    def test_flag_outlier_single_txn_not_flagged(self):
        """L2: a store with a single non-null txn is never flagged (not strictly greater)."""
        result = _run_driver(
            """
            transactions = pl.DataFrame(
                {
                    "txn_id": [1, 2],
                    "store": ["A", "B"],
                    "employee_id": [1, 2],
                    "category": ["food", "food"],
                    "amount": [500.0, 7.0],
                },
                schema={"txn_id": pl.Int64, "store": pl.String,
                        "employee_id": pl.Int64, "category": pl.String,
                        "amount": pl.Float64},
            )
            df = R.flag_outlier_transactions(transactions)
            print(json.dumps(_df_to_records(df)))
            """
        )
        flags = {r["txn_id"]: r["above_store_avg"] for r in result["rows"]}
        assert flags[1] is False, "single-txn store must not be flagged"
        assert flags[2] is False

    def test_empty_input_shapes_all_functions(self):
        """L2: every function returns an empty DataFrame with correct columns on empty input."""
        result = _run_driver(
            """
            transactions = pl.DataFrame(
                schema={"txn_id": pl.Int64, "store": pl.String,
                        "employee_id": pl.Int64, "category": pl.String,
                        "amount": pl.Float64},
            )
            employees = pl.DataFrame(
                schema={"employee_id": pl.Int64, "name": pl.String, "store": pl.String},
            )
            out = {}
            ss = R.store_summary(transactions)
            out["store_summary"] = {"cols": list(ss.columns), "h": ss.height}
            te = R.top_employee_per_store(transactions, employees)
            out["top_employee"] = {"cols": list(te.columns), "h": te.height}
            cp = R.category_pivot(transactions)
            out["category_pivot"] = {"cols": list(cp.columns), "h": cp.height}
            fo = R.flag_outlier_transactions(transactions)
            out["flag_outlier"] = {"cols": list(fo.columns), "h": fo.height}
            print(json.dumps(out))
            """
        )
        ss = result["store_summary"]
        assert ss["h"] == 0, "store_summary must be empty on empty input"
        assert ss["cols"] == [
            "store",
            "total_amount",
            "txn_count",
            "valid_txn_count",
            "avg_valid_amount",
        ], "store_summary empty cols: %s" % ss["cols"]
        te = result["top_employee"]
        assert te["h"] == 0
        assert te["cols"] == ["store", "employee_id", "name", "employee_total"], (
            "top_employee empty cols: %s" % te["cols"]
        )
        cp = result["category_pivot"]
        assert cp["h"] == 0
        assert cp["cols"][0] == "store", "category_pivot empty must keep store column"
        fo = result["flag_outlier"]
        assert fo["h"] == 0
        assert "above_store_avg" in fo["cols"], (
            "flag_outlier empty must keep above_store_avg column"
        )

    def test_native_pytest_suite_passes(self):
        """L2: the agent's own pytest suite for the module passes (acceptance command)."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "examples/sales_pipeline/test_report.py", "-q"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=420,
        )
        assert proc.returncode == 0, (
            "native pytest suite failed (rc=%s)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:])
        )
