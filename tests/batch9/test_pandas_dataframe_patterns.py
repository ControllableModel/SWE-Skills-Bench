"""Tests for the ``pandas-dataframe-patterns`` skill task (variant ext9).

The task asks the agent to create ``scripts/reshape_tidy.py`` inside the pandas
repository, exposing three public functions that convert between wide and long
("tidy") measurement layouts and tidy messy column headers:

    * ``wide_to_long(df, id_cols)``  -- melt a wide measurement table into a long
      ``id_cols + [metric, value]`` frame, dropping missing measurements, sorted
      by ``id_cols`` then ``metric``, index reset, input not mutated.
    * ``long_to_wide(df, id_cols)``  -- the inverse: pivot a long frame back to a
      wide frame, ``id_cols`` as ordinary columns sorted ascending, absent
      combinations left missing, index reset, input not mutated.
    * ``clean_headers(df)``          -- normalise column names: strip, lowercase,
      and collapse runs of internal whitespace into a single underscore, cells
      and row order unchanged, input not mutated.

The agent must also ship ``scripts/tests/test_reshape_tidy.py``.

These tests verify the *behaviour* of the agent's module dynamically. Each L2
case drives the real functions through a subprocess (so the installed pandas is
used, not the unbuilt repo source tree), and deep-validates the long/wide
shapes, the metric/value column contract, missing-cell dropping, round-trip
value preservation, header normalisation, sorting/index-reset, and the
"do not mutate the caller's frame" contracts.

A naive solution that merely creates files, that keeps missing measurements as
rows, that forgets to sort or reset the index, that hardcodes column names, that
lowercases without collapsing whitespace, or that mutates its input -- will fail.
"""

import json
import os
import subprocess
import tempfile
import textwrap


class TestPandasDataframePatterns:
    REPO_DIR = "/workspace/pandas"

    MODULE_REL = os.path.join("scripts", "reshape_tidy.py")
    TEST_REL = os.path.join("scripts", "tests", "test_reshape_tidy.py")

    # ---- helpers ---------------------------------------------------------

    def _module_path(self):
        return os.path.join(self.REPO_DIR, self.MODULE_REL)

    def _run_driver(self, body, timeout=120):
        """Run a python snippet that imports the agent's reshape_tidy module.

        The driver runs from a clean temporary cwd (NOT the repo root) so that
        ``import pandas`` resolves to the installed/built pandas instead of the
        repository's source tree. The agent's ``scripts`` directory is put on
        sys.path so ``import reshape_tidy`` finds the deliverable. The snippet is
        expected to ``print`` a single JSON line as its final output.

        Top-level chunks separated by a form-feed (``\\f``) are dedented
        independently so a flush-left literal can be concatenated with an
        indented body.
        """
        scripts_dir = os.path.join(self.REPO_DIR, "scripts")
        assert os.path.isfile(self._module_path()), (
            "scripts/reshape_tidy.py does not exist; agent did not create the "
            "deliverable module."
        )
        header = textwrap.dedent(
            f"""
            import sys, json
            sys.path.insert(0, {scripts_dir!r})
            import pandas as pd
            import numpy as np
            import reshape_tidy as rt
            """
        )
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

    # A reusable wide-table literal, defined once for driver snippets.
    WIDE = textwrap.dedent(
        """
        wide = pd.DataFrame({
            'site':   ['A', 'B'],
            'day':    [1,   2],
            'temp':   [20.0, 21.0],
            'humid':  [0.5,  np.nan],   # B/humid is missing
            'press':  [1010.0, 1005.0],
        })
        """
    )

    # ---- L1: deliverables exist & minimally well-formed ------------------

    def test_module_file_exists(self):
        """L1: scripts/reshape_tidy.py must exist."""
        assert os.path.isfile(self._module_path()), (
            f"missing deliverable: {self._module_path()}"
        )

    def test_test_file_exists(self):
        """L1: scripts/tests/test_reshape_tidy.py must exist."""
        assert os.path.isfile(os.path.join(self.REPO_DIR, self.TEST_REL)), (
            "missing deliverable test file scripts/tests/test_reshape_tidy.py"
        )

    def test_public_functions_present(self):
        """L1: the three required public functions are importable callables."""
        out = self._run_json(
            """
            names = ['wide_to_long', 'long_to_wide', 'clean_headers']
            res = {n: callable(getattr(rt, n, None)) for n in names}
            print(json.dumps(res))
            """
        )
        for name, ok in out.items():
            assert ok, f"reshape_tidy.{name} is missing or not callable"

    # ---- L2: wide_to_long ------------------------------------------------

    def test_wide_to_long_shape_columns_and_drops_missing(self):
        """L2: long frame has id_cols + metric + value, missing cells dropped."""
        out = self._run_json(
            self.WIDE
            + "\f"
            + """
            res = rt.wide_to_long(wide, ['site', 'day'])
            cols = list(res.columns)
            triples = [
                (r['site'], int(r['day']), r['metric'], float(r['value']))
                for _, r in res.iterrows()
            ]
            print(json.dumps({
                'cols': cols,
                'n': int(len(res)),
                'index': [int(i) for i in res.index],
                'triples': triples,
                'any_value_na': bool(res['value'].isna().any()),
            }))
            """
        )
        assert out["cols"] == ["site", "day", "metric", "value"], (
            f"long frame must be id_cols + [metric, value]; got {out['cols']}"
        )
        # 2 sites x 3 metrics = 6 cells, minus the one missing (B/humid) = 5 rows.
        assert out["n"] == 5, "missing measurement cell must be dropped, not kept"
        assert out["index"] == [0, 1, 2, 3, 4], "index must be reset to 0..n-1"
        assert not out["any_value_na"], "no missing value may survive in the long output"
        triples = {(s, d, m): v for (s, d, m, v) in out["triples"]}
        # the B/humid combination must be entirely absent
        assert ("B", 2, "humid") not in triples, "missing cell must not appear as a row"
        assert triples[("A", 1, "temp")] == 20.0
        assert triples[("A", 1, "humid")] == 0.5
        assert triples[("A", 1, "press")] == 1010.0
        assert triples[("B", 2, "temp")] == 21.0
        assert triples[("B", 2, "press")] == 1005.0

    def test_wide_to_long_sorted_by_id_then_metric(self):
        """L2: output sorted by id_cols (in order) then metric ascending."""
        out = self._run_json(
            """
            # deliberately unsorted ids and non-alphabetical metric columns
            wide = pd.DataFrame({
                'site':  ['B', 'A'],
                'day':   [2,   1],
                'zeta':  [9.0, 1.0],
                'alpha': [8.0, 2.0],
            })
            res = rt.wide_to_long(wide, ['site', 'day'])
            order = [(r['site'], int(r['day']), r['metric'])
                     for _, r in res.iterrows()]
            print(json.dumps({'order': order}))
            """
        )
        assert out["order"] == [
            ["A", 1, "alpha"],
            ["A", 1, "zeta"],
            ["B", 2, "alpha"],
            ["B", 2, "zeta"],
        ], f"rows not sorted by id_cols then metric ascending: {out['order']}"

    def test_wide_to_long_does_not_mutate_input(self):
        """L2: the caller's wide frame must be unchanged after wide_to_long."""
        out = self._run_json(
            self.WIDE
            + "\f"
            + """
            before_cols = list(wide.columns)
            before_hash = pd.util.hash_pandas_object(wide, index=True).sum()
            _ = rt.wide_to_long(wide, ['site', 'day'])
            after_cols = list(wide.columns)
            after_hash = pd.util.hash_pandas_object(wide, index=True).sum()
            print(json.dumps({
                'cols_same': before_cols == after_cols,
                'hash_same': bool(before_hash == after_hash),
                'has_metric': 'metric' in wide.columns,
                'has_value': 'value' in wide.columns,
            }))
            """
        )
        assert out["cols_same"], "wide_to_long must not change input columns"
        assert out["hash_same"], "wide_to_long must not alter input values"
        assert not out["has_metric"], "wide_to_long must not add metric to the input"
        assert not out["has_value"], "wide_to_long must not add value to the input"

    # ---- L2: long_to_wide ------------------------------------------------

    def test_long_to_wide_shape_and_absent_combo_missing(self):
        """L2: inverse pivot; id_cols are ordinary columns, absent cell is NaN."""
        out = self._run_json(
            """
            long = pd.DataFrame({
                'site':   ['A', 'A', 'B'],
                'day':    [1,   1,   2],
                'metric': ['temp', 'humid', 'temp'],   # (B, 2, humid) absent
                'value':  [20.0, 0.5, 21.0],
            })
            res = rt.long_to_wide(long, ['site', 'day'])
            cols = list(res.columns)
            recs = []
            for _, r in res.iterrows():
                recs.append({
                    'site': r['site'],
                    'day': int(r['day']),
                    'temp': (None if pd.isna(r['temp']) else float(r['temp'])),
                    'humid': (None if pd.isna(r['humid']) else float(r['humid'])),
                })
            print(json.dumps({
                'cols': cols,
                'n': int(len(res)),
                'index': [int(i) for i in res.index],
                'recs': recs,
            }))
            """
        )
        # id_cols must be ordinary columns, not the index
        assert "site" in out["cols"] and "day" in out["cols"], (
            f"id_cols must be ordinary columns; got {out['cols']}"
        )
        assert "temp" in out["cols"] and "humid" in out["cols"], (
            f"each distinct metric must become a column; got {out['cols']}"
        )
        assert out["n"] == 2, "one row per distinct (site, day) combination"
        assert out["index"] == [0, 1], "index must be reset to 0..n-1"
        recs = {(r["site"], r["day"]): r for r in out["recs"]}
        assert recs[("A", 1)]["temp"] == 20.0
        assert recs[("A", 1)]["humid"] == 0.5
        assert recs[("B", 2)]["temp"] == 21.0
        # the (B, 2, humid) combination was absent in the long input
        assert recs[("B", 2)]["humid"] is None, "absent combination must be missing"

    def test_long_to_wide_sorted_by_id_cols(self):
        """L2: wide output rows sorted by id_cols ascending."""
        out = self._run_json(
            """
            long = pd.DataFrame({
                'site':   ['B', 'A', 'B', 'A'],
                'day':    [1,   2,   1,   2],
                'metric': ['x', 'x', 'y', 'y'],
                'value':  [1.0, 2.0, 3.0, 4.0],
            })
            res = rt.long_to_wide(long, ['site', 'day'])
            order = [(r['site'], int(r['day'])) for _, r in res.iterrows()]
            print(json.dumps({'order': order}))
            """
        )
        assert out["order"] == [["A", 2], ["B", 1]], (
            f"wide rows must be sorted by id_cols ascending: {out['order']}"
        )

    def test_long_to_wide_does_not_mutate_input(self):
        """L2: long_to_wide must not mutate its input frame."""
        out = self._run_json(
            """
            long = pd.DataFrame({
                'site':   ['A', 'A', 'B'],
                'day':    [1,   1,   2],
                'metric': ['temp', 'humid', 'temp'],
                'value':  [20.0, 0.5, 21.0],
            })
            before_cols = list(long.columns)
            before = pd.util.hash_pandas_object(long, index=True).sum()
            _ = rt.long_to_wide(long, ['site', 'day'])
            after = pd.util.hash_pandas_object(long, index=True).sum()
            print(json.dumps({
                'cols_same': before_cols == ['site', 'day', 'metric', 'value'],
                'hash_same': bool(before == after),
            }))
            """
        )
        assert out["cols_same"], "long_to_wide must not change input columns"
        assert out["hash_same"], "long_to_wide must not alter input values"

    def test_round_trip_preserves_values(self):
        """L2: long_to_wide(wide_to_long(x)) reproduces a complete wide table."""
        out = self._run_json(
            """
            # complete wide table (no missing cells), deliberately unsorted ids
            wide = pd.DataFrame({
                'site':  ['B', 'A', 'C'],
                'day':   [2,   1,   3],
                'temp':  [21.0, 20.0, 22.0],
                'humid': [0.6,  0.5,  0.7],
            })
            long = rt.wide_to_long(wide, ['site', 'day'])
            back = rt.long_to_wide(long, ['site', 'day'])
            # canonicalise both frames for comparison: sort rows & columns
            exp = wide.sort_values(['site', 'day']).reset_index(drop=True)
            exp = exp[sorted(exp.columns)]
            got = back[sorted(back.columns)].reset_index(drop=True)
            recs_exp = {(r['site'], int(r['day'])):
                        {'temp': float(r['temp']), 'humid': float(r['humid'])}
                        for _, r in exp.iterrows()}
            recs_got = {(r['site'], int(r['day'])):
                        {'temp': float(r['temp']), 'humid': float(r['humid'])}
                        for _, r in got.iterrows()}
            print(json.dumps({
                'equal': recs_exp == recs_got,
                'exp': {f'{k[0]}|{k[1]}': v for k, v in recs_exp.items()},
                'got': {f'{k[0]}|{k[1]}': v for k, v in recs_got.items()},
                'any_na': bool(back[['temp', 'humid']].isna().any().any()),
            }))
            """
        )
        assert out["equal"], (
            "round-trip must preserve every value for a complete table.\n"
            f"expected={out['exp']}\ngot={out['got']}"
        )
        assert not out["any_na"], "round-trip of a complete table must have no NaN"

    # ---- L2: clean_headers -----------------------------------------------

    def test_clean_headers_normalisation_example(self):
        """L2: spec example '  Order  ID ' -> 'order_id', plus general rules."""
        out = self._run_json(
            """
            df = pd.DataFrame({
                '  Order  ID ': [1, 2],
                'First Name':   ['x', 'y'],
                ' TOTAL\tAMOUNT ': [10.0, 20.0],
                'already_ok':   [True, False],
            })
            res = rt.clean_headers(df)
            print(json.dumps({'cols': list(res.columns)}))
            """
        )
        assert out["cols"] == [
            "order_id",
            "first_name",
            "total_amount",
            "already_ok",
        ], f"headers not normalised as specified: {out['cols']}"

    def test_clean_headers_preserves_cells_and_row_order(self):
        """L2: only column names change; cell values and row order are intact."""
        out = self._run_json(
            """
            df = pd.DataFrame({
                ' A B ': [3, 1, 2],
                'C':     ['p', 'q', 'r'],
            })
            res = rt.clean_headers(df)
            print(json.dumps({
                'cols': list(res.columns),
                'first_col': [int(x) for x in res.iloc[:, 0].tolist()],
                'second_col': list(res.iloc[:, 1].tolist()),
            }))
            """
        )
        assert out["cols"] == ["a_b", "c"]
        # values and their order must be untouched
        assert out["first_col"] == [3, 1, 2], "cell values / row order must be unchanged"
        assert out["second_col"] == ["p", "q", "r"]

    def test_clean_headers_does_not_mutate_input(self):
        """L2: clean_headers must return a copy and leave the input's columns."""
        out = self._run_json(
            """
            df = pd.DataFrame({'  X Y ': [1], 'Z': [2]})
            before_cols = list(df.columns)
            res = rt.clean_headers(df)
            after_cols = list(df.columns)
            print(json.dumps({
                'input_unchanged': before_cols == after_cols == ['  X Y ', 'Z'],
                'result_cols': list(res.columns),
                'is_copy': res is not df,
            }))
            """
        )
        assert out["input_unchanged"], "clean_headers must not rename the input's columns"
        assert out["result_cols"] == ["x_y", "z"]
        assert out["is_copy"], "clean_headers must return a new frame, not the input"

    # ---- L2: end-to-end native command ----------------------------------

    def test_agent_native_pytest_passes(self):
        """L2: the spec's native command on the agent's own test suite passes."""
        test_file = os.path.join(self.REPO_DIR, self.TEST_REL)
        assert os.path.isfile(test_file), "agent test file missing"
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            ["python", "-m", "pytest", "scripts/tests/test_reshape_tidy.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native command `python -m pytest scripts/tests/test_reshape_tidy.py -q` "
            "failed.\nSTDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr
        )
        # guard against a vacuous (zero-collected) pass
        assert "no tests ran" not in proc.stdout.lower(), (
            "agent test suite collected no tests"
        )
