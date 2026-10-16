"""Tests for the `cheerio-parsing` skill (variant ext7).

Skill task (ext7): add a NEW helper module ``src/api/deflist.ts`` exporting

    parseDefinitionList(html: string, selector: string)

that loads ``html``, finds the first element matching ``selector``, and flattens
an HTML description list (``<dl>`` of ``<dt>``/``<dd>`` pairs) into a key/value
record using cheerio sibling traversal:

  * each ``<dt>`` -> key = trimmed text;
  * the value is built from the ``<dd>`` element(s) immediately following that
    ``<dt>`` up to (but excluding) the next ``<dt>``:
      - exactly one following ``<dd>``  -> the trimmed string;
      - more than one following ``<dd>`` -> an array of trimmed strings in
        document order;
      - zero following ``<dd>``          -> the empty string ``''``;
  * a duplicate ``<dt>`` term -> the later occurrence overwrites the earlier;
  * a selector matching no element     -> ``{}``;
  * all terms and values are trimmed.

The agent edits the cheerio repo at REPO_DIR. After it finishes, this file is
run with pytest. We verify the behavior by:

  * L1 -- the deliverable files exist and are minimally well-formed
    (``src/api/deflist.ts`` exports the function; ``src/api/deflist.spec.ts``
    exercises it).
  * L2 -- DYNAMIC EXECUTION: we drop our OWN independent vitest spec into the
    repo's ``src/api`` directory (importing the freshly-compiled
    ``parseDefinitionList`` through ``./deflist.js``) and assert on the
    individual pass/fail results. A naive implementation -- one that returns a
    fixed value, never produces arrays, ignores trimming, ignores duplicate
    overwrite, or fails the missing-selector case -- fails these specs. We also
    re-run the agent's own ``deflist.spec.ts`` to confirm it passes, which is
    the variant's native acceptance command.

The native acceptance command driven by this file is:

    npx vitest run src/api/deflist.spec.ts
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
DEFLIST_TS = os.path.join(REPO_DIR, "src", "api", "deflist.ts")
DEFLIST_SPEC = os.path.join(REPO_DIR, "src", "api", "deflist.spec.ts")
API_DIR = os.path.join(REPO_DIR, "src", "api")

# Independent injected spec; named distinctly from deflist.spec.ts so it never
# collides with the agent's own file and is not gated by the repo's typecheck.
INJECTED_SPEC_NAME = "deflist_skillcheck.spec.ts"
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
    None), and `assertions` (flattened list of {title, status} dicts).
    """
    cmd = [
        "npx",
        "vitest",
        "run",
        spec_relpath,
        "--reporter=json",
        # Disable typecheck for ad-hoc runs; our injected spec is runtime-only.
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
# Exercises parseDefinitionList strictly through the agent's deliverable module.
# Each it(...) maps to a requirement and has a stable, greppable title so the
# Python layer can assert on individual outcomes (not just an aggregate pass),
# making partial/naive implementations detectable.

_INJECTED_SPEC = r"""
import { describe, expect, it } from 'vitest';
import { parseDefinitionList } from './deflist.js';

describe('parseDefinitionList skillcheck', () => {
  it('SKILLCHECK single dd yields string value', () => {
    const html = '<dl><dt>Color</dt><dd>Red</dd></dl>';
    expect(parseDefinitionList(html, 'dl')).toStrictEqual({ Color: 'Red' });
  });

  it('SKILLCHECK multiple dd yields array value in document order', () => {
    const html = '<dl><dt>Sizes</dt><dd>S</dd><dd>M</dd><dd>L</dd></dl>';
    expect(parseDefinitionList(html, 'dl')).toStrictEqual({
      Sizes: ['S', 'M', 'L'],
    });
  });

  it('SKILLCHECK doc example mixes string and array values', () => {
    const html =
      '<dl><dt>Color</dt><dd>Red</dd><dt>Sizes</dt><dd>S</dd><dd>M</dd></dl>';
    expect(parseDefinitionList(html, 'dl')).toStrictEqual({
      Color: 'Red',
      Sizes: ['S', 'M'],
    });
  });

  it('SKILLCHECK term with no dd before next dt maps to empty string', () => {
    const html = '<dl><dt>Empty</dt><dt>Filled</dt><dd>Yes</dd></dl>';
    expect(parseDefinitionList(html, 'dl')).toStrictEqual({
      Empty: '',
      Filled: 'Yes',
    });
  });

  it('SKILLCHECK trailing term with no dd at end of list maps to empty string', () => {
    const html = '<dl><dt>First</dt><dd>One</dd><dt>Last</dt></dl>';
    expect(parseDefinitionList(html, 'dl')).toStrictEqual({
      First: 'One',
      Last: '',
    });
  });

  it('SKILLCHECK duplicate term: later occurrence overwrites earlier', () => {
    const html =
      '<dl><dt>K</dt><dd>old</dd><dt>K</dt><dd>new1</dd><dd>new2</dd></dl>';
    expect(parseDefinitionList(html, 'dl')).toStrictEqual({
      K: ['new1', 'new2'],
    });
  });

  it('SKILLCHECK duplicate term can overwrite an array with a string', () => {
    const html =
      '<dl><dt>K</dt><dd>a</dd><dd>b</dd><dt>K</dt><dd>final</dd></dl>';
    expect(parseDefinitionList(html, 'dl')).toStrictEqual({ K: 'final' });
  });

  it('SKILLCHECK missing selector returns empty object', () => {
    expect(parseDefinitionList('<p>x</p>', 'dl')).toStrictEqual({});
  });

  it('SKILLCHECK empty dl returns empty object', () => {
    expect(parseDefinitionList('<dl></dl>', 'dl')).toStrictEqual({});
  });

  it('SKILLCHECK whitespace around terms and values is trimmed', () => {
    const html =
      '<dl><dt>  Name  </dt><dd>\n  Alice  \n</dd><dt> Tags </dt><dd>  x  </dd><dd>  y  </dd></dl>';
    expect(parseDefinitionList(html, 'dl')).toStrictEqual({
      Name: 'Alice',
      Tags: ['x', 'y'],
    });
  });

  it('SKILLCHECK only the first matching element is used', () => {
    const html =
      '<dl class="a"><dt>One</dt><dd>1</dd></dl>' +
      '<dl class="a"><dt>Two</dt><dd>2</dd></dl>';
    expect(parseDefinitionList(html, '.a')).toStrictEqual({ One: '1' });
  });

  it('SKILLCHECK arbitrary selector locates a nested dl', () => {
    const html =
      '<div><section id="meta"><dl><dt>A</dt><dd>1</dd>' +
      '<dt>B</dt><dd>2</dd></dl></section></div>';
    expect(parseDefinitionList(html, '#meta dl')).toStrictEqual({
      A: '1',
      B: '2',
    });
  });

  it('SKILLCHECK single-element array is not flattened to a string', () => {
    // A naive impl that always returns arrays, or always returns strings,
    // cannot satisfy both this and the multi-dd case simultaneously.
    const html = '<dl><dt>Solo</dt><dd>only</dd></dl>';
    const out = parseDefinitionList(html, 'dl');
    expect(out).toStrictEqual({ Solo: 'only' });
    expect(Array.isArray((out as any).Solo)).toBe(false);
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

    def test_l1_deflist_source_exists(self):
        """L1: src/api/deflist.ts exists and exports parseDefinitionList."""
        assert os.path.isfile(DEFLIST_TS), f"missing {DEFLIST_TS}"
        content = open(DEFLIST_TS, encoding="utf-8").read()
        assert re.search(
            r"export\s+(?:async\s+)?function\s+parseDefinitionList"
            r"|export\s+(?:const|let)\s+parseDefinitionList"
            r"|export\s*\{[^}]*\bparseDefinitionList\b",
            content,
        ), "deflist.ts must export parseDefinitionList"
        assert len(content) > 200, "deflist.ts unexpectedly small"

    def test_l1_deflist_uses_cheerio_traversal(self):
        """L1: deflist.ts loads markup and traverses dt/dd via cheerio."""
        content = open(DEFLIST_TS, encoding="utf-8").read()
        # Must actually parse HTML through cheerio, not regex-scrape.
        assert "load" in content, "deflist.ts must use cheerio's load()"
        assert "dt" in content and "dd" in content, (
            "deflist.ts must reference dt/dd elements"
        )

    def test_l1_deflist_spec_exists(self):
        """L1: src/api/deflist.spec.ts exists and exercises the function."""
        assert os.path.isfile(DEFLIST_SPEC), f"missing {DEFLIST_SPEC}"
        content = open(DEFLIST_SPEC, encoding="utf-8").read()
        assert "parseDefinitionList" in content, (
            "spec must exercise parseDefinitionList(...)"
        )

    def test_l1_spec_covers_required_cases(self):
        """L1: deflist.spec.ts references the required scenarios from the doc."""
        content = open(DEFLIST_SPEC, encoding="utf-8").read()
        # The doc requires coverage of: single-dd, multi-dd array, no-dd '',
        # duplicate overwrite, missing-selector {}, and whitespace trimming.
        assert content.count("parseDefinitionList") >= 4, (
            "spec should contain several parseDefinitionList scenarios"
        )

    # ----------------------- L2: dynamic execution -----------------------

    def test_l2_injected_spec_runs_clean(self):
        """L2: the injected independent spec compiles and runs (vitest exit 0).

        This is the gate: if parseDefinitionList is missing or its semantics are
        wrong, the behavioral assertions below fail and drive a non-zero exit.
        """
        result = _get_injected_result()
        assert result["returncode"] == 0, (
            "Injected vitest spec failed.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )

    def test_l2_single_dd_string(self):
        """L2: a single following dd yields the trimmed string value."""
        _assert_titles_passed(
            _get_injected_result(),
            ["single dd yields string value"],
        )

    def test_l2_multiple_dd_array_in_order(self):
        """L2: multiple following dd yield an array in document order."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "multiple dd yields array value in document order",
                "doc example mixes string and array values",
            ],
        )

    def test_l2_single_vs_array_discriminator(self):
        """L2: single value stays a string (not wrapped in an array).

        This pair of cases breaks any naive impl that always returns strings or
        always returns arrays.
        """
        _assert_titles_passed(
            _get_injected_result(),
            ["single-element array is not flattened to a string"],
        )

    def test_l2_no_dd_yields_empty_string(self):
        """L2: a term with no dd (mid-list or trailing) maps to ''."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "term with no dd before next dt maps to empty string",
                "trailing term with no dd at end of list maps to empty string",
            ],
        )

    def test_l2_duplicate_term_overwrite(self):
        """L2: a duplicate dt term lets the later occurrence overwrite."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "duplicate term: later occurrence overwrites earlier",
                "duplicate term can overwrite an array with a string",
            ],
        )

    def test_l2_missing_selector_empty_object(self):
        """L2: a selector matching nothing returns {} (and empty dl too)."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "missing selector returns empty object",
                "empty dl returns empty object",
            ],
        )

    def test_l2_whitespace_trimmed(self):
        """L2: whitespace around terms and values is trimmed."""
        _assert_titles_passed(
            _get_injected_result(),
            ["whitespace around terms and values is trimmed"],
        )

    def test_l2_first_match_only(self):
        """L2: only the first element matching the selector is used."""
        _assert_titles_passed(
            _get_injected_result(),
            ["only the first matching element is used"],
        )

    def test_l2_arbitrary_selector_nested(self):
        """L2: an arbitrary selector locates a nested dl correctly."""
        _assert_titles_passed(
            _get_injected_result(),
            ["arbitrary selector locates a nested dl"],
        )

    def test_l2_agent_deflist_spec_passes(self):
        """L2: the agent's own deflist.spec.ts passes (native acceptance command).

        Drives exactly `npx vitest run src/api/deflist.spec.ts`.
        """
        rel = os.path.join("src", "api", "deflist.spec.ts")
        result = _run_vitest(rel, timeout=600)
        assert result["returncode"] == 0, (
            "Agent's deflist.spec.ts must pass under "
            "`npx vitest run src/api/deflist.spec.ts`.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )
