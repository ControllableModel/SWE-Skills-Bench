"""
Test for the 'beautifulsoup-parsing' skill (variant ext7) — Link Auditing and
Classification Module.

Verifies the Agent created a self-contained link-auditing module at
``bs4/links.py`` exposing ``classify_links``, ``internal_links``,
``external_hosts`` and ``broken_anchor_targets``, plus an accompanying test
file ``bs4/tests/test_links.py``.

Strategy
--------
* L1 checks the two deliverable files exist and the module is importable and
  exposes the four public callables.
* L2 drives the Agent's *actual* module independently of any test file the
  Agent itself may have written: a tiny JSON-emitting driver is written into
  REPO_DIR, run with the repo's own Python interpreter (cwd=REPO_DIR so
  ``import bs4.links`` resolves), and the emitted plain-data structures are
  deep-validated against the requirement's contract.  Each ``kind`` branch and
  its precedence, relative/absolute URL resolution, internal dedup with order
  preservation, sorted external hosts, broken-vs-present anchor fragments, and
  omission of href-less anchors are exercised with concrete expected values.
  A hardcoded / look-alike solution that does not really parse and resolve the
  HTML cannot satisfy these fixtures.
* One L2 case also runs the native acceptance command
  (``python -m pytest bs4/tests/test_links.py -v``).
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
    Python so that ``import bs4.links`` resolves, and return the parsed JSON
    that the driver prints to stdout.

    The driver imports the Agent's real module — there is no stubbing — so the
    returned data reflects genuine parsing/classification behaviour.
    """
    driver_dir = os.path.join(REPO_DIR, "_skill_driver_tmp")
    os.makedirs(driver_dir, exist_ok=True)
    driver_path = os.path.join(driver_dir, "drv.py")

    header = textwrap.dedent(
        """
        import json, sys, os
        sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
        from bs4.links import (
            classify_links,
            internal_links,
            external_hosts,
            broken_anchor_targets,
        )
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


BASE_URL = "https://shop.example.com/catalog/"

# A page exercising every kind branch, relative/absolute resolution, dedup,
# external hosts, and broken-vs-present in-page anchors.
PAGE_HTML = """
<html>
  <body>
    <h2 id="top">Catalog</h2>
    <a href="item/9">relative internal</a>
    <a href="https://shop.example.com/catalog/item/9">same absolute internal dup</a>
    <a href="https://other.example.com/x">external one</a>
    <a href="https://other.example.com/y">external one again</a>
    <a href="https://second.example.org/z">external two</a>
    <a href="#section-2">in-page present</a>
    <a href="#missing-frag">in-page broken</a>
    <a href="">empty anchor</a>
    <a href="mailto:hi@x.com">mail me</a>
    <a name="noref">no href anchor</a>
    <div id="section-2">Section 2 body</div>
  </body>
</html>
"""


class TestBeautifulsoupParsing:
    """Validate the link-auditing/classification module and its behaviour."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are importable
    # ------------------------------------------------------------------

    def test_links_module_file_exists(self):
        """bs4/links.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "links.py")), \
            "bs4/links.py was not created"

    def test_links_test_file_exists(self):
        """bs4/tests/test_links.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "tests", "test_links.py")), \
            "bs4/tests/test_links.py was not created"

    def test_module_exposes_public_callables(self):
        """The module must import cleanly and expose the four public functions."""
        res = _run_driver(
            """
            RESULT = {
                "classify": callable(classify_links),
                "internal": callable(internal_links),
                "external": callable(external_hosts),
                "broken": callable(broken_anchor_targets),
            }
            """
        )
        assert res == {
            "classify": True,
            "internal": True,
            "external": True,
            "broken": True,
        }, "links.py must define callable classify_links/internal_links/external_hosts/broken_anchor_targets"

    # ------------------------------------------------------------------
    # L2: classify_links — shape, order, and href-less omission
    # ------------------------------------------------------------------

    def test_classify_shape_keys_and_count(self):
        """classify_links returns one dict per <a href>, in document order, with exactly 4 keys."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = classify_links(HTML, %r)
            """ % (PAGE_HTML, BASE_URL)
        )
        assert isinstance(res, list), "classify_links must return a list"
        # 9 anchors carry href; the <a name="noref"> has none and must be omitted.
        assert len(res) == 9, "expected 9 href-bearing links, got %d" % len(res)
        for d in res:
            assert set(d.keys()) == {"href", "resolved", "kind", "text"}, \
                "each link dict must have exactly keys href/resolved/kind/text, got %r" % sorted(d.keys())
        hrefs = [d["href"] for d in res]
        # Document order with the raw, unmodified href values; no href-less anchor.
        assert hrefs == [
            "item/9",
            "https://shop.example.com/catalog/item/9",
            "https://other.example.com/x",
            "https://other.example.com/y",
            "https://second.example.org/z",
            "#section-2",
            "#missing-frag",
            "",
            "mailto:hi@x.com",
        ], "raw hrefs must be in document order, href-less anchor omitted: %r" % hrefs

    def test_classify_kinds_and_precedence(self):
        """Each kind branch and the anchor/mailto precedence-over-host rules."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = {d["href"]: d["kind"] for d in classify_links(HTML, %r)}
            """ % (PAGE_HTML, BASE_URL)
        )
        assert res["item/9"] == "internal", \
            "relative same-host href must be internal, got %r" % res["item/9"]
        assert res["https://shop.example.com/catalog/item/9"] == "internal", \
            "absolute same-host href must be internal, got %r" % res
        assert res["https://other.example.com/x"] == "external", \
            "different-host href must be external, got %r" % res["https://other.example.com/x"]
        assert res["#section-2"] == "anchor", \
            "fragment href must classify as anchor, got %r" % res["#section-2"]
        assert res[""] == "anchor", \
            "empty href must classify as anchor, got %r" % res[""]
        assert res["mailto:hi@x.com"] == "mailto", \
            "mailto: href must classify as mailto, got %r" % res["mailto:hi@x.com"]

    def test_classify_resolution_relative_and_absolute(self):
        """resolved field: relative resolved against base; absolute unchanged."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = {d["href"]: d["resolved"] for d in classify_links(HTML, %r)}
            """ % (PAGE_HTML, BASE_URL)
        )
        assert res["item/9"] == "https://shop.example.com/catalog/item/9", \
            "relative href must resolve against base_url, got %r" % res["item/9"]
        assert res["https://other.example.com/x"] == "https://other.example.com/x", \
            "absolute external href must be unchanged, got %r" % res["https://other.example.com/x"]

    def test_classify_text_stripped_and_default(self):
        """text is the stripped visible text; '' when there is none."""
        html = """
        <body>
          <a href="/a">   Spaced   Text   </a>
          <a href="/b"></a>
          <a href="/c"><span> Nested </span></a>
        </body>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = {d["href"]: d["text"] for d in classify_links(HTML, %r)}
            """ % (html, "https://shop.example.com/")
        )
        assert res["/a"] == "Spaced   Text" or res["/a"] == "Spaced Text", \
            "leading/trailing whitespace must be stripped, got %r" % res["/a"]
        assert res["/a"].strip() == res["/a"] and res["/a"], \
            "text must be stripped and non-empty for a link with content, got %r" % res["/a"]
        assert res["/b"] == "", "link with no text must yield empty string, got %r" % res["/b"]
        assert res["/c"] == "Nested", \
            "nested-tag visible text must be stripped to 'Nested', got %r" % res["/c"]

    # ------------------------------------------------------------------
    # L2: internal_links — dedup with order preservation
    # ------------------------------------------------------------------

    def test_internal_links_dedup_order_preserved(self):
        """internal_links: resolved internal URLs, dedup, first-seen order preserved."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = internal_links(HTML, %r)
            """ % (PAGE_HTML, BASE_URL)
        )
        # 'item/9' and its absolute twin collapse to a single entry. In-page
        # anchors, mailto and external links are excluded.
        assert res == ["https://shop.example.com/catalog/item/9"], \
            "internal_links must collapse duplicates and exclude non-internal kinds, got %r" % res

    def test_internal_links_first_occurrence_kept(self):
        """Dedup keeps the first occurrence and overall document order."""
        html = """
        <body>
          <a href="b">b1</a>
          <a href="a">a1</a>
          <a href="b">b2 dup</a>
          <a href="https://other.example.com/x">ext</a>
          <a href="c">c1</a>
          <a href="a">a2 dup</a>
        </body>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = internal_links(HTML, %r)
            """ % (html, "https://shop.example.com/catalog/")
        )
        assert res == [
            "https://shop.example.com/catalog/b",
            "https://shop.example.com/catalog/a",
            "https://shop.example.com/catalog/c",
        ], "internal_links must keep first-seen order with duplicates removed, got %r" % res

    # ------------------------------------------------------------------
    # L2: external_hosts — sorted distinct hosts
    # ------------------------------------------------------------------

    def test_external_hosts_sorted_distinct(self):
        """external_hosts returns the sorted distinct hosts of external links only."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = external_hosts(HTML, %r)
            """ % (PAGE_HTML, BASE_URL)
        )
        assert res == ["other.example.com", "second.example.org"], \
            "external_hosts must be sorted distinct hosts of external links, got %r" % res

    def test_external_hosts_excludes_internal_and_special(self):
        """No internal/anchor/mailto host leaks into external_hosts; output stays sorted."""
        html = """
        <body>
          <a href="https://zeta.example.com/1">z</a>
          <a href="https://alpha.example.com/2">a</a>
          <a href="https://alpha.example.com/3">a dup host</a>
          <a href="local/page">internal</a>
          <a href="#frag">anchor</a>
          <a href="mailto:x@y.com">mail</a>
        </body>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = external_hosts(HTML, %r)
            """ % (html, "https://shop.example.com/catalog/")
        )
        assert res == ["alpha.example.com", "zeta.example.com"], \
            "external_hosts must be sorted, distinct, and exclude non-external links, got %r" % res

    # ------------------------------------------------------------------
    # L2: broken_anchor_targets
    # ------------------------------------------------------------------

    def test_broken_anchor_targets_detects_missing(self):
        """Fragment with no matching id is reported; fragment with matching id is not."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = broken_anchor_targets(HTML)
            """ % (PAGE_HTML,)
        )
        assert res == ["missing-frag"], \
            "only fragments without a matching id must be reported, got %r" % res

    def test_broken_anchor_targets_sorted_and_empty_when_all_present(self):
        """Result is sorted; a page where every in-page anchor resolves yields []."""
        broken_html = """
        <body>
          <a href="#zeta">z</a>
          <a href="#alpha">a</a>
          <a href="#mid">m</a>
          <div id="mid">present</div>
        </body>
        """
        ok_html = """
        <body>
          <a href="#one">1</a>
          <a href="#two">2</a>
          <h1 id="one">One</h1>
          <h2 id="two">Two</h2>
        </body>
        """
        res = _run_driver(
            """
            BROKEN = %r
            OK = %r
            RESULT = {
                "broken": broken_anchor_targets(BROKEN),
                "ok": broken_anchor_targets(OK),
            }
            """ % (broken_html, ok_html)
        )
        assert res["broken"] == ["alpha", "zeta"], \
            "broken targets must be sorted and exclude fragments with a matching id, got %r" % res["broken"]
        assert res["ok"] == [], \
            "a page where every in-page anchor resolves must yield [], got %r" % res["ok"]

    # ------------------------------------------------------------------
    # L2: robustness — malformed HTML and href-less omission
    # ------------------------------------------------------------------

    def test_hrefless_anchor_omitted_everywhere(self):
        """An <a> without href contributes to no output and never raises."""
        html = """
        <body>
          <a name="x">no href</a>
          <a>also no href</a>
          <a href="ok">internal</a>
        </body>
        """
        res = _run_driver(
            """
            HTML = %r
            base = "https://shop.example.com/catalog/"
            RESULT = {
                "n": len(classify_links(HTML, base)),
                "internal": internal_links(HTML, base),
                "external": external_hosts(HTML, base),
            }
            """ % (html,)
        )
        assert res["n"] == 1, "only the single href-bearing anchor must be classified, got %d" % res["n"]
        assert res["internal"] == ["https://shop.example.com/catalog/ok"], \
            "href-less anchors must not appear in internal_links, got %r" % res["internal"]
        assert res["external"] == [], "no external links expected, got %r" % res["external"]

    def test_tolerates_malformed_html(self):
        """Malformed/misnested markup must not raise and still recovers links."""
        malformed = (
            '<div><a href="x/1">one'
            '<a href="https://other.example.com/y">two'
            '<a href="#frag"><span>three'
            '<div id="frag"></div>'
        )
        res = _run_driver(
            """
            HTML = %r
            base = "https://shop.example.com/c/"
            classes = classify_links(HTML, base)
            RESULT = {
                "kinds": sorted({d["kind"] for d in classes}),
                "internal": internal_links(HTML, base),
                "external": external_hosts(HTML, base),
                "broken": broken_anchor_targets(HTML),
            }
            """ % (malformed,)
        )
        assert "internal" in res["kinds"] and "external" in res["kinds"], \
            "malformed input must still classify internal+external links, got %r" % res["kinds"]
        assert "https://shop.example.com/c/x/1" in res["internal"], \
            "relative link in malformed markup must resolve, got %r" % res["internal"]
        assert res["external"] == ["other.example.com"], \
            "external host must be recovered from malformed markup, got %r" % res["external"]
        assert res["broken"] == [], \
            "the #frag anchor has a matching id even in malformed markup, got %r" % res["broken"]

    # ------------------------------------------------------------------
    # L2: native acceptance command
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The Agent's own bs4/tests/test_links.py must collect and pass green."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "bs4/tests/test_links.py", "-v"],
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
            "test_links.py collected no tests:\n" + proc.stdout
        assert " passed" in proc.stdout, \
            "expected at least one passing test in native suite:\n" + proc.stdout
