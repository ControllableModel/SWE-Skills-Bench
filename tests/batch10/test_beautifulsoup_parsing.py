"""
Test for the 'beautifulsoup-parsing' skill (variant ext10) — Definition-List
Specification Extraction Module.

Verifies the Agent created a self-contained extraction module at
``bs4/specs.py`` exposing ``extract_dl``, ``dl_to_dict``, ``spec_table`` and
``find_value``, plus an accompanying test file ``bs4/tests/test_specs.py``.

This is a DISTINCT task from ext1 (which built ``bs4/extract.py`` with
``extract_cards``/``extract_table``/``extract_links``). Here we parse key/value
markup: definition lists (``<dl>`` / ``<dt>`` / ``<dd>``) and two-column spec
tables, with whitespace normalization, document-order term/definition
association, first-wins on duplicate keys, and case-insensitive cross-structure
lookup.

Strategy
--------
* L1 checks the two deliverable files exist and the module imports cleanly and
  exposes the four public callables.
* L2 drives the Agent's *actual* module independently of any test file the
  Agent itself may have written: a tiny JSON-emitting driver is written into
  REPO_DIR, run with the repo's own Python (cwd=REPO_DIR so ``import bs4.specs``
  resolves), and the emitted plain-data structures are deep-validated against
  the requirement's contract. A hardcoded / look-alike solution that ignores
  its input, skips multi-``<dd>`` association, or hardcodes outputs cannot
  satisfy these fixtures.
* One L2 case runs the native acceptance command
  (``python -m pytest bs4/tests/test_specs.py -v``).
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/BeautifulSoup4"


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _run_driver(body, timeout=120):
    """
    Write ``body`` (a Python snippet that defines a module-level ``RESULT``
    object) into a throwaway driver under REPO_DIR, execute it with the repo's
    Python so that ``import bs4.specs`` resolves, and return the parsed JSON
    the driver prints to stdout.

    The driver imports the Agent's real module — there is no stubbing — so the
    returned data reflects genuine parsing behaviour.
    """
    driver_dir = os.path.join(REPO_DIR, "_skill_driver_tmp")
    os.makedirs(driver_dir, exist_ok=True)
    driver_path = os.path.join(driver_dir, "drv_specs.py")

    header = textwrap.dedent(
        """
        import json, sys, os
        sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
        from bs4.specs import extract_dl, dl_to_dict, spec_table, find_value
        """
    )
    full = header + "\n" + textwrap.dedent(body) + "\nprint(json.dumps(RESULT))\n"

    with open(driver_path, "w") as fh:
        fh.write(full)

    try:
        proc = subprocess.run(
            ["python", driver_path],
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

    assert proc.returncode == 0, (
        "driver failed (returncode={})\n--- stdout ---\n{}\n--- stderr ---\n{}".format(
            proc.returncode, proc.stdout, proc.stderr
        )
    )
    out = proc.stdout.strip().splitlines()
    assert out, "driver produced no stdout; stderr=\n" + proc.stderr
    return json.loads(out[-1])


# A definition list with: a multi-<dd> term, a normal term, a term whose text is
# split across nested inline tags (whitespace must collapse), a duplicate term
# (first wins), and an empty-definition term (values == []).
DL_HTML = """
<html><body>
  <dl>
    <dt>Colors</dt>
      <dd>Red</dd>
      <dd> Green </dd>
    <dt>Weight</dt>
      <dd>  2.5
          kg </dd>
    <dt><span>Power</span> <span>Source</span></dt>
      <dd>AC <b>Adapter</b></dd>
    <dt>Weight</dt>
      <dd>SHOULD NOT WIN</dd>
    <dt>Notes</dt>
  </dl>
</body></html>
"""

# A two-column spec table: <th> label cells, <td> value cells, one short row
# (single cell, must be skipped), and a duplicate label (first wins).
TABLE_HTML = """
<html><body>
  <table>
    <tr><th>Material</th><td> Aluminum </td></tr>
    <tr><th>Weight</th><td>1.2 kg</td></tr>
    <tr><th>Origin</th></tr>
    <tr><th>Material</th><td>SHOULD NOT WIN</td></tr>
  </table>
</body></html>
"""


# ----------------------------------------------------------------------------
# L1: deliverables exist and are importable
# ----------------------------------------------------------------------------

class TestBeautifulsoupParsing:
    """Validate the definition-list specification extraction module."""

    REPO_DIR = REPO_DIR

    def test_specs_module_file_exists(self):
        """bs4/specs.py must exist (L1 deliverable)."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "specs.py")), \
            "bs4/specs.py was not created"

    def test_specs_test_file_exists(self):
        """bs4/tests/test_specs.py must exist (L1 deliverable)."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "tests", "test_specs.py")), \
            "bs4/tests/test_specs.py was not created"

    def test_module_exposes_public_callables(self):
        """The module imports cleanly and exposes the four public functions."""
        res = _run_driver(
            """
            RESULT = {
                "extract_dl": callable(extract_dl),
                "dl_to_dict": callable(dl_to_dict),
                "spec_table": callable(spec_table),
                "find_value": callable(find_value),
            }
            """
        )
        assert res == {
            "extract_dl": True,
            "dl_to_dict": True,
            "spec_table": True,
            "find_value": True,
        }, "specs.py must define callable extract_dl/dl_to_dict/spec_table/find_value"

    # ------------------------------------------------------------------
    # L2: extract_dl behaviour
    # ------------------------------------------------------------------

    def test_extract_dl_structure_and_order(self):
        """extract_dl returns one dict per <dt> in document order with term/values keys."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = extract_dl(HTML)
            """ % DL_HTML
        )
        assert isinstance(res, list), "extract_dl must return a list"
        # 5 <dt> elements, but the first-wins/duplicate handling is for dl_to_dict;
        # extract_dl reports every pairing in document order.
        terms = [d["term"] for d in res]
        assert terms == ["Colors", "Weight", "Power Source", "Weight", "Notes"], \
            "terms must be in document order with normalized text, got %r" % terms
        for d in res:
            assert set(d.keys()) == {"term", "values"}, \
                "each entry must have exactly keys {term, values}, got %r" % sorted(d.keys())

    def test_extract_dl_multi_and_empty_definitions(self):
        """A <dt> with two <dd> -> values length 2; a <dt> with no <dd> -> []."""
        res = _run_driver(
            """
            HTML = %r
            out = extract_dl(HTML)
            RESULT = {d["term"]: d["values"] for d in out if d["term"] != "Weight"}
            RESULT["_first_weight"] = next(d["values"] for d in out if d["term"] == "Weight")
            """ % DL_HTML
        )
        assert res["Colors"] == ["Red", "Green"], \
            "multi-<dd> term must collect both values (normalized), got %r" % res["Colors"]
        assert res["Notes"] == [], \
            "<dt> with no following <dd> must have values == [], got %r" % res["Notes"]
        assert res["_first_weight"] == ["2.5 kg"], \
            "internal whitespace runs spanning newlines must collapse, got %r" % res["_first_weight"]

    def test_extract_dl_normalizes_nested_inline_whitespace(self):
        """Term/value text spanning nested inline tags collapses to single spaces."""
        res = _run_driver(
            """
            HTML = %r
            out = extract_dl(HTML)
            RESULT = next(d for d in out if d["term"] == "Power Source")
            """ % DL_HTML
        )
        assert res["term"] == "Power Source", \
            "nested-tag term must normalize to 'Power Source', got %r" % res["term"]
        assert res["values"] == ["AC Adapter"], \
            "value with nested <b> must normalize to 'AC Adapter', got %r" % res["values"]

    def test_extract_dl_empty_document(self):
        """A document with no <dl> yields []."""
        res = _run_driver(
            """
            RESULT = extract_dl("<html><body><p>no dl here</p></body></html>")
            """
        )
        assert res == [], "document with no <dl> must yield [], got %r" % res

    # ------------------------------------------------------------------
    # L2: dl_to_dict behaviour
    # ------------------------------------------------------------------

    def test_dl_to_dict_first_value_and_first_wins(self):
        """dl_to_dict maps each term to its first <dd>; duplicate term keeps the first."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = dl_to_dict(HTML)
            """ % DL_HTML
        )
        assert res.get("Colors") == "Red", \
            "term must map to its first <dd> value, got %r" % res.get("Colors")
        assert res.get("Power Source") == "AC Adapter", \
            "normalized nested term/value mismatch, got %r" % res.get("Power Source")
        assert res.get("Weight") == "2.5 kg", \
            "duplicate term must keep the FIRST occurrence, got %r" % res.get("Weight")
        assert res.get("Notes") == "", \
            "term with no <dd> must map to empty string, got %r" % res.get("Notes")

    def test_dl_to_dict_empty_document(self):
        """No <dl> -> {}."""
        res = _run_driver(
            """
            RESULT = dl_to_dict("<html><body><span>nada</span></body></html>")
            """
        )
        assert res == {}, "document with no <dl> must yield {}, got %r" % res

    # ------------------------------------------------------------------
    # L2: spec_table behaviour
    # ------------------------------------------------------------------

    def test_spec_table_two_column_mapping(self):
        """spec_table maps first-cell label -> second-cell value for the first table."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = spec_table(HTML)
            """ % TABLE_HTML
        )
        assert res.get("Material") == "Aluminum", \
            "label/value mapping with normalization failed, got %r" % res.get("Material")
        assert res.get("Weight") == "1.2 kg", \
            "second-cell value mismatch, got %r" % res.get("Weight")

    def test_spec_table_short_row_skipped_and_first_wins(self):
        """A row with a single cell is skipped; duplicate label keeps the first."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = spec_table(HTML)
            """ % TABLE_HTML
        )
        assert "Origin" not in res, \
            "row with only one cell must be skipped, got keys %r" % sorted(res.keys())
        assert res.get("Material") == "Aluminum", \
            "duplicate label must keep the FIRST row's value, got %r" % res.get("Material")
        # Exactly the two valid distinct labels survive.
        assert set(res.keys()) == {"Material", "Weight"}, \
            "spec_table keys mismatch, got %r" % sorted(res.keys())

    def test_spec_table_first_table_only(self):
        """Only the first <table> is parsed; a later table is ignored."""
        html = """
        <html><body>
          <table>
            <tr><td>A</td><td>1</td></tr>
          </table>
          <table>
            <tr><td>B</td><td>2</td></tr>
          </table>
        </body></html>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = spec_table(HTML)
            """ % html
        )
        assert res == {"A": "1"}, \
            "only the first table must be parsed, got %r" % res

    def test_spec_table_empty_document(self):
        """No <table> -> {}."""
        res = _run_driver(
            """
            RESULT = spec_table("<html><body><p>no table</p></body></html>")
            """
        )
        assert res == {}, "document with no <table> must yield {}, got %r" % res

    # ------------------------------------------------------------------
    # L2: find_value cross-structure lookup
    # ------------------------------------------------------------------

    def test_find_value_case_insensitive_in_dl(self):
        """find_value matches a <dl> term case-insensitively and returns its value."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "lower": find_value(HTML, "weight"),
                "upper": find_value(HTML, "POWER SOURCE"),
                "exact": find_value(HTML, "Colors"),
            }
            """ % DL_HTML
        )
        assert res["lower"] == "2.5 kg", \
            "case-insensitive term match in <dl> failed, got %r" % res["lower"]
        assert res["upper"] == "AC Adapter", \
            "case-insensitive normalized term match failed, got %r" % res["upper"]
        assert res["exact"] == "Red", \
            "exact term match must return first value, got %r" % res["exact"]

    def test_find_value_falls_through_to_table(self):
        """When the label is not in the <dl>, find_value searches the spec <table>."""
        html = """
        <html><body>
          <dl>
            <dt>Colors</dt><dd>Red</dd>
          </dl>
          <table>
            <tr><th>Material</th><td>Steel</td></tr>
            <tr><th>Finish</th><td> Matte </td></tr>
          </table>
        </body></html>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "from_dl": find_value(HTML, "colors"),
                "from_table": find_value(HTML, "finish"),
                "absent": find_value(HTML, "Voltage"),
            }
            """ % html
        )
        assert res["from_dl"] == "Red", \
            "label present in <dl> must resolve from <dl>, got %r" % res["from_dl"]
        assert res["from_table"] == "Matte", \
            "label only in <table> must resolve from table (case-insensitive), got %r" % res["from_table"]
        assert res["absent"] is None, \
            "label absent from both structures must return None, got %r" % res["absent"]

    def test_find_value_none_on_empty_document(self):
        """A document with neither <dl> nor <table> -> find_value is None."""
        res = _run_driver(
            """
            RESULT = find_value("<html><body><p>empty</p></body></html>", "Weight")
            """
        )
        assert res is None, "missing label in empty document must return None, got %r" % res

    # ------------------------------------------------------------------
    # L2: cross-cutting — empty document over all four functions
    # ------------------------------------------------------------------

    def test_all_functions_on_neither_dl_nor_table(self):
        """With neither <dl> nor <table>, all four functions yield documented empties."""
        res = _run_driver(
            """
            HTML = "<html><body><h1>Just a heading</h1></body></html>"
            RESULT = {
                "extract_dl": extract_dl(HTML),
                "dl_to_dict": dl_to_dict(HTML),
                "spec_table": spec_table(HTML),
                "find_value": find_value(HTML, "anything"),
            }
            """
        )
        assert res["extract_dl"] == [], "extract_dl must be [] on empty doc"
        assert res["dl_to_dict"] == {}, "dl_to_dict must be {} on empty doc"
        assert res["spec_table"] == {}, "spec_table must be {} on empty doc"
        assert res["find_value"] is None, "find_value must be None on empty doc"

    def test_tolerate_malformed_markup(self):
        """Malformed / partially recoverable HTML must not raise."""
        malformed = (
            "<dl><dt>Width<dd>10 cm<dt>Height<dd>20 cm"
            "<table><tr><th>Depth<td>5 cm"
        )
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "dl": dl_to_dict(HTML),
                "table": spec_table(HTML),
                "find": find_value(HTML, "height"),
            }
            """ % malformed
        )
        assert res["dl"].get("Width") == "10 cm", \
            "malformed <dl> must still recover term/value, got %r" % res["dl"]
        assert res["dl"].get("Height") == "20 cm", \
            "second pairing in malformed <dl> must recover, got %r" % res["dl"]
        assert res["find"] == "20 cm", \
            "find_value must work over malformed markup, got %r" % res["find"]

    # ------------------------------------------------------------------
    # L2: native acceptance command
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The Agent's own bs4/tests/test_specs.py must collect and pass green."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "bs4/tests/test_specs.py", "-v"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            "native acceptance command failed\n--- stdout ---\n{}\n--- stderr ---\n{}".format(
                proc.stdout, proc.stderr
            )
        )
        assert "no tests ran" not in proc.stdout.lower(), \
            "test_specs.py collected no tests:\n" + proc.stdout
        assert " passed" in proc.stdout, \
            "expected at least one passing test in native suite:\n" + proc.stdout
