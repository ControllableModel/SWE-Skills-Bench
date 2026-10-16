"""
Test for the 'beautifulsoup-parsing' skill (variant ext2) — DOM Ancestry and
Sibling Navigation Module.

Verifies the Agent created a self-contained navigation utility at
``bs4/navigate.py`` exposing ``breadcrumb``, ``nearest_ancestor``,
``siblings_of`` and ``depth_of``, plus an accompanying test file
``bs4/tests/test_navigate.py``.

Strategy
--------
* L1 checks the two deliverable files exist and the module is importable and
  exposes the four public callables.
* L2 drives the Agent's *actual* module independently of any test file the
  Agent itself may have written: a tiny JSON-emitting driver is written into
  REPO_DIR, executed with the repo's own Python interpreter (cwd=REPO_DIR so
  ``import bs4.navigate`` resolves), and the emitted plain-data structures are
  deep-validated against the requirement's contract.  Each fixture is built so
  that a hardcoded / look-alike implementation (one that returns a fixed value,
  ignores its inputs, includes text nodes, or counts the wrong direction)
  fails.  Cases cover ancestor-chain ordering, closest-tag+class ancestor
  selection, sibling separation with intervening whitespace, depth counting,
  malformed-HTML tolerance, and every missing-target branch.
* One L2 case runs the native acceptance command
  (``python -m pytest bs4/tests/test_navigate.py -v``).
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
    Python so ``import bs4.navigate`` resolves, and return the parsed JSON that
    the driver prints to stdout.

    The driver imports the Agent's real module — there is no stubbing — so the
    returned data reflects genuine traversal behaviour.
    """
    driver_dir = os.path.join(REPO_DIR, "_skill_driver_tmp")
    os.makedirs(driver_dir, exist_ok=True)
    driver_path = os.path.join(driver_dir, "drv.py")

    header = textwrap.dedent(
        """
        import json, sys, os
        sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
        from bs4.navigate import breadcrumb, nearest_ancestor, siblings_of, depth_of
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


# A nested document used by several cases.  Note intentional whitespace and
# text nodes between elements, plus comments, so traversals that include text
# nodes or comments will produce wrong answers.
NESTED_HTML = """
<html>
  <body>
    <div id="outer" class="container main">
      <!-- a comment that must never appear in any traversal -->
      some loose text
      <section class="wrap">
        <article class="box card" id="art">
          <div class="inner card">
            <p id="target" class="leaf">hello <b>world</b></p>
          </div>
        </article>
      </section>
    </div>
  </body>
</html>
"""

# A flat sibling fixture: two element siblings before the target, one after,
# with whitespace and a comment interleaved.
SIBLING_HTML = """
<ul id="list">
  <li id="a">A</li>
  text-between
  <li id="b">B</li>
  <!-- comment -->
  <li id="target">T</li>
  <li id="c">C</li>
</ul>
"""


class TestBeautifulsoupParsing:
    """Validate the DOM ancestry / sibling navigation module and its behaviour."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are importable
    # ------------------------------------------------------------------

    def test_navigate_module_file_exists(self):
        """bs4/navigate.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "navigate.py")), \
            "bs4/navigate.py was not created"

    def test_navigate_test_file_exists(self):
        """bs4/tests/test_navigate.py must exist."""
        assert os.path.isfile(
            os.path.join(REPO_DIR, "bs4", "tests", "test_navigate.py")
        ), "bs4/tests/test_navigate.py was not created"

    def test_module_exposes_public_callables(self):
        """The module must import cleanly and expose the four public functions."""
        res = _run_driver(
            """
            RESULT = {
                "breadcrumb": callable(breadcrumb),
                "nearest_ancestor": callable(nearest_ancestor),
                "siblings_of": callable(siblings_of),
                "depth_of": callable(depth_of),
            }
            """
        )
        assert res == {
            "breadcrumb": True,
            "nearest_ancestor": True,
            "siblings_of": True,
            "depth_of": True,
        }, "navigate.py must define callable breadcrumb/nearest_ancestor/siblings_of/depth_of"

    # ------------------------------------------------------------------
    # L2: breadcrumb behaviour
    # ------------------------------------------------------------------

    def test_breadcrumb_full_ancestor_chain_ordering(self):
        """breadcrumb returns the tag chain top-to-bottom, ending at the target tag."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = breadcrumb(HTML, "target")
            """ % NESTED_HTML
        )
        assert isinstance(res, list), "breadcrumb must return a list"
        # Top-to-bottom: every element ancestor then the target's own tag last.
        # html > body > div > section > article > div > p
        assert res[-1] == "p", "breadcrumb must end with the target's own tag, got %r" % res
        # Ordering invariant: outer tags precede inner tags.
        assert res.index("div") < res.index("section") < res.index("article"), \
            "ancestors must be top-to-bottom ordered, got %r" % res
        assert "section" in res and "article" in res, \
            "every enclosing element tag must appear, got %r" % res
        # Text nodes / comments must never leak in.
        assert all(t.isidentifier() or "-" in t for t in res), \
            "only element tag names may appear, got %r" % res
        # The two 'div' levels (outer + inner) must both be represented.
        assert res.count("div") == 2, \
            "both enclosing div levels must appear in the chain, got %r" % res

    def test_breadcrumb_simple_example_from_doc(self):
        """The doc's <div><section><p id='t'> example: chain ends 'p', contains section/div."""
        html = '<div><section><p id="t">x</p></section></div>'
        res = _run_driver(
            """
            RESULT = breadcrumb(%r, "t")
            """ % html
        )
        assert res[-1] == "p", "chain must end with 'p', got %r" % res
        assert "section" in res and "div" in res, "chain must contain section and div, got %r" % res
        assert res.index("div") < res.index("section") < res.index("p"), \
            "div must precede section must precede p, got %r" % res

    def test_breadcrumb_missing_target_returns_empty_list(self):
        """A missing id yields [] (and never raises)."""
        res = _run_driver(
            """
            RESULT = breadcrumb(%r, "does-not-exist")
            """ % NESTED_HTML
        )
        assert res == [], "missing target must yield [], got %r" % res

    # ------------------------------------------------------------------
    # L2: nearest_ancestor behaviour
    # ------------------------------------------------------------------

    def test_nearest_ancestor_picks_closest_matching_tag_and_class(self):
        """nearest_ancestor returns the CLOSEST div carrying class 'card', not a farther one."""
        # Both the inner <div class="inner card"> and the outer <article class="box card">
        # carry 'card'; only the inner one is a <div>.  With tag_name='div',class='card'
        # the closest matching ancestor is the inner div (which has no id).
        res = _run_driver(
            """
            HTML = %r
            RESULT = nearest_ancestor(HTML, "target", "div", "card")
            """ % NESTED_HTML
        )
        assert isinstance(res, dict), "nearest_ancestor must return a dict on match, got %r" % res
        assert set(res.keys()) == {"id", "classes"}, \
            "match dict must have exactly keys id/classes, got %r" % sorted(res.keys())
        assert res["id"] is None, \
            "closest div.card (the inner div) has no id -> None, got %r" % res["id"]
        assert res["classes"] == ["inner", "card"], \
            "classes must be in attribute order for the closest match, got %r" % res["classes"]

    def test_nearest_ancestor_outer_match_when_inner_lacks_class(self):
        """When the inner wrapper lacks the class, the outer one (with id) is returned."""
        html = (
            '<div class="outer card" id="o">'
            '<div class="inner"><p id="t">x</p></div>'
            '</div>'
        )
        res = _run_driver(
            """
            RESULT = nearest_ancestor(%r, "t", "div", "card")
            """ % html
        )
        assert res == {"id": "o", "classes": ["outer", "card"]}, \
            "must return the outer div.card info (id 'o'), got %r" % res

    def test_nearest_ancestor_no_match_returns_none(self):
        """No ancestor matches tag+class -> None (not an empty dict)."""
        res = _run_driver(
            """
            RESULT = nearest_ancestor(%r, "target", "span", "card")
            """ % NESTED_HTML
        )
        assert res is None, "no <span class=card> ancestor must yield None, got %r" % res

    def test_nearest_ancestor_missing_target_returns_none(self):
        """A missing target id yields None."""
        res = _run_driver(
            """
            RESULT = nearest_ancestor(%r, "nope", "div", "card")
            """ % NESTED_HTML
        )
        assert res is None, "missing target must yield None, got %r" % res

    # ------------------------------------------------------------------
    # L2: siblings_of behaviour
    # ------------------------------------------------------------------

    def test_siblings_separated_ignoring_whitespace_and_comments(self):
        """previous/next list element siblings in order, excluding text/comments/self."""
        res = _run_driver(
            """
            RESULT = siblings_of(%r, "target")
            """ % SIBLING_HTML
        )
        assert isinstance(res, dict), "siblings_of must return a dict"
        assert set(res.keys()) == {"previous", "next"}, \
            "dict must have exactly keys previous/next, got %r" % sorted(res.keys())
        # Two <li> before (a, b), one after (c); all are <li> elements.
        assert res["previous"] == ["li", "li"], \
            "two element siblings before target expected, got %r" % res["previous"]
        assert res["next"] == ["li"], \
            "one element sibling after target expected, got %r" % res["next"]

    def test_siblings_distinct_tag_names_preserved(self):
        """Sibling tag names are reported as-is (not collapsed) and in document order."""
        html = (
            '<div id="p">'
            '<h1 id="h">H</h1> txt '
            '<span id="s">S</span>'
            '<a id="target">T</a>'
            '<img id="i"/>'
            '<p id="last">P</p>'
            '</div>'
        )
        res = _run_driver(
            """
            RESULT = siblings_of(%r, "target")
            """ % html
        )
        assert res["previous"] == ["h1", "span"], \
            "previous siblings must be [h1, span] in order, got %r" % res["previous"]
        assert res["next"] == ["img", "p"], \
            "next siblings must be [img, p] in order, got %r" % res["next"]

    def test_siblings_missing_target_returns_empty_dict(self):
        """A missing target yields {'previous': [], 'next': []}."""
        res = _run_driver(
            """
            RESULT = siblings_of(%r, "ghost")
            """ % SIBLING_HTML
        )
        assert res == {"previous": [], "next": []}, \
            "missing target must yield empty-sibling dict, got %r" % res

    # ------------------------------------------------------------------
    # L2: depth_of behaviour
    # ------------------------------------------------------------------

    def test_depth_counts_element_ancestors(self):
        """depth_of counts the number of element ancestors strictly above the target."""
        # html > body > div > section > article > div > p(target)
        # Element ancestors above target: html, body, div, section, article, div = 6.
        res = _run_driver(
            """
            RESULT = depth_of(%r, "target")
            """ % NESTED_HTML
        )
        assert res == 6, \
            "target has 6 element ancestors (html/body/div/section/article/div), got %r" % res

    def test_depth_top_level_child_is_one(self):
        """An element whose only enclosing element is the top tag has depth 1."""
        html = '<div><p id="t">x</p></div>'
        res = _run_driver(
            """
            RESULT = depth_of(%r, "t")
            """ % html
        )
        assert res == 1, "single enclosing top element -> depth 1, got %r" % res

    def test_depth_three_levels_below_top(self):
        """An element three element-levels below the top tag returns 3."""
        html = '<div><section><span><p id="t">x</p></span></section></div>'
        res = _run_driver(
            """
            RESULT = depth_of(%r, "t")
            """ % html
        )
        assert res == 3, "three element ancestors -> depth 3, got %r" % res

    def test_depth_missing_target_returns_negative_one(self):
        """A missing target yields -1."""
        res = _run_driver(
            """
            RESULT = depth_of(%r, "absent")
            """ % NESTED_HTML
        )
        assert res == -1, "missing target must yield -1, got %r" % res

    # ------------------------------------------------------------------
    # L2: malformed-HTML tolerance (cross-cutting requirement)
    # ------------------------------------------------------------------

    def test_malformed_html_tolerated_without_raising(self):
        """Unclosed/misnested markup still parses; traversals report element tags only."""
        malformed = (
            '<div id="outer"><section><p id="target">broken'
            '<span>tail'  # unclosed span and p
        )
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "crumb": breadcrumb(HTML, "target"),
                "depth": depth_of(HTML, "target"),
                "sibs": siblings_of(HTML, "target"),
            }
            """ % malformed
        )
        crumb = res["crumb"]
        assert isinstance(crumb, list) and crumb, \
            "malformed input must still yield a non-empty breadcrumb, got %r" % crumb
        assert crumb[-1] == "p", "breadcrumb must still end at target 'p', got %r" % crumb
        assert "div" in crumb and "section" in crumb, \
            "recoverable enclosing tags must appear, got %r" % crumb
        assert isinstance(res["depth"], int) and res["depth"] >= 1, \
            "depth must be a positive int for the recovered structure, got %r" % res["depth"]
        assert set(res["sibs"].keys()) == {"previous", "next"}, \
            "siblings dict shape must hold for malformed input, got %r" % res["sibs"]

    # ------------------------------------------------------------------
    # L2: native acceptance command
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The Agent's own bs4/tests/test_navigate.py must collect and pass green."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "bs4/tests/test_navigate.py", "-v"],
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
            "test_navigate.py collected no tests:\n" + proc.stdout
        assert " passed" in proc.stdout, \
            "expected at least one passing test in native suite:\n" + proc.stdout
