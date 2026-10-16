"""Tests for the `polars-dataframe` skill task (variant ext7): a Tag and Text
Normalization Module.

Verifies the deliverable `examples/text_normalize/normalize.py` inside the
polars repository (REPO_DIR=/workspace/polars). The three public functions
(`clean_titles`, `explode_tags`, `tag_frequencies`) are exercised dynamically:
a focused driver script is written into REPO_DIR, imports the agent's module
plus polars, runs it on controlled in-memory DataFrames, and emits JSON that is
deep-validated here.

L1 cases check the deliverable files exist and the public functions are
importable/callable. L2 cases drive real polars behavior:
  - clean_titles: trim+lowercase, null propagation through title_clean/title_len,
    character length, preservation of original columns, sort by item_id.
  - explode_tags: comma split, per-tag trim+lowercase, dropping of empty tags
    (consecutive/leading/trailing commas, null/empty tags), zero rows for items
    with no usable tags, exact (item_id, tag) column order and sort.
  - tag_frequencies: distinct-item counting (dedup of a tag repeated within one
    item), and sort by item_count desc then tag asc.
  - empty-input shapes for all three functions.

These cases are designed so a naive/stub implementation (e.g. one that does not
lowercase/trim, keeps empty tags, double-counts a repeated tag, ignores nulls,
or hardcodes outputs) fails. The variant's native acceptance command
(`python -m pytest examples/text_normalize/test_normalize.py -q`) is also driven
as an independent L2 check.
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/polars"
PKG_DIR = os.path.join(REPO_DIR, "examples", "text_normalize")
NORMALIZE_PY = os.path.join(PKG_DIR, "normalize.py")


# ---------------------------------------------------------------------------
# Driver harness: run a python snippet from REPO_DIR with the agent's module
# importable, capturing a single JSON object printed on the LAST stdout line.
# ---------------------------------------------------------------------------

_PREAMBLE = textwrap.dedent(
    """
    import json, sys, os
    import polars as pl
    sys.path.insert(0, os.path.join(os.getcwd(), "examples"))
    from text_normalize import normalize as N

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
        return {"columns": cols, "dtypes": dtypes, "rows": out}
    """
)


def _run_driver(body, timeout=180):
    """Write `body` (which must `print(json.dumps(result))`) and run it.

    Returns the parsed JSON from the last non-empty stdout line.
    """
    script = _PREAMBLE + "\n" + textwrap.dedent(body)
    driver_path = os.path.join(REPO_DIR, "_skilltest_driver_ext7.py")
    with open(driver_path, "w") as fh:
        fh.write(script)
    try:
        proc = subprocess.run(
            ["python", "_skilltest_driver_ext7.py"],
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


# Shared fixture: a small item catalog exercising whitespace, case, nulls,
# empties, consecutive commas, leading/trailing commas, and intra-item dups.
_BUILD_ITEMS = """
    items = pl.DataFrame(
        {
            "item_id": [3, 1, 2, 4, 5],
            "title": ["  Red Shoe  ", "BLUE Hat", None, "  ", "Green Bag"],
            "tags": ["red, Sale ,new", "a,,b,", None, "", "red,red, BLUE "],
        },
        schema={
            "item_id": pl.Int64,
            "title": pl.String,
            "tags": pl.String,
        },
    )
"""


class TestPolarsDataframe:
    REPO_DIR = "/workspace/polars"

    # ------------------------------------------------------------------ L1

    def test_package_marker_exists(self):
        """L1: the package marker __init__.py is present."""
        assert os.path.isfile(
            os.path.join(PKG_DIR, "__init__.py")
        ), "examples/text_normalize/__init__.py missing"

    def test_normalize_module_exists(self):
        """L1: normalize.py deliverable exists and is non-trivial."""
        assert os.path.isfile(
            NORMALIZE_PY
        ), "examples/text_normalize/normalize.py missing"
        assert os.path.getsize(NORMALIZE_PY) > 200, "normalize.py is suspiciously small"

    def test_public_functions_importable(self):
        """L1: the three public functions are importable and callable."""
        result = _run_driver(
            """
            names = ["clean_titles", "explode_tags", "tag_frequencies"]
            out = {n: callable(getattr(N, n, None)) for n in names}
            print(json.dumps(out))
            """
        )
        for name, ok in result.items():
            assert ok, "%s missing or not callable in normalize.py" % name

    # ------------------------------------------------------------------ L2: clean_titles

    def test_clean_titles_columns_preserved_and_sorted(self):
        """L2: clean_titles keeps all original columns, adds two, sorts by item_id asc."""
        result = _run_driver(
            _BUILD_ITEMS
            + """
            df = N.clean_titles(items)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        cols = result["columns"]
        for original in ["item_id", "title", "tags"]:
            assert original in cols, "original column %s dropped" % original
        assert "title_clean" in cols, "title_clean column missing"
        assert "title_len" in cols, "title_len column missing"
        ids = [r["item_id"] for r in result["rows"]]
        assert ids == sorted(ids), "rows must be sorted by item_id ascending"
        assert ids == [1, 2, 3, 4, 5]
        # row count preserved (every input row present)
        assert len(result["rows"]) == 5, "clean_titles must return every input row"

    def test_clean_titles_trim_lowercase_and_length(self):
        """L2: title trimmed+lowercased; title_len = char length of cleaned title."""
        result = _run_driver(
            _BUILD_ITEMS
            + """
            df = N.clean_titles(items)
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_id = {r["item_id"]: r for r in result["rows"]}
        # "  Red Shoe  " -> "red shoe" (len 8)
        assert by_id[3]["title_clean"] == "red shoe", (
            "expected 'red shoe', got %r" % by_id[3]["title_clean"]
        )
        assert by_id[3]["title_len"] == 8, (
            "title_len must be char length 8, got %r" % by_id[3]["title_len"]
        )
        # "BLUE Hat" -> "blue hat" (len 8)
        assert by_id[1]["title_clean"] == "blue hat"
        assert by_id[1]["title_len"] == 8
        # "Green Bag" -> "green bag" (len 9)
        assert by_id[5]["title_clean"] == "green bag"
        assert by_id[5]["title_len"] == 9

    def test_clean_titles_null_propagation(self):
        """L2: a null title yields null title_clean AND null title_len."""
        result = _run_driver(
            _BUILD_ITEMS
            + """
            df = N.clean_titles(items)
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_id = {r["item_id"]: r for r in result["rows"]}
        # item 2 has a null title
        assert by_id[2]["title_clean"] is None, (
            "null title must yield null title_clean, got %r" % by_id[2]["title_clean"]
        )
        assert by_id[2]["title_len"] is None, (
            "null title must yield null title_len, got %r" % by_id[2]["title_len"]
        )

    def test_clean_titles_whitespace_only_becomes_empty(self):
        """L2: a whitespace-only title trims to '' (len 0), not null (it was not null)."""
        result = _run_driver(
            _BUILD_ITEMS
            + """
            df = N.clean_titles(items)
            print(json.dumps(_df_to_records(df)))
            """
        )
        by_id = {r["item_id"]: r for r in result["rows"]}
        # item 4 title is "  " -> trimmed "" with length 0 (distinct from null)
        assert by_id[4]["title_clean"] == "", (
            "whitespace-only title must trim to empty string, got %r"
            % by_id[4]["title_clean"]
        )
        assert by_id[4]["title_len"] == 0, (
            "empty cleaned title must have length 0, got %r" % by_id[4]["title_len"]
        )

    def test_clean_titles_dtypes(self):
        """L2: title_clean is String and title_len is Int64."""
        result = _run_driver(
            _BUILD_ITEMS
            + """
            df = N.clean_titles(items)
            print(json.dumps(_df_to_records(df)))
            """
        )
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["title_clean"].lower().startswith("str"), (
            "title_clean must be String, got %s" % dtype_map["title_clean"]
        )
        assert dtype_map["title_len"].lower().startswith("int64"), (
            "title_len must be Int64, got %s" % dtype_map["title_len"]
        )

    # ------------------------------------------------------------------ L2: explode_tags

    def test_explode_tags_columns_and_order(self):
        """L2: explode_tags returns exactly [item_id, tag] in that order."""
        result = _run_driver(
            _BUILD_ITEMS
            + """
            df = N.explode_tags(items)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["item_id", "tag"], (
            "explode_tags columns must be exactly [item_id, tag], got %s"
            % result["columns"]
        )
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["item_id"].lower().startswith("int64")
        assert dtype_map["tag"].lower().startswith("str")

    def test_explode_tags_split_trim_lowercase_and_sort(self):
        """L2: tags split on comma, trimmed+lowercased; sorted by item_id then tag."""
        result = _run_driver(
            _BUILD_ITEMS
            + """
            df = N.explode_tags(items)
            print(json.dumps(_df_to_records(df)))
            """
        )
        rows = [(r["item_id"], r["tag"]) for r in result["rows"]]
        # item 1 tags "red, Sale ,new" -> new, red, sale (sorted, lowercased, trimmed)
        # item 4 tags "a,,b," -> a, b (empties dropped)
        # item 5 tags "red,red, BLUE " -> blue, red, red (trimmed/lowercased)
        # items 2 (null) and 3 (empty "") -> no rows
        expected = [
            (1, "new"),
            (1, "red"),
            (1, "sale"),
            (4, "a"),
            (4, "b"),
            (5, "blue"),
            (5, "red"),
            (5, "red"),
        ]
        assert rows == expected, "explode_tags rows wrong.\n got: %s\nwant: %s" % (
            rows,
            expected,
        )

    def test_explode_tags_drops_empty_and_null_items(self):
        """L2: items with null/empty tags or only-empty pieces emit zero rows."""
        result = _run_driver(
            """
            items = pl.DataFrame(
                {
                    "item_id": [10, 11, 12, 13],
                    "title": ["x", "y", "z", "w"],
                    "tags": [None, "", ",,", " , "],
                },
                schema={"item_id": pl.Int64, "title": pl.String, "tags": pl.String},
            )
            df = N.explode_tags(items)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["rows"] == [], (
            "items with no usable tags must emit zero rows, got %s" % result["rows"]
        )
        # columns still correct even when empty
        assert result["columns"] == ["item_id", "tag"]

    # ------------------------------------------------------------------ L2: tag_frequencies

    def test_tag_frequencies_columns_and_order(self):
        """L2: tag_frequencies returns exactly [tag, item_count] in that order."""
        result = _run_driver(
            _BUILD_ITEMS
            + """
            df = N.tag_frequencies(items)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["tag", "item_count"], (
            "tag_frequencies columns must be [tag, item_count], got %s"
            % result["columns"]
        )

    def test_tag_frequencies_distinct_items_and_sort(self):
        """L2: item_count counts DISTINCT items per tag; intra-item dups count once."""
        result = _run_driver(
            _BUILD_ITEMS
            + """
            df = N.tag_frequencies(items)
            print(json.dumps(_df_to_records(df)))
            """
        )
        freq = {r["tag"]: r["item_count"] for r in result["rows"]}
        # Normalized tags across items:
        #   item1: new, red, sale
        #   item4: a, b
        #   item5: blue, red, red  -> red counted ONCE for item5
        # So red appears in items 1 and 5 -> count 2 (NOT 3 despite the dup).
        assert freq.get("red") == 2, (
            "red must count distinct items (1 and 5) = 2, got %r" % freq.get("red")
        )
        assert freq.get("new") == 1
        assert freq.get("sale") == 1
        assert freq.get("blue") == 1
        assert freq.get("a") == 1
        assert freq.get("b") == 1
        # sort: item_count desc, then tag asc. red(2) first, then alpha among the 1s.
        ordered = [(r["tag"], r["item_count"]) for r in result["rows"]]
        assert ordered[0] == ("red", 2), "highest count tag must come first: %s" % ordered
        ones = ordered[1:]
        tags_in_ones = [t for t, _ in ones]
        assert tags_in_ones == sorted(tags_in_ones), (
            "ties on item_count must sort by tag ascending: %s" % tags_in_ones
        )
        assert all(c == 1 for _, c in ones)

    def test_tag_frequencies_intra_item_dedup_strict(self):
        """L2: a single item listing the same tag twice contributes exactly 1, not 2."""
        result = _run_driver(
            """
            items = pl.DataFrame(
                {
                    "item_id": [1],
                    "title": ["only"],
                    "tags": ["red,red,RED, red "],
                },
                schema={"item_id": pl.Int64, "title": pl.String, "tags": pl.String},
            )
            df = N.tag_frequencies(items)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert len(result["rows"]) == 1, "only one distinct tag expected"
        row = result["rows"][0]
        assert row["tag"] == "red"
        assert row["item_count"] == 1, (
            "repeated tag within one item must count once, got %r" % row["item_count"]
        )

    # ------------------------------------------------------------------ L2: empty input

    def test_empty_input_shapes_all_functions(self):
        """L2: every function returns an empty DataFrame with correct columns on empty input."""
        result = _run_driver(
            """
            items = pl.DataFrame(
                schema={"item_id": pl.Int64, "title": pl.String, "tags": pl.String},
            )
            out = {}
            ct = N.clean_titles(items)
            out["clean_titles"] = {"cols": list(ct.columns), "h": ct.height}
            et = N.explode_tags(items)
            out["explode_tags"] = {"cols": list(et.columns), "h": et.height}
            tf = N.tag_frequencies(items)
            out["tag_frequencies"] = {"cols": list(tf.columns), "h": tf.height}
            print(json.dumps(out))
            """
        )
        ct = result["clean_titles"]
        assert ct["h"] == 0, "clean_titles must be empty on empty input"
        for c in ["item_id", "title", "tags", "title_clean", "title_len"]:
            assert c in ct["cols"], "clean_titles empty missing col %s: %s" % (c, ct["cols"])
        et = result["explode_tags"]
        assert et["h"] == 0
        assert et["cols"] == ["item_id", "tag"], "explode_tags empty cols: %s" % et["cols"]
        tf = result["tag_frequencies"]
        assert tf["h"] == 0
        assert tf["cols"] == ["tag", "item_count"], (
            "tag_frequencies empty cols: %s" % tf["cols"]
        )

    # ------------------------------------------------------------------ L2: native acceptance

    def test_native_pytest_suite_passes(self):
        """L2: the agent's own pytest suite for the module passes (acceptance command)."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "examples/text_normalize/test_normalize.py", "-q"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=420,
        )
        assert proc.returncode == 0, (
            "native pytest suite failed (rc=%s)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:])
        )
