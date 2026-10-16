"""Tests for the ``pandas-dataframe-patterns`` skill task (variant ext6).

The task asks the agent to create ``scripts/dtype_optimize.py`` inside the
pandas repository, exposing three public functions that shrink the in-memory
footprint of a table without changing its values:

  * ``optimize(df, max_category_ratio=0.5)`` — downcast integers to the
    smallest signed int dtype, downcast floats to the smallest float dtype no
    wider than the original, and convert low-cardinality object columns
    (distinct/rows STRICTLY below ``max_category_ratio``) to categorical, all
    while preserving every value and never mutating the caller's frame.
  * ``memory_report(df)`` — one row per column with ``column``, ``dtype`` and
    integer ``bytes`` (deep memory), indexed 0..n-1 in column order.
  * ``savings(original, optimized)`` — float fraction of deep memory saved,
    ``1 - optimized_total / original_total``.

Verification strategy: each L2 case drives the real functions through a
subprocess (so the installed/built pandas is used, not the repo source tree)
and deep-validates the resulting dtypes, byte counts, value preservation,
non-mutation contracts, and the strict-ratio categorical boundary.

A naive solution that merely creates files, returns the frame unchanged, uses
``downcast='integer'`` without choosing the *smallest* signed dtype, converts
every object column (or none) to categorical regardless of cardinality, ignores
the ``max_category_ratio`` boundary, reports shallow instead of deep memory, or
mutates its input will fail these tests. The final case runs the spec's native
acceptance command against the agent's own test suite.
"""

import json
import os
import subprocess
import tempfile
import textwrap


class TestPandasDataframePatterns:
    REPO_DIR = "/workspace/pandas"

    MODULE_REL = os.path.join("scripts", "dtype_optimize.py")
    TEST_REL = os.path.join("scripts", "tests", "test_dtype_optimize.py")

    # ---- helpers ---------------------------------------------------------

    def _module_path(self):
        return os.path.join(self.REPO_DIR, self.MODULE_REL)

    def _run_driver(self, body, timeout=120):
        """Run a python snippet that imports the agent's dtype_optimize module.

        The driver runs from a clean temporary cwd (NOT the repo root) so that
        ``import pandas`` resolves to the installed/built pandas instead of the
        repository's source tree. The agent's ``scripts`` directory is put on
        sys.path so ``import dtype_optimize`` finds the deliverable. The snippet
        is expected to ``print`` a single JSON line as its final output.
        """
        scripts_dir = os.path.join(self.REPO_DIR, "scripts")
        assert os.path.isfile(self._module_path()), (
            "scripts/dtype_optimize.py does not exist; agent did not create the "
            "deliverable module."
        )
        header = textwrap.dedent(
            f"""
            import sys, json
            sys.path.insert(0, {scripts_dir!r})
            import pandas as pd
            import numpy as np
            import dtype_optimize as do
            """
        )
        # Dedent each top-level chunk independently. Callers may concatenate a
        # flush-left literal with an indented body; dedenting the whole string
        # would find no common prefix and leave the body indented.
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

    # ---- L1: deliverables exist & minimally well-formed ------------------

    def test_module_file_exists(self):
        """L1: scripts/dtype_optimize.py must exist."""
        assert os.path.isfile(self._module_path()), (
            f"missing deliverable: {self._module_path()}"
        )

    def test_test_file_exists(self):
        """L1: scripts/tests/test_dtype_optimize.py must exist."""
        assert os.path.isfile(os.path.join(self.REPO_DIR, self.TEST_REL)), (
            "missing deliverable test file scripts/tests/test_dtype_optimize.py"
        )

    def test_public_functions_present(self):
        """L1: the three required public functions are importable callables."""
        out = self._run_json(
            """
            names = ['optimize', 'memory_report', 'savings']
            res = {n: callable(getattr(do, n, None)) for n in names}
            print(json.dumps(res))
            """
        )
        for name, ok in out.items():
            assert ok, f"dtype_optimize.{name} is missing or not callable"

    # ---- L2: optimize integer downcast ----------------------------------

    def test_optimize_int_downcast_to_smallest_signed(self):
        """L2: int columns become the SMALLEST signed int dtype that fits."""
        out = self._run_json(
            """
            df = pd.DataFrame({
                'tiny':   [1, 2, 3],            # fits int8
                'small':  [1, 200, 3],          # 200 > 127 -> needs int16
                'medn':   [-40000, 0, 40000],   # needs int32
                'big':    [1, 2, 3000000000],   # > 2**31 -> needs int64
            })
            res = do.optimize(df)
            dtypes = {c: str(res[c].dtype) for c in res.columns}
            # value preservation
            equal = bool((res.reset_index(drop=True)
                          == df.reset_index(drop=True)).all().all())
            print(json.dumps({'dtypes': dtypes, 'equal': equal}))
            """
        )
        d = out["dtypes"]
        assert d["tiny"] == "int8", "[1,2,3] must downcast to int8"
        assert d["small"] == "int16", "value 200 needs int16, not int8"
        assert d["medn"] == "int32", "+/-40000 needs int32, not int16"
        assert d["big"] == "int64", "3e9 needs int64"
        assert out["equal"], "optimize must preserve every integer value"

    def test_optimize_int_uses_signed_dtypes_only(self):
        """L2: even all-positive int columns use a SIGNED dtype (spec wording)."""
        out = self._run_json(
            """
            df = pd.DataFrame({'pos': [0, 1, 100, 127]})  # fits int8 signed
            res = do.optimize(df)
            dt = str(res['pos'].dtype)
            print(json.dumps({'dtype': dt, 'unsigned': dt.startswith('uint')}))
            """
        )
        assert out["dtype"] == "int8", "all-positive in [0,127] must be int8"
        assert not out["unsigned"], "spec requires the smallest SIGNED int dtype"

    # ---- L2: optimize float downcast ------------------------------------

    def test_optimize_float_downcast_no_wider_than_original(self):
        """L2: float columns downcast to a narrower float, never wider, lossless."""
        out = self._run_json(
            """
            df = pd.DataFrame({
                'f': pd.Series([1.0, 2.5, 3.25], dtype='float64'),
            })
            res = do.optimize(df)
            dt = str(res['f'].dtype)
            equal = bool((res['f'].to_numpy() == df['f'].to_numpy()).all())
            width = res['f'].dtype.itemsize
            print(json.dumps({'dtype': dt, 'equal': equal, 'width': int(width)}))
            """
        )
        # 1.0, 2.5, 3.25 are exactly representable in float32
        assert out["dtype"] in ("float32", "float16"), (
            f"exactly-representable floats should downcast, got {out['dtype']}"
        )
        assert out["width"] <= 8, "result must be no wider than the float64 input"
        assert out["equal"], "float downcast must preserve values exactly"

    def test_optimize_float_not_widened(self):
        """L2: a float32 input must not be promoted to a wider float by optimize."""
        out = self._run_json(
            """
            df = pd.DataFrame({'f': pd.Series([1.0, 2.0, 3.0], dtype='float32')})
            orig_width = df['f'].dtype.itemsize
            res = do.optimize(df)
            print(json.dumps({
                'orig_width': int(orig_width),
                'new_width': int(res['f'].dtype.itemsize),
                'is_float': bool(res['f'].dtype.kind == 'f'),
            }))
            """
        )
        assert out["is_float"], "float column must stay floating point"
        assert out["new_width"] <= out["orig_width"], (
            "optimize must never produce a float wider than the original"
        )

    # ---- L2: optimize categorical boundary ------------------------------

    def test_optimize_low_cardinality_object_becomes_categorical(self):
        """L2: 2 distinct values in 100 rows -> categorical (ratio 0.02 < 0.5)."""
        out = self._run_json(
            """
            df = pd.DataFrame({'col': ['a', 'b'] * 50})  # 2 distinct / 100 rows
            res = do.optimize(df)
            dt = str(res['col'].dtype)
            vals = list(res['col'].astype(object))
            print(json.dumps({
                'is_cat': dt == 'category',
                'values_equal': vals == list(df['col']),
            }))
            """
        )
        assert out["is_cat"], "low-cardinality object column must become category"
        assert out["values_equal"], "categorical conversion must preserve values"

    def test_optimize_high_cardinality_object_stays_object(self):
        """L2: all-unique object column stays object (ratio 1.0 >= 0.5)."""
        out = self._run_json(
            """
            df = pd.DataFrame({'col': [f'u{i}' for i in range(20)]})
            res = do.optimize(df)
            print(json.dumps({'dtype': str(res['col'].dtype)}))
            """
        )
        assert out["dtype"] == "object", (
            "high-cardinality object column must remain object, not category"
        )

    def test_optimize_category_ratio_is_strict_boundary(self):
        """L2: ratio EXACTLY equal to threshold stays object (strict '<')."""
        out = self._run_json(
            """
            # 2 distinct in 4 rows -> ratio 0.5 ; threshold 0.5 ; strict '<' so NO.
            df = pd.DataFrame({'col': ['a', 'b', 'a', 'b']})
            at = do.optimize(df, max_category_ratio=0.5)
            # ratio 0.25 < 0.5 -> YES with default; bump threshold below ratio.
            below = do.optimize(df, max_category_ratio=0.4)  # 0.5 not < 0.4 -> object
            above = do.optimize(df, max_category_ratio=0.6)  # 0.5 < 0.6 -> category
            print(json.dumps({
                'at_threshold': str(at['col'].dtype),
                'below': str(below['col'].dtype),
                'above': str(above['col'].dtype),
            }))
            """
        )
        # ratio is exactly 0.5 here
        assert out["at_threshold"] == "object", (
            "ratio == max_category_ratio must NOT convert (strictly-less rule)"
        )
        assert out["below"] == "object", "0.5 is not < 0.4 -> object"
        assert out["above"] == "category", "0.5 < 0.6 -> category"

    def test_optimize_respects_custom_ratio_argument(self):
        """L2: max_category_ratio must actually be honoured, not hardcoded."""
        out = self._run_json(
            """
            # 5 distinct in 10 rows -> ratio 0.5
            df = pd.DataFrame({'col': [str(i % 5) for i in range(10)]})
            strict = do.optimize(df, max_category_ratio=0.3)  # 0.5 !< 0.3 -> object
            loose = do.optimize(df, max_category_ratio=0.9)   # 0.5 < 0.9 -> category
            print(json.dumps({
                'strict': str(strict['col'].dtype),
                'loose': str(loose['col'].dtype),
            }))
            """
        )
        assert out["strict"] == "object", "tight ratio must keep column object"
        assert out["loose"] == "category", "loose ratio must convert to category"

    # ---- L2: non-mutation contracts -------------------------------------

    def test_optimize_does_not_mutate_input(self):
        """L2: the caller's frame must be byte-for-byte unchanged after optimize."""
        out = self._run_json(
            """
            df = pd.DataFrame({
                'i': pd.Series([1, 2, 3], dtype='int64'),
                'f': pd.Series([1.0, 2.0, 3.0], dtype='float64'),
                's': ['a', 'a', 'b'],
            })
            dtypes_before = {c: str(df[c].dtype) for c in df.columns}
            hash_before = pd.util.hash_pandas_object(df, index=True).sum()
            res = do.optimize(df)
            dtypes_after = {c: str(df[c].dtype) for c in df.columns}
            hash_after = pd.util.hash_pandas_object(df, index=True).sum()
            # ensure the result is genuinely a different object with new dtypes
            res_int_dtype = str(res['i'].dtype)
            print(json.dumps({
                'dtypes_same': dtypes_before == dtypes_after,
                'hash_same': bool(hash_before == hash_after),
                'res_changed': res_int_dtype != dtypes_before['i'],
            }))
            """
        )
        assert out["dtypes_same"], "optimize must not change the input's dtypes"
        assert out["hash_same"], "optimize must not alter the input's values"
        assert out["res_changed"], (
            "optimize must actually downcast (int64 -> smaller) in the result"
        )

    # ---- L2: memory_report ----------------------------------------------

    def test_memory_report_shape_and_values(self):
        """L2: one row per column, deep positive integer bytes, column order kept."""
        out = self._run_json(
            """
            df = pd.DataFrame({
                'a': pd.Series([1, 2, 3], dtype='int64'),
                'b': ['xx', 'yy', 'zz'],
            })
            rep = do.memory_report(df)
            cols = list(rep.columns)
            idx = list(rep.index)
            order = [str(x) for x in rep['column'].tolist()]
            dtypes = [str(x) for x in rep['dtype'].tolist()]
            byts = [int(x) for x in rep['bytes'].tolist()]
            # cross-check 'bytes' against pandas' own deep memory usage
            deep = df.memory_usage(deep=True)
            expected = {c: int(deep[c]) for c in df.columns}
            print(json.dumps({
                'cols': cols, 'index': idx, 'order': order,
                'dtypes': dtypes, 'bytes': byts, 'expected': expected,
            }))
            """
        )
        for c in ("column", "dtype", "bytes"):
            assert c in out["cols"], f"memory_report missing column {c}"
        assert out["index"] == [0, 1], "report index must be reset to 0..n-1"
        assert out["order"] == ["a", "b"], "rows must follow df column order"
        assert out["dtypes"][0] == "int64"
        assert out["dtypes"][1] == "object"
        assert all(b > 0 for b in out["bytes"]), "bytes must be positive"
        # the reported bytes must be the DEEP usage (object column counts string
        # payload). Shallow usage would under-report the object column.
        report = {c: b for c, b in zip(out["order"], out["bytes"])}
        assert report["a"] == out["expected"]["a"], "int bytes must match deep usage"
        assert report["b"] == out["expected"]["b"], (
            "object bytes must be DEEP memory (includes the strings), not shallow"
        )

    def test_memory_report_does_not_mutate_input(self):
        """L2: memory_report must leave its input frame unchanged."""
        out = self._run_json(
            """
            df = pd.DataFrame({'a': [1, 2, 3], 's': ['x', 'y', 'z']})
            hash_before = pd.util.hash_pandas_object(df, index=True).sum()
            dtypes_before = {c: str(df[c].dtype) for c in df.columns}
            _ = do.memory_report(df)
            hash_after = pd.util.hash_pandas_object(df, index=True).sum()
            dtypes_after = {c: str(df[c].dtype) for c in df.columns}
            print(json.dumps({
                'hash_same': bool(hash_before == hash_after),
                'dtypes_same': dtypes_before == dtypes_after,
            }))
            """
        )
        assert out["hash_same"], "memory_report must not mutate input values"
        assert out["dtypes_same"], "memory_report must not mutate input dtypes"

    # ---- L2: savings -----------------------------------------------------

    def test_savings_between_zero_and_one_for_smaller_frame(self):
        """L2: savings of an optimized frame is strictly in (0, 1) and exact."""
        out = self._run_json(
            """
            df = pd.DataFrame({
                'i': pd.Series([1, 2, 3, 4], dtype='int64'),
                's': ['a', 'b', 'a', 'b'],
            })
            opt = do.optimize(df)
            frac = float(do.savings(df, opt))
            # independently recompute the expected fraction from deep memory
            orig_total = int(df.memory_usage(deep=True).drop('Index').sum())
            opt_total = int(opt.memory_usage(deep=True).drop('Index').sum())
            expected = 1 - opt_total / orig_total
            print(json.dumps({
                'frac': frac, 'expected': expected,
                'orig_total': orig_total, 'opt_total': opt_total,
            }))
            """
        )
        assert 0.0 < out["frac"] < 1.0, (
            f"savings of a genuinely smaller frame must be in (0,1): {out['frac']}"
        )
        assert out["opt_total"] < out["orig_total"], "optimized frame must be smaller"
        assert abs(out["frac"] - out["expected"]) < 1e-9, (
            "savings must equal 1 - optimized_total/original_total over deep memory"
        )

    def test_savings_zero_for_identical_frames(self):
        """L2: savings of a frame against itself is 0.0 (no improvement)."""
        out = self._run_json(
            """
            df = pd.DataFrame({'i': pd.Series([1, 2, 3], dtype='int8'),
                               's': ['a', 'b', 'c']})
            frac = float(do.savings(df, df))
            print(json.dumps({'frac': frac}))
            """
        )
        assert abs(out["frac"]) < 1e-9, (
            "savings between identical frames must be 0.0, not a hardcoded value"
        )

    def test_savings_does_not_mutate_inputs(self):
        """L2: savings must not mutate either of its input frames."""
        out = self._run_json(
            """
            df = pd.DataFrame({'i': pd.Series([1, 2, 3], dtype='int64'),
                               's': ['a', 'a', 'b']})
            opt = do.optimize(df)
            h_orig_before = pd.util.hash_pandas_object(df, index=True).sum()
            h_opt_before = pd.util.hash_pandas_object(opt, index=True).sum()
            dt_orig_before = {c: str(df[c].dtype) for c in df.columns}
            dt_opt_before = {c: str(opt[c].dtype) for c in opt.columns}
            _ = do.savings(df, opt)
            print(json.dumps({
                'orig_hash_same': bool(
                    h_orig_before == pd.util.hash_pandas_object(df, index=True).sum()),
                'opt_hash_same': bool(
                    h_opt_before == pd.util.hash_pandas_object(opt, index=True).sum()),
                'orig_dt_same': dt_orig_before == {c: str(df[c].dtype) for c in df.columns},
                'opt_dt_same': dt_opt_before == {c: str(opt[c].dtype) for c in opt.columns},
            }))
            """
        )
        assert out["orig_hash_same"], "savings must not mutate the original frame"
        assert out["opt_hash_same"], "savings must not mutate the optimized frame"
        assert out["orig_dt_same"] and out["opt_dt_same"], (
            "savings must not change either input's dtypes"
        )

    # ---- L2: end-to-end native command ----------------------------------

    def test_agent_native_pytest_passes(self):
        """L2: the spec's native command on the agent's own test suite passes."""
        test_file = os.path.join(self.REPO_DIR, self.TEST_REL)
        assert os.path.isfile(test_file), "agent test file missing"
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            ["python", "-m", "pytest", "scripts/tests/test_dtype_optimize.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native command `python -m pytest scripts/tests/test_dtype_optimize.py -q` "
            "failed.\nSTDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr
        )
        # guard against a vacuous (zero-collected) pass
        assert "no tests ran" not in proc.stdout.lower(), (
            "agent test suite collected no tests"
        )
