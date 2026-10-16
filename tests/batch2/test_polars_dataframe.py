"""Tests for the `polars-dataframe` skill task (ext2 variant): an Inventory
Ledger Window-Analytics Module.

Verifies the deliverable `examples/inventory_ledger/ledger.py` inside the polars
repository (REPO_DIR=/workspace/polars). The three public functions
(`running_balance`, `movement_rank`, `warehouse_share`) are exercised
dynamically: a focused driver script is written into REPO_DIR, imports the
agent's module + polars, runs it on controlled in-memory DataFrames, and emits
JSON that is deep-validated here.

L1 cases check the deliverable files exist and the functions are importable.
L2 cases drive real polars behavior so a naive/hardcoded solution fails:
  - `running_balance`: per-product cumulative sum in seq order, restarting at
    zero per product, no cross-product leakage, output sort order preserved.
  - `movement_rank`: per-product DENSE rank of |delta| with the LARGEST
    magnitude as rank 1, ties share a rank, no gaps, exact output ordering.
  - `warehouse_share`: receipt-fraction of per-warehouse positive total, 0.0
    for non-receipts, 0.0 (never NaN / never raising) for receipt-free
    warehouses, original columns preserved.
  - empty-input shapes for all three functions.
Finally the agent's own pytest suite (the native acceptance command) is run.
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/polars"
PKG_DIR = os.path.join(REPO_DIR, "examples", "inventory_ledger")
LEDGER_PY = os.path.join(PKG_DIR, "ledger.py")


# ---------------------------------------------------------------------------
# Driver harness: run a python snippet from REPO_DIR with the agent's module
# importable, capturing a single JSON object printed on the LAST stdout line.
# ---------------------------------------------------------------------------

_PREAMBLE = textwrap.dedent(
    """
    import json, sys, os
    import polars as pl
    sys.path.insert(0, os.path.join(os.getcwd(), "examples"))
    from inventory_ledger import ledger as L

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
    driver_path = os.path.join(REPO_DIR, "_skilltest_ledger_driver.py")
    with open(driver_path, "w") as fh:
        fh.write(script)
    try:
        proc = subprocess.run(
            ["python", "_skilltest_ledger_driver.py"],
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


# Shared, intentionally UNSORTED fixture exercising cross-product interleaving,
# magnitude ties, mixed-sign deltas, and a receipt-free warehouse. ----------
#
# seq order within product P1: 1(+5), 4(-2), 6(+3)  -> balances 5, 3, 6
# seq order within product P2: 2(+10), 3(-4), 5(+4) -> balances 10, 6, 10
#
# warehouse W1 receipts: seq1 +5, seq2 +10, seq6 +3 = 18 total
# warehouse W2 receipts: seq5 +4 = 4 total ; W2 also has seq3 -4, seq4 -2 (<=0)
_BUILD_MOVES = """
    movements = pl.DataFrame(
        {
            "seq":       [4,     6,     2,     5,     1,     3],
            "product":   ["P1",  "P1",  "P2",  "P2",  "P1",  "P2"],
            "warehouse": ["W1",  "W1",  "W1",  "W2",  "W1",  "W2"],
            "delta":     [-2,    3,     10,    4,     5,     -4],
        },
        schema={
            "seq": pl.Int64,
            "product": pl.String,
            "warehouse": pl.String,
            "delta": pl.Int64,
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
        ), "examples/inventory_ledger/__init__.py missing"

    def test_ledger_module_exists(self):
        """L1: ledger.py deliverable exists and is non-trivial."""
        assert os.path.isfile(LEDGER_PY), "examples/inventory_ledger/ledger.py missing"
        assert os.path.getsize(LEDGER_PY) > 200, "ledger.py is suspiciously small"

    def test_public_functions_importable(self):
        """L1: the three public functions are importable and callable."""
        result = _run_driver(
            """
            names = ["running_balance", "movement_rank", "warehouse_share"]
            out = {n: callable(getattr(L, n, None)) for n in names}
            print(json.dumps(out))
            """
        )
        for name, ok in result.items():
            assert ok, "%s missing or not callable in ledger.py" % name

    # ------------------------------------------------------------------ L2: running_balance

    def test_running_balance_columns_and_sort_order(self):
        """L2: running_balance preserves all columns, adds Int64 balance, sorts by product,seq."""
        result = _run_driver(
            _BUILD_MOVES
            + """
            df = L.running_balance(movements)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        for c in ["seq", "product", "warehouse", "delta", "balance"]:
            assert c in cols, "running_balance missing column %s: %s" % (c, cols)
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["balance"].lower().startswith("int"), (
            "balance must be an integer dtype, got %s" % dtype_map["balance"]
        )
        # sorted by product asc, then seq asc
        order = [(r["product"], r["seq"]) for r in result["rows"]]
        assert order == sorted(order), "rows must be sorted by product then seq: %s" % order
        # full seq set preserved (no rows dropped/added)
        assert sorted(r["seq"] for r in result["rows"]) == [1, 2, 3, 4, 5, 6]

    def test_running_balance_per_product_cumsum_values(self):
        """L2: balance is per-product cumulative sum in seq order, restarting per product."""
        result = _run_driver(
            _BUILD_MOVES
            + """
            df = L.running_balance(movements)
            print(json.dumps(_df_to_records(df)))
            """
        )
        bal = {r["seq"]: r["balance"] for r in result["rows"]}
        # P1 in seq order: seq1 +5 ->5, seq4 -2 ->3, seq6 +3 ->6
        assert bal[1] == 5, "P1 seq1 balance"
        assert bal[4] == 3, "P1 seq4 balance (5-2)"
        assert bal[6] == 6, "P1 seq6 balance (3+3)"
        # P2 in seq order: seq2 +10 ->10, seq3 -4 ->6, seq5 +4 ->10
        assert bal[2] == 10, "P2 seq2 balance"
        assert bal[3] == 6, "P2 seq3 balance (10-4)"
        assert bal[5] == 10, "P2 seq5 balance (6+4)"

    def test_running_balance_no_cross_product_leak(self):
        """L2: an interleaved-by-seq second product must NOT inherit the first's running total."""
        result = _run_driver(
            """
            movements = pl.DataFrame(
                {
                    "seq":       [1,    2,    3,    4],
                    "product":   ["A",  "B",  "A",  "B"],
                    "warehouse": ["W",  "W",  "W",  "W"],
                    "delta":     [100,  1,    100,  1],
                },
                schema={"seq": pl.Int64, "product": pl.String,
                        "warehouse": pl.String, "delta": pl.Int64},
            )
            df = L.running_balance(movements)
            print(json.dumps(_df_to_records(df)))
            """
        )
        bal = {r["seq"]: r["balance"] for r in result["rows"]}
        # A: seq1 100, seq3 200 ; B must stay tiny (1, then 2) -> proves no leakage
        assert bal[1] == 100
        assert bal[3] == 200
        assert bal[2] == 1, "product B must restart at zero, not inherit A's 100"
        assert bal[4] == 2, "product B cumulative must be 1+1=2, not contaminated by A"

    # ------------------------------------------------------------------ L2: movement_rank

    def test_movement_rank_columns_order_and_sort(self):
        """L2: movement_rank returns exactly product,seq,delta,abs_rank in that order, sorted."""
        result = _run_driver(
            _BUILD_MOVES
            + """
            df = L.movement_rank(movements)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["product", "seq", "delta", "abs_rank"], (
            "unexpected column set/order: %s" % result["columns"]
        )
        # sorted by product asc, abs_rank asc, seq asc
        order = [(r["product"], r["abs_rank"], r["seq"]) for r in result["rows"]]
        assert order == sorted(order), "rows must be sorted by product, abs_rank, seq: %s" % order
        # one row per (product, seq)
        assert sorted(r["seq"] for r in result["rows"]) == [1, 2, 3, 4, 5, 6]

    def test_movement_rank_dense_largest_is_one(self):
        """L2: largest |delta| in a product is rank 1; ranks are dense (no gaps)."""
        result = _run_driver(
            _BUILD_MOVES
            + """
            df = L.movement_rank(movements)
            print(json.dumps(_df_to_records(df)))
            """
        )
        rank = {r["seq"]: r["abs_rank"] for r in result["rows"]}
        # P1 magnitudes: seq1 |5|=5, seq4 |-2|=2, seq6 |3|=3
        #   5 -> rank1, 3 -> rank2, 2 -> rank3
        assert rank[1] == 1, "P1 largest magnitude (5) must be rank 1"
        assert rank[6] == 2, "P1 magnitude 3 -> rank 2"
        assert rank[4] == 3, "P1 magnitude 2 -> rank 3"
        # P2 magnitudes: seq2 |10|=10, seq3 |-4|=4, seq5 |4|=4
        #   10 -> rank1 ; the two magnitude-4 rows tie at rank2 ; no rank3 produced
        assert rank[2] == 1, "P2 largest magnitude (10) must be rank 1"
        assert rank[3] == 2, "P2 magnitude 4 -> rank 2 (tie)"
        assert rank[5] == 2, "P2 magnitude 4 -> rank 2 (tie)"

    def test_movement_rank_ties_share_rank_next_continues(self):
        """L2: tied magnitudes share a rank and the next distinct magnitude is the very next int."""
        result = _run_driver(
            """
            movements = pl.DataFrame(
                {
                    "seq":       [10,   11,   12,   13],
                    "product":   ["X",  "X",  "X",  "X"],
                    "warehouse": ["W",  "W",  "W",  "W"],
                    "delta":     [4,    -4,   9,    1],
                },
                schema={"seq": pl.Int64, "product": pl.String,
                        "warehouse": pl.String, "delta": pl.Int64},
            )
            df = L.movement_rank(movements)
            print(json.dumps(_df_to_records(df)))
            """
        )
        rank = {r["seq"]: r["abs_rank"] for r in result["rows"]}
        # magnitudes: 9 (seq12) -> 1 ; 4 and 4 (seq10, seq11) -> 2 ; 1 (seq13) -> 3
        assert rank[12] == 1, "largest magnitude 9 -> rank 1"
        assert rank[10] == 2, "magnitude 4 tie -> rank 2"
        assert rank[11] == 2, "magnitude 4 tie -> rank 2"
        assert rank[13] == 3, "next distinct magnitude (1) must continue at 3 (dense, no gap)"

    def test_movement_rank_independent_per_product(self):
        """L2: ranking restarts per product (each product's largest is its own rank 1)."""
        result = _run_driver(
            """
            movements = pl.DataFrame(
                {
                    "seq":       [1,    2,    3,    4],
                    "product":   ["A",  "A",  "B",  "B"],
                    "warehouse": ["W",  "W",  "W",  "W"],
                    "delta":     [2,    1,    -50,  -10],
                },
                schema={"seq": pl.Int64, "product": pl.String,
                        "warehouse": pl.String, "delta": pl.Int64},
            )
            df = L.movement_rank(movements)
            print(json.dumps(_df_to_records(df)))
            """
        )
        rank = {(r["product"], r["seq"]): r["abs_rank"] for r in result["rows"]}
        # A: |2| -> 1, |1| -> 2
        assert rank[("A", 1)] == 1
        assert rank[("A", 2)] == 2
        # B: |-50| -> 1, |-10| -> 2  (B's biggest 50 is rank 1 even though A's biggest is only 2)
        assert rank[("B", 3)] == 1, "product B must rank within itself, largest=50 -> 1"
        assert rank[("B", 4)] == 2

    # ------------------------------------------------------------------ L2: warehouse_share

    def test_warehouse_share_columns_sort_and_dtype(self):
        """L2: warehouse_share preserves columns, adds Float64 received_share, sorts by warehouse,seq."""
        result = _run_driver(
            _BUILD_MOVES
            + """
            df = L.warehouse_share(movements)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        for c in ["seq", "product", "warehouse", "delta", "received_share"]:
            assert c in cols, "warehouse_share missing column %s: %s" % (c, cols)
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["received_share"].lower().startswith("float"), (
            "received_share must be Float64, got %s" % dtype_map["received_share"]
        )
        order = [(r["warehouse"], r["seq"]) for r in result["rows"]]
        assert order == sorted(order), "rows must be sorted by warehouse then seq: %s" % order
        assert sorted(r["seq"] for r in result["rows"]) == [1, 2, 3, 4, 5, 6]

    def test_warehouse_share_receipt_fractions(self):
        """L2: receipts divide by per-warehouse positive total; non-receipts are exactly 0.0."""
        result = _run_driver(
            _BUILD_MOVES
            + """
            df = L.warehouse_share(movements)
            print(json.dumps(_df_to_records(df)))
            """
        )
        share = {r["seq"]: r["received_share"] for r in result["rows"]}
        # W1 receipts: seq1 +5, seq2 +10, seq6 +3 -> total 18
        assert share[1] == pytest.approx(5.0 / 18.0)
        assert share[2] == pytest.approx(10.0 / 18.0)
        assert share[6] == pytest.approx(3.0 / 18.0)
        # W2: receipts seq5 +4 -> total 4 ; seq3 (-4) and seq4 (-2) are non-receipts
        assert share[5] == pytest.approx(1.0), "sole W2 receipt is 4/4 = 1.0"
        assert share[3] == pytest.approx(0.0), "shipment (delta<=0) share must be 0.0"
        assert share[4] == pytest.approx(0.0), "shipment (delta<=0) share must be 0.0"

    def test_warehouse_share_simple_two_receipts(self):
        """L2: warehouse with receipts 2 and 6 yields shares 0.25 and 0.75; shipment 0.0."""
        result = _run_driver(
            """
            movements = pl.DataFrame(
                {
                    "seq":       [1,    2,    3],
                    "product":   ["P",  "P",  "P"],
                    "warehouse": ["W",  "W",  "W"],
                    "delta":     [2,    6,    -3],
                },
                schema={"seq": pl.Int64, "product": pl.String,
                        "warehouse": pl.String, "delta": pl.Int64},
            )
            df = L.warehouse_share(movements)
            print(json.dumps(_df_to_records(df)))
            """
        )
        share = {r["seq"]: r["received_share"] for r in result["rows"]}
        assert share[1] == pytest.approx(0.25), "2 / (2+6) = 0.25"
        assert share[2] == pytest.approx(0.75), "6 / (2+6) = 0.75"
        assert share[3] == pytest.approx(0.0), "shipment must be 0.0"

    def test_warehouse_share_receipt_free_warehouse_no_nan(self):
        """L2: a warehouse with only shipments yields 0.0 everywhere, never NaN, never raises."""
        result = _run_driver(
            """
            movements = pl.DataFrame(
                {
                    "seq":       [1,    2,    3],
                    "product":   ["P",  "P",  "P"],
                    "warehouse": ["S",  "S",  "S"],
                    "delta":     [-1,   -5,   0],
                },
                schema={"seq": pl.Int64, "product": pl.String,
                        "warehouse": pl.String, "delta": pl.Int64},
            )
            df = L.warehouse_share(movements)
            print(json.dumps(_df_to_records(df)))
            """
        )
        for r in result["rows"]:
            assert r["received_share"] != "__NAN__", (
                "receipt-free warehouse must not produce NaN (seq %s)" % r["seq"]
            )
            assert r["received_share"] == pytest.approx(0.0), (
                "every row of a receipt-free warehouse must be 0.0 (seq %s -> %r)"
                % (r["seq"], r["received_share"])
            )

    # ------------------------------------------------------------------ L2: empty input

    def test_empty_input_shapes_all_functions(self):
        """L2: every function returns an empty DataFrame with the correct columns/dtypes on empty input."""
        result = _run_driver(
            """
            movements = pl.DataFrame(
                schema={"seq": pl.Int64, "product": pl.String,
                        "warehouse": pl.String, "delta": pl.Int64},
            )
            out = {}
            rb = L.running_balance(movements)
            out["running_balance"] = {"cols": list(rb.columns), "h": rb.height,
                                      "dtypes": [str(rb.schema[c]) for c in rb.columns]}
            mr = L.movement_rank(movements)
            out["movement_rank"] = {"cols": list(mr.columns), "h": mr.height}
            ws = L.warehouse_share(movements)
            out["warehouse_share"] = {"cols": list(ws.columns), "h": ws.height,
                                      "dtypes": [str(ws.schema[c]) for c in ws.columns]}
            print(json.dumps(out))
            """
        )
        rb = result["running_balance"]
        assert rb["h"] == 0, "running_balance must be empty on empty input"
        assert "balance" in rb["cols"], "running_balance empty must keep balance column"
        for c in ["seq", "product", "warehouse", "delta"]:
            assert c in rb["cols"], "running_balance empty missing %s: %s" % (c, rb["cols"])
        rb_dtypes = dict(zip(rb["cols"], rb["dtypes"]))
        assert rb_dtypes["balance"].lower().startswith("int"), (
            "balance dtype must be integer even when empty: %s" % rb_dtypes["balance"]
        )

        mr = result["movement_rank"]
        assert mr["h"] == 0
        assert mr["cols"] == ["product", "seq", "delta", "abs_rank"], (
            "movement_rank empty cols/order: %s" % mr["cols"]
        )

        ws = result["warehouse_share"]
        assert ws["h"] == 0
        assert "received_share" in ws["cols"], "warehouse_share empty must keep received_share"
        ws_dtypes = dict(zip(ws["cols"], ws["dtypes"]))
        assert ws_dtypes["received_share"].lower().startswith("float"), (
            "received_share dtype must be Float64 even when empty: %s"
            % ws_dtypes["received_share"]
        )

    # ------------------------------------------------------------------ native acceptance

    def test_native_pytest_suite_passes(self):
        """L2: the agent's own pytest suite for the module passes (native acceptance command)."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "examples/inventory_ledger/test_ledger.py", "-q"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=420,
        )
        assert proc.returncode == 0, (
            "native pytest suite failed (rc=%s)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:])
        )
