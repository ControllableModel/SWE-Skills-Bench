"""Tests for the ``pandas-dataframe-patterns`` skill task (variant ext4).

The ext4 task asks the agent to create ``scripts/survey_clean.py`` inside the
pandas repository, exposing three public functions that clean raw survey
responses:

* ``dedupe_responses(responses)`` -- keep exactly one row per ``respondent_id``
  (the latest ``submitted_at``, ties broken by last input occurrence), sorted by
  ``respondent_id`` ascending with a reset 0..n-1 index, without mutating input.
* ``impute(responses)`` -- fill missing ``rating`` with the *median* of present
  ratings (whole table) and missing ``comment`` with the literal
  ``"(no comment)"``; no remaining NaNs; input untouched.
* ``normalize_types(responses)`` -- coerce dtypes: ``respondent_id`` integer,
  ``submitted_at`` datetime, ``comment`` categorical, ``rating`` float, while
  preserving values and not mutating the input.

These tests verify the *behaviour* of the agent's module dynamically. Each L2
case drives the real functions through a subprocess (so the installed pandas is
used, not the unbuilt repo source tree) and deep-validates concrete values:
which rows survive deduplication, the exact median imputed, the fill literal,
the resulting dtypes, ordering / index, and the "do not mutate the input"
contracts.

A naive solution that merely creates files, keeps the *first* (earliest)
submission, drops duplicate respondents arbitrarily, fills ratings with the mean
or a constant, forgets to reset/sort the index, leaves dtypes as object, or
mutates the caller's frame will fail.

The final L2 case runs the spec's own native acceptance command
(``python -m pytest scripts/tests/test_survey_clean.py -q``) against the agent's
own test suite.
"""

import json
import os
import subprocess
import tempfile
import textwrap


class TestPandasDataframePatterns:
    REPO_DIR = "/workspace/pandas"

    MODULE_REL = os.path.join("scripts", "survey_clean.py")
    TEST_REL = os.path.join("scripts", "tests", "test_survey_clean.py")

    # ---- helpers ---------------------------------------------------------

    def _module_path(self):
        return os.path.join(self.REPO_DIR, self.MODULE_REL)

    def _run_driver(self, body, timeout=120):
        """Run a python snippet that imports the agent's survey_clean module.

        The driver runs from a clean temporary cwd (NOT the repo root) so that
        ``import pandas`` resolves to the installed/built pandas instead of the
        repository's source tree. The agent's ``scripts`` directory is put on
        sys.path so ``import survey_clean`` finds the deliverable. The snippet
        is expected to ``print`` a single JSON line as its final output.

        Top-level chunks are separated by a form-feed (\\f) so that a flush-left
        literal can be concatenated with an indented body and each chunk
        dedented independently.
        """
        scripts_dir = os.path.join(self.REPO_DIR, "scripts")
        assert os.path.isfile(self._module_path()), (
            "scripts/survey_clean.py does not exist; agent did not create the "
            "deliverable module."
        )
        header = textwrap.dedent(
            f"""
            import sys, json
            sys.path.insert(0, {scripts_dir!r})
            import pandas as pd
            import numpy as np
            import survey_clean as sc
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

    # A reusable sample dataset literal, defined once for driver snippets.
    # Respondent 7 submits twice (2023-01-01 then 2023-02-01); respondent 3 has
    # a missing rating; respondent 5 has a missing comment.
    SAMPLE = textwrap.dedent(
        """
        responses = pd.DataFrame({
            'respondent_id': [7, 3, 7, 5, 1],
            'submitted_at':  ['2023-01-01', '2023-01-05', '2023-02-01',
                              '2023-01-10', '2023-01-02'],
            'rating':        [4.0, np.nan, 5.0, 3.0, 1.0],
            'comment':       ['ok', 'meh', 'great', np.nan, 'bad'],
        })
        """
    )

    # ---- L1: deliverables exist & minimally well-formed ------------------

    def test_module_file_exists(self):
        """L1: scripts/survey_clean.py must exist."""
        assert os.path.isfile(self._module_path()), (
            f"missing deliverable: {self._module_path()}"
        )

    def test_test_file_exists(self):
        """L1: scripts/tests/test_survey_clean.py must exist."""
        assert os.path.isfile(os.path.join(self.REPO_DIR, self.TEST_REL)), (
            "missing deliverable test file scripts/tests/test_survey_clean.py"
        )

    def test_public_functions_present(self):
        """L1: the three required public functions are importable callables."""
        out = self._run_json(
            """
            names = ['dedupe_responses', 'impute', 'normalize_types']
            res = {n: callable(getattr(sc, n, None)) for n in names}
            print(json.dumps(res))
            """
        )
        for name, ok in out.items():
            assert ok, f"survey_clean.{name} is missing or not callable"

    # ---- L2: dedupe_responses -------------------------------------------

    def test_dedupe_keeps_latest_submission(self):
        """L2: for a respondent with two rows, only the latest survives."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = sc.dedupe_responses(responses)
            ids = [int(x) for x in res['respondent_id'].tolist()]
            # map respondent_id -> (rating, comment) of surviving row
            survive = {}
            for _, r in res.iterrows():
                survive[int(r['respondent_id'])] = {
                    'rating': (None if pd.isna(r['rating']) else float(r['rating'])),
                    'submitted_at': str(r['submitted_at']),
                }
            print(json.dumps({
                'n': int(len(res)),
                'ids': ids,
                'survive': survive,
            }))
            """
        )
        # four distinct respondents: 1, 3, 5, 7
        assert out["n"] == 4, "dedupe must keep exactly one row per respondent_id"
        assert out["ids"] == [1, 3, 5, 7], "output must be sorted by respondent_id"
        # respondent 7's surviving row is the 2023-02-01 one (rating 5.0),
        # not the earlier 2023-01-01 one (rating 4.0)
        assert out["survive"]["7"]["rating"] == 5.0, (
            "dedupe must keep the LATEST submitted_at row, not the earliest"
        )
        assert out["survive"]["7"]["submitted_at"].startswith("2023-02-01")

    def test_dedupe_index_is_reset_and_contiguous(self):
        """L2: the result index is reset to a contiguous 0..n-1 range."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = sc.dedupe_responses(responses)
            print(json.dumps({
                'index': [int(i) for i in res.index.tolist()],
                'n': int(len(res)),
            }))
            """
        )
        assert out["index"] == list(range(out["n"])), (
            "dedupe must reset the index to 0..n-1"
        )

    def test_dedupe_tie_breaks_by_last_occurrence(self):
        """L2: equal submitted_at -> keep the last occurrence in input order."""
        out = self._run_json(
            """
            responses = pd.DataFrame({
                'respondent_id': [9, 9, 2],
                'submitted_at':  ['2023-03-01', '2023-03-01', '2023-03-02'],
                'rating':        [1.0, 2.0, 3.0],
                'comment':       ['first', 'second', 'other'],
            })
            res = sc.dedupe_responses(responses)
            row9 = res[res['respondent_id'] == 9].iloc[0]
            print(json.dumps({
                'n': int(len(res)),
                'rating9': float(row9['rating']),
                'comment9': str(row9['comment']),
            }))
            """
        )
        assert out["n"] == 2, "two distinct respondents expected"
        # the tie must resolve to the LAST input row for respondent 9
        assert out["rating9"] == 2.0, "tie on submitted_at must keep last occurrence"
        assert out["comment9"] == "second"

    def test_dedupe_does_not_mutate_input(self):
        """L2: the caller's responses frame must be unchanged after dedupe."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_cols = list(responses.columns)
            before_len = int(len(responses))
            before_hash = pd.util.hash_pandas_object(responses, index=True).sum()
            _ = sc.dedupe_responses(responses)
            after_hash = pd.util.hash_pandas_object(responses, index=True).sum()
            print(json.dumps({
                'cols_same': before_cols == list(responses.columns),
                'len_same': before_len == int(len(responses)),
                'hash_same': bool(before_hash == after_hash),
            }))
            """
        )
        assert out["cols_same"], "dedupe must not change input columns"
        assert out["len_same"], "dedupe must not drop rows from the input"
        assert out["hash_same"], "dedupe must not alter input values"

    # ---- L2: impute ------------------------------------------------------

    def test_impute_rating_uses_global_median(self):
        """L2: spec example [2.0, NaN, 4.0, 6.0] -> gap becomes 4.0 (median)."""
        out = self._run_json(
            """
            responses = pd.DataFrame({
                'respondent_id': [1, 2, 3, 4],
                'submitted_at':  ['2023-01-01','2023-01-02','2023-01-03','2023-01-04'],
                'rating':        [2.0, np.nan, 4.0, 6.0],
                'comment':       ['a','b','c','d'],
            })
            res = sc.impute(responses)
            ratings = [float(x) for x in res['rating'].tolist()]
            print(json.dumps({
                'ratings': ratings,
                'any_na': bool(res['rating'].isna().any()),
            }))
            """
        )
        # median of present values [2,4,6] is 4.0 (a mean would give 4.0 too,
        # so the discriminating example below uses values whose mean != median)
        assert out["ratings"] == [2.0, 4.0, 4.0, 6.0]
        assert not out["any_na"], "impute must leave no missing rating"

    def test_impute_rating_is_median_not_mean(self):
        """L2: skewed ratings -> the gap is the MEDIAN, not the mean."""
        out = self._run_json(
            """
            # present ratings [1, 2, 9] -> median 2.0, mean 4.0; they differ.
            responses = pd.DataFrame({
                'respondent_id': [1, 2, 3, 4],
                'submitted_at':  ['2023-01-01','2023-01-02','2023-01-03','2023-01-04'],
                'rating':        [1.0, 2.0, np.nan, 9.0],
                'comment':       ['a','b','c','d'],
            })
            res = sc.impute(responses)
            filled = float(res['rating'].iloc[2])
            print(json.dumps({'filled': filled}))
            """
        )
        assert out["filled"] == 2.0, (
            "missing rating must be filled with the median (2.0), not the mean (4.0)"
        )

    def test_impute_comment_literal_and_no_na(self):
        """L2: missing comment becomes the literal '(no comment)'; no NaNs left."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = sc.impute(responses)
            # respondent 5 (index 3 in SAMPLE) had a missing comment
            comments = [str(x) for x in res['comment'].tolist()]
            print(json.dumps({
                'comments': comments,
                'comment_na': bool(res['comment'].isna().any()),
                'rating_na': bool(res['rating'].isna().any()),
                'has_placeholder': '(no comment)' in comments,
            }))
            """
        )
        assert out["has_placeholder"], (
            "missing comment must be filled with the literal '(no comment)'"
        )
        assert not out["comment_na"], "impute must leave no missing comment"
        assert not out["rating_na"], "impute must leave no missing rating"

    def test_impute_does_not_mutate_input(self):
        """L2: impute must not mutate its input frame."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_hash = pd.util.hash_pandas_object(responses, index=True).sum()
            rating_na_before = int(responses['rating'].isna().sum())
            comment_na_before = int(responses['comment'].isna().sum())
            _ = sc.impute(responses)
            after_hash = pd.util.hash_pandas_object(responses, index=True).sum()
            print(json.dumps({
                'hash_same': bool(before_hash == after_hash),
                'rating_na_before': rating_na_before,
                'rating_na_after': int(responses['rating'].isna().sum()),
                'comment_na_before': comment_na_before,
                'comment_na_after': int(responses['comment'].isna().sum()),
            }))
            """
        )
        assert out["hash_same"], "impute must not mutate its input"
        assert out["rating_na_after"] == out["rating_na_before"] == 1, (
            "the input's missing rating must remain after calling impute"
        )
        assert out["comment_na_after"] == out["comment_na_before"] == 1, (
            "the input's missing comment must remain after calling impute"
        )

    # ---- L2: normalize_types --------------------------------------------

    def test_normalize_types_produces_expected_dtypes(self):
        """L2: respondent_id int, submitted_at datetime, comment categorical, rating float."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = sc.normalize_types(responses)
            import pandas.api.types as pat
            print(json.dumps({
                'id_int': bool(pat.is_integer_dtype(res['respondent_id'])),
                'dt': bool(pat.is_datetime64_any_dtype(res['submitted_at'])),
                'cat': bool(isinstance(res['comment'].dtype,
                                       pd.CategoricalDtype)),
                'rating_float': bool(pat.is_float_dtype(res['rating'])),
            }))
            """
        )
        assert out["id_int"], "respondent_id must be an integer dtype"
        assert out["dt"], "submitted_at must be a datetime dtype, not object/string"
        assert out["cat"], "comment must be a categorical dtype"
        assert out["rating_float"], "rating must be a float dtype"

    def test_normalize_types_preserves_values(self):
        """L2: only the representation changes; underlying values are preserved."""
        out = self._run_json(
            """
            responses = pd.DataFrame({
                'respondent_id': [7, 3],
                'submitted_at':  ['2023-02-01', '2023-01-05'],
                'rating':        [5.0, 2.5],
                'comment':       ['great', 'meh'],
            })
            res = sc.normalize_types(responses)
            print(json.dumps({
                'ids': [int(x) for x in res['respondent_id'].tolist()],
                'dates': [pd.Timestamp(x).strftime('%Y-%m-%d')
                          for x in res['submitted_at'].tolist()],
                'ratings': [float(x) for x in res['rating'].tolist()],
                'comments': [str(x) for x in res['comment'].tolist()],
            }))
            """
        )
        assert out["ids"] == [7, 3]
        assert out["dates"] == ["2023-02-01", "2023-01-05"], (
            "submitted_at values must be preserved through datetime conversion"
        )
        assert out["ratings"] == [5.0, 2.5]
        assert out["comments"] == ["great", "meh"], (
            "comment values must be preserved through categorical conversion"
        )

    def test_normalize_types_does_not_mutate_input(self):
        """L2: normalize_types must not mutate its input frame's dtypes/values."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_id_dtype = str(responses['respondent_id'].dtype)
            before_dt_dtype = str(responses['submitted_at'].dtype)
            before_comment_dtype = str(responses['comment'].dtype)
            _ = sc.normalize_types(responses)
            print(json.dumps({
                'id_same': before_id_dtype == str(responses['respondent_id'].dtype),
                'dt_same': before_dt_dtype == str(responses['submitted_at'].dtype),
                'comment_same':
                    before_comment_dtype == str(responses['comment'].dtype),
                'dt_still_object':
                    str(responses['submitted_at'].dtype) == 'object',
            }))
            """
        )
        assert out["id_same"], "normalize_types must not change input id dtype"
        assert out["comment_same"], (
            "normalize_types must not change input comment dtype"
        )
        assert out["dt_still_object"], (
            "the input's submitted_at must remain an object/string dtype"
        )

    # ---- L2: end-to-end native command ----------------------------------

    def test_agent_native_pytest_passes(self):
        """L2: the spec's native command on the agent's own test suite passes."""
        test_file = os.path.join(self.REPO_DIR, self.TEST_REL)
        assert os.path.isfile(test_file), "agent test file missing"
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            ["python", "-m", "pytest", "scripts/tests/test_survey_clean.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native command `python -m pytest scripts/tests/test_survey_clean.py "
            "-q` failed.\nSTDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr
        )
        # guard against a vacuous (zero-collected) pass
        assert "no tests ran" not in proc.stdout.lower(), (
            "agent test suite collected no tests"
        )
