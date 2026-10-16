"""
Test for the 'beautifulsoup-parsing' skill — Document Heading Outline Module.

Variant: ext8.  The Agent must create a self-contained outline utility at
``bs4/outline.py`` exposing four public functions —

    * ``headings(html)``            -> list[dict] (level, text, id) in doc order
    * ``slugify_anchor(text)``      -> URL-fragment slug str
    * ``table_of_contents(html)``   -> list[dict] (level, text, anchor)
    * ``nest_outline(html)``        -> nested list-of-node tree

— plus an accompanying deterministic test file ``bs4/tests/test_outline.py``.

Strategy
--------
* L1 checks the two deliverable files exist, the module imports cleanly and
  exposes the four documented callables.
* L2 drives the Agent's *actual* module independently of any test file the
  Agent itself may have written: a small JSON-emitting driver is written into
  REPO_DIR and executed with the repo's own Python (cwd=REPO_DIR so
  ``import bs4.outline`` resolves) and the emitted plain-data structures are
  deep-validated against the requirement contract.  A naive/stub solution that
  hardcodes output, ignores the level digit, skips text normalization, or does
  not really build the nesting tree cannot satisfy these fixtures.
* One L2 case also runs the native acceptance command
  (``python -m pytest bs4/tests/test_outline.py -v``).
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
    Python so that ``import bs4.outline`` resolves, and return the parsed JSON
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
        from bs4.outline import headings, slugify_anchor, table_of_contents, nest_outline
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


# A representative document exercising: ordering, all six levels via separate
# fixtures, id-vs-no-id, nested inline tags with whitespace, repeated levels.
DOC_HTML = """
<html><body>
  <h1 id="top">Introduction</h1>
  <h2>Getting Started: Part 2!</h2>
  <h2 id="intro">Intro</h2>
  <h3>Deep
      <code>Dive</code>   and   <em>More</em></h3>
</body></html>
"""


# ----------------------------------------------------------------------------
# L1: deliverables exist and are importable
# ----------------------------------------------------------------------------

class TestBeautifulsoupParsing:
    """Validate the document heading outline module and its behaviour."""

    REPO_DIR = REPO_DIR

    def test_outline_module_file_exists(self):
        """bs4/outline.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "outline.py")), \
            "bs4/outline.py was not created"

    def test_outline_test_file_exists(self):
        """bs4/tests/test_outline.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "tests", "test_outline.py")), \
            "bs4/tests/test_outline.py was not created"

    def test_module_exposes_public_callables(self):
        """The module must import cleanly and expose the four public functions."""
        res = _run_driver(
            """
            RESULT = {
                "headings": callable(headings),
                "slugify_anchor": callable(slugify_anchor),
                "table_of_contents": callable(table_of_contents),
                "nest_outline": callable(nest_outline),
            }
            """
        )
        assert res == {
            "headings": True,
            "slugify_anchor": True,
            "table_of_contents": True,
            "nest_outline": True,
        }, "outline.py must define callable headings/slugify_anchor/table_of_contents/nest_outline"

    # ------------------------------------------------------------------
    # L2: headings() behaviour
    # ------------------------------------------------------------------

    def test_headings_order_levels_and_keys(self):
        """headings yields one dict per heading in document order with exact keys."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = headings(HTML)
            """ % DOC_HTML
        )
        assert isinstance(res, list), "headings must return a list"
        assert len(res) == 4, "expected exactly 4 headings, got %d" % len(res)
        levels = [h["level"] for h in res]
        assert levels == [1, 2, 2, 3], \
            "levels must be derived from tag name in document order, got %r" % levels
        for h in res:
            assert set(h.keys()) == {"level", "text", "id"}, \
                "each heading dict must have exactly keys level/text/id, got %r" % sorted(h.keys())
            assert isinstance(h["level"], int), "level must be an int, got %r" % type(h["level"])

    def test_headings_level_derivation_all_six(self):
        """level must be the digit in the tag name for every h1..h6."""
        html = (
            "<h6>f</h6><h1>a</h1><h5>e</h5><h2>b</h2><h4>d</h4><h3>c</h3>"
        )
        res = _run_driver(
            """
            HTML = %r
            RESULT = [(h["text"], h["level"]) for h in headings(HTML)]
            """ % html
        )
        # document order preserved; level keyed off tag digit not position.
        assert res == [
            ["f", 6], ["a", 1], ["e", 5], ["b", 2], ["d", 4], ["c", 3]
        ], "level must come from the tag digit, in document order, got %r" % res

    def test_headings_text_normalization_nested_inline(self):
        """Text spanning nested inline tags + newlines collapses to single spaces."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = [h["text"] for h in headings(HTML)]
            """ % DOC_HTML
        )
        assert res[0] == "Introduction", "simple text mis-normalized: %r" % res[0]
        assert res[1] == "Getting Started: Part 2!", "text mis-normalized: %r" % res[1]
        assert res[3] == "Deep Dive and More", \
            "nested-inline text must collapse to single spaces, got %r" % res[3]

    def test_headings_id_attribute_capture(self):
        """id is the heading's id attribute, or None when absent."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = [h["id"] for h in headings(HTML)]
            """ % DOC_HTML
        )
        assert res == ["top", None, "intro", None], \
            "id attribute must be captured (None when absent), got %r" % res

    def test_headings_empty_text_and_no_headings(self):
        """An empty heading -> '' text; a document with no headings -> []."""
        res = _run_driver(
            """
            empty = headings("<h2></h2>")
            none = headings("<html><body><p>no headings here</p></body></html>")
            RESULT = {"empty_text": empty[0]["text"], "empty_level": empty[0]["level"],
                      "none": none}
            """
        )
        assert res["empty_text"] == "", "empty heading must yield '' text, got %r" % res["empty_text"]
        assert res["empty_level"] == 2, "empty <h2> must still report level 2"
        assert res["none"] == [], "no-heading document must yield [], got %r" % res["none"]

    # ------------------------------------------------------------------
    # L2: slugify_anchor() behaviour
    # ------------------------------------------------------------------

    def test_slugify_basic_and_punctuation_runs(self):
        """slugify lowercases and collapses non-alnum runs to single hyphens."""
        res = _run_driver(
            """
            RESULT = {
                "a": slugify_anchor("  Getting Started: Part 2!  "),
                "b": slugify_anchor("Hello, World!!!"),
                "c": slugify_anchor("A & B / C"),
            }
            """
        )
        assert res["a"] == "getting-started-part-2", \
            "punctuation runs/leading-trailing must reduce, got %r" % res["a"]
        assert res["b"] == "hello-world", \
            "trailing punctuation run must be stripped, got %r" % res["b"]
        assert res["c"] == "a-b-c", \
            "interior non-alnum runs must collapse to single hyphen, got %r" % res["c"]

    def test_slugify_edge_cases_empty_and_all_separators(self):
        """Input reducing to nothing returns '' (no leading/trailing hyphens)."""
        res = _run_driver(
            """
            RESULT = {
                "empty": slugify_anchor(""),
                "punct": slugify_anchor("---!!!---"),
                "spaces": slugify_anchor("   "),
                "lead_trail": slugify_anchor("--Edge--"),
            }
            """
        )
        assert res["empty"] == "", "empty input must yield '', got %r" % res["empty"]
        assert res["punct"] == "", "all-separator input must yield '', got %r" % res["punct"]
        assert res["spaces"] == "", "whitespace-only input must yield '', got %r" % res["spaces"]
        assert res["lead_trail"] == "edge", \
            "leading/trailing separators must be stripped, got %r" % res["lead_trail"]

    # ------------------------------------------------------------------
    # L2: table_of_contents() behaviour
    # ------------------------------------------------------------------

    def test_toc_anchor_id_vs_slug(self):
        """anchor uses the id when present, else the slug of the normalized text."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = table_of_contents(HTML)
            """ % DOC_HTML
        )
        assert isinstance(res, list) and len(res) == 4, \
            "table_of_contents must return one entry per heading, got %r" % res
        for e in res:
            assert set(e.keys()) == {"level", "text", "anchor"}, \
                "each toc entry must have keys level/text/anchor, got %r" % sorted(e.keys())
        anchors = [e["anchor"] for e in res]
        # h1 has id="top"; h2 (no id) -> slug; h2 has id="intro"; h3 (no id) -> slug
        assert anchors == [
            "top", "getting-started-part-2", "intro", "deep-dive-and-more"
        ], "anchor must prefer id then fall back to slug of normalized text, got %r" % anchors

    def test_toc_levels_and_text_match_headings(self):
        """toc level/text mirror headings() exactly (shared normalization)."""
        res = _run_driver(
            """
            HTML = %r
            hs = headings(HTML)
            toc = table_of_contents(HTML)
            RESULT = {
                "levels": [e["level"] for e in toc],
                "h_levels": [h["level"] for h in hs],
                "texts": [e["text"] for e in toc],
                "h_texts": [h["text"] for h in hs],
            }
            """ % DOC_HTML
        )
        assert res["levels"] == res["h_levels"] == [1, 2, 2, 3], \
            "toc levels must match heading levels, got %r" % res["levels"]
        assert res["texts"] == res["h_texts"], \
            "toc text normalization must match headings(), got %r" % res["texts"]

    def test_toc_empty_document(self):
        """A document with no headings yields an empty toc."""
        res = _run_driver(
            """
            RESULT = table_of_contents("<html><body><p>nope</p></body></html>")
            """
        )
        assert res == [], "no-heading document must yield [], got %r" % res

    # ------------------------------------------------------------------
    # L2: nest_outline() behaviour
    # ------------------------------------------------------------------

    def test_nest_outline_basic_tree(self):
        """h1 > (h2, h2 > h3) builds one root with two children, last child has one."""
        html = """
        <h1>Root</h1>
          <h2>Alpha</h2>
          <h2>Beta</h2>
            <h3>Beta-1</h3>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = nest_outline(HTML)
            """ % html
        )
        assert isinstance(res, list) and len(res) == 1, \
            "expected exactly one root node, got %r" % res
        root = res[0]
        assert set(root.keys()) == {"level", "text", "children"}, \
            "each node must have keys level/text/children, got %r" % sorted(root.keys())
        assert root["level"] == 1 and root["text"] == "Root", \
            "root node mis-built: %r" % root
        kids = root["children"]
        assert [c["text"] for c in kids] == ["Alpha", "Beta"], \
            "h1 must have two h2 children in document order, got %r" % [c["text"] for c in kids]
        assert kids[0]["children"] == [], "first h2 must have no children, got %r" % kids[0]
        assert [g["text"] for g in kids[1]["children"]] == ["Beta-1"], \
            "second h2 must contain the h3 child, got %r" % kids[1]["children"]
        assert kids[1]["children"][0]["level"] == 3, "grandchild must report level 3"

    def test_nest_outline_skipped_and_multiple_roots(self):
        """Strictly-smaller-predecessor rule: skipped levels and roots handled."""
        # h2 first (no smaller predecessor -> root), h4 nests under it (skip h3),
        # then another h2 starts a second root tree.
        html = """
        <h2>First</h2>
          <h4>Deep</h4>
        <h2>Second</h2>
          <h3>Sub</h3>
        """
        res = _run_driver(
            """
            HTML = %r
            tree = nest_outline(HTML)
            RESULT = {
                "roots": [n["text"] for n in tree],
                "root_levels": [n["level"] for n in tree],
                "first_children": [c["text"] for c in tree[0]["children"]],
                "first_child_level": tree[0]["children"][0]["level"],
                "second_children": [c["text"] for c in tree[1]["children"]],
            }
            """ % html
        )
        assert res["roots"] == ["First", "Second"], \
            "two h2 headings must each be roots, got %r" % res["roots"]
        assert res["root_levels"] == [2, 2], "root levels must be 2, got %r" % res["root_levels"]
        assert res["first_children"] == ["Deep"], \
            "h4 must nest under the preceding h2 despite skipped h3, got %r" % res["first_children"]
        assert res["first_child_level"] == 4, "skipped-level child must keep level 4"
        assert res["second_children"] == ["Sub"], \
            "h3 must nest under the second h2 root, got %r" % res["second_children"]

    def test_nest_outline_repeated_levels_are_siblings(self):
        """Repeated equal levels under a parent become siblings, order preserved."""
        html = "<h1>R</h1><h2>A</h2><h2>B</h2><h2>C</h2>"
        res = _run_driver(
            """
            HTML = %r
            tree = nest_outline(HTML)
            RESULT = {"roots": len(tree),
                      "children": [c["text"] for c in tree[0]["children"]]}
            """ % html
        )
        assert res["roots"] == 1, "single h1 must be the only root, got %r" % res["roots"]
        assert res["children"] == ["A", "B", "C"], \
            "equal-level headings must be ordered siblings, got %r" % res["children"]

    def test_nest_outline_empty_document(self):
        """A document with no headings yields an empty list of roots."""
        res = _run_driver(
            """
            RESULT = nest_outline("<html><body><p>none</p></body></html>")
            """
        )
        assert res == [], "no-heading document must yield [], got %r" % res

    # ------------------------------------------------------------------
    # L2: malformed-HTML tolerance (cross-cutting requirement)
    # ------------------------------------------------------------------

    def test_malformed_html_tolerated(self):
        """Unclosed / misnested heading markup must still parse without raising."""
        malformed = "<h1>Top<h2 id=mid>Mid<h3>Bot</h2></h1>"
        res = _run_driver(
            """
            HTML = %r
            hs = headings(HTML)
            RESULT = {
                "levels": [h["level"] for h in hs],
                "texts": [h["text"] for h in hs],
                "anchors": [e["anchor"] for e in table_of_contents(HTML)],
            }
            """ % malformed
        )
        assert res["levels"] == [1, 2, 3], \
            "all three recoverable headings must be found, got %r" % res["levels"]
        # First heading's text begins with "Top" (parser recovery may nest others
        # inside it depending on html.parser behaviour); assert the structural
        # contract that matters: levels recovered and the id-bearing anchor used.
        assert "mid" in res["anchors"], \
            "id-bearing heading in malformed markup must use its id anchor, got %r" % res["anchors"]

    # ------------------------------------------------------------------
    # L2: native acceptance command
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The Agent's own bs4/tests/test_outline.py must collect and pass green."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "bs4/tests/test_outline.py", "-v"],
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
            "test_outline.py collected no tests:\n" + proc.stdout
        assert " passed" in proc.stdout, \
            "expected at least one passing test in native suite:\n" + proc.stdout
