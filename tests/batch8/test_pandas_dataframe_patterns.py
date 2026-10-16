"""Tests for the ``pandas-dataframe-patterns`` skill task (variant ext8).

The ext8 task asks the agent to create ``scripts/price_analytics.py`` inside the
pandas repository, exposing three public functions that compute rolling-window
technical indicators and per-symbol returns from a daily price log:

* ``daily_returns(prices)``   -> per-symbol simple daily return, leading row NaN.
* ``moving_average(prices, window)`` -> per-symbol trailing rolling mean over
  ``window`` rows, leading ``window-1`` rows NaN.
* ``max_drawdown(prices)``    -> per-symbol most-negative drawdown vs. running max.

The agent must also ship a deterministic test suite at
``scripts/tests/test_price_analytics.py`` and the native command
``python -m pytest scripts/tests/test_price_analytics.py -q`` must pass.

Verification strategy
---------------------
Each L2 case drives the agent's real functions through a subprocess from a clean
temporary cwd (so ``import pandas`` resolves to the installed/built pandas, not
the repository source tree). We deep-validate numeric output, per-symbol
isolation, leading-NaN positions, ordering, index reset, and the
"do not mutate the input" contract — using an INDEPENDENT verification harness
rather than trusting the agent's own tests. A separate L2 case finally runs the
spec's native pytest command on the agent's own suite.

A naive solution will fail: one that returns fixed values, ignores ``window``,
lets returns/rolling means bleed across symbols (e.g. a global ``pct_change`` /
``rolling`` without per-symbol grouping), forgets the leading-NaN positions,
mutates its input, or computes drawdown against the global max instead of each
symbol's running cumulative max.
"""

import json
import os
import subprocess
import tempfile
import textwrap


class TestPandasDataframePatterns:
    REPO_DIR = "/workspace/pandas"

    MODULE_REL = os.path.join("scripts", "price_analytics.py")
    TEST_REL = os.path.join("scripts", "tests", "test_price_analytics.py")

    # ---- helpers ---------------------------------------------------------

    def _module_path(self):
        return os.path.join(self.REPO_DIR, self.MODULE_REL)

    def _run_driver(self, body, timeout=120):
        """Run a python snippet that imports the agent's price_analytics module.

        The driver runs from a clean temporary cwd (NOT the repo root) so that
        ``import pandas`` resolves to the installed/built pandas instead of the
        repository's source tree. The agent's ``scripts`` directory is put on
        sys.path so ``import price_analytics`` finds the deliverable. The snippet
        is expected to ``print`` a single JSON line as its final output.
        """
        scripts_dir = os.path.join(self.REPO_DIR, "scripts")
        assert os.path.isfile(self._module_path()), (
            "scripts/price_analytics.py does not exist; agent did not create the "
            "deliverable module."
        )
        header = textwrap.dedent(
            f"""
            import sys, json
            sys.path.insert(0, {scripts_dir!r})
            import pandas as pd
            import numpy as np
            import price_analytics as pa
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

    # A reusable two-symbol sample dataset literal, defined once for snippets.
    # Symbol A closes: 100, 110, 99  ; Symbol B closes: 50, 60, 48.
    # The rows are deliberately interleaved and unsorted by date to catch
    # implementations that forget to group / sort per symbol.
    SAMPLE = textwrap.dedent(
        """
        prices = pd.DataFrame({
            'symbol': ['A', 'B', 'A', 'B', 'A', 'B'],
            'date':   ['2023-01-03', '2023-01-01', '2023-01-01',
                       '2023-01-03', '2023-01-02', '2023-01-02'],
            'close':  [99.0, 50.0, 100.0, 48.0, 110.0, 60.0],
        })
        """
    )

    # ---- L1: deliverables exist & minimally well-formed ------------------

    def test_module_file_exists(self):
        """L1: scripts/price_analytics.py must exist."""
        assert os.path.isfile(self._module_path()), (
            f"missing deliverable: {self._module_path()}"
        )

    def test_test_file_exists(self):
        """L1: scripts/tests/test_price_analytics.py must exist."""
        assert os.path.isfile(os.path.join(self.REPO_DIR, self.TEST_REL)), (
            "missing deliverable test file scripts/tests/test_price_analytics.py"
        )

    def test_public_functions_present(self):
        """L1: the three required public functions are importable callables."""
        out = self._run_json(
            """
            names = ['daily_returns', 'moving_average', 'max_drawdown']
            res = {n: callable(getattr(pa, n, None)) for n in names}
            print(json.dumps(res))
            """
        )
        for name, ok in out.items():
            assert ok, f"price_analytics.{name} is missing or not callable"

    # ---- L2: daily_returns -----------------------------------------------

    def test_daily_returns_basic_example(self):
        """L2: closes [100, 110] for one symbol -> [NaN, 0.1]."""
        out = self._run_json(
            """
            prices = pd.DataFrame({
                'symbol': ['A', 'A'],
                'date':   ['2023-01-01', '2023-01-02'],
                'close':  [100.0, 110.0],
            })
            res = pa.daily_returns(prices)
            rets = [None if pd.isna(r) else round(float(r), 10)
                    for r in res['daily_return'].tolist()]
            print(json.dumps({
                'rets': rets,
                'n': int(len(res)),
                'cols_have_return': 'daily_return' in res.columns,
            }))
            """
        )
        assert out["cols_have_return"], "result must add a daily_return column"
        assert out["n"] == 2, "daily_returns must preserve the row count"
        assert out["rets"][0] is None, "first row of a symbol has no prior close"
        assert out["rets"][1] == 0.1, "(110-100)/100 == 0.1"

    def test_daily_returns_per_symbol_no_bleed(self):
        """L2: interleaved symbols -> returns are computed per symbol only.

        A global ``pct_change`` (no per-symbol grouping) would compute the first
        B return against the last A close and vice-versa; that must NOT happen.
        Each symbol's first chronological row must be NaN.
        """
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = pa.daily_returns(prices)
            # sorted by symbol then date per the contract
            recs = [(r['symbol'], r['date'],
                     None if pd.isna(r['daily_return']) else round(float(r['daily_return']), 10))
                    for _, r in res.iterrows()]
            idx = list(res.index)
            print(json.dumps({
                'recs': recs,
                'index': idx,
                'n': int(len(res)),
            }))
            """
        )
        assert out["n"] == 6, "row count must be preserved"
        assert out["index"] == [0, 1, 2, 3, 4, 5], "index must reset to 0..n-1"
        recs = out["recs"]
        # Output sorted by symbol then date ascending.
        order = [(r[0], r[1]) for r in recs]
        assert order == [
            ("A", "2023-01-01"), ("A", "2023-01-02"), ("A", "2023-01-03"),
            ("B", "2023-01-01"), ("B", "2023-01-02"), ("B", "2023-01-03"),
        ], f"rows not sorted by symbol then date: {order}"
        ret = {(r[0], r[1]): r[2] for r in recs}
        # Symbol A: 100 -> 110 -> 99
        assert ret[("A", "2023-01-01")] is None, "A first row must be NaN"
        assert ret[("A", "2023-01-02")] == 0.1, "(110-100)/100"
        assert ret[("A", "2023-01-03")] == -0.1, "(99-110)/110 == -0.1"
        # Symbol B: 50 -> 60 -> 48 ; first row NaN, never references A's close
        assert ret[("B", "2023-01-01")] is None, (
            "B first row must be NaN — return must not bleed from symbol A"
        )
        assert ret[("B", "2023-01-02")] == 0.2, "(60-50)/50 == 0.2"
        assert ret[("B", "2023-01-03")] == -0.2, "(48-60)/60 == -0.2"

    def test_daily_returns_does_not_mutate_input(self):
        """L2: the caller's prices frame must be unchanged after the call."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_cols = list(prices.columns)
            before_hash = pd.util.hash_pandas_object(prices, index=True).sum()
            _ = pa.daily_returns(prices)
            after_cols = list(prices.columns)
            after_hash = pd.util.hash_pandas_object(prices, index=True).sum()
            print(json.dumps({
                'cols_same': before_cols == after_cols,
                'hash_same': bool(before_hash == after_hash),
                'has_return': 'daily_return' in prices.columns,
            }))
            """
        )
        assert out["cols_same"], "daily_returns must not change input columns"
        assert out["hash_same"], "daily_returns must not alter input values"
        assert not out["has_return"], (
            "daily_returns must not add daily_return to the caller's input"
        )

    # ---- L2: moving_average ----------------------------------------------

    def test_moving_average_window2_example(self):
        """L2: window=2 over [10, 20, 30] one symbol -> [NaN, 15, 25]."""
        out = self._run_json(
            """
            prices = pd.DataFrame({
                'symbol': ['A', 'A', 'A'],
                'date':   ['2023-01-01', '2023-01-02', '2023-01-03'],
                'close':  [10.0, 20.0, 30.0],
            })
            res = pa.moving_average(prices, 2)
            ma = [None if pd.isna(x) else round(float(x), 10)
                  for x in res['ma'].tolist()]
            print(json.dumps({
                'ma': ma,
                'has_ma': 'ma' in res.columns,
                'n': int(len(res)),
            }))
            """
        )
        assert out["has_ma"], "result must add an ma column"
        assert out["n"] == 3, "row count must be preserved"
        assert out["ma"][0] is None, "first window-1 rows are missing"
        assert out["ma"][1] == 15.0, "mean(10,20) == 15"
        assert out["ma"][2] == 25.0, "mean(20,30) == 25"

    def test_moving_average_per_symbol_isolated(self):
        """L2: rolling mean is computed independently per symbol.

        A global rolling window (without per-symbol grouping) would mix A's and
        B's closes at the boundary. Each symbol must restart its window, so each
        symbol's leading (window-1) rows are NaN.
        """
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = pa.moving_average(prices, 2)
            recs = [(r['symbol'], r['date'],
                     None if pd.isna(r['ma']) else round(float(r['ma']), 10))
                    for _, r in res.iterrows()]
            print(json.dumps({
                'recs': recs,
                'index': list(res.index),
            }))
            """
        )
        assert out["index"] == [0, 1, 2, 3, 4, 5], "index must reset to 0..n-1"
        ma = {(r[0], r[1]): r[2] for r in out["recs"]}
        # A closes sorted by date: 100, 110, 99
        assert ma[("A", "2023-01-01")] is None, "A leading row must be NaN"
        assert ma[("A", "2023-01-02")] == 105.0, "mean(100,110)"
        assert ma[("A", "2023-01-03")] == 104.5, "mean(110,99)"
        # B closes sorted by date: 50, 60, 48 — first must be NaN (no bleed from A)
        assert ma[("B", "2023-01-01")] is None, (
            "B leading row must be NaN — rolling window must not bleed from A"
        )
        assert ma[("B", "2023-01-02")] == 55.0, "mean(50,60)"
        assert ma[("B", "2023-01-03")] == 54.0, "mean(60,48)"

    def test_moving_average_window1_is_identity(self):
        """L2: window=1 reproduces close exactly with no missing values."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = pa.moving_average(prices, 1)
            recs = {(r['symbol'], r['date']): round(float(r['ma']), 10)
                    for _, r in res.iterrows()}
            closes = {(r['symbol'], r['date']): round(float(r['close']), 10)
                      for _, r in res.iterrows()}
            print(json.dumps({
                'any_na': bool(res['ma'].isna().any()),
                'equal': recs == closes,
            }))
            """
        )
        assert not out["any_na"], "window=1 must have no missing ma values"
        assert out["equal"], "window=1 ma must equal close for every row"

    def test_moving_average_does_not_mutate_input(self):
        """L2: moving_average must not mutate its input frame."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before = pd.util.hash_pandas_object(prices, index=True).sum()
            cols_before = list(prices.columns)
            _ = pa.moving_average(prices, 2)
            after = pd.util.hash_pandas_object(prices, index=True).sum()
            print(json.dumps({
                'hash_same': bool(before == after),
                'no_ma': 'ma' not in prices.columns,
                'cols_same': cols_before == list(prices.columns),
            }))
            """
        )
        assert out["hash_same"], "moving_average must not mutate its input values"
        assert out["no_ma"], "moving_average must not add ma to the caller's input"
        assert out["cols_same"], "moving_average must not change input columns"

    # ---- L2: max_drawdown ------------------------------------------------

    def test_max_drawdown_basic_example(self):
        """L2: closes [100, 80, 120] one symbol -> -0.2."""
        out = self._run_json(
            """
            prices = pd.DataFrame({
                'symbol': ['A', 'A', 'A'],
                'date':   ['2023-01-01', '2023-01-02', '2023-01-03'],
                'close':  [100.0, 80.0, 120.0],
            })
            res = pa.max_drawdown(prices)
            cols = sorted(res.columns.tolist())
            d = {r['symbol']: round(float(r['max_drawdown']), 10)
                 for _, r in res.iterrows()}
            print(json.dumps({
                'cols': cols,
                'dd': d,
                'n': int(len(res)),
                'index': list(res.index),
            }))
            """
        )
        assert out["cols"] == ["max_drawdown", "symbol"], (
            "max_drawdown must return columns symbol and max_drawdown"
        )
        assert out["n"] == 1, "one symbol -> one row"
        assert out["index"] == [0], "index must reset to 0..n-1"
        # running max stays 100 through the dip to 80: (80-100)/100 = -0.2
        assert out["dd"]["A"] == -0.2, "deepest drawdown is -0.2 at the dip to 80"

    def test_max_drawdown_per_symbol_and_running_max(self):
        """L2: drawdown is per-symbol vs. each symbol's cumulative running max.

        A monotonically rising symbol has drawdown exactly 0.0; another symbol's
        dip must not affect it (no global running max across symbols).
        """
        out = self._run_json(
            """
            prices = pd.DataFrame({
                'symbol': ['A','A','A','B','B','B'],
                'date':   ['2023-01-01','2023-01-02','2023-01-03',
                           '2023-01-01','2023-01-02','2023-01-03'],
                # A: 100 -> 80 -> 120  (dd -0.2)
                # B: 10 -> 20 -> 30    (monotone up, dd 0.0)
                'close':  [100.0, 80.0, 120.0, 10.0, 20.0, 30.0],
            })
            res = pa.max_drawdown(prices)
            recs = [(r['symbol'], round(float(r['max_drawdown']), 10))
                    for _, r in res.iterrows()]
            print(json.dumps({
                'recs': recs,
                'symbols_sorted': [r[0] for r in recs] == sorted(r[0] for r in recs),
            }))
            """
        )
        dd = {r[0]: r[1] for r in out["recs"]}
        assert out["symbols_sorted"], "result must be sorted by symbol"
        assert dd["A"] == -0.2, "A deepest drawdown is -0.2"
        assert dd["B"] == 0.0, (
            "a monotonically rising symbol has drawdown 0.0 (running max == close)"
        )

    def test_max_drawdown_deepest_not_last(self):
        """L2: the reported value is the MOST NEGATIVE drawdown, not the final one."""
        out = self._run_json(
            """
            # close path: 100 -> 50 -> 70 -> 90
            # running max stays 100; deepest dip is at 50 -> (50-100)/100 = -0.5,
            # while the final-row drawdown is only (90-100)/100 = -0.1.
            prices = pd.DataFrame({
                'symbol': ['A','A','A','A'],
                'date':   ['2023-01-01','2023-01-02','2023-01-03','2023-01-04'],
                'close':  [100.0, 50.0, 70.0, 90.0],
            })
            res = pa.max_drawdown(prices)
            val = round(float(res.iloc[0]['max_drawdown']), 10)
            print(json.dumps({'val': val}))
            """
        )
        assert out["val"] == -0.5, (
            "max_drawdown must report the deepest dip (-0.5), not the last "
            "row's drawdown (-0.1)"
        )

    def test_max_drawdown_does_not_mutate_input(self):
        """L2: max_drawdown must not mutate its input frame."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before = pd.util.hash_pandas_object(prices, index=True).sum()
            cols_before = list(prices.columns)
            _ = pa.max_drawdown(prices)
            after = pd.util.hash_pandas_object(prices, index=True).sum()
            print(json.dumps({
                'hash_same': bool(before == after),
                'cols_same': cols_before == list(prices.columns),
            }))
            """
        )
        assert out["hash_same"], "max_drawdown must not mutate its input values"
        assert out["cols_same"], "max_drawdown must not change input columns"

    # ---- L2: end-to-end native command -----------------------------------

    def test_agent_native_pytest_passes(self):
        """L2: the spec's native command on the agent's own test suite passes."""
        test_file = os.path.join(self.REPO_DIR, self.TEST_REL)
        assert os.path.isfile(test_file), "agent test file missing"
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scripts/tests/test_price_analytics.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native command `python -m pytest "
            "scripts/tests/test_price_analytics.py -q` failed.\nSTDOUT:\n"
            + proc.stdout + "\nSTDERR:\n" + proc.stderr
        )
        # guard against a vacuous (zero-collected) pass
        assert "no tests ran" not in proc.stdout.lower(), (
            "agent test suite collected no tests"
        )
