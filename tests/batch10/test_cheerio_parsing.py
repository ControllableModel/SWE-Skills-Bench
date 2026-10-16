"""Tests for the `cheerio-parsing` skill (variant ext10).

Skill task (ext10): add a nested-list outline parser to the cheerio repo.

The agent must create ``src/api/outline.ts`` exporting a
``parseOutline(html, selector)`` function that loads ``html``, finds the first
``<ul>`` matching ``selector``, and returns a recursive tree of nodes. Each node
mirrors a *direct-child* ``<li>`` and has:

  * ``text``  -- the ``<li>``'s own immediate text, trimmed, EXCLUDING text
                 contributed by any nested ``<ul>`` (only the item's own label).
  * ``children`` -- an array of child nodes parsed from the first nested ``<ul>``
                 that is a direct child of the ``<li>`` (``[]`` for a leaf).

Only direct-child ``<li>`` of a ``<ul>`` become nodes; arbitrary nesting depth is
supported; a non-matching selector returns ``[]``.

Verification strategy
---------------------
  * L1 -- the deliverable files exist and are minimally well-formed
    (``src/api/outline.ts`` exports ``parseOutline``; ``outline.spec.ts`` exercises
    it; the source uses cheerio child-traversal rather than a regex hack).
  * L2 -- DYNAMIC EXECUTION: we drop an INDEPENDENT vitest spec into the repo's
    own ``src/api`` directory that imports the agent's real ``parseOutline``
    through ``./outline.js`` and asserts exact tree shapes with
    ``toStrictEqual``. A naive implementation (returning a flat list, including
    nested ``<ul>`` text in a parent's ``text``, treating grandchild ``<li>`` as
    direct children, hardcoding ``children: []``, or not honoring the selector)
    will fail these specs. We also run the agent's own ``outline.spec.ts``.

The agent edits the cheerio repo at REPO_DIR; the native acceptance command is
``npx vitest run src/api/outline.spec.ts``.
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
OUTLINE_TS = os.path.join(API_DIR, "outline.ts")
OUTLINE_SPEC = os.path.join(API_DIR, "outline.spec.ts")

# Independent spec we inject; distinct name so the repo's scoped typecheck does
# not gate it and so it never collides with the agent's own spec file.
INJECTED_SPEC_NAME = "outline_skillcheck.spec.ts"
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
    try:
        if os.path.isfile(INJECTED_SPEC_PATH):
            os.remove(INJECTED_SPEC_PATH)
    except OSError:
        pass


def _run_vitest(spec_relpath, timeout=600):
    """Run a single spec via vitest in JSON-reporter mode and parse the report."""
    cmd = [
        "npx",
        "vitest",
        "run",
        spec_relpath,
        "--reporter=json",
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
# Every it(...) maps to a requirement and has a stable, greppable title so the
# Python layer can assert on individual outcomes (not just an aggregate pass).
# The spec imports the agent's real parseOutline from './outline.js'.

_INJECTED_SPEC = r"""
import { describe, expect, it } from 'vitest';
import { parseOutline } from './outline.js';

const TWO_LEVEL =
  '<ul id="o"><li>A<ul><li>A1</li><li>A2</li></ul></li><li>B</li></ul>';

const THREE_LEVEL =
  '<ul id="o">' +
  '<li>A<ul><li>A1<ul><li>A1a</li></ul></li><li>A2</li></ul></li>' +
  '<li>B</li>' +
  '</ul>';

describe('parseOutline skillcheck', () => {
  it('SKILLCHECK two-level tree exact shape', () => {
    const out = parseOutline(TWO_LEVEL, '#o');
    expect(out).toStrictEqual([
      {
        text: 'A',
        children: [
          { text: 'A1', children: [] },
          { text: 'A2', children: [] },
        ],
      },
      { text: 'B', children: [] },
    ]);
  });

  it('SKILLCHECK three-level deeper tree exact shape', () => {
    const out = parseOutline(THREE_LEVEL, '#o');
    expect(out).toStrictEqual([
      {
        text: 'A',
        children: [
          { text: 'A1', children: [{ text: 'A1a', children: [] }] },
          { text: 'A2', children: [] },
        ],
      },
      { text: 'B', children: [] },
    ]);
  });

  it('SKILLCHECK leaf node has empty children array', () => {
    const out = parseOutline('<ul id="o"><li>Solo</li></ul>', '#o');
    expect(out).toStrictEqual([{ text: 'Solo', children: [] }]);
    expect(Array.isArray(out[0].children)).toBe(true);
    expect(out[0].children.length).toBe(0);
  });

  it('SKILLCHECK parent text excludes nested ul text', () => {
    const out = parseOutline(
      '<ul id="o"><li>Fruit<ul><li>Apple</li></ul></li></ul>',
      '#o',
    );
    // text must be exactly 'Fruit', NOT 'FruitApple'.
    expect(out[0].text).toBe('Fruit');
    expect(out).toStrictEqual([
      { text: 'Fruit', children: [{ text: 'Apple', children: [] }] },
    ]);
  });

  it('SKILLCHECK text is trimmed', () => {
    const out = parseOutline('<ul id="o"><li>   Spaced   </li></ul>', '#o');
    expect(out).toStrictEqual([{ text: 'Spaced', children: [] }]);
  });

  it('SKILLCHECK only direct-child li become top-level nodes', () => {
    // The top <ul> has exactly one direct-child <li> ('A'); 'A1'/'A2' are
    // grandchildren and must NOT appear at the top level.
    const out = parseOutline(TWO_LEVEL, '#o');
    expect(out.length).toBe(2);
    expect(out.map((n: any) => n.text)).toStrictEqual(['A', 'B']);
    // 'A1'/'A2' live under A, not at top level.
    expect(out[0].children.map((n: any) => n.text)).toStrictEqual(['A1', 'A2']);
  });

  it('SKILLCHECK missing selector returns empty array', () => {
    expect(parseOutline('<p>x</p>', 'ul')).toStrictEqual([]);
    expect(parseOutline('<ul id="o"><li>A</li></ul>', '#nope')).toStrictEqual(
      [],
    );
  });

  it('SKILLCHECK selects first matching ul only', () => {
    const html =
      '<ul class="o"><li>First</li></ul><ul class="o"><li>Second</li></ul>';
    const out = parseOutline(html, '.o');
    expect(out).toStrictEqual([{ text: 'First', children: [] }]);
  });

  it('SKILLCHECK only first nested ul of an li is used for children', () => {
    // An <li> with two direct nested <ul>s: only the first contributes children.
    const html =
      '<ul id="o"><li>P<ul><li>one</li></ul><ul><li>two</li></ul></li></ul>';
    const out = parseOutline(html, '#o');
    expect(out).toStrictEqual([
      { text: 'P', children: [{ text: 'one', children: [] }] },
    ]);
  });

  it('SKILLCHECK siblings each keep independent children', () => {
    const html =
      '<ul id="o">' +
      '<li>X<ul><li>x1</li></ul></li>' +
      '<li>Y<ul><li>y1</li><li>y2</li></ul></li>' +
      '<li>Z</li>' +
      '</ul>';
    const out = parseOutline(html, '#o');
    expect(out).toStrictEqual([
      { text: 'X', children: [{ text: 'x1', children: [] }] },
      {
        text: 'Y',
        children: [
          { text: 'y1', children: [] },
          { text: 'y2', children: [] },
        ],
      },
      { text: 'Z', children: [] },
    ]);
  });

  it('SKILLCHECK four-level nesting supported', () => {
    const html =
      '<ul id="o"><li>L1<ul><li>L2<ul><li>L3<ul><li>L4</li></ul></li></ul></li></ul></li></ul>';
    const out = parseOutline(html, '#o');
    expect(out).toStrictEqual([
      {
        text: 'L1',
        children: [
          {
            text: 'L2',
            children: [
              { text: 'L3', children: [{ text: 'L4', children: [] }] },
            ],
          },
        ],
      },
    ]);
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

    def test_l1_outline_source_exists(self):
        """L1: src/api/outline.ts exists and exports parseOutline."""
        assert os.path.isfile(OUTLINE_TS), f"missing {OUTLINE_TS}"
        content = open(OUTLINE_TS, encoding="utf-8").read()
        assert re.search(
            r"export\s+(?:async\s+)?function\s+parseOutline\b", content
        ) or re.search(
            r"export\s+(?:const|let)\s+parseOutline\b", content
        ) or re.search(
            r"export\s*\{[^}]*\bparseOutline\b", content
        ), "outline.ts must export a `parseOutline` symbol"
        assert len(content) > 200, "outline.ts unexpectedly small"

    def test_l1_outline_uses_cheerio_traversal(self):
        """L1: implementation loads cheerio and traverses children (not a regex)."""
        content = open(OUTLINE_TS, encoding="utf-8").read()
        # Must rely on cheerio's load + child traversal, signalling a real parse.
        assert re.search(r"\bload\b", content), (
            "outline.ts should use cheerio's load() to parse the HTML"
        )
        assert re.search(r"children|find|each|\.contents\(", content), (
            "outline.ts should traverse child <li>/<ul> elements"
        )

    def test_l1_spec_exists_and_exercises_parseoutline(self):
        """L1: outline.spec.ts exists and calls parseOutline."""
        assert os.path.isfile(OUTLINE_SPEC), f"missing {OUTLINE_SPEC}"
        content = open(OUTLINE_SPEC, encoding="utf-8").read()
        assert "parseOutline(" in content, "spec must call parseOutline(...)"

    def test_l1_spec_covers_required_cases(self):
        """L1: outline.spec.ts references the required scenarios from the doc."""
        content = open(OUTLINE_SPEC, encoding="utf-8").read()
        assert "children" in content, "spec must assert on node children"
        assert re.search(r"\[\s*\]", content) or "toStrictEqual([])" in content, (
            "spec should cover the empty-result / leaf case"
        )

    # ----------------------- L2: dynamic execution -----------------------

    def test_l2_injected_spec_runs_clean(self):
        """L2: the injected independent spec compiles and runs (vitest exit 0).

        This is the gate: it imports the agent's real parseOutline and asserts
        exact tree shapes. Any naive/stub implementation makes this non-zero.
        """
        result = _get_injected_result()
        assert result["returncode"] == 0, (
            "Injected vitest spec failed.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )

    def test_l2_two_level_tree(self):
        """L2: a two-level <ul> parses to the exact nested node tree."""
        _assert_titles_passed(
            _get_injected_result(),
            ["two-level tree exact shape"],
        )

    def test_l2_three_level_tree(self):
        """L2: a deeper three-level tree parses recursively to exact shape."""
        _assert_titles_passed(
            _get_injected_result(),
            ["three-level deeper tree exact shape"],
        )

    def test_l2_leaf_empty_children(self):
        """L2: a leaf <li> yields children: [] (an actual empty array)."""
        _assert_titles_passed(
            _get_injected_result(),
            ["leaf node has empty children array"],
        )

    def test_l2_parent_text_excludes_nested(self):
        """L2: a parent's text excludes nested <ul> text (Fruit, not FruitApple)."""
        _assert_titles_passed(
            _get_injected_result(),
            ["parent text excludes nested ul text"],
        )

    def test_l2_text_trimmed(self):
        """L2: each node's text is trimmed of surrounding whitespace."""
        _assert_titles_passed(
            _get_injected_result(),
            ["text is trimmed"],
        )

    def test_l2_direct_children_only(self):
        """L2: only direct-child <li> become top-level nodes; grandchildren nest."""
        _assert_titles_passed(
            _get_injected_result(),
            ["only direct-child li become top-level nodes"],
        )

    def test_l2_missing_selector_empty(self):
        """L2: a non-matching selector returns an empty array."""
        _assert_titles_passed(
            _get_injected_result(),
            ["missing selector returns empty array"],
        )

    def test_l2_first_matching_ul(self):
        """L2: only the first <ul> matching the selector is parsed."""
        _assert_titles_passed(
            _get_injected_result(),
            ["selects first matching ul only"],
        )

    def test_l2_first_nested_ul_for_children(self):
        """L2: only the first nested <ul> of an <li> contributes its children."""
        _assert_titles_passed(
            _get_injected_result(),
            ["only first nested ul of an li is used for children"],
        )

    def test_l2_siblings_independent_children(self):
        """L2: sibling nodes keep their own independent child subtrees."""
        _assert_titles_passed(
            _get_injected_result(),
            ["siblings each keep independent children"],
        )

    def test_l2_deep_nesting_supported(self):
        """L2: four-level nesting is parsed recursively to the exact shape."""
        _assert_titles_passed(
            _get_injected_result(),
            ["four-level nesting supported"],
        )

    def test_l2_native_acceptance_command_passes(self):
        """L2: the doc's native command `npx vitest run src/api/outline.spec.ts`
        passes against the agent's own spec and implementation."""
        rel = os.path.join("src", "api", "outline.spec.ts")
        result = _run_vitest(rel, timeout=600)
        assert result["returncode"] == 0, (
            "Native acceptance command must pass: "
            "npx vitest run src/api/outline.spec.ts\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )
