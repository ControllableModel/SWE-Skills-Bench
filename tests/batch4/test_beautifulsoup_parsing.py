"""
Test for the 'beautifulsoup-parsing' skill (variant ext4) — Article Text
Extraction ("readability") Module.

Variant task
------------
The Agent must create a self-contained module at ``bs4/reader.py`` exposing
four public functions that turn a noisy HTML *string* into clean article text:

* ``clean_text(html)``       -> normalized visible text of the article root,
                                with <script>/<style>/<noscript>/<template>
                                content removed and whitespace collapsed.
* ``paragraphs(html)``       -> list[str] of cleaned text of each non-empty
                                <p> in the article root, document order.
* ``word_count(html)``       -> int, whitespace-delimited tokens of clean_text.
* ``first_paragraph(html)``  -> cleaned text of the first non-empty <p>, or "".

The "article root" is the first <article> if present, else <body>, else the
whole document. A companion test file ``bs4/tests/test_reader.py`` is also
required and is exercised by the native acceptance command.

Verification strategy
----------------------
* L1 — the two deliverable files exist and the module is importable and
  exposes the four documented callables.
* L2 — the Agent's *real* module is driven independently of the test file the
  Agent itself wrote: a tiny JSON-emitting driver is written into REPO_DIR and
  run with the repo's own Python (cwd=REPO_DIR so ``import bs4.reader``
  resolves). The emitted plain-data results are deep-validated against the
  requirement contract: noise-element removal, whitespace collapsing across
  nested inline tags, empty-paragraph omission, the article/body/document
  fallback chain, word counting, first_paragraph consistency, and malformed
  HTML tolerance. A stub that hardcodes output, ignores its input, or fails to
  strip script/style noise cannot satisfy these fixtures.
* One L2 case runs the native acceptance command
  ``python -m pytest bs4/tests/test_reader.py -v``.
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
    Python so that ``import bs4.reader`` resolves, and return the parsed JSON
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
        from bs4.reader import clean_text, paragraphs, word_count, first_paragraph
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


# An article with script noise interleaved between two paragraphs, a paragraph
# whose text spans nested inline tags with embedded newlines, and a paragraph
# that holds only a <style> block (no visible text -> must be omitted).
ARTICLE_HTML = """
<html><body>
  <nav>Home About Contact</nav>
  <article>
    <h1>The   Headline</h1>
    <p>First
        paragraph with <strong>bold</strong> and
        <a href="x">a link</a>.</p>
    <script>var leak = "DO NOT SHOW";\nconsole.log(leak);</script>
    <p>   Second   paragraph.   </p>
    <p><style>.x{color:red}</style></p>
    <noscript>enable js please</noscript>
    <template><p>shadow</p></template>
  </article>
  <footer>copyright stuff</footer>
</body></html>
"""


# ----------------------------------------------------------------------------
# L1: deliverables exist and are importable
# ----------------------------------------------------------------------------

class TestBeautifulsoupParsing:
    """Validate the article text-extraction (reader) module and its behaviour."""

    REPO_DIR = REPO_DIR

    def test_reader_module_file_exists(self):
        """bs4/reader.py must exist (L1 deliverable)."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "reader.py")), \
            "bs4/reader.py was not created"

    def test_reader_test_file_exists(self):
        """bs4/tests/test_reader.py must exist (L1 deliverable)."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "tests", "test_reader.py")), \
            "bs4/tests/test_reader.py was not created"

    def test_module_exposes_public_callables(self):
        """The module must import cleanly and expose the four public functions."""
        res = _run_driver(
            """
            RESULT = {
                "clean_text": callable(clean_text),
                "paragraphs": callable(paragraphs),
                "word_count": callable(word_count),
                "first_paragraph": callable(first_paragraph),
            }
            """
        )
        assert res == {
            "clean_text": True,
            "paragraphs": True,
            "word_count": True,
            "first_paragraph": True,
        }, "reader.py must define callable clean_text/paragraphs/word_count/first_paragraph"

    # ------------------------------------------------------------------
    # L2: clean_text behaviour
    # ------------------------------------------------------------------

    def test_clean_text_strips_noise_and_normalizes_whitespace(self):
        """
        clean_text must exclude <script>/<style>/<noscript>/<template> text and
        return a single-space-normalized string with no boilerplate leak.
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = clean_text(HTML)
            """ % ARTICLE_HTML
        )
        assert isinstance(res, str), "clean_text must return a str, got %r" % type(res)
        # No leading/trailing whitespace and no multi-space runs.
        assert res == res.strip(), "clean_text must not have leading/trailing whitespace: %r" % res
        assert "  " not in res, "clean_text must collapse internal whitespace runs: %r" % res
        assert "\n" not in res and "\t" not in res, \
            "clean_text must collapse newlines/tabs to single spaces: %r" % res
        # Script/style/noscript/template content must never leak.
        for leak in ("DO NOT SHOW", "console.log", "color:red", "enable js please", "shadow"):
            assert leak not in res, "noise content leaked into clean_text: %r in %r" % (leak, res)
        # Visible article text must be present.
        assert "The Headline" in res, "headline text missing/uncollapsed: %r" % res
        assert "First paragraph with bold and a link." in res, \
            "first paragraph text missing or not space-collapsed: %r" % res
        assert "Second paragraph." in res, "second paragraph text missing: %r" % res

    def test_clean_text_scoped_to_article_excludes_body_chrome(self):
        """
        When an <article> exists it is the root: <nav>/<footer> text outside the
        article must NOT appear in clean_text.
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = clean_text(HTML)
            """ % ARTICLE_HTML
        )
        assert "Home About Contact" not in res, \
            "nav chrome outside <article> must be excluded: %r" % res
        assert "copyright stuff" not in res, \
            "footer chrome outside <article> must be excluded: %r" % res

    def test_clean_text_body_fallback_when_no_article(self):
        """With no <article>, the root falls back to <body> (not the <head>)."""
        html = (
            "<html><head><title>TITLEONLY</title>"
            "<style>p{x}</style></head>"
            "<body><p>Body  para  here</p><span>tail</span></body></html>"
        )
        res = _run_driver(
            """
            HTML = %r
            RESULT = clean_text(HTML)
            """ % html
        )
        assert "TITLEONLY" not in res, "<head>/<title> must be outside the body root: %r" % res
        assert "Body para here" in res, "body text missing/uncollapsed: %r" % res
        assert "tail" in res, "non-paragraph body text must still be in clean_text: %r" % res
        assert res == res.strip() and "  " not in res, "whitespace not normalized: %r" % res

    def test_clean_text_empty_when_no_visible_text(self):
        """An article root with only noise/whitespace yields the empty string."""
        html = (
            "<article>   <script>junk()</script>\n\t"
            "<style>.a{b:c}</style>  </article>"
        )
        res = _run_driver(
            """
            HTML = %r
            RESULT = clean_text(HTML)
            """ % html
        )
        assert res == "", "noise-only article root must yield '', got %r" % res

    # ------------------------------------------------------------------
    # L2: paragraphs behaviour
    # ------------------------------------------------------------------

    def test_paragraphs_exact_list_and_order(self):
        """
        paragraphs returns exactly the cleaned non-empty <p> texts in document
        order; the style-only paragraph is omitted, nested-tag text collapsed.
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = paragraphs(HTML)
            """ % ARTICLE_HTML
        )
        assert isinstance(res, list), "paragraphs must return a list, got %r" % type(res)
        assert res == [
            "First paragraph with bold and a link.",
            "Second paragraph.",
        ], "paragraphs mis-extracted (order/whitespace/empty-omission): %r" % res

    def test_paragraphs_omits_whitespace_and_noise_only(self):
        """<p> elements containing only whitespace or only noise are omitted."""
        html = (
            "<article>"
            "<p>  </p>"
            "<p><script>x()</script></p>"
            "<p>Kept paragraph</p>"
            "<p>\n\t</p>"
            "</article>"
        )
        res = _run_driver(
            """
            HTML = %r
            RESULT = paragraphs(HTML)
            """ % html
        )
        assert res == ["Kept paragraph"], \
            "only the non-empty visible <p> should remain, got %r" % res

    def test_paragraphs_empty_when_none(self):
        """A document with no <p> yields an empty list (no raise)."""
        res = _run_driver(
            """
            RESULT = paragraphs("<article><h1>only a heading</h1></article>")
            """
        )
        assert res == [], "document with no <p> must yield [], got %r" % res

    # ------------------------------------------------------------------
    # L2: word_count behaviour
    # ------------------------------------------------------------------

    def test_word_count_matches_clean_text_tokens(self):
        """
        word_count equals the number of whitespace tokens of clean_text and
        excludes any script/style content.
        """
        res = _run_driver(
            """
            HTML = %r
            ct = clean_text(HTML)
            RESULT = {"wc": word_count(HTML), "tokens": len(ct.split())}
            """ % ARTICLE_HTML
        )
        assert res["wc"] == res["tokens"], \
            "word_count must equal len(clean_text.split()): %r" % res
        # "The Headline First paragraph with bold and a link. Second paragraph."
        assert res["wc"] == 11, "expected 11 visible tokens, got %r" % res["wc"]

    def test_word_count_simple_phrase_and_empty(self):
        """word_count('hello brave new world') -> 4; noise-only -> 0."""
        res = _run_driver(
            """
            html4 = "<article><p>hello   brave\\nnew\\tworld</p></article>"
            empty = "<article><script>noise()</script></article>"
            RESULT = {"four": word_count(html4), "zero": word_count(empty)}
            """
        )
        assert res["four"] == 4, "four-word phrase must count 4, got %r" % res["four"]
        assert res["zero"] == 0, "noise-only article must count 0, got %r" % res["zero"]

    # ------------------------------------------------------------------
    # L2: first_paragraph behaviour
    # ------------------------------------------------------------------

    def test_first_paragraph_consistent_with_list(self):
        """first_paragraph equals paragraphs(...)[0] when that list is non-empty."""
        res = _run_driver(
            """
            HTML = %r
            ps = paragraphs(HTML)
            RESULT = {"first": first_paragraph(HTML), "list0": ps[0] if ps else None}
            """ % ARTICLE_HTML
        )
        assert res["first"] == "First paragraph with bold and a link.", \
            "first_paragraph wrong: %r" % res["first"]
        assert res["first"] == res["list0"], \
            "first_paragraph must equal paragraphs(...)[0]: %r" % res

    def test_first_paragraph_skips_empty_paragraphs(self):
        """first_paragraph returns the first NON-empty <p>, skipping blank ones."""
        html = (
            "<article>"
            "<p>   </p>"
            "<p><style>.a{}</style></p>"
            "<p>Real   first   para</p>"
            "</article>"
        )
        res = _run_driver(
            """
            HTML = %r
            RESULT = first_paragraph(HTML)
            """ % html
        )
        assert res == "Real first para", \
            "first_paragraph must skip empty <p> and collapse whitespace, got %r" % res

    def test_first_paragraph_empty_when_none(self):
        """first_paragraph returns '' when there is no non-empty <p>."""
        res = _run_driver(
            """
            RESULT = first_paragraph("<article><h1>heading</h1><p>  </p></article>")
            """
        )
        assert res == "", "no non-empty <p> must yield '', got %r" % res

    # ------------------------------------------------------------------
    # L2: fallback chain + robustness
    # ------------------------------------------------------------------

    def test_document_fallback_when_no_article_or_body(self):
        """With neither <article> nor <body>, the whole document is the root."""
        html = "<p>loose paragraph</p><span>and tail</span>"
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "clean": clean_text(HTML),
                "paras": paragraphs(HTML),
                "first": first_paragraph(HTML),
            }
            """ % html
        )
        assert "loose paragraph" in res["clean"], \
            "document-level fallback must include loose text, got %r" % res["clean"]
        assert "and tail" in res["clean"], \
            "document-level fallback must include non-<p> text, got %r" % res["clean"]
        assert res["paras"] == ["loose paragraph"], \
            "document-level fallback must find the loose <p>, got %r" % res["paras"]
        assert res["first"] == "loose paragraph", \
            "first_paragraph on document fallback wrong: %r" % res["first"]

    def test_tolerates_malformed_html(self):
        """Unclosed / misnested markup must parse without raising and recover text."""
        malformed = (
            "<article><p>Para <strong>one "
            "<script>break()</script>"
            "<p>Para two <a href=z>link"
            "<style>.q{}</style>"
        )
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "clean": clean_text(HTML),
                "paras": paragraphs(HTML),
                "wc": word_count(HTML),
            }
            """ % malformed
        )
        assert "break()" not in res["clean"], \
            "script content must not leak from malformed markup: %r" % res["clean"]
        assert ".q{}" not in res["clean"] and "color" not in res["clean"], \
            "style content must not leak from malformed markup: %r" % res["clean"]
        assert res["clean"] == res["clean"].strip() and "  " not in res["clean"], \
            "malformed-recovery text must still be whitespace-normalized: %r" % res["clean"]
        assert len(res["paras"]) >= 2, \
            "both recoverable paragraphs expected from malformed markup, got %r" % res["paras"]
        assert any("Para one" in p for p in res["paras"]), \
            "first malformed paragraph text wrong: %r" % res["paras"]
        assert any("Para two" in p for p in res["paras"]), \
            "second malformed paragraph text wrong: %r" % res["paras"]
        assert res["wc"] == len(res["clean"].split()), \
            "word_count must stay consistent with clean_text on malformed input: %r" % res

    # ------------------------------------------------------------------
    # L2: native acceptance command
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The Agent's own bs4/tests/test_reader.py must collect and pass green."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "bs4/tests/test_reader.py", "-v"],
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
            "test_reader.py collected no tests:\n" + proc.stdout
        assert " passed" in proc.stdout, \
            "expected at least one passing test in native suite:\n" + proc.stdout
