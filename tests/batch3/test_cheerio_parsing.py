"""Tests for the `cheerio-parsing` skill (variant ext3).

Skill task (ext3): add an absolute-link collector to the cheerio repo.

  * New module ``src/api/links.ts`` exporting
    ``collectLinks(html: string, baseUrl: string): string[]`` which loads
    ``html`` with cheerio, walks every ``<a>`` element in document order, and
    returns the list of ``href`` targets resolved to ABSOLUTE URLs against
    ``baseUrl`` (WHATWG URL resolution).
  * New spec ``src/api/links.spec.ts`` with deterministic cases.

Contract specifics that the implementation MUST honour:

  * Anchors with no ``href`` attribute are skipped.
  * Anchors with an empty (``""``) ``href`` are skipped.
  * Anchors whose ``href`` starts with ``#`` (fragment-only) are skipped.
  * Already-absolute hrefs are returned unchanged.
  * Relative hrefs are resolved against ``baseUrl``.
  * Hrefs that cannot be parsed even against the base are skipped (no throw).
  * Document order AND duplicates are preserved.

Verification strategy: this test runs AFTER the agent. We verify by:

  * L1 -- the deliverable files exist and are minimally well-formed.
  * L2 -- DYNAMIC EXECUTION: we drop an INDEPENDENT vitest spec into the repo's
    own ``src/api`` directory so it imports the real, freshly-built
    ``collectLinks`` through the module the agent created, and we assert on the
    pass/fail of individual, stably-titled ``it(...)`` cases. A naive
    implementation (returns a fixed array, ignores skip rules, drops order /
    duplicates, fails to resolve relative URLs, or throws on bad input) WILL
    fail these specs. We also run the agent's own ``links.spec.ts`` via the
    native acceptance command to confirm it passes.
"""

import json
import os
import re
import subprocess

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - fallback if helper not present
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/cheerio"
API_DIR = os.path.join(REPO_DIR, "src", "api")
LINKS_TS = os.path.join(API_DIR, "links.ts")
LINKS_SPEC = os.path.join(API_DIR, "links.spec.ts")

# Independent injected spec; distinct name so the repo's own typecheck scoping
# does not gate it and so we never clobber the agent's links.spec.ts.
INJECTED_SPEC_NAME = "links_skillcheck.spec.ts"
INJECTED_SPEC_PATH = os.path.join(API_DIR, INJECTED_SPEC_NAME)


@pytest.fixture(scope="module", autouse=True)
def _install_deps():
    """Install repo node dependencies once before any native test runs."""
    if ensure_npm_dependencies is not None:
        ensure_npm_dependencies(REPO_DIR)
    else:
        if not os.path.isdir(os.path.join(REPO_DIR, "node_modules")):
            cmd = (
                ["npm", "ci", "--legacy-peer-deps"]
                if os.path.isfile(os.path.join(REPO_DIR, "package-lock.json"))
                else ["npm", "install", "--legacy-peer-deps"]
            )
            subprocess.run(
                cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=1800
            )
    yield
    # Best-effort cleanup of the injected spec.
    try:
        if os.path.isfile(INJECTED_SPEC_PATH):
            os.remove(INJECTED_SPEC_PATH)
    except OSError:
        pass


def _run_vitest(spec_relpath, timeout=600):
    """Run a single spec via vitest in JSON-reporter mode and parse the report.

    Returns a dict with keys: returncode, stdout, stderr, report (parsed JSON or
    None), and `assertions` (flattened list of {title, status, messages}).
    """
    cmd = [
        "npx",
        "vitest",
        "run",
        spec_relpath,
        "--reporter=json",
        # Our injected spec is runtime-only; disable typecheck for ad-hoc runs.
        "--typecheck.enabled=false",
    ]
    proc = subprocess.run(
        cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=timeout
    )
    report = None
    out = proc.stdout
    start = out.find("{")
    end = out.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = out[start : end + 1]
        try:
            report = json.loads(candidate)
        except json.JSONDecodeError:
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        report = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
    assertions = []
    if report and isinstance(report.get("testResults"), list):
        for tr in report["testResults"]:
            for a in tr.get("assertionResults", []):
                assertions.append(
                    {
                        "title": a.get("title") or a.get("fullName") or "",
                        "fullName": a.get("fullName") or "",
                        "status": a.get("status"),
                        "messages": a.get("failureMessages") or [],
                    }
                )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "report": report,
        "assertions": assertions,
    }


# ---------------------------------------------------------------------------
# Injected independent spec content.
# ---------------------------------------------------------------------------
# Imports collectLinks from the agent's module via a relative path and exercises
# the full contract through it. Each it(...) maps to a requirement and carries a
# stable, greppable title so the Python layer can assert on individual outcomes,
# making partial / naive implementations detectable.

_INJECTED_SPEC = r"""
import { describe, expect, it } from 'vitest';
import { collectLinks } from './links.js';

const BASE = 'https://example.com/products/';

describe('links skillcheck (collectLinks)', () => {
  it('SKILLCHECK resolves relative and keeps absolute, skips fragment', () => {
    const html =
      '<a href="item1">a</a>' +
      '<a href="/help">b</a>' +
      '<a href="#top">c</a>' +
      '<a href="https://cdn.test/a">d</a>';
    const out = collectLinks(html, BASE);
    expect(out).toStrictEqual([
      'https://example.com/products/item1',
      'https://example.com/help',
      'https://cdn.test/a',
    ]);
  });

  it('SKILLCHECK skips anchors with no href attribute', () => {
    const html = '<a>no href</a><a href="x">y</a>';
    const out = collectLinks(html, BASE);
    expect(out).toStrictEqual(['https://example.com/products/x']);
  });

  it('SKILLCHECK skips anchors with empty href', () => {
    const html = '<a href="">empty</a><a href="x">y</a>';
    const out = collectLinks(html, BASE);
    expect(out).toStrictEqual(['https://example.com/products/x']);
  });

  it('SKILLCHECK skips fragment-only href', () => {
    const html = '<a href="#a">f1</a><a href="#section-2">f2</a>';
    const out = collectLinks(html, BASE);
    expect(out).toStrictEqual([]);
  });

  it('SKILLCHECK already-absolute href returned unchanged', () => {
    const html = '<a href="https://other.test/x?q=1#h">o</a>';
    const out = collectLinks(html, BASE);
    expect(out).toStrictEqual(['https://other.test/x?q=1#h']);
  });

  it('SKILLCHECK relative parent and root paths resolve against base', () => {
    const html =
      '<a href="about">x</a>' +
      '<a href="../up">y</a>' +
      '<a href="/root">z</a>';
    const out = collectLinks(html, BASE);
    expect(out).toStrictEqual([
      'https://example.com/products/about',
      'https://example.com/up',
      'https://example.com/root',
    ]);
  });

  it('SKILLCHECK preserves document order', () => {
    const html =
      '<a href="https://b.test/2">b</a>' +
      '<a href="https://a.test/1">a</a>' +
      '<a href="https://c.test/3">c</a>';
    const out = collectLinks(html, BASE);
    expect(out).toStrictEqual([
      'https://b.test/2',
      'https://a.test/1',
      'https://c.test/3',
    ]);
  });

  it('SKILLCHECK preserves duplicate targets', () => {
    const html =
      '<a href="dup">1</a>' +
      '<a href="dup">2</a>' +
      '<a href="https://x.test/dup">3</a>' +
      '<a href="https://x.test/dup">4</a>';
    const out = collectLinks(html, BASE);
    expect(out).toStrictEqual([
      'https://example.com/products/dup',
      'https://example.com/products/dup',
      'https://x.test/dup',
      'https://x.test/dup',
    ]);
  });

  it('SKILLCHECK only anchors are collected, nested anchors included', () => {
    const html =
      '<div><span href="ignore">not an a</span>' +
      '<p><a href="deep">deep</a></p></div>' +
      '<a href="top">top</a>';
    const out = collectLinks(html, BASE);
    expect(out).toStrictEqual([
      'https://example.com/products/deep',
      'https://example.com/products/top',
    ]);
  });

  it('SKILLCHECK unparseable href is skipped, not thrown', () => {
    // ':://' has no valid scheme and is not a valid relative reference that
    // resolves; it must be skipped rather than throwing. The valid neighbours
    // around it must still be collected.
    const html =
      '<a href="ok1">1</a>' +
      '<a href="http://[bad">bad</a>' +
      '<a href="ok2">2</a>';
    let out: string[] = [];
    expect(() => {
      out = collectLinks(html, BASE);
    }).not.toThrow();
    expect(out).toStrictEqual([
      'https://example.com/products/ok1',
      'https://example.com/products/ok2',
    ]);
  });

  it('SKILLCHECK empty document yields empty array', () => {
    expect(collectLinks('<div>no links here</div>', BASE)).toStrictEqual([]);
  });

  it('SKILLCHECK different base changes relative resolution', () => {
    const html = '<a href="x">x</a>';
    const out = collectLinks(html, 'https://other.example/deep/path/');
    expect(out).toStrictEqual(['https://other.example/deep/path/x']);
  });
});
"""


def _write_injected_spec():
    assert os.path.isdir(API_DIR), f"missing api dir: {API_DIR}"
    with open(INJECTED_SPEC_PATH, "w", encoding="utf-8") as fh:
        fh.write(_INJECTED_SPEC)


def _assert_titles_passed(result, required_substrings):
    """Assert each required title-substring exists and passed in vitest report."""
    if result["report"] is None:
        pytest.fail(
            "Could not parse vitest JSON report.\n"
            f"returncode={result['returncode']}\n"
            f"STDOUT(tail):\n{result['stdout'][-3000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )
    by_title = {a["title"]: a for a in result["assertions"]}
    for sub in required_substrings:
        match = next((a for t, a in by_title.items() if sub in t), None)
        assert match is not None, (
            f"Expected a test titled containing {sub!r}, but none ran. "
            f"Ran titles: {sorted(by_title)}"
        )
        assert match["status"] == "passed", (
            f"Test {match['title']!r} did not pass (status={match['status']}). "
            f"Messages: {match['messages']}"
        )


# Cache for the single injected-spec run, shared across L2 tests.
_INJECTED_RESULT = {}


def _get_injected_result():
    if "result" not in _INJECTED_RESULT:
        _write_injected_spec()
        rel = os.path.join("src", "api", INJECTED_SPEC_NAME)
        _INJECTED_RESULT["result"] = _run_vitest(rel, timeout=600)
    return _INJECTED_RESULT["result"]


class TestCheerioParsing:
    REPO_DIR = "/workspace/cheerio"

    # ----------------------- L1: deliverables exist -----------------------

    def test_l1_links_source_exists(self):
        """L1: src/api/links.ts exists and is non-trivial TypeScript."""
        assert os.path.isfile(LINKS_TS), f"missing {LINKS_TS}"
        content = open(LINKS_TS, encoding="utf-8").read()
        assert len(content) > 150, "links.ts unexpectedly small"

    def test_l1_links_exports_collect_links(self):
        """L1: links.ts exports a `collectLinks` symbol."""
        content = open(LINKS_TS, encoding="utf-8").read()
        assert re.search(r"\bexport\b", content), "links.ts must export something"
        assert "collectLinks" in content, (
            "links.ts must define/export `collectLinks`"
        )

    def test_l1_links_loads_cheerio_and_selects_anchors(self):
        """L1: the implementation loads cheerio and targets anchor elements."""
        content = open(LINKS_TS, encoding="utf-8").read()
        # Must use cheerio's load and select <a> elements somehow.
        assert re.search(r"\bload\b", content), (
            "links.ts must use cheerio's load() to parse the html"
        )
        assert re.search(r"['\"`]a['\"`]|<a|'a'|\"a\"", content) or "a[" in content, (
            "links.ts must select anchor (<a>) elements"
        )

    def test_l1_spec_exists_and_uses_collect_links(self):
        """L1: src/api/links.spec.ts exists and exercises collectLinks."""
        assert os.path.isfile(LINKS_SPEC), f"missing {LINKS_SPEC}"
        content = open(LINKS_SPEC, encoding="utf-8").read()
        assert "collectLinks" in content, (
            "links.spec.ts must call collectLinks(...)"
        )

    def test_l1_spec_covers_required_cases(self):
        """L1: links.spec.ts references the key contract scenarios."""
        content = open(LINKS_SPEC, encoding="utf-8").read()
        # Fragment skip + missing/empty href + duplicate/order are required by
        # the acceptance criteria; require the spec to mention them textually.
        assert "#" in content, "spec must cover a fragment-only href case"
        assert re.search(r"href\s*=\s*[\"']{2}|empty|no href|without href", content), (
            "spec must cover an empty/missing href case"
        )

    # ----------------------- L2: dynamic execution -----------------------

    def test_l2_injected_spec_runs_clean(self):
        """L2 gate: the injected independent spec compiles and passes (exit 0).

        If collectLinks is missing or naive, the behavioral assertions below
        drive a non-zero exit code here.
        """
        result = _get_injected_result()
        assert result["returncode"] == 0, (
            "Injected vitest spec failed.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )

    def test_l2_relative_absolute_fragment_mix(self):
        """L2: relative resolves, absolute kept, fragment skipped (doc example)."""
        _assert_titles_passed(
            _get_injected_result(),
            ["resolves relative and keeps absolute, skips fragment"],
        )

    def test_l2_missing_href_skipped(self):
        """L2: anchors without an href attribute are omitted."""
        _assert_titles_passed(
            _get_injected_result(),
            ["skips anchors with no href attribute"],
        )

    def test_l2_empty_href_skipped(self):
        """L2: anchors with an empty href are omitted."""
        _assert_titles_passed(
            _get_injected_result(),
            ["skips anchors with empty href"],
        )

    def test_l2_fragment_only_skipped(self):
        """L2: fragment-only (#...) hrefs are omitted entirely."""
        _assert_titles_passed(
            _get_injected_result(),
            ["skips fragment-only href"],
        )

    def test_l2_absolute_href_unchanged(self):
        """L2: an already-absolute href (with query/fragment) is returned as-is."""
        _assert_titles_passed(
            _get_injected_result(),
            ["already-absolute href returned unchanged"],
        )

    def test_l2_relative_path_resolution(self):
        """L2: relative, parent-relative, and root-relative paths resolve."""
        _assert_titles_passed(
            _get_injected_result(),
            ["relative parent and root paths resolve against base"],
        )

    def test_l2_document_order_preserved(self):
        """L2: results follow document order, not lexical/host order."""
        _assert_titles_passed(
            _get_injected_result(),
            ["preserves document order"],
        )

    def test_l2_duplicates_preserved(self):
        """L2: duplicate resolved targets are both kept."""
        _assert_titles_passed(
            _get_injected_result(),
            ["preserves duplicate targets"],
        )

    def test_l2_only_anchors_collected(self):
        """L2: only <a> elements (incl. nested) are collected; others ignored."""
        _assert_titles_passed(
            _get_injected_result(),
            ["only anchors are collected, nested anchors included"],
        )

    def test_l2_unparseable_href_skipped_not_thrown(self):
        """L2: an unparseable href is skipped without throwing; neighbours kept."""
        _assert_titles_passed(
            _get_injected_result(),
            ["unparseable href is skipped, not thrown"],
        )

    def test_l2_empty_and_base_sensitivity(self):
        """L2: empty doc -> [] and a different base changes resolution."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "empty document yields empty array",
                "different base changes relative resolution",
            ],
        )

    def test_l2_agent_links_spec_passes(self):
        """L2: the agent's own links.spec.ts passes via the native command.

        Mirrors the doc's acceptance command:
            npx vitest run src/api/links.spec.ts
        """
        rel = os.path.join("src", "api", "links.spec.ts")
        result = _run_vitest(rel, timeout=600)
        assert result["returncode"] == 0, (
            "Repo's links.spec.ts must pass under `vitest run`.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )
