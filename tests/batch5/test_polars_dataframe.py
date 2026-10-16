"""Tests for the `polars-dataframe` skill task (variant ext5): a Survey Response
Reshaping Module.

Verifies the deliverable `examples/survey_reshape/reshape.py` inside the polars
repository (REPO_DIR=/workspace/polars). The three public functions
(`to_wide`, `to_long`, `answered_counts`) are exercised dynamically: a focused
driver script is written into REPO_DIR, imports the agent's module + polars,
runs it on controlled in-memory DataFrames, and emits JSON that is
deep-validated here.

L1 cases check the deliverable files exist and the functions are importable.
L2 cases drive real polars behavior so that a naive or hardcoded solution
fails:
  * `to_wide` -> one alphabetically ordered column per distinct question,
    null for unanswered (respondent, question) pairs, respondents sorted asc.
  * `to_long` -> unpivots every question column to (question, score) rows,
    DROPS null-score rows, sorted by respondent then question.
  * round trip `to_long(to_wide(long))` recovers the original record SET.
  * `answered_counts` -> per-respondent non-null count + mean score.
  * empty-input shape/dtype contracts for all three functions.

The variant's native acceptance command is also driven directly:
    python -m pytest examples/survey_reshape/test_reshape.py -q
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/polars"
PKG_DIR = os.path.join(REPO_DIR, "examples", "survey_reshape")
RESHAPE_PY = os.path.join(PKG_DIR, "reshape.py")


# ---------------------------------------------------------------------------
# Driver harness: run a python snippet from REPO_DIR with the agent's module
# importable, capturing a single JSON object printed on the LAST stdout line.
# ---------------------------------------------------------------------------

_PREAMBLE = textwrap.dedent(
    """
    import json, sys, os
    import polars as pl
    sys.path.insert(0, os.path.join(os.getcwd(), "examples"))
    from survey_reshape import reshape as R

    def _df_to_records(df):
        # ordered column names + python-native rows + dtypes
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
    driver_path = os.path.join(REPO_DIR, "_skilltest_driver_ext5.py")
    with open(driver_path, "w") as fh:
        fh.write(script)
    try:
        proc = subprocess.run(
            ["python", "_skilltest_driver_ext5.py"],
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


# Shared fixture: a long survey frame with a deliberately incomplete grid.
# Respondents r1, r2, r3 over questions q1, q2, q3; not every pair present.
#   r1: q1=5, q2=3            (no q3)
#   r2: q1=1, q3=4            (no q2)
#   r3: q2=2                  (only q2)
# Distinct questions: q1, q2, q3  -> wide must have all three columns.
_BUILD_LONG = """
    long = pl.DataFrame(
        {
            "respondent": ["r1", "r1", "r2", "r2", "r3"],
            "question": ["q1", "q2", "q1", "q3", "q2"],
            "score": [5, 3, 1, 4, 2],
        },
        schema={"respondent": pl.String, "question": pl.String, "score": pl.Int64},
    )
"""


class TestPolarsDataframe:
    REPO_DIR = "/workspace/polars"

    # ------------------------------------------------------------------ L1

    def test_package_marker_exists(self):
        """L1: the package marker __init__.py is present."""
        assert os.path.isfile(
            os.path.join(PKG_DIR, "__init__.py")
        ), "examples/survey_reshape/__init__.py missing"

    def test_reshape_module_exists(self):
        """L1: reshape.py deliverable exists and is non-trivial."""
        assert os.path.isfile(RESHAPE_PY), "examples/survey_reshape/reshape.py missing"
        assert os.path.getsize(RESHAPE_PY) > 200, "reshape.py is suspiciously small"

    def test_public_functions_importable(self):
        """L1: to_wide, to_long, answered_counts are importable and callable."""
        result = _run_driver(
            """
            names = ["to_wide", "to_long", "answered_counts"]
            out = {n: callable(getattr(R, n, None)) for n in names}
            print(json.dumps(out))
            """
        )
        for name, ok in result.items():
            assert ok, "%s missing or not callable in reshape.py" % name

    # ------------------------------------------------------------------ L2

    def test_to_wide_columns_alphabetical_and_respondent_sorted(self):
        """L2: to_wide first col is respondent, then every distinct question alphabetically;
        respondents sorted ascending."""
        result = _run_driver(
            _BUILD_LONG
            + """
            df = R.to_wide(long)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        assert cols[0] == "respondent", "first column must be respondent, got %s" % cols
        q_cols = cols[1:]
        assert q_cols == sorted(q_cols), "question columns must be alphabetical: %s" % q_cols
        assert q_cols == ["q1", "q2", "q3"], (
            "must include every distinct question as a column: %s" % q_cols
        )
        resp = [r["respondent"] for r in result["rows"]]
        assert resp == ["r1", "r2", "r3"], "respondents must be sorted ascending: %s" % resp
        # respondent must remain String, score columns Int64
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["respondent"].lower().startswith("str"), dtype_map
        for q in ("q1", "q2", "q3"):
            assert dtype_map[q] == "Int64", "score column %s dtype %s" % (q, dtype_map[q])

    def test_to_wide_null_for_unanswered_pairs(self):
        """L2: a (respondent, question) pair absent from the long input is null in wide."""
        result = _run_driver(
            _BUILD_LONG
            + """
            df = R.to_wide(long)
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_resp = {r["respondent"]: r for r in result["rows"]}
        # r1: q1=5, q2=3, q3 absent -> null
        assert by_resp["r1"]["q1"] == 5
        assert by_resp["r1"]["q2"] == 3
        assert by_resp["r1"]["q3"] is None, "unanswered pair (r1,q3) must be null"
        # r2: q1=1, q2 absent -> null, q3=4
        assert by_resp["r2"]["q1"] == 1
        assert by_resp["r2"]["q2"] is None, "unanswered pair (r2,q2) must be null"
        assert by_resp["r2"]["q3"] == 4
        # r3: only q2=2 -> q1 and q3 null
        assert by_resp["r3"]["q1"] is None, "unanswered pair (r3,q1) must be null"
        assert by_resp["r3"]["q2"] == 2
        assert by_resp["r3"]["q3"] is None, "unanswered pair (r3,q3) must be null"

    def test_to_wide_single_answer_respondent(self):
        """L2: a respondent who answered only one question gets that score and null elsewhere."""
        result = _run_driver(
            """
            long = pl.DataFrame(
                {
                    "respondent": ["solo", "other", "other"],
                    "question": ["q1", "q1", "q2"],
                    "score": [9, 1, 2],
                },
                schema={"respondent": pl.String, "question": pl.String, "score": pl.Int64},
            )
            df = R.to_wide(long)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        assert cols == ["respondent", "q1", "q2"], "cols: %s" % cols
        by_resp = {r["respondent"]: r for r in result["rows"]}
        assert by_resp["solo"]["q1"] == 9
        assert by_resp["solo"]["q2"] is None, "solo respondent's unanswered q2 must be null"

    def test_to_long_columns_order_and_drops_nulls(self):
        """L2: to_long has exact column order, drops null-score rows, sorted resp then question."""
        result = _run_driver(
            _BUILD_LONG
            + """
            wide = R.to_wide(long)
            df = R.to_long(wide)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["respondent", "question", "score"], (
            "to_long column order must be exactly respondent, question, score: %s"
            % result["columns"]
        )
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["respondent"].lower().startswith("str")
        assert dtype_map["question"].lower().startswith("str")
        assert dtype_map["score"] == "Int64", "score dtype: %s" % dtype_map["score"]
        rows = [(r["respondent"], r["question"], r["score"]) for r in result["rows"]]
        # No null scores survive the unpivot.
        assert all(s is not None for (_, _, s) in rows), "null-score rows must be dropped: %s" % rows
        # Exactly the originally-present pairs remain (5 of them).
        assert len(rows) == 5, "expected 5 non-null rows, got %d: %s" % (len(rows), rows)
        # Sorted by respondent asc, then question asc.
        assert rows == sorted(rows, key=lambda t: (t[0], t[1])), (
            "to_long must be sorted by respondent then question: %s" % rows
        )

    def test_round_trip_recovers_original_set(self):
        """L2: to_long(to_wide(long)) reproduces the original (respondent,question,score) SET."""
        result = _run_driver(
            _BUILD_LONG
            + """
            back = R.to_long(R.to_wide(long))
            out = {
                "orig": sorted(long.rows()),
                "round": sorted(back.select(["respondent","question","score"]).rows()),
            }
            print(json.dumps(out))
            """
        )
        orig = [tuple(x) for x in result["orig"]]
        rnd = [tuple(x) for x in result["round"]]
        assert rnd == orig, (
            "round trip must recover original records as a set\norig=%s\nround=%s"
            % (orig, rnd)
        )

    def test_to_long_does_not_invent_rows(self):
        """L2: to_long must not emit a row for a wide null cell (naive melt-without-drop fails)."""
        result = _run_driver(
            """
            # Build wide directly with an explicit null cell to bypass to_wide.
            wide = pl.DataFrame(
                {
                    "respondent": ["a", "b"],
                    "q1": [10, None],
                    "q2": [None, 20],
                },
                schema={"respondent": pl.String, "q1": pl.Int64, "q2": pl.Int64},
            )
            df = R.to_long(wide)
            print(json.dumps(_df_to_records(df)))
            """
        )
        rows = [(r["respondent"], r["question"], r["score"]) for r in result["rows"]]
        assert sorted(rows) == [("a", "q1", 10), ("b", "q2", 20)], (
            "to_long must drop the two null cells, got: %s" % rows
        )

    def test_answered_counts_columns_and_values(self):
        """L2: answered_counts has exact columns and counts non-null answers + mean score."""
        result = _run_driver(
            _BUILD_LONG
            + """
            df = R.answered_counts(long)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["respondent", "answered", "avg_score"], (
            "answered_counts column order must be respondent, answered, avg_score: %s"
            % result["columns"]
        )
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["respondent"].lower().startswith("str")
        assert dtype_map["answered"] in ("Int64", "UInt32"), (
            "answered dtype must be Int64/UInt32, got %s" % dtype_map["answered"]
        )
        assert dtype_map["avg_score"] == "Float64", "avg_score dtype: %s" % dtype_map["avg_score"]
        resp = [r["respondent"] for r in result["rows"]]
        assert resp == ["r1", "r2", "r3"], "must be sorted by respondent asc: %s" % resp
        by_resp = {r["respondent"]: r for r in result["rows"]}
        # r1 answered q1=5, q2=3 -> 2 answered, avg 4.0
        assert by_resp["r1"]["answered"] == 2
        assert by_resp["r1"]["avg_score"] == pytest.approx(4.0)
        # r2 answered q1=1, q3=4 -> 2 answered, avg 2.5
        assert by_resp["r2"]["answered"] == 2
        assert by_resp["r2"]["avg_score"] == pytest.approx(2.5)
        # r3 answered q2=2 -> 1 answered, avg 2.0
        assert by_resp["r3"]["answered"] == 1
        assert by_resp["r3"]["avg_score"] == pytest.approx(2.0)

    def test_answered_counts_ignores_null_when_fed_wide_derived_long(self):
        """L2: counts reflect only truly-answered questions, not the full question grid."""
        result = _run_driver(
            """
            long = pl.DataFrame(
                {
                    "respondent": ["x", "x", "x", "y"],
                    "question": ["q1", "q2", "q3", "q1"],
                    "score": [2, 4, 6, 100],
                },
                schema={"respondent": pl.String, "question": pl.String, "score": pl.Int64},
            )
            df = R.answered_counts(long)
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_resp = {r["respondent"]: r for r in result["rows"]}
        # x answered 3 of 3 -> avg 4.0; y answered only q1 -> 1 answered, avg 100.0
        assert by_resp["x"]["answered"] == 3
        assert by_resp["x"]["avg_score"] == pytest.approx(4.0)
        assert by_resp["y"]["answered"] == 1, (
            "y answered only one question; a naive count of all questions would fail"
        )
        assert by_resp["y"]["avg_score"] == pytest.approx(100.0)

    def test_to_wide_requires_full_question_universe(self):
        """L2: every question seen anywhere yields a column even if only one respondent used it."""
        result = _run_driver(
            """
            long = pl.DataFrame(
                {
                    "respondent": ["a", "a", "b"],
                    "question": ["common", "rare", "common"],
                    "score": [1, 2, 3],
                },
                schema={"respondent": pl.String, "question": pl.String, "score": pl.Int64},
            )
            df = R.to_wide(long)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        assert cols == ["respondent", "common", "rare"], "cols: %s" % cols
        by_resp = {r["respondent"]: r for r in result["rows"]}
        assert by_resp["b"]["rare"] is None, "b never answered 'rare' -> must be null"
        assert by_resp["a"]["rare"] == 2

    def test_empty_input_shapes_all_functions(self):
        """L2: every function returns a correctly-shaped/typed empty DataFrame on empty input."""
        result = _run_driver(
            """
            long = pl.DataFrame(
                schema={"respondent": pl.String, "question": pl.String, "score": pl.Int64},
            )
            wide = pl.DataFrame(schema={"respondent": pl.String})
            out = {}
            tw = R.to_wide(long)
            out["to_wide"] = {"cols": list(tw.columns), "h": tw.height,
                              "dtypes": [str(tw.schema[c]) for c in tw.columns]}
            tl = R.to_long(wide)
            out["to_long"] = {"cols": list(tl.columns), "h": tl.height,
                              "dtypes": [str(tl.schema[c]) for c in tl.columns]}
            ac = R.answered_counts(long)
            out["answered_counts"] = {"cols": list(ac.columns), "h": ac.height,
                                      "dtypes": [str(ac.schema[c]) for c in ac.columns]}
            print(json.dumps(out))
            """
        )
        tw = result["to_wide"]
        assert tw["h"] == 0, "to_wide must be empty on empty input"
        assert tw["cols"] == ["respondent"], (
            "to_wide on empty long must keep the respondent column only: %s" % tw["cols"]
        )
        tl = result["to_long"]
        assert tl["h"] == 0, "to_long must be empty on empty input"
        assert tl["cols"] == ["respondent", "question", "score"], (
            "to_long empty cols/order: %s" % tl["cols"]
        )
        assert dict(zip(tl["cols"], tl["dtypes"]))["score"] == "Int64", tl["dtypes"]
        ac = result["answered_counts"]
        assert ac["h"] == 0, "answered_counts must be empty on empty input"
        assert ac["cols"] == ["respondent", "answered", "avg_score"], (
            "answered_counts empty cols/order: %s" % ac["cols"]
        )
        ac_dtypes = dict(zip(ac["cols"], ac["dtypes"]))
        assert ac_dtypes["avg_score"] == "Float64", ac_dtypes

    def test_native_pytest_suite_passes(self):
        """L2: the agent's own pytest suite for the module passes (native acceptance command)."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "examples/survey_reshape/test_reshape.py", "-q"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=420,
        )
        assert proc.returncode == 0, (
            "native pytest suite failed (rc=%s)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:])
        )
