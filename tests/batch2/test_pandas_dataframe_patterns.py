"""Tests for the ``pandas-dataframe-patterns`` skill task (variant ext2).

The ext2 task asks the agent to create ``scripts/txn_reconcile.py`` inside the
pandas repository, exposing three public functions that reconcile actual
transactions against an expected ledger on the composite key
``(account_id, period)``:

  * ``match_transactions(actual, expected)`` -- a left-style join that attaches
    ``expected_amount`` to every ``actual`` row exactly once (no drops, no
    duplication), raising when ``expected`` has a duplicate composite key.
  * ``flag_discrepancies(matched, tolerance)`` -- adds ``delta`` and a boolean
    ``is_match`` column under a tolerance, treating missing expectations as a
    non-match with a missing delta.
  * ``unmatched_only(matched)`` -- the subset of rows that had no expected
    entry, with the index reset to ``0..n-1``.

The tests verify the *behaviour* of the agent's module dynamically. Each L2
case drives the real functions through a subprocess (so the installed pandas is
used, not the unbuilt repo source tree) and deep-validates the join shape,
numeric deltas, the tolerance boundary, missing-value semantics, the
duplicate-key error, the index-reset and the "do not mutate / do not drop / do
not duplicate" contracts.

A naive solution that merely creates files, uses an inner-join (dropping
unmatched actuals), silently duplicates rows on a duplicated expected key,
hard-codes ``is_match`` or ``delta``, treats a missing expectation as a match,
or mutates its inputs will fail.
"""

import json
import os
import subprocess
import tempfile
import textwrap


class TestPandasDataframePatterns:
    REPO_DIR = "/workspace/pandas"

    MODULE_REL = os.path.join("scripts", "txn_reconcile.py")
    TEST_REL = os.path.join("scripts", "tests", "test_txn_reconcile.py")

    # ---- helpers ---------------------------------------------------------

    def _module_path(self):
        return os.path.join(self.REPO_DIR, self.MODULE_REL)

    def _run_driver(self, body, timeout=120):
        """Run a python snippet that imports the agent's txn_reconcile module.

        The driver runs from a clean temporary cwd (NOT the repo root) so that
        ``import pandas`` resolves to the installed/built pandas instead of the
        repository's source tree. The agent's ``scripts`` directory is put on
        sys.path so ``import txn_reconcile`` finds the deliverable. The snippet
        is expected to ``print`` a single JSON line as its final output.
        """
        scripts_dir = os.path.join(self.REPO_DIR, "scripts")
        assert os.path.isfile(self._module_path()), (
            "scripts/txn_reconcile.py does not exist; agent did not create the "
            "deliverable module."
        )
        header = textwrap.dedent(
            f"""
            import sys, json
            sys.path.insert(0, {scripts_dir!r})
            import pandas as pd
            import numpy as np
            import txn_reconcile as tr
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
    # account 1 has two periods; account 2 has one period that is NOT in the
    # expected ledger (so it must survive as an unmatched row).
    SAMPLE = textwrap.dedent(
        """
        actual = pd.DataFrame({
            'account_id': [1,        1,        2,        1],
            'period':     ['2023-Q1','2023-Q2','2023-Q1','2023-Q1'],
            'txn_id':     [101,      102,      103,      104],
            'amount':     [100.0,    50.0,     75.0,     100.4],
        })
        expected = pd.DataFrame({
            'account_id':     [1,        1],
            'period':         ['2023-Q1','2023-Q2'],
            'expected_amount':[100.5,    50.0],
        })
        """
    )

    # ---- L1: deliverables exist & minimally well-formed ------------------

    def test_module_file_exists(self):
        """L1: scripts/txn_reconcile.py must exist."""
        assert os.path.isfile(self._module_path()), (
            f"missing deliverable: {self._module_path()}"
        )

    def test_test_file_exists(self):
        """L1: scripts/tests/test_txn_reconcile.py must exist."""
        assert os.path.isfile(os.path.join(self.REPO_DIR, self.TEST_REL)), (
            "missing deliverable test file scripts/tests/test_txn_reconcile.py"
        )

    def test_public_functions_present(self):
        """L1: the three required public functions are importable callables."""
        out = self._run_json(
            """
            names = ['match_transactions','flag_discrepancies','unmatched_only']
            res = {n: callable(getattr(tr, n, None)) for n in names}
            print(json.dumps(res))
            """
        )
        for name, ok in out.items():
            assert ok, f"txn_reconcile.{name} is missing or not callable"

    # ---- L2: match_transactions -----------------------------------------

    def test_match_keeps_all_actual_rows_once(self):
        """L2: match returns every actual txn exactly once with expected_amount."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = tr.match_transactions(actual, expected)
            txn_ids = sorted(int(x) for x in res['txn_id'].tolist())
            exp = {int(t): (None if pd.isna(e) else float(e))
                   for t, e in zip(res['txn_id'], res['expected_amount'])}
            amt = {int(t): float(a)
                   for t, a in zip(res['txn_id'], res['amount'])}
            print(json.dumps({
                'n': int(len(res)),
                'txn_ids': txn_ids,
                'exp': exp,
                'amt': amt,
                'has_exp_col': 'expected_amount' in res.columns,
            }))
            """
        )
        assert out["has_exp_col"], "result must carry an expected_amount column"
        assert out["n"] == 4, "match must not drop or duplicate actual rows"
        assert out["txn_ids"] == [101, 102, 103, 104], (
            "every actual txn_id must appear exactly once"
        )
        # expected_amount attached from the matching (account_id, period)
        assert out["exp"]["101"] == 100.5
        assert out["exp"]["104"] == 100.5  # same (1, 2023-Q1) key
        assert out["exp"]["102"] == 50.0
        # account 2 / 2023-Q1 absent from expected -> missing expected_amount
        assert out["exp"]["103"] is None, (
            "actual row with no expected entry must survive with missing "
            "expected_amount"
        )
        # amounts must be preserved verbatim from actual
        assert out["amt"]["101"] == 100.0
        assert out["amt"]["103"] == 75.0

    def test_match_duplicate_expected_key_raises(self):
        """L2: a duplicated (account_id, period) in expected must raise."""
        proc = self._run_driver(
            """
            actual = pd.DataFrame({
                'account_id':[1,2],
                'period':['2023-Q1','2023-Q1'],
                'txn_id':[1,2],
                'amount':[10.0,20.0],
            })
            expected = pd.DataFrame({
                'account_id':[1,1,2],                 # (1,2023-Q1) duplicated
                'period':['2023-Q1','2023-Q1','2023-Q1'],
                'expected_amount':[10.0,99.0,20.0],
            })
            try:
                tr.match_transactions(actual, expected)
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
            "match_transactions must raise on a duplicated expected composite "
            "key rather than multiplying actual rows"
        )

    def test_match_does_not_duplicate_on_duplicate_actual_key(self):
        """L2: many actual rows sharing a key all match the single expected row."""
        out = self._run_json(
            """
            # three actual rows on the SAME (1, 2023-Q1) key; one expected row.
            actual = pd.DataFrame({
                'account_id':[1,1,1],
                'period':['2023-Q1','2023-Q1','2023-Q1'],
                'txn_id':[1,2,3],
                'amount':[10.0,20.0,30.0],
            })
            expected = pd.DataFrame({
                'account_id':[1],
                'period':['2023-Q1'],
                'expected_amount':[15.0],
            })
            res = tr.match_transactions(actual, expected)
            exp = sorted(float(x) for x in res['expected_amount'].tolist())
            print(json.dumps({
                'n': int(len(res)),
                'txn_ids': sorted(int(x) for x in res['txn_id'].tolist()),
                'exp': exp,
            }))
            """
        )
        assert out["n"] == 3, "row count must equal the actual row count"
        assert out["txn_ids"] == [1, 2, 3]
        assert out["exp"] == [15.0, 15.0, 15.0], (
            "each actual row on the key gets the single expected_amount"
        )

    def test_match_does_not_mutate_input(self):
        """L2: the caller's actual frame must be unchanged after match."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_cols = list(actual.columns)
            before_hash = pd.util.hash_pandas_object(actual, index=True).sum()
            _ = tr.match_transactions(actual, expected)
            after_cols = list(actual.columns)
            after_hash = pd.util.hash_pandas_object(actual, index=True).sum()
            print(json.dumps({
                'cols_same': before_cols == after_cols,
                'hash_same': bool(before_hash == after_hash),
                'has_expected': 'expected_amount' in actual.columns,
            }))
            """
        )
        assert out["cols_same"], "match must not change input columns"
        assert out["hash_same"], "match must not alter input values"
        assert not out["has_expected"], (
            "match must not add expected_amount to the caller's actual frame"
        )

    # ---- L2: flag_discrepancies -----------------------------------------

    def test_flag_delta_and_is_match_values(self):
        """L2: delta = amount - expected_amount; is_match correct per row."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            matched = tr.match_transactions(actual, expected)
            flagged = tr.flag_discrepancies(matched, 0.5)
            by_txn = {}
            for t, d, m in zip(flagged['txn_id'], flagged['delta'],
                               flagged['is_match']):
                by_txn[int(t)] = {
                    'delta': (None if pd.isna(d) else round(float(d), 6)),
                    'is_match': bool(m),
                }
            print(json.dumps({
                'by_txn': by_txn,
                'has_delta': 'delta' in flagged.columns,
                'has_is_match': 'is_match' in flagged.columns,
            }))
            """
        )
        assert out["has_delta"] and out["has_is_match"], (
            "flagged frame must add delta and is_match columns"
        )
        bt = out["by_txn"]
        # txn 101: amount 100.0, expected 100.5 -> delta -0.5, |delta|<=0.5 -> True
        assert bt["101"]["delta"] == -0.5
        assert bt["101"]["is_match"] is True
        # txn 104: amount 100.4, expected 100.5 -> delta -0.1 -> True
        assert bt["104"]["delta"] == -0.1
        assert bt["104"]["is_match"] is True
        # txn 102: amount 50.0, expected 50.0 -> delta 0.0 -> True
        assert bt["102"]["delta"] == 0.0
        assert bt["102"]["is_match"] is True
        # txn 103: no expected -> delta missing, is_match False
        assert bt["103"]["delta"] is None, (
            "missing expected_amount must yield a missing delta"
        )
        assert bt["103"]["is_match"] is False, (
            "missing expected_amount must never be a match"
        )

    def test_flag_tolerance_boundary(self):
        """L2: same data, tighter tolerance flips a near-match to non-match."""
        out = self._run_json(
            """
            actual = pd.DataFrame({
                'account_id':[1],
                'period':['2023-Q1'],
                'txn_id':[1],
                'amount':[100.0],
            })
            expected = pd.DataFrame({
                'account_id':[1],
                'period':['2023-Q1'],
                'expected_amount':[100.4],
            })
            matched = tr.match_transactions(actual, expected)
            loose = tr.flag_discrepancies(matched, 0.5)
            tight = tr.flag_discrepancies(matched, 0.1)
            print(json.dumps({
                'loose': bool(loose['is_match'].iloc[0]),
                'tight': bool(tight['is_match'].iloc[0]),
                'delta': round(float(loose['delta'].iloc[0]), 6),
            }))
            """
        )
        # |100.0 - 100.4| = 0.4 ; <= 0.5 True, <= 0.1 False
        assert out["delta"] == -0.4
        assert out["loose"] is True, "tolerance 0.5 must accept a 0.4 gap"
        assert out["tight"] is False, "tolerance 0.1 must reject a 0.4 gap"

    def test_flag_is_match_dtype_is_boolean(self):
        """L2: is_match must be genuine booleans, not strings/ints/NaN."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            matched = tr.match_transactions(actual, expected)
            flagged = tr.flag_discrepancies(matched, 0.5)
            vals = flagged['is_match'].tolist()
            print(json.dumps({
                'all_bool': all(isinstance(v, (bool, np.bool_)) for v in vals),
                'any_na': bool(pd.isna(flagged['is_match']).any()),
                'n_true': int(sum(1 for v in vals if bool(v))),
                'n_false': int(sum(1 for v in vals if not bool(v))),
            }))
            """
        )
        assert out["all_bool"], "is_match values must be booleans"
        assert not out["any_na"], "is_match must never be missing"
        # 3 matched rows (101,102,104) True, 1 unmatched (103) False
        assert out["n_true"] == 3
        assert out["n_false"] == 1

    def test_flag_does_not_mutate_input(self):
        """L2: flag_discrepancies must not mutate the matched frame."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            matched = tr.match_transactions(actual, expected)
            before_cols = list(matched.columns)
            before_hash = pd.util.hash_pandas_object(matched, index=True).sum()
            _ = tr.flag_discrepancies(matched, 0.5)
            after_cols = list(matched.columns)
            after_hash = pd.util.hash_pandas_object(matched, index=True).sum()
            print(json.dumps({
                'cols_same': before_cols == after_cols,
                'hash_same': bool(before_hash == after_hash),
                'has_delta': 'delta' in matched.columns,
                'has_is_match': 'is_match' in matched.columns,
            }))
            """
        )
        assert out["cols_same"], "flag must not change the matched frame's columns"
        assert out["hash_same"], "flag must not alter the matched frame's values"
        assert not out["has_delta"], "flag must not add delta to its input"
        assert not out["has_is_match"], "flag must not add is_match to its input"

    # ---- L2: unmatched_only ---------------------------------------------

    def test_unmatched_only_selects_missing_and_resets_index(self):
        """L2: only rows with no expected entry, index reset to 0..n-1."""
        out = self._run_json(
            """
            actual = pd.DataFrame({
                'account_id':[1,        2,        3,        2],
                'period':    ['2023-Q1','2023-Q1','2023-Q2','2023-Q2'],
                'txn_id':    [10,       11,       12,       13],
                'amount':    [1.0,      2.0,      3.0,      4.0],
            })
            expected = pd.DataFrame({
                'account_id':[1],
                'period':['2023-Q1'],
                'expected_amount':[1.0],
            })
            matched = tr.match_transactions(actual, expected)
            res = tr.unmatched_only(matched)
            print(json.dumps({
                'txn_ids': sorted(int(x) for x in res['txn_id'].tolist()),
                'n': int(len(res)),
                'index': [int(i) for i in res.index.tolist()],
                'all_exp_na': bool(res['expected_amount'].isna().all()),
            }))
            """
        )
        # only (1,2023-Q1) is expected; txn 10 matched, 11/12/13 unmatched
        assert out["n"] == 3
        assert out["txn_ids"] == [11, 12, 13], (
            "unmatched_only must return exactly the rows with no expected entry"
        )
        assert out["index"] == [0, 1, 2], "index must be reset to 0..n-1"
        assert out["all_exp_na"], (
            "every returned row must have a missing expected_amount"
        )

    def test_unmatched_only_empty_when_all_matched(self):
        """L2: when every actual row matches, unmatched_only is empty."""
        out = self._run_json(
            """
            actual = pd.DataFrame({
                'account_id':[1,1],
                'period':['2023-Q1','2023-Q2'],
                'txn_id':[1,2],
                'amount':[5.0,6.0],
            })
            expected = pd.DataFrame({
                'account_id':[1,1],
                'period':['2023-Q1','2023-Q2'],
                'expected_amount':[5.0,6.0],
            })
            matched = tr.match_transactions(actual, expected)
            res = tr.unmatched_only(matched)
            print(json.dumps({'n': int(len(res))}))
            """
        )
        assert out["n"] == 0, "no unmatched rows expected when all keys are present"

    def test_unmatched_only_does_not_mutate_input(self):
        """L2: unmatched_only must not mutate the matched frame."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            matched = tr.match_transactions(actual, expected)
            before_hash = pd.util.hash_pandas_object(matched, index=True).sum()
            before_n = int(len(matched))
            _ = tr.unmatched_only(matched)
            after_hash = pd.util.hash_pandas_object(matched, index=True).sum()
            after_n = int(len(matched))
            print(json.dumps({
                'hash_same': bool(before_hash == after_hash),
                'n_same': before_n == after_n,
            }))
            """
        )
        assert out["hash_same"], "unmatched_only must not alter its input's values"
        assert out["n_same"], "unmatched_only must not drop rows from its input"

    # ---- L2: end-to-end native command ----------------------------------

    def test_agent_native_pytest_passes(self):
        """L2: the spec's native command on the agent's own test suite passes."""
        test_file = os.path.join(self.REPO_DIR, self.TEST_REL)
        assert os.path.isfile(test_file), "agent test file missing"
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            ["python", "-m", "pytest", "scripts/tests/test_txn_reconcile.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native command `python -m pytest scripts/tests/test_txn_reconcile.py "
            "-q` failed.\nSTDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr
        )
        # guard against a vacuous (zero-collected) pass
        assert "no tests ran" not in proc.stdout.lower(), (
            "agent test suite collected no tests"
        )
