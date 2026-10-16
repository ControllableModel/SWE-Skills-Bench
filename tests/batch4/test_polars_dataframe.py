"""Tests for the `polars-dataframe` skill task (ext4): an Order-Fulfillment
Reconciliation Module.

Verifies the deliverable `examples/order_recon/recon.py` inside the polars
repository (REPO_DIR=/workspace/polars). The four public functions
(`enrich_orders`, `unshipped_orders`, `fulfillment_status`,
`orphan_shipments`) are exercised dynamically: a focused driver script is
written into REPO_DIR, imports the agent's module + polars, runs it on
controlled in-memory DataFrames, and emits JSON that is deep-validated here.

L1 cases check the deliverable files exist and the public functions are
importable/callable. L2 cases drive real polars behavior:
  * enrich_orders keeps catalog-less orders with null name + null line_total
    (a naive inner-join solution that drops them, or one that treats price as
    0.0, fails);
  * unshipped_orders returns only orders absent from shipments without adding
    shipment columns;
  * fulfillment_status sums shipped qty per order (0 not null when none) and
    assigns complete/partial/pending by strict thresholds;
  * orphan_shipments returns shipments whose order_id is absent from orders,
    keeping only shipment columns and stable order for equal order_id;
  * every function returns a correctly-shaped EMPTY DataFrame on empty input.

The final L2 case runs the doc's native acceptance command
(`python -m pytest examples/order_recon/test_recon.py -q`).
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/polars"
PKG_DIR = os.path.join(REPO_DIR, "examples", "order_recon")
RECON_PY = os.path.join(PKG_DIR, "recon.py")


# ---------------------------------------------------------------------------
# Driver harness: run a python snippet from REPO_DIR with the agent's module
# importable, capturing a single JSON object printed on the LAST stdout line.
# ---------------------------------------------------------------------------

_PREAMBLE = textwrap.dedent(
    """
    import json, sys, os
    import polars as pl
    sys.path.insert(0, os.path.join(os.getcwd(), "examples"))
    from order_recon import recon as R

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
    driver_path = os.path.join(REPO_DIR, "_skilltest_recon_driver.py")
    with open(driver_path, "w") as fh:
        fh.write(script)
    try:
        proc = subprocess.run(
            ["python", "_skilltest_recon_driver.py"],
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

# orders: order 1 (sku a), 2 (sku b), 3 (sku z = not in catalog),
#         4 (sku a, no shipment -> pending), 5 (sku b, fully shipped)
_BUILD_ORDERS = """
    orders = pl.DataFrame(
        {
            "order_id": [3, 1, 5, 2, 4],
            "sku": ["z", "a", "b", "b", "a"],
            "qty_ordered": [4, 10, 6, 3, 7],
        },
        schema={"order_id": pl.Int64, "sku": pl.String, "qty_ordered": pl.Int64},
    )
"""

# shipments: order 1 partial (4), order 1 partial (6) -> complete (10),
#            order 2 partial (1) -> partial, order 3 (5) ships,
#            order 5 (6) -> complete, order 99 orphan (2)
_BUILD_SHIPMENTS = """
    shipments = pl.DataFrame(
        {
            "order_id": [1, 1, 2, 3, 5, 99],
            "qty_shipped": [4, 6, 1, 5, 6, 2],
        },
        schema={"order_id": pl.Int64, "qty_shipped": pl.Int64},
    )
"""

# catalog: a, b priced; "z" intentionally absent
_BUILD_CATALOG = """
    catalog = pl.DataFrame(
        {
            "sku": ["a", "b"],
            "product_name": ["Widget", "Gadget"],
            "unit_price": [2.5, 4.0],
        },
        schema={"sku": pl.String, "product_name": pl.String, "unit_price": pl.Float64},
    )
"""


class TestPolarsDataframe:
    REPO_DIR = "/workspace/polars"

    # ------------------------------------------------------------------ L1

    def test_package_marker_exists(self):
        """L1: the package marker __init__.py is present."""
        assert os.path.isfile(
            os.path.join(PKG_DIR, "__init__.py")
        ), "examples/order_recon/__init__.py missing"

    def test_recon_module_exists(self):
        """L1: recon.py deliverable exists and is non-trivial."""
        assert os.path.isfile(RECON_PY), "examples/order_recon/recon.py missing"
        assert os.path.getsize(RECON_PY) > 200, "recon.py is suspiciously small"

    def test_public_functions_importable(self):
        """L1: the four public functions are importable and callable."""
        result = _run_driver(
            """
            names = ["enrich_orders", "unshipped_orders",
                     "fulfillment_status", "orphan_shipments"]
            out = {n: callable(getattr(R, n, None)) for n in names}
            print(json.dumps(out))
            """
        )
        for name, ok in result.items():
            assert ok, "%s missing or not callable in recon.py" % name

    # ------------------------------------------------------------------ L2
    # enrich_orders ----------------------------------------------------------

    def test_enrich_orders_columns_order_and_sort(self):
        """L2: enrich_orders has exact columns in order, sorted by order_id asc."""
        result = _run_driver(
            _BUILD_ORDERS
            + _BUILD_CATALOG
            + """
            df = R.enrich_orders(orders, catalog)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == [
            "order_id",
            "sku",
            "qty_ordered",
            "product_name",
            "line_total",
        ], "unexpected columns/order: %s" % result["columns"]
        ids = [r["order_id"] for r in result["rows"]]
        assert ids == sorted(ids), "rows must be sorted by order_id ascending"
        assert ids == [1, 2, 3, 4, 5], "every order must survive enrich (got %s)" % ids
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["product_name"].lower().startswith("str"), (
            "product_name dtype must be String, got %s" % dtype_map["product_name"]
        )
        assert "float" in dtype_map["line_total"].lower(), (
            "line_total dtype must be Float64, got %s" % dtype_map["line_total"]
        )

    def test_enrich_orders_line_total_and_name(self):
        """L2: line_total = qty_ordered * unit_price and product_name resolved."""
        result = _run_driver(
            _BUILD_ORDERS
            + _BUILD_CATALOG
            + """
            df = R.enrich_orders(orders, catalog).sort("order_id")
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_id = {r["order_id"]: r for r in result["rows"]}
        # order 1: sku a, qty 10, price 2.5 -> 25.0, name Widget
        assert by_id[1]["product_name"] == "Widget"
        assert by_id[1]["line_total"] == pytest.approx(25.0)
        # order 2: sku b, qty 3, price 4.0 -> 12.0
        assert by_id[2]["product_name"] == "Gadget"
        assert by_id[2]["line_total"] == pytest.approx(12.0)
        # order 5: sku b, qty 6, price 4.0 -> 24.0
        assert by_id[5]["line_total"] == pytest.approx(24.0)
        # order 4: sku a, qty 7, price 2.5 -> 17.5
        assert by_id[4]["line_total"] == pytest.approx(17.5)

    def test_enrich_orders_missing_sku_keeps_nulls(self):
        """L2: order with sku absent from catalog survives with null name + null total.

        A naive inner-join (drops it) or zero-price impl (line_total=0.0) fails.
        """
        result = _run_driver(
            _BUILD_ORDERS
            + _BUILD_CATALOG
            + """
            df = R.enrich_orders(orders, catalog).sort("order_id")
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_id = {r["order_id"]: r for r in result["rows"]}
        assert 3 in by_id, "order 3 (sku not in catalog) must NOT be dropped"
        o3 = by_id[3]
        assert o3["sku"] == "z"
        assert o3["qty_ordered"] == 4
        assert o3["product_name"] is None, (
            "missing-catalog product_name must be null, got %r" % o3["product_name"]
        )
        assert o3["line_total"] is None, (
            "missing-catalog line_total must be null (not 0.0), got %r"
            % o3["line_total"]
        )

    # unshipped_orders -------------------------------------------------------

    def test_unshipped_orders_only_unshipped_no_extra_cols(self):
        """L2: unshipped_orders returns only orders absent from shipments, no extra cols."""
        result = _run_driver(
            _BUILD_ORDERS
            + _BUILD_SHIPMENTS
            + """
            df = R.unshipped_orders(orders, shipments)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        # only order 4 has no shipment row
        assert result["columns"] == ["order_id", "sku", "qty_ordered"], (
            "unshipped_orders must keep exactly orders columns, got %s"
            % result["columns"]
        )
        ids = [r["order_id"] for r in result["rows"]]
        assert ids == [4], "only order 4 is unshipped, got %s" % ids
        assert result["rows"][0]["sku"] == "a"
        assert result["rows"][0]["qty_ordered"] == 7

    def test_unshipped_orders_empty_when_all_shipped(self):
        """L2: when every order has a shipment, return empty frame with orders columns."""
        result = _run_driver(
            """
            orders = pl.DataFrame(
                {"order_id": [1, 2], "sku": ["a", "b"], "qty_ordered": [3, 4]},
                schema={"order_id": pl.Int64, "sku": pl.String, "qty_ordered": pl.Int64},
            )
            shipments = pl.DataFrame(
                {"order_id": [2, 1], "qty_shipped": [1, 1]},
                schema={"order_id": pl.Int64, "qty_shipped": pl.Int64},
            )
            df = R.unshipped_orders(orders, shipments)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["order_id", "sku", "qty_ordered"]
        assert result["rows"] == [], "no order should be unshipped"

    # fulfillment_status -----------------------------------------------------

    def test_fulfillment_status_columns_and_sort(self):
        """L2: fulfillment_status exact columns/order, one row per order, sorted asc."""
        result = _run_driver(
            _BUILD_ORDERS
            + _BUILD_SHIPMENTS
            + """
            df = R.fulfillment_status(orders, shipments)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == [
            "order_id",
            "qty_ordered",
            "qty_shipped_total",
            "status",
        ], "unexpected columns/order: %s" % result["columns"]
        ids = [r["order_id"] for r in result["rows"]]
        assert ids == [1, 2, 3, 4, 5], "one row per order, sorted asc, got %s" % ids
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert "int" in dtype_map["qty_shipped_total"].lower(), (
            "qty_shipped_total dtype must be Int64, got %s"
            % dtype_map["qty_shipped_total"]
        )

    def test_fulfillment_status_sums_and_thresholds(self):
        """L2: qty_shipped_total sums per order (0 when none) and statuses by threshold."""
        result = _run_driver(
            _BUILD_ORDERS
            + _BUILD_SHIPMENTS
            + """
            df = R.fulfillment_status(orders, shipments).sort("order_id")
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_id = {r["order_id"]: r for r in result["rows"]}
        # order 1: shipped 4+6=10, ordered 10 -> complete
        assert by_id[1]["qty_shipped_total"] == 10
        assert by_id[1]["status"] == "complete"
        # order 2: shipped 1, ordered 3 -> partial
        assert by_id[2]["qty_shipped_total"] == 1
        assert by_id[2]["status"] == "partial"
        # order 3: shipped 5, ordered 4 -> shipped >= ordered and >0 -> complete
        assert by_id[3]["qty_shipped_total"] == 5
        assert by_id[3]["status"] == "complete"
        # order 4: no shipment -> 0 (not null), pending
        assert by_id[4]["qty_shipped_total"] == 0, (
            "order with no shipment must total 0 not null, got %r"
            % by_id[4]["qty_shipped_total"]
        )
        assert by_id[4]["status"] == "pending"
        # order 5: shipped 6, ordered 6 -> complete
        assert by_id[5]["qty_shipped_total"] == 6
        assert by_id[5]["status"] == "complete"

    def test_fulfillment_status_partial_exact_boundary(self):
        """L2: status thresholds are strict — equal qty is complete, one short is partial."""
        result = _run_driver(
            """
            orders = pl.DataFrame(
                {"order_id": [1, 2], "sku": ["a", "a"], "qty_ordered": [5, 5]},
                schema={"order_id": pl.Int64, "sku": pl.String, "qty_ordered": pl.Int64},
            )
            shipments = pl.DataFrame(
                {"order_id": [1, 2], "qty_shipped": [5, 4]},
                schema={"order_id": pl.Int64, "qty_shipped": pl.Int64},
            )
            df = R.fulfillment_status(orders, shipments).sort("order_id")
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_id = {r["order_id"]: r for r in result["rows"]}
        assert by_id[1]["status"] == "complete", "shipped==ordered must be complete"
        assert by_id[2]["status"] == "partial", "shipped one short must be partial"

    # orphan_shipments -------------------------------------------------------

    def test_orphan_shipments_only_unmatched_no_extra_cols(self):
        """L2: orphan_shipments returns shipments whose order_id is absent from orders."""
        result = _run_driver(
            _BUILD_ORDERS
            + _BUILD_SHIPMENTS
            + """
            df = R.orphan_shipments(orders, shipments)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["order_id", "qty_shipped"], (
            "orphan_shipments must keep exactly shipments columns, got %s"
            % result["columns"]
        )
        rows = result["rows"]
        # order 99 is the only shipment order_id not in orders
        assert [r["order_id"] for r in rows] == [99], (
            "only order 99 is orphan, got %s" % [r["order_id"] for r in rows]
        )
        assert rows[0]["qty_shipped"] == 2

    def test_orphan_shipments_stable_order_for_equal_id(self):
        """L2: orphans sorted by order_id, preserving original order for equal ids."""
        result = _run_driver(
            """
            orders = pl.DataFrame(
                {"order_id": [1], "sku": ["a"], "qty_ordered": [3]},
                schema={"order_id": pl.Int64, "sku": pl.String, "qty_ordered": pl.Int64},
            )
            shipments = pl.DataFrame(
                {"order_id": [50, 7, 50, 7], "qty_shipped": [100, 200, 300, 400]},
                schema={"order_id": pl.Int64, "qty_shipped": pl.Int64},
            )
            df = R.orphan_shipments(orders, shipments)
            print(json.dumps(_df_to_records(df)))
            """
        )
        rows = result["rows"]
        # all four shipments are orphans (no order_id 50 or 7 in orders)
        ids = [r["order_id"] for r in rows]
        assert ids == [7, 7, 50, 50], "must be sorted by order_id asc, got %s" % ids
        pairs = [(r["order_id"], r["qty_shipped"]) for r in rows]
        # within order_id 7, original relative order (200 before 400); within 50 (100 before 300)
        assert pairs == [(7, 200), (7, 400), (50, 100), (50, 300)], (
            "stable order within equal order_id not preserved: %s" % pairs
        )

    # empty inputs -----------------------------------------------------------

    def test_empty_input_shapes_all_functions(self):
        """L2: every function returns an empty DataFrame with the correct columns."""
        result = _run_driver(
            """
            orders = pl.DataFrame(
                schema={"order_id": pl.Int64, "sku": pl.String, "qty_ordered": pl.Int64},
            )
            shipments = pl.DataFrame(
                schema={"order_id": pl.Int64, "qty_shipped": pl.Int64},
            )
            catalog = pl.DataFrame(
                schema={"sku": pl.String, "product_name": pl.String, "unit_price": pl.Float64},
            )
            out = {}
            eo = R.enrich_orders(orders, catalog)
            out["enrich_orders"] = {"cols": list(eo.columns), "h": eo.height}
            uo = R.unshipped_orders(orders, shipments)
            out["unshipped_orders"] = {"cols": list(uo.columns), "h": uo.height}
            fs = R.fulfillment_status(orders, shipments)
            out["fulfillment_status"] = {"cols": list(fs.columns), "h": fs.height}
            os_ = R.orphan_shipments(orders, shipments)
            out["orphan_shipments"] = {"cols": list(os_.columns), "h": os_.height}
            print(json.dumps(out))
            """
        )
        eo = result["enrich_orders"]
        assert eo["h"] == 0, "enrich_orders must be empty on empty input"
        assert eo["cols"] == [
            "order_id",
            "sku",
            "qty_ordered",
            "product_name",
            "line_total",
        ], "enrich_orders empty cols: %s" % eo["cols"]
        uo = result["unshipped_orders"]
        assert uo["h"] == 0
        assert uo["cols"] == ["order_id", "sku", "qty_ordered"], (
            "unshipped_orders empty cols: %s" % uo["cols"]
        )
        fs = result["fulfillment_status"]
        assert fs["h"] == 0
        assert fs["cols"] == [
            "order_id",
            "qty_ordered",
            "qty_shipped_total",
            "status",
        ], "fulfillment_status empty cols: %s" % fs["cols"]
        os_ = result["orphan_shipments"]
        assert os_["h"] == 0
        assert os_["cols"] == ["order_id", "qty_shipped"], (
            "orphan_shipments empty cols: %s" % os_["cols"]
        )

    # native acceptance command ---------------------------------------------

    def test_native_pytest_suite_passes(self):
        """L2: the agent's own pytest suite passes (doc's native acceptance command)."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "examples/order_recon/test_recon.py", "-q"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=420,
        )
        assert proc.returncode == 0, (
            "native pytest suite failed (rc=%s)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:])
        )
