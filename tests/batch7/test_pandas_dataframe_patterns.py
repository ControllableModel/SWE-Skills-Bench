"""Tests for the ``pandas-dataframe-patterns`` skill task (variant ext7).

The task asks the agent to create ``scripts/grades_aggregate.py`` inside the
pandas repository, exposing three public functions that turn raw grade records
into per-student and per-course summaries:

  * ``weighted_course_average(grades)`` — per ``(student_id, course)`` weighted
    average ``sum(score*weight)/sum(weight)``; flat, sorted by
    ``(student_id, course)``, contiguous index, input not mutated.
  * ``student_gpa(course_averages, scale)`` — map each ``weighted_avg`` into a
    grade band ``[low, high) -> points`` and return per-student the *unweighted*
    mean of those points; sorted by ``student_id``, contiguous index, neither
    input mutated.
  * ``course_stats(grades)`` — per-course ``student_count`` (distinct
    ``student_id``), ``mean_score`` (mean raw score), ``max_score`` (max raw
    score); sorted by ``course``, contiguous index, input not mutated.

The agent also delivers ``scripts/tests/test_grades_aggregate.py`` and the
native acceptance command is::

    python -m pytest scripts/tests/test_grades_aggregate.py -q

Verification strategy: each L2 case drives the agent's real functions through a
subprocess (so the *installed* pandas is used, not the unbuilt repo source
tree) and deep-validates numeric output, returned structure, ordering, the
weighted-vs-plain-mean distinction, distinct-student counting, half-open band
mapping, and the "do not mutate the inputs" contract.

A naive solution that merely creates files, that returns a plain (unweighted)
mean, that counts rows instead of distinct students, that mis-handles band
boundaries, that fails to sort / reset the index, or that mutates its inputs
must fail these tests.
"""

import json
import os
import subprocess
import tempfile
import textwrap


class TestPandasDataframePatterns:
    REPO_DIR = "/workspace/pandas"

    MODULE_REL = os.path.join("scripts", "grades_aggregate.py")
    TEST_REL = os.path.join("scripts", "tests", "test_grades_aggregate.py")

    # ---- helpers ---------------------------------------------------------

    def _module_path(self):
        return os.path.join(self.REPO_DIR, self.MODULE_REL)

    def _run_driver(self, body, timeout=120):
        """Run a python snippet that imports the agent's grades_aggregate module.

        The driver runs from a clean temporary cwd (NOT the repo root) so that
        ``import pandas`` resolves to the installed/built pandas instead of the
        repository's source tree. The agent's ``scripts`` directory is put on
        sys.path so ``import grades_aggregate`` finds the deliverable. The
        snippet is expected to ``print`` a single JSON line as its final output.

        Chunks separated by the form-feed char ``\\f`` are dedented
        independently, so a flush-left sample literal can be concatenated with
        an indented body.
        """
        scripts_dir = os.path.join(self.REPO_DIR, "scripts")
        assert os.path.isfile(self._module_path()), (
            "scripts/grades_aggregate.py does not exist; agent did not create "
            "the deliverable module."
        )
        header = textwrap.dedent(
            f"""
            import sys, json
            sys.path.insert(0, {scripts_dir!r})
            import pandas as pd
            import numpy as np
            import grades_aggregate as ga
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

    # A reusable sample grade dataset literal, defined once for driver snippets.
    # student 1 / Math:    scores [80,100] weights [1,3] -> weighted avg 95.0
    # student 1 / History: scores [60,90]  weights [1,1] -> weighted avg 75.0
    # student 2 / Math:    scores [50,70]  weights [3,1] -> weighted avg 55.0
    SAMPLE = textwrap.dedent(
        """
        grades = pd.DataFrame({
            'student_id': [1, 1, 1, 1, 2, 2],
            'course':     ['Math','Math','History','History','Math','Math'],
            'assignment': ['a1','a2','a1','a2','a1','a2'],
            'score':      [80.0, 100.0, 60.0, 90.0, 50.0, 70.0],
            'weight':     [1.0, 3.0, 1.0, 1.0, 3.0, 1.0],
        })
        """
    )

    # ---- L1: deliverables exist & minimally well-formed ------------------

    def test_module_file_exists(self):
        """L1: scripts/grades_aggregate.py must exist."""
        assert os.path.isfile(self._module_path()), (
            f"missing deliverable: {self._module_path()}"
        )

    def test_test_file_exists(self):
        """L1: scripts/tests/test_grades_aggregate.py must exist."""
        assert os.path.isfile(os.path.join(self.REPO_DIR, self.TEST_REL)), (
            "missing deliverable test file scripts/tests/test_grades_aggregate.py"
        )

    def test_public_functions_present(self):
        """L1: the three required public functions are importable callables."""
        out = self._run_json(
            """
            names = ['weighted_course_average', 'student_gpa', 'course_stats']
            res = {n: callable(getattr(ga, n, None)) for n in names}
            print(json.dumps(res))
            """
        )
        for name, ok in out.items():
            assert ok, f"grades_aggregate.{name} is missing or not callable"

    # ---- L2: weighted_course_average ------------------------------------

    def test_weighted_average_is_weighted_not_plain_mean(self):
        """L2: spec example scores [80,100] weights [1,3] -> 95.0, not 90.0."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = ga.weighted_course_average(grades)
            cols = list(res.columns)
            idx = list(res.index)
            rows = []
            for _, r in res.iterrows():
                rows.append({
                    'student_id': int(r['student_id']),
                    'course': r['course'],
                    'weighted_avg': float(r['weighted_avg']),
                })
            print(json.dumps({'cols': cols, 'index': idx, 'rows': rows}))
            """
        )
        for c in ("student_id", "course", "weighted_avg"):
            assert c in out["cols"], f"weighted_course_average missing column {c}"
        assert out["index"] == [0, 1, 2], "index must be reset to 0..n-1"
        by_key = {(r["student_id"], r["course"]): r["weighted_avg"]
                  for r in out["rows"]}
        # (80*1 + 100*3) / (1+3) = 380/4 = 95.0 ; the plain mean would be 90.0
        assert by_key[(1, "Math")] == 95.0, (
            "weighted average must weight by `weight`, not be a plain mean"
        )
        # (60*1 + 90*1) / 2 = 75.0
        assert by_key[(1, "History")] == 75.0
        # (50*3 + 70*1) / 4 = 220/4 = 55.0 ; the plain mean would be 60.0
        assert by_key[(2, "Math")] == 55.0, (
            "unequal weights must shift the average away from the plain mean"
        )

    def test_weighted_average_sorted_and_flat(self):
        """L2: output sorted by (student_id, course) ascending, one row per group."""
        out = self._run_json(
            """
            grades = pd.DataFrame({
                'student_id': [2, 1, 2, 1],
                'course':     ['Zoo','Bio','Art','Zoo'],
                'assignment': ['a','a','a','a'],
                'score':      [10.0, 20.0, 30.0, 40.0],
                'weight':     [1.0, 1.0, 1.0, 1.0],
            })
            res = ga.weighted_course_average(grades)
            keys = [(int(r['student_id']), r['course'])
                    for _, r in res.iterrows()]
            print(json.dumps({'keys': keys, 'n': int(len(res)),
                              'index': list(res.index)}))
            """
        )
        assert out["n"] == 4, "one row per distinct (student_id, course)"
        assert out["keys"] == [
            (1, "Bio"), (1, "Zoo"), (2, "Art"), (2, "Zoo"),
        ], f"rows not sorted by (student_id, course): {out['keys']}"
        assert out["index"] == [0, 1, 2, 3], "index must be contiguous 0..n-1"

    def test_weighted_average_collapses_groups(self):
        """L2: multiple rows of one (student, course) collapse to a single row."""
        out = self._run_json(
            """
            grades = pd.DataFrame({
                'student_id': [5, 5, 5],
                'course':     ['Math','Math','Math'],
                'assignment': ['a','b','c'],
                'score':      [0.0, 50.0, 100.0],
                'weight':     [1.0, 1.0, 2.0],
            })
            res = ga.weighted_course_average(grades)
            print(json.dumps({
                'n': int(len(res)),
                'avg': float(res.iloc[0]['weighted_avg']),
            }))
            """
        )
        assert out["n"] == 1, "all rows of one group must collapse to a single row"
        # (0*1 + 50*1 + 100*2) / (1+1+2) = 250/4 = 62.5
        assert out["avg"] == 62.5

    def test_weighted_average_does_not_mutate_input(self):
        """L2: the caller's grades frame must be unchanged after the call."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_cols = list(grades.columns)
            before_hash = pd.util.hash_pandas_object(grades, index=True).sum()
            _ = ga.weighted_course_average(grades)
            after_cols = list(grades.columns)
            after_hash = pd.util.hash_pandas_object(grades, index=True).sum()
            print(json.dumps({
                'cols_same': before_cols == after_cols,
                'hash_same': bool(before_hash == after_hash),
            }))
            """
        )
        assert out["cols_same"], "weighted_course_average must not change input columns"
        assert out["hash_same"], "weighted_course_average must not alter input values"

    # ---- L2: student_gpa -------------------------------------------------

    def test_student_gpa_band_mapping_and_mean(self):
        """L2: half-open band [low, high) -> points, unweighted mean per student."""
        out = self._run_json(
            """
            course_averages = pd.DataFrame({
                'student_id':  [1, 1, 2],
                'course':      ['Math','History','Math'],
                'weighted_avg':[95.0, 75.0, 55.0],
            })
            scale = pd.DataFrame({
                'low':    [0.0, 60.0, 70.0, 80.0, 90.0],
                'high':   [60.0, 70.0, 80.0, 90.0, 100.0001],
                'points': [0.0, 1.0, 2.0, 3.0, 4.0],
            })
            res = ga.student_gpa(course_averages, scale)
            cols = list(res.columns)
            idx = list(res.index)
            gpa = {int(r['student_id']): float(r['gpa'])
                   for _, r in res.iterrows()}
            print(json.dumps({'cols': cols, 'index': idx, 'gpa': gpa}))
            """
        )
        for c in ("student_id", "gpa"):
            assert c in out["cols"], f"student_gpa missing column {c}"
        assert out["index"] == [0, 1], "index must be reset to 0..n-1"
        # student 1: 95.0 -> 4.0 (band [90,100)), 75.0 -> 2.0 (band [70,80))
        #   unweighted mean = (4.0 + 2.0)/2 = 3.0
        assert out["gpa"][1] == 3.0, "GPA must be the unweighted mean of band points"
        # student 2: 55.0 -> 0.0 (band [0,60))
        assert out["gpa"][2] == 0.0

    def test_student_gpa_band_is_half_open(self):
        """L2: a value equal to a band's `low` maps to that band, not the lower one."""
        out = self._run_json(
            """
            # weighted_avg exactly 90.0 must land in [90,100) -> 4.0, not [80,90).
            course_averages = pd.DataFrame({
                'student_id':  [7],
                'course':      ['Math'],
                'weighted_avg':[90.0],
            })
            scale = pd.DataFrame({
                'low':    [80.0, 90.0],
                'high':   [90.0, 100.0001],
                'points': [3.0, 4.0],
            })
            res = ga.student_gpa(course_averages, scale)
            print(json.dumps({'gpa': float(res.iloc[0]['gpa'])}))
            """
        )
        assert out["gpa"] == 4.0, (
            "band is half-open [low, high): a value equal to `low` belongs to "
            "that (upper) band"
        )

    def test_student_gpa_sorted_by_student(self):
        """L2: result sorted by student_id ascending with contiguous index."""
        out = self._run_json(
            """
            course_averages = pd.DataFrame({
                'student_id':  [3, 1, 2, 1],
                'course':      ['A','B','C','D'],
                'weighted_avg':[95.0, 95.0, 65.0, 75.0],
            })
            scale = pd.DataFrame({
                'low':    [0.0, 60.0, 70.0, 80.0, 90.0],
                'high':   [60.0, 70.0, 80.0, 90.0, 100.0001],
                'points': [0.0, 1.0, 2.0, 3.0, 4.0],
            })
            res = ga.student_gpa(course_averages, scale)
            ids = [int(r['student_id']) for _, r in res.iterrows()]
            gpa = {int(r['student_id']): float(r['gpa'])
                   for _, r in res.iterrows()}
            print(json.dumps({'ids': ids, 'index': list(res.index), 'gpa': gpa}))
            """
        )
        assert out["ids"] == [1, 2, 3], "students must be sorted ascending"
        assert out["index"] == [0, 1, 2], "index must be contiguous 0..n-1"
        # student 1: 95.0 -> 4.0, 75.0 -> 2.0 -> mean 3.0
        assert out["gpa"][1] == 3.0
        # student 2: 65.0 -> 1.0
        assert out["gpa"][2] == 1.0
        # student 3: 95.0 -> 4.0
        assert out["gpa"][3] == 4.0

    def test_student_gpa_does_not_mutate_inputs(self):
        """L2: neither course_averages nor scale may be mutated."""
        out = self._run_json(
            """
            course_averages = pd.DataFrame({
                'student_id':  [1, 2],
                'course':      ['Math','Math'],
                'weighted_avg':[95.0, 55.0],
            })
            scale = pd.DataFrame({
                'low':    [0.0, 90.0],
                'high':   [90.0, 100.0001],
                'points': [0.0, 4.0],
            })
            ca_before = pd.util.hash_pandas_object(course_averages, index=True).sum()
            sc_before = pd.util.hash_pandas_object(scale, index=True).sum()
            _ = ga.student_gpa(course_averages, scale)
            ca_after = pd.util.hash_pandas_object(course_averages, index=True).sum()
            sc_after = pd.util.hash_pandas_object(scale, index=True).sum()
            print(json.dumps({
                'ca_same': bool(ca_before == ca_after),
                'sc_same': bool(sc_before == sc_after),
            }))
            """
        )
        assert out["ca_same"], "student_gpa must not mutate course_averages"
        assert out["sc_same"], "student_gpa must not mutate the scale frame"

    # ---- L2: course_stats ------------------------------------------------

    def test_course_stats_values_and_shape(self):
        """L2: distinct student_count, raw mean_score and max_score per course."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = ga.course_stats(grades)
            cols = list(res.columns)
            idx = list(res.index)
            rows = []
            for _, r in res.iterrows():
                rows.append({
                    'course': r['course'],
                    'student_count': int(r['student_count']),
                    'mean_score': float(r['mean_score']),
                    'max_score': float(r['max_score']),
                })
            print(json.dumps({'cols': cols, 'index': idx, 'rows': rows}))
            """
        )
        for c in ("course", "student_count", "mean_score", "max_score"):
            assert c in out["cols"], f"course_stats missing column {c}"
        assert out["index"] == [0, 1], "index must be reset to 0..n-1"
        by_course = {r["course"]: r for r in out["rows"]}
        # courses sorted ascending: History before Math
        assert [r["course"] for r in out["rows"]] == ["History", "Math"], (
            "courses must be sorted ascending"
        )
        # History rows: scores [60, 90] from a single distinct student (id 1)
        hist = by_course["History"]
        assert hist["student_count"] == 1, "History has only student 1"
        assert hist["mean_score"] == 75.0  # (60+90)/2
        assert hist["max_score"] == 90.0
        # Math rows: scores [80,100,50,70] from two distinct students (1 and 2)
        math = by_course["Math"]
        assert math["student_count"] == 2, "Math has students 1 and 2"
        assert math["mean_score"] == 75.0  # (80+100+50+70)/4
        assert math["max_score"] == 100.0

    def test_course_stats_student_count_is_distinct(self):
        """L2: student_count counts DISTINCT student_id, not the number of rows."""
        out = self._run_json(
            """
            # course 'X' has 3 rows but only 2 distinct students (10 appears twice).
            grades = pd.DataFrame({
                'student_id': [10, 10, 20],
                'course':     ['X','X','X'],
                'assignment': ['a','b','a'],
                'score':      [40.0, 60.0, 100.0],
                'weight':     [1.0, 1.0, 1.0],
            })
            res = ga.course_stats(grades)
            r = res.iloc[0]
            print(json.dumps({
                'student_count': int(r['student_count']),
                'mean_score': float(r['mean_score']),
                'max_score': float(r['max_score']),
            }))
            """
        )
        assert out["student_count"] == 2, (
            "student_count must count distinct student_id, not rows"
        )
        # mean over all rows = (40+60+100)/3 ~= 66.667
        assert abs(out["mean_score"] - (200.0 / 3.0)) < 1e-9, (
            "mean_score must be the mean of every raw score row"
        )
        assert out["max_score"] == 100.0

    def test_course_stats_does_not_mutate_input(self):
        """L2: course_stats must not mutate its input frame."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_cols = list(grades.columns)
            before_hash = pd.util.hash_pandas_object(grades, index=True).sum()
            _ = ga.course_stats(grades)
            after_cols = list(grades.columns)
            after_hash = pd.util.hash_pandas_object(grades, index=True).sum()
            print(json.dumps({
                'cols_same': before_cols == after_cols,
                'hash_same': bool(before_hash == after_hash),
            }))
            """
        )
        assert out["cols_same"], "course_stats must not change input columns"
        assert out["hash_same"], "course_stats must not alter input values"

    # ---- L2: end-to-end native command ----------------------------------

    def test_agent_native_pytest_passes(self):
        """L2: the spec's native command on the agent's own test suite passes."""
        test_file = os.path.join(self.REPO_DIR, self.TEST_REL)
        assert os.path.isfile(test_file), "agent test file missing"
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scripts/tests/test_grades_aggregate.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native command `python -m pytest "
            "scripts/tests/test_grades_aggregate.py -q` failed.\nSTDOUT:\n"
            + proc.stdout + "\nSTDERR:\n" + proc.stderr
        )
        # guard against a vacuous (zero-collected) pass
        assert "no tests ran" not in proc.stdout.lower(), (
            "agent test suite collected no tests"
        )
