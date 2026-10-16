"""Tests for the ``pandas-dataframe-patterns`` skill task (variant ext5).

The task asks the agent to create ``scripts/inventory_pivot.py`` inside the
pandas repository, exposing three public functions that reshape a long
inventory-movement log into wide pivot reports:

  * ``quantity_by_warehouse_product(movements)`` -- net (in minus out) quantity
    pivot, one row per warehouse, one column per product, absent pairs = 0,
    no missing values, index/columns sorted ascending, input not mutated.
  * ``direction_counts(movements)`` -- cross-tab counting movement rows per
    warehouse for directions ``in`` / ``out``; missing combos = 0; no mutation.
  * ``top_product_per_warehouse(movements)`` -- for each warehouse the product
    with greatest net quantity, ties broken by alphabetically smallest product;
    one row per warehouse, sorted by warehouse, index reset 0..n-1; no mutation.

The companion deliverable ``scripts/tests/test_inventory_pivot.py`` is also
required, and the spec's native command
``python -m pytest scripts/tests/test_inventory_pivot.py -q`` must pass.

Verification strategy: these tests drive the agent's real functions through a
subprocess (so the *installed* pandas is used, not the unbuilt repo source
tree). Each L2 case deep-validates concrete numeric values, the
net = in - out arithmetic, zero-fill of absent combinations, NaN-freeness,
sorting, deterministic alphabetical tie-breaking and the "do not mutate input"
contract. A naive solution that merely creates the files, that uses a raw
sum/count instead of net = in - out, that leaves NaN for absent combos, that
breaks ties non-deterministically, or that mutates its inputs will fail.
"""

import json
import os
import subprocess
import tempfile
import textwrap


class TestPandasDataframePatterns:
    REPO_DIR = "/workspace/pandas"

    MODULE_REL = os.path.join("scripts", "inventory_pivot.py")
    TEST_REL = os.path.join("scripts", "tests", "test_inventory_pivot.py")

    # ---- helpers ---------------------------------------------------------

    def _module_path(self):
        return os.path.join(self.REPO_DIR, self.MODULE_REL)

    def _run_driver(self, body, timeout=120):
        """Run a python snippet that imports the agent's inventory_pivot module.

        The driver runs from a clean temporary cwd (NOT the repo root) so that
        ``import pandas`` resolves to the installed/built pandas instead of the
        repository's source tree. The agent's ``scripts`` directory is put on
        sys.path so ``import inventory_pivot`` finds the deliverable. The snippet
        is expected to ``print`` a single JSON line as its final output.
        """
        scripts_dir = os.path.join(self.REPO_DIR, "scripts")
        assert os.path.isfile(self._module_path()), (
            "scripts/inventory_pivot.py does not exist; agent did not create the "
            "deliverable module."
        )
        header = textwrap.dedent(
            f"""
            import sys, json
            sys.path.insert(0, {scripts_dir!r})
            import pandas as pd
            import numpy as np
            import inventory_pivot as ip
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

    # A reusable sample movement log, defined once for driver snippets.
    # Net quantities (in - out):
    #   W1/A: in 10, out 3        -> 7
    #   W1/B: in 4                -> 4
    #   W2/A: in 5, out 5         -> 0
    #   W2/C: in 8                -> 8
    # Absent pairs (e.g. W1/C, W2/B) must be 0.
    SAMPLE = textwrap.dedent(
        """
        movements = pd.DataFrame({
            'warehouse': ['W1','W1','W1','W2','W2','W2'],
            'product':   ['A', 'A', 'B', 'A', 'A', 'C'],
            'direction': ['in','out','in','in','out','in'],
            'quantity':  [10,  3,    4,    5,   5,    8 ],
        })
        """
    )

    # ---- L1: deliverables exist & minimally well-formed ------------------

    def test_module_file_exists(self):
        """L1: scripts/inventory_pivot.py must exist."""
        assert os.path.isfile(self._module_path()), (
            f"missing deliverable: {self._module_path()}"
        )

    def test_test_file_exists(self):
        """L1: scripts/tests/test_inventory_pivot.py must exist."""
        assert os.path.isfile(os.path.join(self.REPO_DIR, self.TEST_REL)), (
            "missing deliverable test file scripts/tests/test_inventory_pivot.py"
        )

    def test_public_functions_present(self):
        """L1: the three required public functions are importable callables."""
        out = self._run_json(
            """
            names = ['quantity_by_warehouse_product','direction_counts',
                     'top_product_per_warehouse']
            res = {n: callable(getattr(ip, n, None)) for n in names}
            print(json.dumps(res))
            """
        )
        for name, ok in out.items():
            assert ok, f"inventory_pivot.{name} is missing or not callable"

    # ---- L2: quantity_by_warehouse_product ------------------------------

    def test_quantity_net_values(self):
        """L2: cells are net = sum(in) - sum(out) per (warehouse, product)."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = ip.quantity_by_warehouse_product(movements)
            d = {str(w): {str(p): int(res.loc[w, p]) for p in res.columns}
                 for w in res.index}
            print(json.dumps({
                'data': d,
                'rows': [str(w) for w in res.index],
                'cols': [str(c) for c in res.columns],
                'any_na': bool(res.isna().any().any()),
            }))
            """
        )
        data = out["data"]
        # W1/A: in10 - out3 = 7 (spec example)
        assert data["W1"]["A"] == 7, "W1/A must be net 7 (in 10 minus out 3)"
        # W1/B: in 4, no out -> 4
        assert data["W1"]["B"] == 4
        # W2/A: in 5 - out 5 = 0
        assert data["W2"]["A"] == 0, "equal in/out must net to 0"
        # W2/C: in 8 -> 8
        assert data["W2"]["C"] == 8
        assert not out["any_na"], "pivot must contain no missing values"

    def test_quantity_absent_pairs_are_zero(self):
        """L2: a (warehouse, product) pair that never appears is 0, not NaN."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = ip.quantity_by_warehouse_product(movements)
            print(json.dumps({
                'w1_c': int(res.loc['W1', 'C']),  # W1 never moved product C
                'w2_b': int(res.loc['W2', 'B']),  # W2 never moved product B
                'any_na': bool(res.isna().any().any()),
            }))
            """
        )
        assert out["w1_c"] == 0, "absent (W1, C) combination must be 0"
        assert out["w2_b"] == 0, "absent (W2, B) combination must be 0"
        assert not out["any_na"], "no missing values allowed in the pivot"

    def test_quantity_index_and_columns_sorted(self):
        """L2: warehouse index and product columns are sorted ascending."""
        out = self._run_json(
            """
            # deliberately unsorted warehouses/products
            movements = pd.DataFrame({
                'warehouse': ['WB','WA','WB','WA'],
                'product':   ['Z', 'M', 'A', 'Z'],
                'direction': ['in','in','in','in'],
                'quantity':  [1,   2,   3,   4 ],
            })
            res = ip.quantity_by_warehouse_product(movements)
            print(json.dumps({
                'rows': [str(w) for w in res.index],
                'cols': [str(c) for c in res.columns],
            }))
            """
        )
        assert out["rows"] == ["WA", "WB"], "warehouse index must be sorted ascending"
        assert out["cols"] == ["A", "M", "Z"], "product columns must be sorted ascending"

    def test_quantity_does_not_mutate_input(self):
        """L2: quantity_by_warehouse_product must not mutate its input frame."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_cols = list(movements.columns)
            before_hash = pd.util.hash_pandas_object(movements, index=True).sum()
            before_n = int(len(movements))
            _ = ip.quantity_by_warehouse_product(movements)
            after_cols = list(movements.columns)
            after_hash = pd.util.hash_pandas_object(movements, index=True).sum()
            after_n = int(len(movements))
            print(json.dumps({
                'cols_same': before_cols == after_cols,
                'hash_same': bool(before_hash == after_hash),
                'len_same': before_n == after_n,
            }))
            """
        )
        assert out["cols_same"], "must not change input columns"
        assert out["hash_same"], "must not alter input values"
        assert out["len_same"], "must not add/remove input rows"

    # ---- L2: direction_counts -------------------------------------------

    def test_direction_counts_values(self):
        """L2: cross-tab counts of in/out movement ROWS per warehouse."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = ip.direction_counts(movements)
            cols = [str(c) for c in res.columns]
            d = {str(w): {str(c): int(res.loc[w, c]) for c in res.columns}
                 for w in res.index}
            print(json.dumps({
                'data': d,
                'cols': cols,
                'rows': [str(w) for w in res.index],
                'any_na': bool(res.isna().any().any()),
            }))
            """
        )
        assert "in" in out["cols"] and "out" in out["cols"], (
            "direction_counts must have 'in' and 'out' columns"
        )
        data = out["data"]
        # W1 rows: in (A), out (A), in (B) -> in=2, out=1
        assert data["W1"]["in"] == 2, "W1 has two 'in' movement rows"
        assert data["W1"]["out"] == 1, "W1 has one 'out' movement row"
        # W2 rows: in (A), out (A), in (C) -> in=2, out=1
        assert data["W2"]["in"] == 2
        assert data["W2"]["out"] == 1
        assert not out["any_na"], "no missing values allowed in the cross-tab"

    def test_direction_counts_missing_direction_is_zero(self):
        """L2: a warehouse with only one direction shows 0 for the other."""
        out = self._run_json(
            """
            movements = pd.DataFrame({
                'warehouse': ['W1','W1','W2'],
                'product':   ['A', 'B', 'A'],
                'direction': ['in','in','out'],  # W1 has no 'out', W2 has no 'in'
                'quantity':  [1,   2,   3 ],
            })
            res = ip.direction_counts(movements)
            print(json.dumps({
                'w1_in': int(res.loc['W1', 'in']),
                'w1_out': int(res.loc['W1', 'out']),
                'w2_in': int(res.loc['W2', 'in']),
                'w2_out': int(res.loc['W2', 'out']),
                'any_na': bool(res.isna().any().any()),
            }))
            """
        )
        assert out["w1_in"] == 2
        assert out["w1_out"] == 0, "missing direction must be 0, not NaN"
        assert out["w2_in"] == 0, "missing direction must be 0, not NaN"
        assert out["w2_out"] == 1
        assert not out["any_na"], "missing combinations must be 0, leaving no NaN"

    def test_direction_counts_does_not_mutate_input(self):
        """L2: direction_counts must not mutate its input frame."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_hash = pd.util.hash_pandas_object(movements, index=True).sum()
            before_cols = list(movements.columns)
            _ = ip.direction_counts(movements)
            after_hash = pd.util.hash_pandas_object(movements, index=True).sum()
            after_cols = list(movements.columns)
            print(json.dumps({
                'hash_same': bool(before_hash == after_hash),
                'cols_same': before_cols == after_cols,
            }))
            """
        )
        assert out["hash_same"], "direction_counts must not alter input values"
        assert out["cols_same"], "direction_counts must not alter input columns"

    # ---- L2: top_product_per_warehouse ----------------------------------

    def test_top_product_picks_max_net(self):
        """L2: per warehouse, picks the product with greatest net quantity."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = ip.top_product_per_warehouse(movements)
            cols = list(res.columns)
            idx = [int(i) for i in res.index]
            pairs = [(str(w), str(p))
                     for w, p in zip(res['warehouse'], res['product'])]
            print(json.dumps({'cols': cols, 'index': idx, 'pairs': pairs}))
            """
        )
        assert "warehouse" in out["cols"] and "product" in out["cols"], (
            "result must have 'warehouse' and 'product' columns"
        )
        assert out["index"] == [0, 1], "index must be reset to 0..n-1"
        pairs = dict(out["pairs"])
        # W1 nets: A=7, B=4 -> A is top
        assert pairs["W1"] == "A", "W1 top product must be A (net 7 > B net 4)"
        # W2 nets: A=0, C=8 -> C is top
        assert pairs["W2"] == "C", "W2 top product must be C (net 8 > A net 0)"

    def test_top_product_tie_broken_alphabetically(self):
        """L2: ties on net quantity are broken by alphabetically smallest product."""
        out = self._run_json(
            """
            # W1 net: A=5, B=5 -> tie, must pick 'A' (alphabetically smallest).
            movements = pd.DataFrame({
                'warehouse': ['W1','W1'],
                'product':   ['B', 'A'],   # B listed first to defeat order-based picks
                'direction': ['in','in'],
                'quantity':  [5,   5 ],
            })
            res = ip.top_product_per_warehouse(movements)
            pairs = [(str(w), str(p))
                     for w, p in zip(res['warehouse'], res['product'])]
            print(json.dumps({'pairs': pairs, 'n': int(len(res))}))
            """
        )
        assert out["n"] == 1, "one row per warehouse"
        assert dict(out["pairs"])["W1"] == "A", (
            "tie must be broken by choosing the alphabetically smallest product"
        )

    def test_top_product_one_row_per_warehouse_sorted(self):
        """L2: exactly one row per warehouse, sorted by warehouse ascending."""
        out = self._run_json(
            """
            movements = pd.DataFrame({
                'warehouse': ['W3','W1','W2','W1','W2'],
                'product':   ['X', 'A', 'M', 'B', 'N'],
                'direction': ['in','in','in','in','in'],
                'quantity':  [9,   1,   2,   5,   1 ],
            })
            res = ip.top_product_per_warehouse(movements)
            warehouses = [str(w) for w in res['warehouse']]
            pairs = [(str(w), str(p))
                     for w, p in zip(res['warehouse'], res['product'])]
            print(json.dumps({
                'warehouses': warehouses,
                'sorted': warehouses == sorted(warehouses),
                'unique': len(warehouses) == len(set(warehouses)),
                'pairs': pairs,
                'index': [int(i) for i in res.index],
            }))
            """
        )
        assert out["warehouses"] == ["W1", "W2", "W3"], (
            "one row per warehouse, sorted ascending"
        )
        assert out["sorted"], "warehouses must be sorted ascending"
        assert out["unique"], "exactly one row per warehouse"
        assert out["index"] == [0, 1, 2], "index must be reset to 0..n-1"
        pairs = dict(out["pairs"])
        # W1 nets: A=1, B=5 -> B ; W2 nets: M=2, N=1 -> M ; W3: X=9
        assert pairs["W1"] == "B"
        assert pairs["W2"] == "M"
        assert pairs["W3"] == "X"

    def test_top_product_does_not_mutate_input(self):
        """L2: top_product_per_warehouse must not mutate its input frame."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_hash = pd.util.hash_pandas_object(movements, index=True).sum()
            before_cols = list(movements.columns)
            _ = ip.top_product_per_warehouse(movements)
            after_hash = pd.util.hash_pandas_object(movements, index=True).sum()
            after_cols = list(movements.columns)
            print(json.dumps({
                'hash_same': bool(before_hash == after_hash),
                'cols_same': before_cols == after_cols,
            }))
            """
        )
        assert out["hash_same"], "must not alter input values"
        assert out["cols_same"], "must not alter input columns"

    # ---- L2: end-to-end native command ----------------------------------

    def test_agent_native_pytest_passes(self):
        """L2: the spec's native command on the agent's own test suite passes."""
        test_file = os.path.join(self.REPO_DIR, self.TEST_REL)
        assert os.path.isfile(test_file), "agent test file missing"
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scripts/tests/test_inventory_pivot.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native command `python -m pytest "
            "scripts/tests/test_inventory_pivot.py -q` failed.\nSTDOUT:\n"
            + proc.stdout
            + "\nSTDERR:\n"
            + proc.stderr
        )
        # guard against a vacuous (zero-collected) pass
        assert "no tests ran" not in proc.stdout.lower(), (
            "agent test suite collected no tests"
        )
