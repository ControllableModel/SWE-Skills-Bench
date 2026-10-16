"""Tests for the ``pandas-dataframe-patterns`` skill task.

The task asks the agent to create ``scripts/sales_report.py`` inside the pandas
repository, exposing five public functions that turn raw order records into
summary reports: ``enrich_orders``, ``fill_prices``, ``region_segment_summary``,
``revenue_pivot`` and ``daily_revenue``.

These tests verify the *behaviour* of the agent's module dynamically. Each L2
case drives the real functions through a subprocess (so the installed pandas is
used, not the unbuilt repo source tree) and deep-validates numeric output,
returned structures, ordering, missing-value handling, edge cases and the
"do not mutate / do not drop / do not duplicate rows" contracts.

A naive solution that merely creates files, or that uses an inner-join (drops
unmatched orders), silent duplication on duplicate keys, forward-fill instead
of per-region median, leaves NaNs, or skips empty calendar days will fail.
"""

import json
import os
import subprocess
import tempfile
import textwrap

import pytest


class TestPandasDataframePatterns:
    REPO_DIR = "/workspace/pandas"

    MODULE_REL = os.path.join("scripts", "sales_report.py")
    TEST_REL = os.path.join("scripts", "tests", "test_sales_report.py")

    # ---- helpers ---------------------------------------------------------

    def _module_path(self):
        return os.path.join(self.REPO_DIR, self.MODULE_REL)

    def _run_driver(self, body, timeout=120):
        """Run a python snippet that imports the agent's sales_report module.

        The driver runs from a clean temporary cwd (NOT the repo root) so that
        ``import pandas`` resolves to the installed/built pandas instead of the
        repository's source tree. The agent's ``scripts`` directory is put on
        sys.path so ``import sales_report`` finds the deliverable. The snippet is
        expected to ``print`` a single JSON line as its final output.
        """
        scripts_dir = os.path.join(self.REPO_DIR, "scripts")
        assert os.path.isfile(self._module_path()), (
            "scripts/sales_report.py does not exist; agent did not create the "
            "deliverable module."
        )
        header = textwrap.dedent(
            f"""
            import sys, json
            sys.path.insert(0, {scripts_dir!r})
            import pandas as pd
            import numpy as np
            import sales_report as sr
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
    SAMPLE = textwrap.dedent(
        """
        orders = pd.DataFrame({
            'order_id':   [101, 102, 103, 104, 105],
            'customer_id':[10,  20,  30,  10,  40],
            'region':     ['East','East','West','West','East'],
            'order_date': ['2023-01-01','2023-01-03','2023-01-01',
                           '2023-01-01','2023-01-03'],
            'units':      [2,    3,    1,    5,    4],
            'unit_price': [10.0, np.nan, 20.0, 4.0, 5.0],
        })
        customers = pd.DataFrame({
            'customer_id':[10, 20, 30],
            'segment':    ['Gold','Silver','Gold'],
        })
        """
    )

    # ---- L1: deliverables exist & minimally well-formed ------------------

    def test_module_file_exists(self):
        """L1: scripts/sales_report.py must exist."""
        assert os.path.isfile(self._module_path()), (
            f"missing deliverable: {self._module_path()}"
        )

    def test_test_file_exists(self):
        """L1: scripts/tests/test_sales_report.py must exist."""
        assert os.path.isfile(os.path.join(self.REPO_DIR, self.TEST_REL)), (
            "missing deliverable test file scripts/tests/test_sales_report.py"
        )

    def test_public_functions_present(self):
        """L1: the five required public functions are importable callables."""
        out = self._run_json(
            """
            names = ['enrich_orders','fill_prices','region_segment_summary',
                     'revenue_pivot','daily_revenue']
            res = {n: callable(getattr(sr, n, None)) for n in names}
            print(json.dumps(res))
            """
        )
        for name, ok in out.items():
            assert ok, f"sales_report.{name} is missing or not callable"

    # ---- L2: enrich_orders ----------------------------------------------

    def test_enrich_left_join_keeps_all_rows_and_revenue(self):
        """L2: enrich keeps every order once, adds segment + revenue (NaN-safe)."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = sr.enrich_orders(orders, customers)
            order_ids = sorted(int(x) for x in res['order_id'].tolist())
            # segment for each customer_id, with unmatched (40) -> None
            seg = {int(o): (None if pd.isna(s) else s)
                   for o, s in zip(res['order_id'], res['segment'])}
            rev = {int(o): (None if pd.isna(r) else float(r))
                   for o, r in zip(res['order_id'], res['revenue'])}
            print(json.dumps({
                'n': int(len(res)),
                'order_ids': order_ids,
                'seg': seg,
                'rev': rev,
            }))
            """
        )
        assert out["n"] == 5, "enrich must not drop or duplicate rows"
        assert out["order_ids"] == [101, 102, 103, 104, 105]
        # matched segments
        assert out["seg"]["101"] == "Gold"
        assert out["seg"]["102"] == "Silver"
        assert out["seg"]["103"] == "Gold"
        assert out["seg"]["104"] == "Gold"
        # order 105 customer_id 40 has no match -> missing segment
        assert out["seg"]["105"] is None, "unmatched order must survive with NaN segment"
        # revenue = units * unit_price, computed before any imputation
        assert out["rev"]["101"] == 20.0
        assert out["rev"]["103"] == 20.0
        assert out["rev"]["104"] == 20.0
        assert out["rev"]["105"] == 20.0
        # order 102 has missing unit_price -> revenue is missing here
        assert out["rev"]["102"] is None, "missing price must yield missing revenue pre-fill"

    def test_enrich_duplicate_customer_raises(self):
        """L2: a duplicated customer_id in the reference table must raise."""
        proc = self._run_driver(
            """
            orders = pd.DataFrame({
                'order_id':[1,2], 'customer_id':[10,20],
                'region':['East','West'],
                'order_date':['2023-01-01','2023-01-02'],
                'units':[1,1], 'unit_price':[5.0,5.0],
            })
            customers = pd.DataFrame({
                'customer_id':[10,10,20],          # duplicate key 10
                'segment':['Gold','Silver','Gold'],
            })
            try:
                sr.enrich_orders(orders, customers)
            except Exception as exc:
                print(json.dumps({'raised': True, 'type': type(exc).__name__}))
            else:
                print(json.dumps({'raised': False}))
            """
        )
        assert proc.returncode == 0, proc.stderr
        last = [ln for ln in proc.stdout.splitlines() if ln.strip()][-1]
        res = json.loads(last)
        assert res["raised"] is True, (
            "enrich_orders must raise on duplicate customer_id rather than "
            "multiplying order rows"
        )

    def test_enrich_does_not_mutate_input(self):
        """L2: the caller's orders frame must be unchanged after enrich."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_cols = list(orders.columns)
            before_hash = pd.util.hash_pandas_object(orders, index=True).sum()
            _ = sr.enrich_orders(orders, customers)
            after_cols = list(orders.columns)
            after_hash = pd.util.hash_pandas_object(orders, index=True).sum()
            print(json.dumps({
                'cols_same': before_cols == after_cols,
                'hash_same': bool(before_hash == after_hash),
                'has_segment': 'segment' in orders.columns,
                'has_revenue': 'revenue' in orders.columns,
            }))
            """
        )
        assert out["cols_same"], "enrich must not change input columns"
        assert out["hash_same"], "enrich must not alter input values"
        assert not out["has_segment"], "enrich must not add segment to the input"
        assert not out["has_revenue"], "enrich must not add revenue to the input"

    # ---- L2: fill_prices -------------------------------------------------

    def test_fill_prices_per_region_median_example(self):
        """L2: spec example [10, NaN, 20] in one region -> gap becomes 15.0."""
        out = self._run_json(
            """
            enriched = pd.DataFrame({
                'order_id':[1,2,3],
                'region':['R','R','R'],
                'segment':['A','A','A'],
                'order_date':['2023-01-01','2023-01-01','2023-01-01'],
                'units':[2,4,3],
                'unit_price':[10.0, np.nan, 20.0],
                'revenue':[20.0, np.nan, 60.0],
            })
            res = sr.fill_prices(enriched)
            filled = res.sort_values('order_id')
            prices = [float(x) for x in filled['unit_price'].tolist()]
            revs   = [float(x) for x in filled['revenue'].tolist()]
            print(json.dumps({
                'prices': prices,
                'revs': revs,
                'any_price_na': bool(res['unit_price'].isna().any()),
                'any_rev_na': bool(res['revenue'].isna().any()),
            }))
            """
        )
        # median of [10, 20] is 15.0
        assert out["prices"] == [10.0, 15.0, 20.0]
        # revenue recomputed: row 2 units=4 * 15.0 = 60.0
        assert out["revs"] == [20.0, 60.0, 60.0]
        assert not out["any_price_na"], "fill_prices must leave no missing prices"
        assert not out["any_rev_na"], "fill_prices must leave no missing revenue"

    def test_fill_prices_medians_are_region_scoped(self):
        """L2: each region's gap is filled from that region's own median only."""
        out = self._run_json(
            """
            enriched = pd.DataFrame({
                'order_id':[1,2,3,4,5,6],
                'region':['East','East','East','West','West','West'],
                'segment':['A']*6,
                'order_date':['2023-01-01']*6,
                'units':[1,1,1,1,1,1],
                'unit_price':[10.0, np.nan, 20.0, 100.0, np.nan, 300.0],
                'revenue':[10.0, np.nan, 20.0, 100.0, np.nan, 300.0],
            })
            res = sr.fill_prices(enriched).sort_values('order_id')
            prices = {int(o): float(p) for o, p in
                      zip(res['order_id'], res['unit_price'])}
            revs = {int(o): float(r) for o, r in
                    zip(res['order_id'], res['revenue'])}
            print(json.dumps({'prices': prices, 'revs': revs}))
            """
        )
        # East median [10,20]=15 ; West median [100,300]=200
        assert out["prices"]["2"] == 15.0, "East gap must use East median, not global"
        assert out["prices"]["5"] == 200.0, "West gap must use West median, not global"
        assert out["revs"]["2"] == 15.0
        assert out["revs"]["5"] == 200.0
        # non-missing rows untouched
        assert out["prices"]["1"] == 10.0
        assert out["prices"]["6"] == 300.0

    def test_fill_prices_does_not_mutate_input(self):
        """L2: fill_prices must not mutate its input frame."""
        out = self._run_json(
            """
            enriched = pd.DataFrame({
                'order_id':[1,2,3],
                'region':['R','R','R'],
                'segment':['A','A','A'],
                'order_date':['2023-01-01']*3,
                'units':[1,1,1],
                'unit_price':[10.0, np.nan, 20.0],
                'revenue':[10.0, np.nan, 20.0],
            })
            before = pd.util.hash_pandas_object(enriched, index=True).sum()
            na_before = int(enriched['unit_price'].isna().sum())
            _ = sr.fill_prices(enriched)
            after = pd.util.hash_pandas_object(enriched, index=True).sum()
            na_after = int(enriched['unit_price'].isna().sum())
            print(json.dumps({
                'hash_same': bool(before == after),
                'na_before': na_before, 'na_after': na_after,
            }))
            """
        )
        assert out["hash_same"], "fill_prices must not mutate its input"
        assert out["na_before"] == 1 and out["na_after"] == 1, (
            "the input's missing price must remain after calling fill_prices"
        )

    # ---- L2: region_segment_summary -------------------------------------

    def test_region_segment_summary_values_and_shape(self):
        """L2: flat, sorted aggregation with correct sums/counts/means."""
        out = self._run_json(
            """
            orders = pd.DataFrame({
                'order_id':[1,2,3,4,5],
                'region':['East','East','East','West','West'],
                'segment':['Gold','Gold','Silver','Gold','Gold'],
                'order_date':['2023-01-01']*5,
                'units':[2,3,1,5,5],
                'unit_price':[10.0,10.0,20.0,4.0,6.0],
                'revenue':[20.0,30.0,20.0,20.0,30.0],
            })
            res = sr.region_segment_summary(orders)
            cols = list(res.columns)
            idx = list(res.index)
            rows = []
            for _, r in res.iterrows():
                rows.append({
                    'region': r['region'], 'segment': r['segment'],
                    'total_revenue': float(r['total_revenue']),
                    'total_units': int(r['total_units']),
                    'order_count': int(r['order_count']),
                    'avg_unit_price': float(r['avg_unit_price']),
                })
            print(json.dumps({'cols': cols, 'index': idx, 'rows': rows}))
            """
        )
        # flat frame: region & segment are ordinary columns, integer index 0..n-1
        for c in ("region", "segment", "total_revenue", "total_units",
                  "order_count", "avg_unit_price"):
            assert c in out["cols"], f"summary missing column {c}"
        assert out["index"] == [0, 1, 2], "index must be reset to 0..n-1"
        rows = out["rows"]
        # sorted by region then segment ascending
        keys = [(r["region"], r["segment"]) for r in rows]
        assert keys == [("East", "Gold"), ("East", "Silver"), ("West", "Gold")], (
            f"rows not sorted / wrong groups: {keys}"
        )
        east_gold = rows[0]
        assert east_gold["total_revenue"] == 50.0
        assert east_gold["total_units"] == 5
        assert east_gold["order_count"] == 2
        assert east_gold["avg_unit_price"] == 10.0
        east_silver = rows[1]
        assert east_silver["total_revenue"] == 20.0
        assert east_silver["order_count"] == 1
        west_gold = rows[2]
        assert west_gold["total_revenue"] == 50.0
        assert west_gold["total_units"] == 10
        assert west_gold["order_count"] == 2
        assert west_gold["avg_unit_price"] == 5.0

    def test_region_segment_summary_order_count_is_distinct(self):
        """L2: order_count counts DISTINCT order_id, not rows."""
        out = self._run_json(
            """
            # Two rows sharing order_id 7 (e.g. a multi-line order) within one
            # (region, segment): order_count must be 2 distinct ids, not 3 rows.
            orders = pd.DataFrame({
                'order_id':[7, 7, 8],
                'region':['East','East','East'],
                'segment':['Gold','Gold','Gold'],
                'order_date':['2023-01-01']*3,
                'units':[1,1,1],
                'unit_price':[5.0,5.0,5.0],
                'revenue':[5.0,5.0,5.0],
            })
            res = sr.region_segment_summary(orders)
            r = res.iloc[0]
            print(json.dumps({
                'order_count': int(r['order_count']),
                'total_units': int(r['total_units']),
            }))
            """
        )
        assert out["order_count"] == 2, "order_count must count distinct order_id"
        assert out["total_units"] == 3, "total_units must sum every row's units"

    def test_region_segment_summary_no_missing_in_agg_columns(self):
        """L2: aggregated columns must contain no missing values."""
        out = self._run_json(
            """
            orders = pd.DataFrame({
                'order_id':[1,2,3],
                'region':['East','West','West'],
                'segment':['Gold','Silver','Silver'],
                'order_date':['2023-01-01']*3,
                'units':[2,3,4],
                'unit_price':[10.0,5.0,5.0],
                'revenue':[20.0,15.0,20.0],
            })
            res = sr.region_segment_summary(orders)
            agg = ['total_revenue','total_units','order_count','avg_unit_price']
            print(json.dumps({
                'any_na': bool(res[agg].isna().any().any()),
                'n': int(len(res)),
            }))
            """
        )
        assert not out["any_na"], "aggregated columns must not contain NaN"
        assert out["n"] == 2

    # ---- L2: revenue_pivot ----------------------------------------------

    def test_revenue_pivot_fills_absent_combos_with_zero(self):
        """L2: pivot cells for absent (region, segment) pairs are 0.0, not NaN."""
        out = self._run_json(
            """
            orders = pd.DataFrame({
                'order_id':[1,2,3],
                'region':['East','East','West'],
                'segment':['Gold','Silver','Gold'],   # West/Silver absent
                'order_date':['2023-01-01']*3,
                'units':[1,1,1],
                'unit_price':[1.0,1.0,1.0],
                'revenue':[20.0,30.0,40.0],
            })
            piv = sr.revenue_pivot(orders)
            d = {str(r): {str(c): float(piv.loc[r, c]) for c in piv.columns}
                 for r in piv.index}
            print(json.dumps({
                'data': d,
                'index_name': piv.index.name,
                'any_na': bool(piv.isna().any().any()),
                'rows': sorted(str(x) for x in piv.index),
                'cols': sorted(str(x) for x in piv.columns),
            }))
            """
        )
        assert not out["any_na"], "pivot must contain no missing values"
        assert out["rows"] == ["East", "West"], "rows must be the distinct regions"
        assert out["cols"] == ["Gold", "Silver"], "cols must be the distinct segments"
        assert out["index_name"] == "region", "row index must be named region"
        assert out["data"]["East"]["Gold"] == 20.0
        assert out["data"]["East"]["Silver"] == 30.0
        assert out["data"]["West"]["Gold"] == 40.0
        # absent (West, Silver) combination must be 0.0
        assert out["data"]["West"]["Silver"] == 0.0, "absent combo must be 0.0"

    # ---- L2: daily_revenue ----------------------------------------------

    def test_daily_revenue_fills_gap_days_with_zero(self):
        """L2: continuous daily index; a gap day (2023-01-02) is present as 0.0."""
        out = self._run_json(
            """
            orders = pd.DataFrame({
                'order_id':[1,2,3],
                'region':['East','East','West'],
                'segment':['Gold','Gold','Gold'],
                'order_date':['2023-01-01','2023-01-03','2023-01-01'],
                'units':[1,1,1],
                'unit_price':[1.0,1.0,1.0],
                'revenue':[10.0,30.0,50.0],
            })
            res = sr.daily_revenue(orders)
            # normalise to (iso-date -> value); res may be a Series or 1-col frame
            if hasattr(res, 'columns'):
                s = res.iloc[:, 0]
            else:
                s = res
            pairs = [(pd.Timestamp(i).strftime('%Y-%m-%d'), float(v))
                     for i, v in zip(s.index, s.values)]
            print(json.dumps({
                'pairs': pairs,
                'any_na': bool(pd.isna(s).any()),
            }))
            """
        )
        pairs = out["pairs"]
        assert [p[0] for p in pairs] == ["2023-01-01", "2023-01-02", "2023-01-03"], (
            f"daily index must be every calendar day with no gaps: {pairs}"
        )
        values = {d: v for d, v in pairs}
        assert values["2023-01-01"] == 60.0, "2023-01-01 sums both orders (10+50)"
        assert values["2023-01-02"] == 0.0, "gap day must be present as 0.0"
        assert values["2023-01-03"] == 30.0
        assert not out["any_na"], "daily_revenue must contain no missing values"

    def test_daily_revenue_index_sorted_and_unique(self):
        """L2: the daily index is sorted ascending with one entry per day."""
        out = self._run_json(
            """
            orders = pd.DataFrame({
                'order_id':[1,2,3,4],
                'region':['East']*4,
                'segment':['Gold']*4,
                # deliberately unsorted, with a wide span and duplicate day
                'order_date':['2023-03-05','2023-03-01','2023-03-05','2023-03-04'],
                'units':[1,1,1,1],
                'unit_price':[1.0,1.0,1.0,1.0],
                'revenue':[5.0,1.0,5.0,4.0],
            })
            res = sr.daily_revenue(orders)
            if hasattr(res, 'columns'):
                s = res.iloc[:, 0]
            else:
                s = res
            dates = [pd.Timestamp(i).strftime('%Y-%m-%d') for i in s.index]
            vals = {d: float(v) for d, v in zip(dates, s.values)}
            print(json.dumps({
                'dates': dates,
                'sorted': dates == sorted(dates),
                'unique': len(dates) == len(set(dates)),
                'vals': vals,
            }))
            """
        )
        # span 2023-03-01 .. 2023-03-05 inclusive -> 5 contiguous days
        assert out["dates"] == [
            "2023-03-01", "2023-03-02", "2023-03-03", "2023-03-04", "2023-03-05",
        ]
        assert out["sorted"], "index must be sorted ascending"
        assert out["unique"], "index must have one entry per day"
        assert out["vals"]["2023-03-01"] == 1.0
        assert out["vals"]["2023-03-02"] == 0.0
        assert out["vals"]["2023-03-03"] == 0.0
        assert out["vals"]["2023-03-04"] == 4.0
        # duplicate-day revenue must be summed: 5 + 5
        assert out["vals"]["2023-03-05"] == 10.0

    # ---- L2: end-to-end native command ----------------------------------

    def test_agent_native_pytest_passes(self):
        """L2: the spec's native command on the agent's own test suite passes."""
        test_file = os.path.join(self.REPO_DIR, self.TEST_REL)
        assert os.path.isfile(test_file), "agent test file missing"
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            ["python", "-m", "pytest", "scripts/tests/test_sales_report.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native command `python -m pytest scripts/tests/test_sales_report.py -q` "
            "failed.\nSTDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr
        )
        # guard against a vacuous (zero-collected) pass
        assert "no tests ran" not in proc.stdout.lower(), (
            "agent test suite collected no tests"
        )
