"""
Test for the 'beautifulsoup-parsing' skill — Page Metadata Extraction Module
(variant ext9).

Verifies the Agent created a self-contained metadata-extraction module at
``bs4/meta.py`` exposing ``page_title``, ``meta_tags``, ``open_graph``,
``canonical_url`` and ``describe``, plus an accompanying test file
``bs4/tests/test_meta.py``.

This variant is DISTINCT from ext1 (which built an HTML *catalog* extractor with
``extract_cards`` / ``extract_table`` / ``extract_links``).  Here the module
reads the ``<head>`` of an HTML page and extracts SEO / link-preview metadata:
the title, ``<meta name=...>`` tags, Open Graph (``og:``) properties and the
canonical link, with URL resolution against a base URL.

Strategy
--------
* L1 checks the two deliverable files exist, the module is importable, and it
  exposes the five public callables.
* L2 drives the Agent's *actual* module independently of any test file the
  Agent itself may have written.  A tiny JSON-emitting driver is written into
  REPO_DIR, executed with the repo's own Python (cwd=REPO_DIR so
  ``import bs4.meta`` resolves), and the emitted plain-data structures are
  deep-validated against the requirement contract.  A naive / hardcoded
  implementation (e.g. one that ignores the input HTML, conflates ``name`` and
  ``property`` meta tags, fails to strip the ``og:`` prefix, ignores
  first-occurrence-wins, skips multi-token ``rel`` matching, or does not resolve
  relative URLs) cannot satisfy these fixtures.
* One L2 case also runs the native acceptance command
  (``python -m pytest bs4/tests/test_meta.py -v``).
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
    Python so that ``import bs4.meta`` resolves, and return the parsed JSON
    that the driver prints to stdout.

    The driver imports the Agent's real module — there is no stubbing — so the
    returned data reflects genuine parsing behaviour.
    """
    driver_dir = os.path.join(REPO_DIR, "_skill_driver_tmp")
    os.makedirs(driver_dir, exist_ok=True)
    driver_path = os.path.join(driver_dir, "drv_meta.py")

    header = textwrap.dedent(
        """
        import json, sys, os
        sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
        from bs4.meta import (
            page_title, meta_tags, open_graph, canonical_url, describe,
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


# A rich head exercising title normalization, name-vs-property separation,
# og prefix stripping, first-occurrence-wins, multi-token rel, and URL
# resolution.  The base URL has a path so relative resolution is observable.
PAGE_HTML = """
<html>
  <head>
    <title>   My   Awesome   Page  </title>
    <meta name="description" content="The meta description">
    <meta name="keywords" content="alpha, beta">
    <meta name="keywords" content="SECOND-should-lose">
    <meta name="robots">
    <meta property="og:title" content="OG Title Wins">
    <meta property="og:description" content="OG description loses">
    <meta property="og:image" content="/img/a.png">
    <meta property="og:image" content="/img/SECOND-should-lose.png">
    <meta property="og:type" content="article">
    <meta content="orphan-no-name-or-property">
    <link rel="alternate canonical" href="../home">
  </head>
  <body><p>hello</p></body>
</html>
"""

BASE_URL = "https://x.example.com/p/sub/"


# ----------------------------------------------------------------------------
# L1: deliverables exist and are importable
# ----------------------------------------------------------------------------

class TestBeautifulsoupParsing:
    """Validate the page metadata extraction module and its behaviour."""

    REPO_DIR = REPO_DIR

    def test_meta_module_file_exists(self):
        """bs4/meta.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "meta.py")), \
            "bs4/meta.py was not created"

    def test_meta_test_file_exists(self):
        """bs4/tests/test_meta.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "tests", "test_meta.py")), \
            "bs4/tests/test_meta.py was not created"

    def test_module_exposes_public_callables(self):
        """The module must import cleanly and expose the five public functions."""
        res = _run_driver(
            """
            RESULT = {
                "page_title": callable(page_title),
                "meta_tags": callable(meta_tags),
                "open_graph": callable(open_graph),
                "canonical_url": callable(canonical_url),
                "describe": callable(describe),
            }
            """
        )
        assert res == {
            "page_title": True,
            "meta_tags": True,
            "open_graph": True,
            "canonical_url": True,
            "describe": True,
        }, "meta.py must define all five callables: %r" % res

    # ------------------------------------------------------------------
    # L2: page_title behaviour
    # ------------------------------------------------------------------

    def test_page_title_whitespace_collapse(self):
        """Title text is stripped and internal whitespace collapsed to single spaces."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = page_title(HTML)
            """ % PAGE_HTML
        )
        assert res == "My Awesome Page", \
            "title must strip+collapse to 'My Awesome Page', got %r" % res

    def test_page_title_missing_returns_empty_string(self):
        """A document with no <title> yields the empty string (not None, no raise)."""
        res = _run_driver(
            """
            RESULT = page_title("<html><head></head><body>x</body></html>")
            """
        )
        assert res == "", "missing title must yield '', got %r" % res

    # ------------------------------------------------------------------
    # L2: meta_tags behaviour
    # ------------------------------------------------------------------

    def test_meta_tags_name_mapping_and_first_wins(self):
        """meta_tags maps name->content; first duplicate name wins; property tags excluded."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = meta_tags(HTML)
            """ % PAGE_HTML
        )
        assert isinstance(res, dict), "meta_tags must return a dict, got %r" % type(res)
        assert res.get("description") == "The meta description", \
            "description meta mis-read: %r" % res.get("description")
        assert res.get("keywords") == "alpha, beta", \
            "first duplicate keywords meta must win, got %r" % res.get("keywords")
        # <meta name="robots"> has no content attribute -> "".
        assert res.get("robots") == "", \
            "name meta without content must map to '', got %r" % res.get("robots")
        # og:* tags carry 'property', not 'name', and must NOT appear here.
        assert "title" not in res and "image" not in res and "type" not in res, \
            "property-based og meta must not leak into meta_tags: %r" % sorted(res)
        # The orphan tag (no name, no property) is ignored.
        assert "" not in res, "meta without a name attribute must be ignored: %r" % sorted(res)

    def test_meta_tags_empty_document(self):
        """No <meta name> tags -> empty dict."""
        res = _run_driver(
            """
            RESULT = meta_tags("<html><head><title>t</title></head></html>")
            """
        )
        assert res == {}, "document with no named meta must yield {}, got %r" % res

    # ------------------------------------------------------------------
    # L2: open_graph behaviour
    # ------------------------------------------------------------------

    def test_open_graph_prefix_strip_and_first_wins(self):
        """open_graph strips the 'og:' prefix, keeps first occurrence, excludes name meta."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = open_graph(HTML)
            """ % PAGE_HTML
        )
        assert isinstance(res, dict), "open_graph must return a dict, got %r" % type(res)
        assert res.get("title") == "OG Title Wins", \
            "og:title key must be 'title' with stripped prefix, got %r" % res.get("title")
        assert res.get("description") == "OG description loses", \
            "og:description mis-read: %r" % res.get("description")
        assert res.get("image") == "/img/a.png", \
            "first og:image must win and keep RAW (unresolved) content, got %r" % res.get("image")
        assert res.get("type") == "article", \
            "og:type mis-read: %r" % res.get("type")
        # Keys must have the og: prefix removed, never retained.
        assert not any(k.startswith("og:") for k in res), \
            "open_graph keys must not retain the 'og:' prefix: %r" % sorted(res)
        # name-based meta (description/keywords) must not be conflated in here as
        # og entries — they appear here only because og: counterparts exist.
        assert "keywords" not in res, \
            "name-only meta must not appear in open_graph: %r" % sorted(res)

    def test_open_graph_empty_document(self):
        """No og: meta -> empty dict."""
        res = _run_driver(
            """
            RESULT = open_graph('<meta name="description" content="x">')
            """
        )
        assert res == {}, "document with no og: meta must yield {}, got %r" % res

    # ------------------------------------------------------------------
    # L2: canonical_url behaviour
    # ------------------------------------------------------------------

    def test_canonical_url_multitoken_rel_and_resolution(self):
        """Multi-token rel='alternate canonical' matches; relative href resolved against base."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = canonical_url(HTML, %r)
            """ % (PAGE_HTML, BASE_URL)
        )
        # base "https://x.example.com/p/sub/" + "../home" -> ".../p/home"
        assert res == "https://x.example.com/p/home", \
            "canonical href '../home' must resolve against base to '/p/home', got %r" % res

    def test_canonical_url_simple_rel_and_absolute_href(self):
        """rel='canonical' matches; an already-absolute href is returned absolute."""
        html = '<link rel="canonical" href="https://canon.example.com/page">'
        res = _run_driver(
            """
            HTML = %r
            RESULT = canonical_url(HTML, %r)
            """ % (html, "https://other.example.com/base/")
        )
        assert res == "https://canon.example.com/page", \
            "absolute canonical href must be returned unchanged, got %r" % res

    def test_canonical_url_absent_and_hrefless(self):
        """No canonical link, or a canonical link without href, yields None."""
        res = _run_driver(
            """
            no_link = canonical_url("<html><head></head></html>", "https://x/")
            no_href = canonical_url('<link rel="canonical">', "https://x/")
            wrong_rel = canonical_url('<link rel="stylesheet" href="/a.css">', "https://x/")
            RESULT = {"no_link": no_link, "no_href": no_href, "wrong_rel": wrong_rel}
            """
        )
        assert res == {"no_link": None, "no_href": None, "wrong_rel": None}, \
            "missing/href-less/non-canonical link must each yield None, got %r" % res

    # ------------------------------------------------------------------
    # L2: describe behaviour (composition + preference rules)
    # ------------------------------------------------------------------

    def test_describe_full_page_preferences(self):
        """describe composes the 4 keys with og:title and meta description preferences, resolving image."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = describe(HTML, %r)
            """ % (PAGE_HTML, BASE_URL)
        )
        assert isinstance(res, dict), "describe must return a dict, got %r" % type(res)
        assert set(res.keys()) == {"title", "description", "canonical", "image"}, \
            "describe must return exactly these 4 keys, got %r" % sorted(res)
        # og:title present -> preferred over <title>.
        assert res["title"] == "OG Title Wins", \
            "describe must prefer og:title over page title, got %r" % res["title"]
        # meta description present -> preferred over og:description.
        assert res["description"] == "The meta description", \
            "describe must prefer meta description over og:description, got %r" % res["description"]
        # canonical resolved.
        assert res["canonical"] == "https://x.example.com/p/home", \
            "describe canonical must be resolved, got %r" % res["canonical"]
        # og:image resolved against base (first occurrence wins: /img/a.png).
        assert res["image"] == "https://x.example.com/p/img/a.png", \
            "describe image must be the resolved first og:image, got %r" % res["image"]

    def test_describe_title_falls_back_to_page_title(self):
        """With no og:title, describe falls back to page_title; og:description used if no meta description."""
        html = """
        <head>
          <title>  Plain  Title </title>
          <meta property="og:description" content="og desc only">
          <meta property="og:image" content="pic.png">
        </head>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = describe(HTML, %r)
            """ % (html, "https://host.example.com/dir/")
        )
        assert res["title"] == "Plain Title", \
            "describe must fall back to normalized page title, got %r" % res["title"]
        assert res["description"] == "og desc only", \
            "describe must fall back to og:description, got %r" % res["description"]
        assert res["canonical"] is None, \
            "no canonical link must give canonical None, got %r" % res["canonical"]
        assert res["image"] == "https://host.example.com/dir/pic.png", \
            "relative og:image must resolve against base, got %r" % res["image"]

    def test_describe_empty_page_defaults(self):
        """A page with no relevant tags yields the documented empty defaults."""
        res = _run_driver(
            """
            empty = describe("<html><head></head><body></body></html>", "https://x.example.com/")
            t = page_title("<html></html>")
            mt = meta_tags("<html></html>")
            og = open_graph("<html></html>")
            cu = canonical_url("<html></html>", "https://x.example.com/")
            RESULT = {"describe": empty, "title": t, "meta": mt, "og": og, "canonical": cu}
            """
        )
        assert res["describe"] == {
            "title": "",
            "description": "",
            "canonical": None,
            "image": None,
        }, "empty-page describe defaults wrong: %r" % res["describe"]
        assert res["title"] == "" and res["meta"] == {} and res["og"] == {} \
            and res["canonical"] is None, \
            "empty-page primitives must be ''/{}/{}/None, got %r" % res

    def test_malformed_html_does_not_raise(self):
        """Malformed / partially recoverable HTML must parse without raising."""
        malformed = (
            '<head><title>Broken'
            '<meta name="description" content="recovered desc"'
            '<meta property="og:image" content="/m/i.png"'
            '<link rel="canonical" href="../c">'
        )
        res = _run_driver(
            """
            HTML = %r
            base = "https://m.example.com/a/b/"
            RESULT = {
                "title": page_title(HTML),
                "meta": meta_tags(HTML),
                "og": open_graph(HTML),
                "canonical": canonical_url(HTML, base),
            }
            """ % malformed
        )
        # We do not over-constrain malformed recovery, but it must not crash and
        # must return the documented container types.
        assert isinstance(res["title"], str), "title must be str on malformed input"
        assert isinstance(res["meta"], dict), "meta_tags must be dict on malformed input"
        assert isinstance(res["og"], dict), "open_graph must be dict on malformed input"
        assert res["canonical"] is None or isinstance(res["canonical"], str), \
            "canonical_url must be None or str on malformed input, got %r" % res["canonical"]

    # ------------------------------------------------------------------
    # L2: native acceptance command
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The Agent's own bs4/tests/test_meta.py must collect and pass green."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "bs4/tests/test_meta.py", "-v"],
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
            "test_meta.py collected no tests:\n" + proc.stdout
        assert " passed" in proc.stdout, \
            "expected at least one passing test in native suite:\n" + proc.stdout
