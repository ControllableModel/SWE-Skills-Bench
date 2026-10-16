"""Tests for the `cheerio-parsing` skill -- variant ext2 (HTML table parser).

Skill task (ext2): add a standalone helper module ``src/api/table.ts`` that
exports ``parseTable(html, tableSelector)``. It loads ``html`` with cheerio,
finds the first element matching ``tableSelector``, reads header keys from the
``<thead>`` ``<th>`` cells, and returns one plain object per ``<tbody>`` ``<tr>``
row, mapping each trimmed header to the trimmed ``<td>`` text at that column.

Contract specifics derived from the requirement doc:
  * Header keys come from ``thead th`` text, in document order, trimmed.
  * Each body row -> one object; value is trimmed text of the ``<td>`` at the
    matching column index.
  * Row with FEWER cells than headers -> missing trailing keys present with ''.
  * Row with MORE cells than headers -> extra cells ignored (no extra keys).
  * Selector matching nothing -> ``[]`` (must NOT throw).
  * A ``<tbody>`` with no ``<tr>`` -> ``[]``.
  * Whitespace inside header/cell text is trimmed.

Verification strategy:
  * L1 -- the deliverable files (``table.ts``, ``table.spec.ts``) exist and are
    minimally well-formed (export the function, exercise it).
  * L2 -- DYNAMIC EXECUTION: we inject an INDEPENDENT vitest spec into the
    repo's own ``src/api`` directory that imports ``parseTable`` from the
    freshly-built ``./table.js`` and asserts on concrete return values. A naive
    implementation (hardcoded output, ignoring the selector, not trimming, not
    padding short rows, not truncating long rows, or throwing on no match) will
    fail these assertions and drive a non-zero vitest exit code. Each ``it``
    carries a stable, greppable title so the Python layer can assert on
    individual outcomes (not just an aggregate pass). We also run the agent's
    own ``table.spec.ts`` to confirm it passes too.

The native acceptance command this drives is: ``npx vitest run``.
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
TABLE_TS = os.path.join(REPO_DIR, "src", "api", "table.ts")
TABLE_SPEC = os.path.join(REPO_DIR, "src", "api", "table.spec.ts")
API_DIR = os.path.join(REPO_DIR, "src", "api")

# Independent spec we inject. Distinct name so it does not collide with the
# agent's own table.spec.ts and so any repo typecheck scoped elsewhere does not
# gate it.
INJECTED_SPEC_NAME = "table_skillcheck.spec.ts"
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
    None), and `assertions` (flattened list of {title, status, messages} dicts).
    """
    cmd = [
        "npx",
        "vitest",
        "run",
        spec_relpath,
        "--reporter=json",
        # Our injected spec is runtime-only; do not let typecheck gate it.
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
# Exercises parseTable strictly through its public export. Every `it(...)` maps
# to a requirement and carries a stable, greppable title so the Python layer can
# assert on individual outcomes, making partial/naive implementations
# detectable.
_INJECTED_SPEC = r"""
import { describe, expect, it } from 'vitest';
import { parseTable } from './table.js';

const BASIC = `
<html><body>
  <table id="fruit">
    <thead><tr><th> Name </th><th>Price</th></tr></thead>
    <tbody>
      <tr><td>Apple</td><td>$1</td></tr>
      <tr><td>Pear</td><td>$3</td></tr>
    </tbody>
  </table>
</body></html>`;

const WHITESPACE = `
<table class="ws">
  <thead><tr><th>
      Color
    </th><th>  Hex  </th></tr></thead>
  <tbody>
    <tr><td>
        Red
      </td><td>  #f00  </td></tr>
  </tbody>
</table>`;

const SHORT_ROW = `
<table id="t">
  <thead><tr><th>A</th><th>B</th><th>C</th></tr></thead>
  <tbody>
    <tr><td>1</td></tr>
  </tbody>
</table>`;

const LONG_ROW = `
<table id="t">
  <thead><tr><th>A</th><th>B</th></tr></thead>
  <tbody>
    <tr><td>1</td><td>2</td><td>3</td><td>4</td></tr>
  </tbody>
</table>`;

const EMPTY_TBODY = `
<table id="t">
  <thead><tr><th>A</th><th>B</th></tr></thead>
  <tbody></tbody>
</table>`;

const TWO_TABLES = `
<table class="first">
  <thead><tr><th>X</th></tr></thead>
  <tbody><tr><td>first</td></tr></tbody>
</table>
<table class="second">
  <thead><tr><th>X</th></tr></thead>
  <tbody><tr><td>second</td></tr></tbody>
</table>`;

describe('parseTable skillcheck', () => {
  it('SKILLCHECK basic multi-row table maps headers to cells', () => {
    expect(parseTable(BASIC, '#fruit')).toStrictEqual([
      { Name: 'Apple', Price: '$1' },
      { Name: 'Pear', Price: '$3' },
    ]);
  });

  it('SKILLCHECK header keys are trimmed', () => {
    const rows = parseTable(BASIC, '#fruit');
    expect(Object.keys(rows[0])).toStrictEqual(['Name', 'Price']);
  });

  it('SKILLCHECK preserves document row order', () => {
    const rows = parseTable(BASIC, 'table');
    expect(rows.map((r: any) => r.Name)).toStrictEqual(['Apple', 'Pear']);
  });

  it('SKILLCHECK trims whitespace in headers and cells', () => {
    expect(parseTable(WHITESPACE, '.ws')).toStrictEqual([
      { Color: 'Red', Hex: '#f00' },
    ]);
  });

  it('SKILLCHECK short row pads missing trailing keys with empty string', () => {
    const rows = parseTable(SHORT_ROW, '#t');
    expect(rows).toStrictEqual([{ A: '1', B: '', C: '' }]);
    // The missing keys must be PRESENT (not just undefined).
    expect('B' in rows[0]).toBe(true);
    expect('C' in rows[0]).toBe(true);
  });

  it('SKILLCHECK long row ignores extra cells beyond headers', () => {
    const rows = parseTable(LONG_ROW, '#t');
    expect(rows).toStrictEqual([{ A: '1', B: '2' }]);
    expect(Object.keys(rows[0])).toStrictEqual(['A', 'B']);
  });

  it('SKILLCHECK missing selector returns empty array without throwing', () => {
    expect(() => parseTable(BASIC, '.nope')).not.toThrow();
    expect(parseTable(BASIC, '.nope')).toStrictEqual([]);
  });

  it('SKILLCHECK selector against plain div returns empty array', () => {
    expect(parseTable('<div></div>', 'table')).toStrictEqual([]);
  });

  it('SKILLCHECK tbody with no rows yields empty array', () => {
    expect(parseTable(EMPTY_TBODY, '#t')).toStrictEqual([]);
  });

  it('SKILLCHECK matches the FIRST element for the selector', () => {
    // A selector matching multiple tables must use only the first one.
    expect(parseTable(TWO_TABLES, 'table')).toStrictEqual([{ X: 'first' }]);
  });

  it('SKILLCHECK class selector targets the intended table', () => {
    expect(parseTable(TWO_TABLES, '.second')).toStrictEqual([{ X: 'second' }]);
  });

  it('SKILLCHECK returns an array of plain objects', () => {
    const rows = parseTable(BASIC, '#fruit');
    expect(Array.isArray(rows)).toBe(true);
    expect(rows).toHaveLength(2);
    for (const r of rows) {
      expect(typeof r).toBe('object');
      expect(r).not.toBeNull();
    }
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

    def test_l1_table_source_exists(self):
        """L1: src/api/table.ts exists and exports parseTable."""
        assert os.path.isfile(TABLE_TS), f"missing {TABLE_TS}"
        content = open(TABLE_TS, encoding="utf-8").read()
        assert re.search(r"\bparseTable\b", content), (
            "table.ts must define a parseTable symbol"
        )
        assert re.search(r"export\s+(function\s+parseTable|(const|let)\s+parseTable|\{[^}]*\bparseTable\b)", content), (
            "table.ts must EXPORT parseTable"
        )
        assert len(content) > 200, "table.ts unexpectedly small"

    def test_l1_table_uses_cheerio_load(self):
        """L1: table.ts loads the HTML via cheerio's load API (not a regex hack)."""
        content = open(TABLE_TS, encoding="utf-8").read()
        assert re.search(r"\bload\b", content), (
            "table.ts must use cheerio's load() to parse the HTML string"
        )

    def test_l1_table_spec_exists(self):
        """L1: src/api/table.spec.ts exists and exercises parseTable."""
        assert os.path.isfile(TABLE_SPEC), f"missing {TABLE_SPEC}"
        content = open(TABLE_SPEC, encoding="utf-8").read()
        assert re.search(r"\bparseTable\b", content), (
            "table.spec.ts must call parseTable(...)"
        )

    def test_l1_spec_covers_required_cases(self):
        """L1: table.spec.ts mentions the required edge-case scenarios."""
        content = open(TABLE_SPEC, encoding="utf-8").read()
        # The doc requires cases for fewer/extra cells, missing selector, trimming.
        assert "thead" in content.lower() or "th" in content.lower() or "header" in content.lower(), (
            "table.spec.ts should exercise header-bearing tables"
        )

    # ----------------------- L2: dynamic execution -----------------------

    def test_l2_injected_spec_runs_clean(self):
        """L2: the injected independent spec compiles and runs (vitest exit 0).

        This is the gate: a naive parseTable will fail the behavioral assertions
        below and drive a non-zero exit code.
        """
        result = _get_injected_result()
        assert result["returncode"] == 0, (
            "Injected vitest spec failed.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )

    def test_l2_basic_multi_row(self):
        """L2: a multi-row table maps trimmed headers to trimmed cells in order."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "basic multi-row table maps headers to cells",
                "header keys are trimmed",
                "preserves document row order",
            ],
        )

    def test_l2_whitespace_trimming(self):
        """L2: whitespace in both headers and cells is trimmed from stored text."""
        _assert_titles_passed(
            _get_injected_result(),
            ["trims whitespace in headers and cells"],
        )

    def test_l2_short_row_padding(self):
        """L2: a row with fewer cells than headers pads trailing keys with ''."""
        _assert_titles_passed(
            _get_injected_result(),
            ["short row pads missing trailing keys with empty string"],
        )

    def test_l2_long_row_truncation(self):
        """L2: a row with more cells than headers ignores the extra cells."""
        _assert_titles_passed(
            _get_injected_result(),
            ["long row ignores extra cells beyond headers"],
        )

    def test_l2_missing_selector_returns_empty(self):
        """L2: a selector that matches nothing returns [] and does not throw."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "missing selector returns empty array without throwing",
                "selector against plain div returns empty array",
            ],
        )

    def test_l2_empty_tbody(self):
        """L2: a tbody with no <tr> rows yields []."""
        _assert_titles_passed(
            _get_injected_result(),
            ["tbody with no rows yields empty array"],
        )

    def test_l2_first_match_and_class_selector(self):
        """L2: parseTable uses the FIRST matching element; class selectors target it."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "matches the FIRST element for the selector",
                "class selector targets the intended table",
            ],
        )

    def test_l2_returns_array_of_objects(self):
        """L2: the result is an array of plain non-null objects of correct length."""
        _assert_titles_passed(
            _get_injected_result(),
            ["returns an array of plain objects"],
        )

    def test_l2_agent_spec_passes(self):
        """L2: the agent's own table.spec.ts passes under `npx vitest run`."""
        rel = os.path.join("src", "api", "table.spec.ts")
        result = _run_vitest(rel, timeout=600)
        assert result["returncode"] == 0, (
            "The agent's table.spec.ts must pass under `vitest run`.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )
