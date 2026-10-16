"""Tests for the `polars-dataframe` skill task (variant ext8): a Multi-Source Feed Merger.

Verifies the deliverable `examples/feed_merge/merge.py` inside the polars
repository (REPO_DIR=/workspace/polars). The three public functions
(`union_feeds`, `tag_source`, `dedupe_by_priority`) union partner product feeds
whose schemas overlap but differ, with source-precedence semantics.

Verification strategy: a focused driver script is written into REPO_DIR that
imports the agent's module + the repo's polars, builds controlled in-memory
`pl.DataFrame` feeds, runs the public functions, and prints a single JSON object
that is deep-validated here. We assert concrete column union/order, row order,
null-fill placement, zero-based `source_idx` tagging, and priority-based
deduplication (cross-feed earliest-feed wins, intra-feed first-occurrence wins,
sorted by sku). The empty-feed-list zero-column shape is checked too.

L1 cases check the deliverable files exist and the public functions are
importable/callable. L2 cases drive real polars behavior so that a naive or
hardcoded implementation (e.g. plain vstack that errors on mismatched schemas,
ignoring precedence, dropping nulls, or forgetting source_idx) fails. The
acceptance command `python -m pytest examples/feed_merge/test_merge.py -q` is
driven as the final L2 case using the repo's real toolchain.
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/polars"
PKG_DIR = os.path.join(REPO_DIR, "examples", "feed_merge")
MERGE_PY = os.path.join(PKG_DIR, "merge.py")
NATIVE_TEST_PY = os.path.join(PKG_DIR, "test_merge.py")


# ---------------------------------------------------------------------------
# Driver harness: run a python snippet from REPO_DIR with the agent's module
# importable, capturing a single JSON object printed on the LAST stdout line.
# ---------------------------------------------------------------------------

_PREAMBLE = textwrap.dedent(
    """
    import json, sys, os
    import polars as pl
    sys.path.insert(0, os.path.join(os.getcwd(), "examples"))
    from feed_merge import merge as M

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
        return {"columns": cols, "dtypes": dtypes, "rows": out, "height": df.height}
    """
)


def _run_driver(body, timeout=180):
    """Write `body` (which must `print(json.dumps(result))`) and run it.

    Returns the parsed JSON from the last non-empty stdout line.
    """
    script = _PREAMBLE + "\n" + textwrap.dedent(body)
    driver_path = os.path.join(REPO_DIR, "_skilltest_driver.py")
    with open(driver_path, "w") as fh:
        fh.write(script)
    try:
        proc = subprocess.run(
            ["python", "_skilltest_driver.py"],
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


# Shared feed builders embedded inside drivers -----------------------------
#
# Feed A: columns sku, price, color   (rows a1, a2, a3 with a duplicate sku S2)
# Feed B: columns sku, price, weight  (rows b1, b2; b1 shares sku S2 with A)
#
# These exercise: differing extra columns (color vs weight), cross-feed
# duplicate sku (S2 in both A and B), and a clean union.
_BUILD_AB = """
    A = pl.DataFrame(
        {
            "sku": ["S2", "S1", "S2"],
            "price": [10.0, 20.0, 99.0],
            "color": ["red", "blue", "green"],
        },
        schema={"sku": pl.String, "price": pl.Float64, "color": pl.String},
    )
    B = pl.DataFrame(
        {
            "sku": ["S2", "S3"],
            "price": [55.0, 77.0],
            "weight": [1.5, 2.5],
        },
        schema={"sku": pl.String, "price": pl.Float64, "weight": pl.Float64},
    )
"""


class TestPolarsDataframe:
    REPO_DIR = "/workspace/polars"

    # ------------------------------------------------------------------ L1

    def test_package_marker_exists(self):
        """L1: the package marker __init__.py is present."""
        assert os.path.isfile(
            os.path.join(PKG_DIR, "__init__.py")
        ), "examples/feed_merge/__init__.py missing"

    def test_merge_module_exists(self):
        """L1: merge.py deliverable exists and is non-trivial."""
        assert os.path.isfile(MERGE_PY), "examples/feed_merge/merge.py missing"
        assert os.path.getsize(MERGE_PY) > 200, "merge.py is suspiciously small"

    def test_native_test_file_exists(self):
        """L1: the agent's own pytest suite file exists."""
        assert os.path.isfile(
            NATIVE_TEST_PY
        ), "examples/feed_merge/test_merge.py missing"

    def test_public_functions_importable(self):
        """L1: the three public functions are importable and callable."""
        result = _run_driver(
            """
            names = ["union_feeds", "tag_source", "dedupe_by_priority"]
            out = {n: callable(getattr(M, n, None)) for n in names}
            print(json.dumps(out))
            """
        )
        for name, ok in result.items():
            assert ok, "%s missing or not callable in merge.py" % name

    # ------------------------------------------------------------------ L2

    def test_union_columns_union_and_order(self):
        """L2: union_feeds yields the full column union in the specified order.

        Common columns (sku, price) first in first-seen order, then remaining
        first-seen columns across the feed list (color from A, then weight
        from B).
        """
        result = _run_driver(
            _BUILD_AB
            + """
            df = M.union_feeds([A, B])
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["sku", "price", "color", "weight"], (
            "unexpected column union/order: %s" % result["columns"]
        )

    def test_union_row_order_and_null_fills(self):
        """L2: rows are feeds concatenated in list order with null fills for absent cols."""
        result = _run_driver(
            _BUILD_AB
            + """
            df = M.union_feeds([A, B])
            print(json.dumps(_df_to_records(df)))
            """
        )
        rows = result["rows"]
        # A has 3 rows then B has 2 rows, internal order preserved.
        assert [r["sku"] for r in rows] == ["S2", "S1", "S2", "S2", "S3"], (
            "row order must be A's rows then B's rows, internal order kept: %s"
            % [r["sku"] for r in rows]
        )
        # A's rows: weight must be null (A lacks weight); color populated.
        for r in rows[:3]:
            assert r["weight"] is None, "A rows must be null under weight: %r" % r
        assert [r["color"] for r in rows[:3]] == ["red", "blue", "green"]
        # B's rows: color must be null (B lacks color); weight populated.
        for r in rows[3:]:
            assert r["color"] is None, "B rows must be null under color: %r" % r
        assert [r["weight"] for r in rows[3:]] == [1.5, 2.5]
        # prices carried through verbatim
        assert [r["price"] for r in rows] == [10.0, 20.0, 99.0, 55.0, 77.0]

    def test_union_empty_list_zero_columns(self):
        """L2: an empty feed list returns a zero-column empty DataFrame."""
        result = _run_driver(
            """
            df = M.union_feeds([])
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["height"] == 0, "empty feed list must yield 0 rows"
        assert result["columns"] == [], (
            "empty feed list must yield ZERO columns, got: %s" % result["columns"]
        )

    def test_union_single_feed_identity(self):
        """L2: a single feed unions to its own columns/rows unchanged in order."""
        result = _run_driver(
            _BUILD_AB
            + """
            df = M.union_feeds([A])
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["sku", "price", "color"], (
            "single feed must keep its own columns: %s" % result["columns"]
        )
        assert [r["sku"] for r in result["rows"]] == ["S2", "S1", "S2"]
        assert result["height"] == 3

    def test_tag_source_leading_index_column(self):
        """L2: tag_source prepends a leading Int64 source_idx column."""
        result = _run_driver(
            _BUILD_AB
            + """
            df = M.tag_source([A, B])
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        assert cols[0] == "source_idx", (
            "source_idx must be the leading column, got: %s" % cols
        )
        assert cols == ["source_idx", "sku", "price", "color", "weight"], (
            "tag_source columns wrong: %s" % cols
        )
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["source_idx"].lower().startswith("int64"), (
            "source_idx must be Int64, got %s" % dtype_map["source_idx"]
        )

    def test_tag_source_zero_based_indices(self):
        """L2: source_idx is the zero-based feed index for each row, in feed order."""
        result = _run_driver(
            _BUILD_AB
            + """
            df = M.tag_source([A, B])
            print(json.dumps(_df_to_records(df)))
            """
        )
        idxs = [r["source_idx"] for r in result["rows"]]
        # A contributes 3 rows (idx 0), B contributes 2 rows (idx 1)
        assert idxs == [0, 0, 0, 1, 1], (
            "source_idx must be 0 for feed A rows, 1 for feed B rows: %s" % idxs
        )
        # underlying union/null semantics preserved
        rows = result["rows"]
        assert [r["sku"] for r in rows] == ["S2", "S1", "S2", "S2", "S3"]
        for r in rows[:3]:
            assert r["weight"] is None
        for r in rows[3:]:
            assert r["color"] is None

    def test_tag_source_three_feeds_distinct_indices(self):
        """L2: with three feeds, source_idx spans 0,1,2 matching contribution counts."""
        result = _run_driver(
            """
            A = pl.DataFrame({"sku": ["x"], "price": [1.0]},
                             schema={"sku": pl.String, "price": pl.Float64})
            B = pl.DataFrame({"sku": ["y", "z"], "price": [2.0, 3.0]},
                             schema={"sku": pl.String, "price": pl.Float64})
            C = pl.DataFrame({"sku": ["w"], "price": [4.0]},
                             schema={"sku": pl.String, "price": pl.Float64})
            df = M.tag_source([A, B, C])
            print(json.dumps(_df_to_records(df)))
            """
        )
        idxs = [r["source_idx"] for r in result["rows"]]
        assert idxs == [0, 1, 1, 2], "three-feed source_idx wrong: %s" % idxs
        assert [r["sku"] for r in result["rows"]] == ["x", "y", "z", "w"]

    def test_dedupe_cross_feed_earliest_wins(self):
        """L2: a sku in two feeds survives once, carrying the EARLIER feed's values.

        S2 appears in A (earlier) and B; the kept row must carry A's price (10.0)
        and A's color (red) with weight null, never B's price (55.0).
        """
        result = _run_driver(
            _BUILD_AB
            + """
            df = M.dedupe_by_priority([A, B])
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        assert "source_idx" not in cols, "dedupe output must NOT have source_idx"
        assert cols == ["sku", "price", "color", "weight"], (
            "dedupe columns must be the union: %s" % cols
        )
        by_sku = {r["sku"]: r for r in result["rows"]}
        # S2 resolved to A's first occurrence (price 10.0, color red)
        assert "S2" in by_sku
        assert by_sku["S2"]["price"] == pytest.approx(10.0), (
            "S2 must keep earliest feed (A) value, not B's: %r" % by_sku["S2"]
        )
        assert by_sku["S2"]["color"] == "red"
        assert by_sku["S2"]["weight"] is None, (
            "S2's kept row is from A which lacks weight -> null"
        )

    def test_dedupe_one_row_per_sku_sorted(self):
        """L2: at most one row per sku, output sorted by sku ascending."""
        result = _run_driver(
            _BUILD_AB
            + """
            df = M.dedupe_by_priority([A, B])
            print(json.dumps(_df_to_records(df)))
            """
        )
        skus = [r["sku"] for r in result["rows"]]
        # distinct skus across A(S2,S1,S2) + B(S2,S3) = {S1,S2,S3}
        assert skus == ["S1", "S2", "S3"], (
            "dedupe must keep one row per sku, sorted asc: %s" % skus
        )
        assert len(skus) == len(set(skus)), "skus must be unique after dedupe"
        by_sku = {r["sku"]: r for r in result["rows"]}
        # S1 only in A; S3 only in B
        assert by_sku["S1"]["price"] == pytest.approx(20.0)
        assert by_sku["S3"]["price"] == pytest.approx(77.0)
        assert by_sku["S3"]["weight"] == pytest.approx(2.5)
        assert by_sku["S3"]["color"] is None

    def test_dedupe_intra_feed_first_occurrence(self):
        """L2: a sku duplicated within one feed keeps that feed's FIRST occurrence."""
        result = _run_driver(
            """
            A = pl.DataFrame(
                {
                    "sku": ["D", "D", "E"],
                    "price": [1.0, 999.0, 2.0],
                    "color": ["first", "second", "ok"],
                },
                schema={"sku": pl.String, "price": pl.Float64, "color": pl.String},
            )
            df = M.dedupe_by_priority([A])
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_sku = {r["sku"]: r for r in result["rows"]}
        assert [r["sku"] for r in result["rows"]] == ["D", "E"], (
            "must be sorted unique: %s" % [r["sku"] for r in result["rows"]]
        )
        # D's first occurrence (price 1.0, color "first") wins over the later 999.0
        assert by_sku["D"]["price"] == pytest.approx(1.0), (
            "intra-feed dup must keep FIRST occurrence, not second: %r" % by_sku["D"]
        )
        assert by_sku["D"]["color"] == "first"

    def test_dedupe_priority_then_first_occurrence_combined(self):
        """L2: cross-feed precedence and intra-feed first-occurrence resolve together."""
        result = _run_driver(
            """
            A = pl.DataFrame(
                {
                    "sku": ["P", "Q", "P"],
                    "price": [10.0, 11.0, 88.0],
                    "color": ["a1", "a2", "a3"],
                },
                schema={"sku": pl.String, "price": pl.Float64, "color": pl.String},
            )
            B = pl.DataFrame(
                {
                    "sku": ["Q", "R"],
                    "price": [200.0, 12.0],
                    "weight": [9.0, 8.0],
                },
                schema={"sku": pl.String, "price": pl.Float64, "weight": pl.Float64},
            )
            df = M.dedupe_by_priority([A, B])
            print(json.dumps(_df_to_records(df)))
            """
        )
        skus = [r["sku"] for r in result["rows"]]
        assert skus == ["P", "Q", "R"], "sorted unique skus: %s" % skus
        by_sku = {r["sku"]: r for r in result["rows"]}
        # P: only in A, duplicated -> keep first (price 10.0)
        assert by_sku["P"]["price"] == pytest.approx(10.0)
        assert by_sku["P"]["color"] == "a1"
        # Q: in A and B -> A earlier wins (price 11.0, color a2, weight null)
        assert by_sku["Q"]["price"] == pytest.approx(11.0), (
            "Q must come from earlier feed A, not B(200.0): %r" % by_sku["Q"]
        )
        assert by_sku["Q"]["color"] == "a2"
        assert by_sku["Q"]["weight"] is None
        # R: only in B
        assert by_sku["R"]["price"] == pytest.approx(12.0)
        assert by_sku["R"]["weight"] == pytest.approx(8.0)
        assert by_sku["R"]["color"] is None

    def test_return_types_are_polars_frames(self):
        """L2: all three functions return polars.DataFrame instances."""
        result = _run_driver(
            _BUILD_AB
            + """
            out = {
                "union": isinstance(M.union_feeds([A, B]), pl.DataFrame),
                "tag": isinstance(M.tag_source([A, B]), pl.DataFrame),
                "dedupe": isinstance(M.dedupe_by_priority([A, B]), pl.DataFrame),
                "union_empty": isinstance(M.union_feeds([]), pl.DataFrame),
            }
            print(json.dumps(out))
            """
        )
        for k, ok in result.items():
            assert ok, "%s did not return a polars.DataFrame" % k

    def test_native_pytest_suite_passes(self):
        """L2: the agent's own pytest suite passes (the doc's acceptance command)."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "examples/feed_merge/test_merge.py", "-q"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=420,
        )
        assert proc.returncode == 0, (
            "native pytest suite failed (rc=%s)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:])
        )
