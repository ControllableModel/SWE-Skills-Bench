"""
Test for the 'beautifulsoup-parsing' skill (variant ext6) — CSS-Selector
Query Helper Module.

Verifies the Agent created a self-contained query-helper module at
``bs4/query.py`` exposing ``count_matches``, ``texts``, ``attrs_of``,
``first_text`` and ``pluck``, plus an accompanying test file
``bs4/tests/test_query.py``.

This is a DISTINCT task from ext1 (which built ``bs4/extract.py`` with
``extract_cards`` / ``extract_table`` / ``extract_links``). Every assertion
here is re-derived from the ext6 requirement doc: CSS-selector counting,
order-preserving text/attr extraction with empty-match placeholders, the
``first_text`` default, and row-scoped ``pluck`` over a ``fields`` mapping.

Strategy
--------
* L1 checks the two deliverable files exist and the module is importable and
  exposes the five public callables.
* L2 drives the Agent's *actual* module independently of any test file the
  Agent itself may have written: a tiny JSON-emitting driver is written into
  REPO_DIR, run with the repo's own Python interpreter (cwd=REPO_DIR so
  ``import bs4.query`` resolves), and the emitted plain-data structures are
  deep-validated against the requirement's contract. A naive implementation
  that hardcodes outputs, drops empty matches, ignores selector scoping, or
  skips the ``fields`` mapping cannot satisfy these fixtures.
* One L2 case also runs the native acceptance command
  (``python -m pytest bs4/tests/test_query.py -v``).
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
    Python so that ``import bs4.query`` resolves, and return the parsed JSON
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
        from bs4.query import count_matches, texts, attrs_of, first_text, pluck
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


# A document exercising child/descendant/class selectors, empty matches,
# missing attributes, and repeated row structure for pluck scoping.
MENU_HTML = """
<html><body>
  <ul class="menu">
    <li class="item">Home</li>
    <li class="item"></li>
    <li class="item">Contact</li>
    <li><span>nested-not-direct-text</span></li>
  </ul>
  <ul class="other">
    <li>Outside</li>
  </ul>
  <nav>
    <a href="/home">Home</a>
    <a>NoHref</a>
    <a href="https://ext.example.com/x">Ext</a>
    <a href="/home">DupHome</a>
  </nav>
  <div class="card">
    <h3>Alpha</h3>
    <span class="price">$10</span>
  </div>
  <div class="card">
    <h3>Beta</h3>
  </div>
</body></html>
"""


# ----------------------------------------------------------------------------
# L1: deliverables exist and are importable
# ----------------------------------------------------------------------------

class TestBeautifulsoupParsing:
    """Validate the CSS-selector query-helper module and its behaviour."""

    REPO_DIR = REPO_DIR

    def test_query_module_file_exists(self):
        """bs4/query.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "query.py")), \
            "bs4/query.py was not created"

    def test_query_test_file_exists(self):
        """bs4/tests/test_query.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "tests", "test_query.py")), \
            "bs4/tests/test_query.py was not created"

    def test_module_exposes_public_callables(self):
        """The module must import cleanly and expose the five public functions."""
        res = _run_driver(
            """
            RESULT = {
                "count_matches": callable(count_matches),
                "texts": callable(texts),
                "attrs_of": callable(attrs_of),
                "first_text": callable(first_text),
                "pluck": callable(pluck),
            }
            """
        )
        assert res == {
            "count_matches": True,
            "texts": True,
            "attrs_of": True,
            "first_text": True,
            "pluck": True,
        }, "query.py must define callable count_matches/texts/attrs_of/first_text/pluck"

    # ------------------------------------------------------------------
    # L2: count_matches behaviour
    # ------------------------------------------------------------------

    def test_count_matches_child_selector(self):
        """count_matches with a child combinator counts only direct <li> children."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "menu_li": count_matches(HTML, "ul.menu > li"),
                "all_menu_li": count_matches(HTML, "ul.menu li"),
                "item": count_matches(HTML, "li.item"),
                "card": count_matches(HTML, ".card"),
            }
            """ % MENU_HTML
        )
        # ul.menu has 4 direct <li> children (the 4th holds a nested span).
        assert res["menu_li"] == 4, \
            "ul.menu > li must count 4 direct children, got %r" % res["menu_li"]
        # Descendant selector additionally picks up nothing extra at li level,
        # but must at least include all 4 direct li elements.
        assert res["all_menu_li"] == 4, \
            "ul.menu li descendant count mismatch, got %r" % res["all_menu_li"]
        assert res["item"] == 3, \
            "li.item class selector must match 3, got %r" % res["item"]
        assert res["card"] == 2, \
            ".card must match 2 cards, got %r" % res["card"]

    def test_count_matches_no_match_is_zero(self):
        """A selector matching nothing returns the integer 0."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = count_matches(HTML, "table.nonexistent")
            """ % MENU_HTML
        )
        assert res == 0, "no-match count_matches must be 0, got %r" % res

    # ------------------------------------------------------------------
    # L2: texts behaviour (stable cardinality + empty placeholders)
    # ------------------------------------------------------------------

    def test_texts_order_and_empty_placeholder(self):
        """texts returns one stripped string per match, empties become '' (kept)."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = texts(HTML, "li.item")
            """ % MENU_HTML
        )
        # Three li.item elements: "Home", "" (empty middle), "Contact".
        assert res == ["Home", "", "Contact"], \
            "texts must keep empty middle match as '' in document order, got %r" % res

    def test_texts_strips_and_collapses_whitespace(self):
        """Visible text is stripped; nested-tag text is gathered, not dropped."""
        html = """
        <body>
          <p class="t">   padded   </p>
          <p class="t"><span>a</span><span>b</span></p>
        </body>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = texts(HTML, "p.t")
            """ % html
        )
        assert len(res) == 2, "expected 2 matched paragraphs, got %r" % res
        assert res[0] == "padded", \
            "leading/trailing whitespace must be stripped, got %r" % res[0]
        # Nested inline text must be gathered for the element (not empty).
        assert res[1].replace(" ", "") == "ab", \
            "nested-tag text must be collected, got %r" % res[1]

    def test_texts_no_match_empty_list(self):
        """A selector matching nothing yields an empty list."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = texts(HTML, "section.missing")
            """ % MENU_HTML
        )
        assert res == [], "no-match texts must be [], got %r" % res

    # ------------------------------------------------------------------
    # L2: attrs_of behaviour (one entry per match, None for missing attr)
    # ------------------------------------------------------------------

    def test_attrs_of_preserves_none_and_duplicates(self):
        """attrs_of yields one value per matched element; missing attr -> None."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = attrs_of(HTML, "nav a", "href")
            """ % MENU_HTML
        )
        # Four <a> in nav: "/home", (no href -> None), absolute, "/home" dup.
        assert res == ["/home", None, "https://ext.example.com/x", "/home"], \
            "attrs_of must keep one entry per match with None for missing href, got %r" % res

    def test_attrs_of_no_match_empty_list(self):
        """attrs_of over a non-matching selector returns []."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = attrs_of(HTML, "img.none", "src")
            """ % MENU_HTML
        )
        assert res == [], "no-match attrs_of must be [], got %r" % res

    # ------------------------------------------------------------------
    # L2: first_text behaviour
    # ------------------------------------------------------------------

    def test_first_text_returns_first_match_and_matches_texts(self):
        """first_text equals the first entry of texts when there is a match."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "first": first_text(HTML, "li.item"),
                "texts0": texts(HTML, "li.item")[0],
            }
            """ % MENU_HTML
        )
        assert res["first"] == "Home", \
            "first_text must return first match's stripped text, got %r" % res["first"]
        assert res["first"] == res["texts0"], \
            "first_text must equal texts(...)[0], got %r vs %r" % (res["first"], res["texts0"])

    def test_first_text_default_on_no_match(self):
        """first_text returns the supplied default (and '' by default) when no match."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "custom": first_text(HTML, "h1.title", "FALLBACK"),
                "implicit": first_text(HTML, "h1.title"),
            }
            """ % MENU_HTML
        )
        assert res["custom"] == "FALLBACK", \
            "first_text must return the supplied default on no match, got %r" % res["custom"]
        assert res["implicit"] == "", \
            "first_text default must be '' when unspecified, got %r" % res["implicit"]

    # ------------------------------------------------------------------
    # L2: pluck behaviour (row-scoped fields, stable keys, '' for missing)
    # ------------------------------------------------------------------

    def test_pluck_row_scoped_fields_and_missing_subfield(self):
        """pluck returns one dict per row; missing sub-selector -> '' (key kept)."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = pluck(HTML, ".card", {"title": "h3", "price": ".price"})
            """ % MENU_HTML
        )
        assert isinstance(res, list) and len(res) == 2, \
            "pluck must return one dict per .card row, got %r" % res
        assert res[0] == {"title": "Alpha", "price": "$10"}, \
            "first card must pluck both fields, got %r" % res[0]
        # Second card lacks .price -> '' but the key must still be present.
        assert res[1] == {"title": "Beta", "price": ""}, \
            "missing sub-field must yield '' with key present, got %r" % res[1]
        for d in res:
            assert set(d.keys()) == {"title", "price"}, \
                "every pluck dict must have exactly the fields keys, got %r" % sorted(d.keys())

    def test_pluck_scoping_is_per_row_independent(self):
        """Sub-selectors resolve relative to each row, not the whole document."""
        html = """
        <body>
          <div class="row"><span class="v">first</span></div>
          <div class="row"><span class="v">second</span></div>
          <div class="row"></div>
        </body>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = pluck(HTML, ".row", {"val": ".v"})
            """ % html
        )
        # If scoping were global, every row would get "first"; correct scoping
        # gives each row its own descendant (and '' for the empty third row).
        assert res == [{"val": "first"}, {"val": "second"}, {"val": ""}], \
            "pluck sub-selectors must be scoped per row, got %r" % res

    def test_pluck_no_match_empty_list(self):
        """pluck over a non-matching row selector returns []."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = pluck(HTML, ".no-such-row", {"x": "span"})
            """ % MENU_HTML
        )
        assert res == [], "no-match pluck must be [], got %r" % res

    # ------------------------------------------------------------------
    # L2: malformed-HTML tolerance
    # ------------------------------------------------------------------

    def test_malformed_html_tolerated(self):
        """Unclosed/misnested markup must still parse and yield recoverable data."""
        malformed = (
            '<ul class="menu"><li class="item">One'
            '<li class="item">Two'
            '<li class="item">Three'
        )
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "count": count_matches(HTML, "li.item"),
                "texts": texts(HTML, "li.item"),
                "first": first_text(HTML, "li.item"),
            }
            """ % malformed
        )
        assert res["count"] >= 3, \
            "malformed markup must still recover 3 list items, got %r" % res["count"]
        assert "One" in res["texts"], \
            "recoverable text from malformed markup expected, got %r" % res["texts"]
        assert res["first"] == "One", \
            "first_text on malformed markup must be 'One', got %r" % res["first"]

    # ------------------------------------------------------------------
    # L2: native acceptance command
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The Agent's own bs4/tests/test_query.py must collect and pass green."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "bs4/tests/test_query.py", "-v"],
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
            "test_query.py collected no tests:\n" + proc.stdout
        assert " passed" in proc.stdout, \
            "expected at least one passing test in native suite:\n" + proc.stdout
