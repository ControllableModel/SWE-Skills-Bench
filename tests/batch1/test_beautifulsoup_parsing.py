"""
Test for the 'beautifulsoup-parsing' skill — HTML Catalog Extraction Module.

Verifies the Agent created a self-contained extraction module at
``bs4/extract.py`` exposing ``extract_cards``, ``extract_table`` and
``extract_links``, plus an accompanying test file ``bs4/tests/test_extract.py``.

Strategy
--------
* L1 checks the two deliverable files exist and the module is importable and
  exposes the three public callables.
* L2 drives the Agent's *actual* module independently of any test file the
  Agent itself may have written: a tiny JSON-emitting driver is written into
  REPO_DIR, run with the repo's own Python interpreter (cwd=REPO_DIR so
  ``import bs4.extract`` resolves), and the emitted plain-data structures are
  deep-validated against the requirement's contract.  A hardcoded / look-alike
  solution that does not really parse the HTML cannot satisfy these fixtures.
* One L2 case also runs the native acceptance command
  (``python -m pytest bs4/tests/test_extract.py -v``).
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
    Python so that ``import bs4.extract`` resolves, and return the parsed JSON
    that the driver prints to stdout.

    The driver imports the Agent's real module — there is no stubbing — so the
    returned data reflects genuine parsing behaviour.
    """
    driver_dir = os.path.join(REPO_DIR, "_skill_driver_tmp")
    os.makedirs(driver_dir, exist_ok=True)
    driver_path = os.path.join(driver_dir, "drv.py")

    header = textwrap.dedent(
        """
        import json, sys, os
        sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
        from bs4.extract import extract_cards, extract_table, extract_links
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


CATALOG_HTML = """
<html><body>
  <div class="product-card featured">
    <h3 class="name"><span>Wireless</span>
        <span>Mouse</span></h3>
    <span class="price">  $1,299.00 </span>
    <a href="item/42">view</a>
    <img src="img/mouse.png">
  </div>
  <div class="product-card">
    <h3 class="name">Plain Keyboard</h3>
    <span class="price">Call us</span>
    <a href="https://other.example.com/x">go</a>
    <img src="https://cdn.example.com/kb.png">
    <span class="out-of-stock">Sold out</span>
  </div>
  <div class="product-card">
    <h3 class="name">Mystery Item</h3>
  </div>
</body></html>
"""

BASE_URL = "https://shop.example.com/catalog/"


# ----------------------------------------------------------------------------
# L1: deliverables exist and are importable
# ----------------------------------------------------------------------------

class TestBeautifulsoupParsing:
    """Validate the HTML catalog extraction module and its behaviour."""

    REPO_DIR = REPO_DIR

    def test_extract_module_file_exists(self):
        """bs4/extract.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "extract.py")), \
            "bs4/extract.py was not created"

    def test_extract_test_file_exists(self):
        """bs4/tests/test_extract.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "tests", "test_extract.py")), \
            "bs4/tests/test_extract.py was not created"

    def test_module_exposes_public_callables(self):
        """The module must import cleanly and expose the three public functions."""
        res = _run_driver(
            """
            RESULT = {
                "cards": callable(extract_cards),
                "table": callable(extract_table),
                "links": callable(extract_links),
            }
            """
        )
        assert res == {"cards": True, "table": True, "links": True}, \
            "extract.py must define callable extract_cards/extract_table/extract_links"

    # ------------------------------------------------------------------
    # L2: extract_cards behaviour
    # ------------------------------------------------------------------

    def test_cards_count_and_document_order(self):
        """extract_cards yields one dict per product-card, in document order."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = extract_cards(HTML, %r)
            """ % (CATALOG_HTML, BASE_URL)
        )
        assert isinstance(res, list), "extract_cards must return a list"
        assert len(res) == 3, "expected exactly 3 product cards, got %d" % len(res)
        names = [c["name"] for c in res]
        assert names == ["Wireless Mouse", "Plain Keyboard", "Mystery Item"], \
            "cards must be returned in document order with normalized names: %r" % names
        for c in res:
            assert set(c.keys()) == {"name", "price", "url", "image", "in_stock"}, \
                "each card dict must have exactly the 5 documented keys, got %r" % sorted(c.keys())

    def test_card_name_collapses_nested_whitespace(self):
        """Name split across nested inline tags collapses to a single-space string."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = extract_cards(HTML, %r)[0]
            """ % (CATALOG_HTML, BASE_URL)
        )
        assert res["name"] == "Wireless Mouse", \
            "nested-tag name must normalize to 'Wireless Mouse', got %r" % res["name"]

    def test_card_price_parsing_success_and_failure(self):
        """Price parsing: '$1,299.00' -> 1299.0; 'Call us' -> None; absent -> None."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = [c["price"] for c in extract_cards(HTML, %r)]
            """ % (CATALOG_HTML, BASE_URL)
        )
        assert res[0] == 1299.0, "'$1,299.00' must parse to float 1299.0, got %r" % res[0]
        assert isinstance(res[0], float), "parsed price must be a float, got %r" % type(res[0])
        assert res[1] is None, "'Call us' must parse to None, got %r" % res[1]
        assert res[2] is None, "card with no price element must yield None, got %r" % res[2]

    def test_card_url_resolution_relative_and_absolute(self):
        """Relative href resolved against base_url; absolute href returned unchanged."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = [c["url"] for c in extract_cards(HTML, %r)]
            """ % (CATALOG_HTML, BASE_URL)
        )
        assert res[0] == "https://shop.example.com/catalog/item/42", \
            "relative link must resolve against base_url, got %r" % res[0]
        assert res[1] == "https://other.example.com/x", \
            "absolute link must be returned unchanged, got %r" % res[1]
        assert res[2] is None, "card with no link must yield url None, got %r" % res[2]

    def test_card_image_resolution_and_missing(self):
        """Image src resolved against base_url; missing image -> None."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = [c["image"] for c in extract_cards(HTML, %r)]
            """ % (CATALOG_HTML, BASE_URL)
        )
        assert res[0] == "https://shop.example.com/catalog/img/mouse.png", \
            "relative image src must resolve against base_url, got %r" % res[0]
        assert res[1] == "https://cdn.example.com/kb.png", \
            "absolute image src must be unchanged, got %r" % res[1]
        assert res[2] is None, "card with no image must yield None, got %r" % res[2]

    def test_card_in_stock_flag(self):
        """in_stock is False only when an out-of-stock marker is present."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = [c["in_stock"] for c in extract_cards(HTML, %r)]
            """ % (CATALOG_HTML, BASE_URL)
        )
        assert res[0] is True, "card without out-of-stock marker must be in_stock True"
        assert res[1] is False, "card with out-of-stock marker must be in_stock False"
        assert res[2] is True, "card without out-of-stock marker must be in_stock True"

    def test_card_multi_class_match_and_missing_name(self):
        """Cards matched regardless of extra classes; missing name -> ''. """
        html = """
        <ul>
          <li class="extra product-card highlighted">
            <a href="/p/1">buy</a>
          </li>
          <li class="not-a-card"><span class="name">Decoy</span></li>
        </ul>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = extract_cards(HTML, %r)
            """ % (html, "https://shop.example.com/")
        )
        assert len(res) == 1, \
            "only the element carrying the product-card class should match, got %d" % len(res)
        assert res[0]["name"] == "", \
            "card with no name element must yield empty string, got %r" % res[0]["name"]
        assert res[0]["url"] == "https://shop.example.com/p/1", \
            "absolute-path link must resolve against base_url host, got %r" % res[0]["url"]

    def test_cards_empty_document(self):
        """A document with no product cards yields an empty list (no raise)."""
        res = _run_driver(
            """
            RESULT = extract_cards("<html><body><p>nothing here</p></body></html>", "https://x/")
            """
        )
        assert res == [], "document with no cards must yield [], got %r" % res

    def test_cards_tolerate_malformed_html(self):
        """Malformed (unclosed/misnested) markup must still parse without raising."""
        malformed = (
            '<div class="product-card"><span class="name">Broken'
            '<span class="price">$9.50<a href="x/1">'
            '<div class="product-card"><span class="name">Second</span>'
            '<span class="price">$3</span><a href="x/2">'
        )
        res = _run_driver(
            """
            HTML = %r
            cards = extract_cards(HTML, %r)
            RESULT = {"n": len(cards), "prices": [c["price"] for c in cards],
                      "urls": [c["url"] for c in cards]}
            """ % (malformed, "https://shop.example.com/c/")
        )
        assert res["n"] >= 1, "malformed input must still recover at least one card"
        assert 9.5 in res["prices"], \
            "price recoverable from malformed markup must parse, got %r" % res["prices"]
        assert any(
            u == "https://shop.example.com/c/x/1" for u in res["urls"]
        ), "relative link in malformed markup must still resolve, got %r" % res["urls"]

    # ------------------------------------------------------------------
    # L2: extract_table behaviour
    # ------------------------------------------------------------------

    def test_table_basic_rows(self):
        """extract_table maps <th> headers to <td> values per body row."""
        html = """
        <table>
          <tr><th>SKU</th><th> Name </th><th>Qty</th></tr>
          <tr><td> A1 </td><td>Widget</td><td>5</td></tr>
          <tr><td>B2</td><td>Gadget</td><td>0</td></tr>
        </table>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = extract_table(HTML)
            """ % html
        )
        assert res == [
            {"SKU": "A1", "Name": "Widget", "Qty": "5"},
            {"SKU": "B2", "Name": "Gadget", "Qty": "0"},
        ], "table body rows mis-parsed: %r" % res

    def test_table_ragged_row_padding(self):
        """A body row with fewer <td> than headers keeps surplus keys with ''. """
        html = """
        <table>
          <tr><th>A</th><th>B</th><th>C</th></tr>
          <tr><td>1</td><td>2</td></tr>
        </table>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = extract_table(HTML)
            """ % html
        )
        assert res == [{"A": "1", "B": "2", "C": ""}], \
            "missing trailing column must be present with '', got %r" % res

    def test_table_extra_cells_ignored_and_first_table_only(self):
        """Extra <td> beyond header count ignored; only the first table parsed."""
        html = """
        <table>
          <tr><th>X</th><th>Y</th></tr>
          <tr><td>1</td><td>2</td><td>IGNORED</td></tr>
        </table>
        <table>
          <tr><th>Z</th></tr><tr><td>second</td></tr>
        </table>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = extract_table(HTML)
            """ % html
        )
        assert res == [{"X": "1", "Y": "2"}], \
            "extra cells must be dropped and only first table parsed, got %r" % res

    def test_table_empty_document(self):
        """No table in document -> empty list."""
        res = _run_driver(
            """
            RESULT = extract_table("<html><body><p>no table</p></body></html>")
            """
        )
        assert res == [], "document with no table must yield [], got %r" % res

    # ------------------------------------------------------------------
    # L2: extract_links behaviour
    # ------------------------------------------------------------------

    def test_links_resolution_order_and_skip_hrefless(self):
        """extract_links resolves, preserves order/duplicates, skips href-less <a>."""
        html = """
        <body>
          <a href="https://abs.example.com/a">abs</a>
          <a href="rel/b">rel</a>
          <a name="anchor">no href</a>
          <a href="rel/b">dup</a>
        </body>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = extract_links(HTML, %r)
            """ % (html, "https://shop.example.com/catalog/")
        )
        assert res == [
            "https://abs.example.com/a",
            "https://shop.example.com/catalog/rel/b",
            "https://shop.example.com/catalog/rel/b",
        ], "links must be resolved, ordered, deduplicate-free, href-less skipped: %r" % res

    def test_links_empty_when_no_anchors(self):
        """A document with no <a href> yields an empty list."""
        res = _run_driver(
            """
            RESULT = extract_links("<p>plain text only</p>", "https://x/")
            """
        )
        assert res == [], "document with no hrefs must yield [], got %r" % res

    # ------------------------------------------------------------------
    # L2: native acceptance command
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The Agent's own bs4/tests/test_extract.py must collect and pass green."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "bs4/tests/test_extract.py", "-v"],
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
        # Guard against a vacuous suite that collects zero tests.
        assert "no tests ran" not in proc.stdout.lower(), \
            "test_extract.py collected no tests:\n" + proc.stdout
        assert " passed" in proc.stdout, \
            "expected at least one passing test in native suite:\n" + proc.stdout
