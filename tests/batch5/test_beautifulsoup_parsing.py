"""
Test for the 'beautifulsoup-parsing' skill (variant ext5) — RSS/Atom Feed
Parsing Module.

The Agent must create a self-contained syndication-feed parser at
``bs4/feed.py`` exposing ``feed_type``, ``feed_title``, ``feed_entries`` and
``entry_count``, plus an accompanying deterministic test file
``bs4/tests/test_feed.py``.  The module builds its tree with
``bs4.BeautifulSoup`` over an in-memory markup string (no network/file access,
no third-party parser package) and matches element names case-insensitively.

Verification strategy
---------------------
* L1 checks the two deliverable files exist and the module is importable and
  exposes the four public callables.
* L2 drives the Agent's *actual* module independently of any test file the
  Agent itself wrote: a tiny JSON-emitting driver is written into REPO_DIR and
  run with the repo's own Python (cwd=REPO_DIR so ``import bs4.feed`` resolves).
  The returned plain-data structures are deep-validated against the
  requirement's contract — feed-type detection, channel-vs-entry title scoping,
  RSS link-text vs Atom href extraction, missing-field defaults, the non-feed
  case, and malformed-input tolerance.  A hardcoded / look-alike solution that
  ignores the markup or confuses container/entry titles MUST fail these cases.
* One L2 case runs the native acceptance command
  (``python -m pytest bs4/tests/test_feed.py -v``).
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
    Python so that ``import bs4.feed`` resolves, and return the parsed JSON
    that the driver prints to stdout.

    The driver imports the Agent's real module — there is no stubbing — so the
    returned data reflects genuine parsing behaviour.
    """
    driver_dir = os.path.join(REPO_DIR, "_skill_feed_driver_tmp")
    os.makedirs(driver_dir, exist_ok=True)
    driver_path = os.path.join(driver_dir, "drv.py")

    header = textwrap.dedent(
        """
        import json, sys, os
        sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
        from bs4.feed import feed_type, feed_title, feed_entries, entry_count
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


# RSS feed with a channel title plus two items.  The second item is missing
# both <description> and <link>; the channel and the first item both carry a
# <title>, which exercises container-vs-entry title scoping.
RSS_HTML = """
<rss version="2.0">
  <channel>
    <title>  Example Channel  </title>
    <link>https://feed.example.com/</link>
    <description>Channel level description</description>
    <item>
      <title>First Post</title>
      <link>  https://feed.example.com/posts/1  </link>
      <description>Summary of the first post.</description>
    </item>
    <item>
      <title>Second Post</title>
    </item>
  </channel>
</rss>
"""

# Atom feed with a feed-level title and one entry.  The entry's link carries an
# empty <link href="..."> element (href is the source of truth, not text) and
# the summary comes from <summary>, not <description>.
ATOM_HTML = """
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Example</title>
  <link href="https://atom.example.com/"></link>
  <entry>
    <title>Atom Entry One</title>
    <link href="https://atom.example.com/e/1"></link>
    <summary>Atom entry summary.</summary>
  </entry>
</feed>
"""

NON_FEED_HTML = """
<html><body>
  <h1>Just a page</h1>
  <title>Page Title</title>
  <p>No syndication here.</p>
  <item><title>looks like an item but no channel/feed</title></item>
</body></html>
"""


class TestBeautifulsoupParsing:
    """Validate the RSS/Atom feed-parsing module and its behaviour."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist / importable
    # ------------------------------------------------------------------

    def test_feed_module_file_exists(self):
        """bs4/feed.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "feed.py")), \
            "bs4/feed.py was not created"

    def test_feed_test_file_exists(self):
        """bs4/tests/test_feed.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "tests", "test_feed.py")), \
            "bs4/tests/test_feed.py was not created"

    def test_module_exposes_public_callables(self):
        """The module must import cleanly and expose the four public functions."""
        res = _run_driver(
            """
            RESULT = {
                "feed_type": callable(feed_type),
                "feed_title": callable(feed_title),
                "feed_entries": callable(feed_entries),
                "entry_count": callable(entry_count),
            }
            """
        )
        assert res == {
            "feed_type": True,
            "feed_title": True,
            "feed_entries": True,
            "entry_count": True,
        }, "feed.py must define callable feed_type/feed_title/feed_entries/entry_count"

    # ------------------------------------------------------------------
    # L2: feed_type detection
    # ------------------------------------------------------------------

    def test_feed_type_detection(self):
        """RSS -> 'rss', Atom -> 'atom', non-feed -> None."""
        res = _run_driver(
            """
            RSS = %r
            ATOM = %r
            NONE = %r
            RESULT = {
                "rss": feed_type(RSS),
                "atom": feed_type(ATOM),
                "none": feed_type(NONE),
            }
            """ % (RSS_HTML, ATOM_HTML, NON_FEED_HTML)
        )
        assert res["rss"] == "rss", "document with <channel> must be 'rss', got %r" % res["rss"]
        assert res["atom"] == "atom", "document with <feed> only must be 'atom', got %r" % res["atom"]
        assert res["none"] is None, "non-feed document must be None, got %r" % res["none"]

    def test_feed_type_channel_wins_over_feed(self):
        """A document containing <channel> is RSS even if a <feed> tag also exists."""
        html = "<feed><channel><title>x</title></channel></feed>"
        res = _run_driver(
            """
            RESULT = feed_type(%r)
            """ % html
        )
        assert res == "rss", "presence of <channel> must classify as 'rss', got %r" % res

    def test_feed_type_case_insensitive(self):
        """Element matching is case-insensitive (<CHANNEL> / <FEED>)."""
        res = _run_driver(
            """
            RESULT = {
                "rss": feed_type("<RSS><CHANNEL><TITLE>x</TITLE></CHANNEL></RSS>"),
                "atom": feed_type("<FEED><TITLE>x</TITLE></FEED>"),
            }
            """
        )
        assert res["rss"] == "rss", "<CHANNEL> must be detected case-insensitively, got %r" % res["rss"]
        assert res["atom"] == "atom", "<FEED> must be detected case-insensitively, got %r" % res["atom"]

    # ------------------------------------------------------------------
    # L2: feed_title container scoping
    # ------------------------------------------------------------------

    def test_feed_title_rss_uses_channel_not_item(self):
        """RSS feed_title is the channel <title>, never an item <title>."""
        res = _run_driver(
            """
            RESULT = feed_title(%r)
            """ % RSS_HTML
        )
        assert res == "Example Channel", \
            "feed_title must be the stripped channel title, not an item title, got %r" % res

    def test_feed_title_atom_uses_feed_not_entry(self):
        """Atom feed_title is the feed-level <title>, never an entry <title>."""
        res = _run_driver(
            """
            RESULT = feed_title(%r)
            """ % ATOM_HTML
        )
        assert res == "Atom Example", \
            "feed_title must be the stripped feed-level title, not an entry title, got %r" % res

    def test_feed_title_defaults_empty(self):
        """No recognizable feed container -> feed_title == ''."""
        res = _run_driver(
            """
            RESULT = {
                "none": feed_title(%r),
                "no_title": feed_title("<rss><channel></channel></rss>"),
            }
            """ % NON_FEED_HTML
        )
        assert res["none"] == "", \
            "non-feed document must yield feed_title '', got %r" % res["none"]
        assert res["no_title"] == "", \
            "channel without a title must yield '', got %r" % res["no_title"]

    # ------------------------------------------------------------------
    # L2: entry_count
    # ------------------------------------------------------------------

    def test_entry_count(self):
        """entry_count: RSS items, Atom entries, non-feed -> 0."""
        res = _run_driver(
            """
            RESULT = {
                "rss": entry_count(%r),
                "atom": entry_count(%r),
                "none": entry_count(%r),
            }
            """ % (RSS_HTML, ATOM_HTML, NON_FEED_HTML)
        )
        assert res["rss"] == 2, "RSS feed has two <item> elements, got %r" % res["rss"]
        assert res["atom"] == 1, "Atom feed has one <entry> element, got %r" % res["atom"]
        assert res["none"] == 0, "non-feed document must yield 0, got %r" % res["none"]

    # ------------------------------------------------------------------
    # L2: feed_entries — RSS
    # ------------------------------------------------------------------

    def test_feed_entries_rss_structure_and_order(self):
        """RSS entries: one dict per item, document order, exact key set."""
        res = _run_driver(
            """
            RESULT = feed_entries(%r)
            """ % RSS_HTML
        )
        assert isinstance(res, list), "feed_entries must return a list"
        assert len(res) == 2, "expected two RSS entries, got %d" % len(res)
        for e in res:
            assert set(e.keys()) == {"title", "link", "summary"}, \
                "each entry dict must have exactly title/link/summary, got %r" % sorted(e.keys())
        assert [e["title"] for e in res] == ["First Post", "Second Post"], \
            "entries must be in document order, got %r" % [e["title"] for e in res]

    def test_feed_entries_rss_link_is_element_text(self):
        """RSS link is the stripped text of the entry's <link> element."""
        res = _run_driver(
            """
            RESULT = [e["link"] for e in feed_entries(%r)]
            """ % RSS_HTML
        )
        assert res[0] == "https://feed.example.com/posts/1", \
            "RSS link must be the stripped <link> text, got %r" % res[0]
        assert res[1] is None, \
            "RSS entry with no <link> must yield link None, got %r" % res[1]

    def test_feed_entries_rss_summary_from_description(self):
        """RSS summary comes from <description>; absent -> ''. """
        res = _run_driver(
            """
            RESULT = [e["summary"] for e in feed_entries(%r)]
            """ % RSS_HTML
        )
        assert res[0] == "Summary of the first post.", \
            "RSS summary must come from <description>, got %r" % res[0]
        assert res[1] == "", \
            "RSS entry missing <description> must yield summary '', got %r" % res[1]

    # ------------------------------------------------------------------
    # L2: feed_entries — Atom
    # ------------------------------------------------------------------

    def test_feed_entries_atom_link_is_href(self):
        """Atom link is the entry <link> href attribute, even when text is empty."""
        res = _run_driver(
            """
            entries = feed_entries(%r)
            RESULT = {
                "n": len(entries),
                "title": entries[0]["title"],
                "link": entries[0]["link"],
                "summary": entries[0]["summary"],
            }
            """ % ATOM_HTML
        )
        assert res["n"] == 1, "expected one Atom entry, got %r" % res["n"]
        assert res["title"] == "Atom Entry One", \
            "Atom entry title mis-parsed, got %r" % res["title"]
        assert res["link"] == "https://atom.example.com/e/1", \
            "Atom link must be the <link href> attribute, got %r" % res["link"]
        assert res["summary"] == "Atom entry summary.", \
            "Atom summary must come from <summary>, got %r" % res["summary"]

    def test_feed_entries_atom_missing_link_and_summary(self):
        """Atom entry with no <link>/<summary> -> link None, summary ''. """
        html = "<feed><title>F</title><entry><title>NoLink</title></entry></feed>"
        res = _run_driver(
            """
            RESULT = feed_entries(%r)[0]
            """ % html
        )
        assert res["link"] is None, \
            "Atom entry with no <link> must yield link None, got %r" % res["link"]
        assert res["summary"] == "", \
            "Atom entry with no <summary> must yield '', got %r" % res["summary"]
        assert res["title"] == "NoLink", \
            "Atom entry title mis-parsed, got %r" % res["title"]

    def test_feed_entries_atom_first_link_used(self):
        """When an Atom entry has multiple <link>s, the first one's href wins."""
        html = (
            "<feed><title>F</title><entry><title>Multi</title>"
            '<link rel="alternate" href="https://a.example.com/first"></link>'
            '<link rel="edit" href="https://a.example.com/second"></link>'
            "</entry></feed>"
        )
        res = _run_driver(
            """
            RESULT = feed_entries(%r)[0]["link"]
            """ % html
        )
        assert res == "https://a.example.com/first", \
            "Atom entry must use the first <link> href, got %r" % res

    # ------------------------------------------------------------------
    # L2: non-feed & malformed input
    # ------------------------------------------------------------------

    def test_non_feed_document_all_defaults(self):
        """Non-feed HTML yields the full documented default tuple."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "type": feed_type(HTML),
                "title": feed_title(HTML),
                "entries": feed_entries(HTML),
                "count": entry_count(HTML),
            }
            """ % NON_FEED_HTML
        )
        assert res["type"] is None, "non-feed feed_type must be None, got %r" % res["type"]
        assert res["title"] == "", "non-feed feed_title must be '', got %r" % res["title"]
        assert res["entries"] == [], "non-feed feed_entries must be [], got %r" % res["entries"]
        assert res["count"] == 0, "non-feed entry_count must be 0, got %r" % res["count"]

    def test_malformed_markup_does_not_raise(self):
        """Partially recoverable / unclosed markup must parse without raising."""
        malformed = (
            "<rss><channel><title>Broken Feed"
            "<item><title>Recoverable<link>https://m.example.com/1"
            "<description>partial"
            "<item><title>Second"
        )
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "type": feed_type(HTML),
                "count": entry_count(HTML),
                "titles": [e["title"] for e in feed_entries(HTML)],
            }
            """ % malformed
        )
        assert res["type"] == "rss", \
            "malformed RSS must still be detected as 'rss', got %r" % res["type"]
        assert res["count"] >= 1, \
            "malformed feed must still recover at least one entry, got %r" % res["count"]
        assert "Recoverable" in res["titles"], \
            "recoverable entry title must be parsed from malformed markup, got %r" % res["titles"]

    # ------------------------------------------------------------------
    # L2: native acceptance command
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The Agent's own bs4/tests/test_feed.py must collect and pass green."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "bs4/tests/test_feed.py", "-v"],
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
            "test_feed.py collected no tests:\n" + proc.stdout
        assert " passed" in proc.stdout, \
            "expected at least one passing test in native suite:\n" + proc.stdout
