"""Tests for the `cheerio-parsing` skill (variant ext9).

Skill task: add a NEW data-attribute collector to the cheerio repo:

  * ``src/api/data-collect.ts`` (new) exporting
    ``collectData(html: string, selector: string)`` which loads ``html``,
    selects every element matching ``selector`` (document order), and returns
    one record object per matched element holding that element's ``data-*``
    attributes.
  * ``src/api/data-collect.spec.ts`` (new) covering the contract.

Contract recap (re-derived from tasks/ext9/cheerio-parsing.md):
  * Each record's key is the attribute name with the ``data-`` prefix removed
    and the remainder camelCased across hyphen boundaries
    (``data-product-id`` -> ``productId``, ``data-id`` -> ``id``).
  * Values are the RAW attribute strings (no numeric coercion;
    ``data-id="123"`` -> ``'123'``).
  * Non-``data-`` attributes (class/id/href/...) MUST NOT appear.
  * An element with no ``data-*`` attributes contributes ``{}``.
  * Records appear one per matched element, in document order.
  * No selector match -> ``[]``.

Verification strategy:
  * L1 -- the two deliverable files exist and are minimally well-formed
    (export present, spec exercises the public function).
  * L2 -- DYNAMIC EXECUTION via the repo's own vitest toolchain. We drop an
    INDEPENDENT vitest spec into ``src/api`` that imports the freshly-built
    ``collectData`` through its real module and asserts concrete return values.
    Each ``it(...)`` has a stable greppable title so the Python layer asserts on
    individual outcomes -- a naive implementation that hardcodes, skips
    camelCasing, coerces values, leaks non-data attributes, or returns the
    wrong arity will fail specific cases (not just an aggregate). We also run
    the repo's own ``data-collect.spec.ts`` to confirm the agent's deliverable
    spec passes under vitest.

The native acceptance command driven by L2 is:

    npx vitest run src/api/data-collect.spec.ts
"""

import json
import os
import subprocess

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - fallback if helper not present
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/cheerio"
API_DIR = os.path.join(REPO_DIR, "src", "api")
DATA_COLLECT_TS = os.path.join(API_DIR, "data-collect.ts")
DATA_COLLECT_SPEC = os.path.join(API_DIR, "data-collect.spec.ts")

# Independent spec we inject. Distinct name so the repo's typecheck (scoped to
# the agent's own spec) does not gate it.
INJECTED_SPEC_NAME = "data_collect_skillcheck.spec.ts"
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
# Injected independent spec content. Imports the agent's collectData directly.
# ---------------------------------------------------------------------------
_INJECTED_SPEC = r"""
import { describe, expect, it } from 'vitest';
import { collectData } from './data-collect.js';

describe('collectData skillcheck', () => {
  it('SKILLCHECK basic data attrs with camelCase and class excluded', () => {
    const html =
      '<ul><li data-id="1" data-product-name="Apple" class="x"></li></ul>';
    expect(collectData(html, 'li')).toStrictEqual([
      { id: '1', productName: 'Apple' },
    ]);
  });

  it('SKILLCHECK multi-hyphen key camelCased fully', () => {
    const html = '<div data-product-id="42" data-a-b-c="z"></div>';
    expect(collectData(html, 'div')).toStrictEqual([
      { productId: '42', aBC: 'z' },
    ]);
  });

  it('SKILLCHECK single-segment key keeps name without prefix', () => {
    const html = '<span data-id="7"></span>';
    expect(collectData(html, 'span')).toStrictEqual([{ id: '7' }]);
  });

  it('SKILLCHECK values stay raw strings (no numeric coercion)', () => {
    const html = '<i data-id="123" data-flag="true" data-amount="0"></i>';
    const out = collectData(html, 'i');
    expect(out).toStrictEqual([{ id: '123', flag: 'true', amount: '0' }]);
    expect(typeof out[0].id).toBe('string');
    expect(typeof out[0].amount).toBe('string');
    expect(out[0].id).toBe('123');
  });

  it('SKILLCHECK non-data attributes are excluded', () => {
    const html =
      '<a href="/x" id="main" class="btn" title="t" data-role="link"></a>';
    expect(collectData(html, 'a')).toStrictEqual([{ role: 'link' }]);
  });

  it('SKILLCHECK element with no data attrs yields empty object', () => {
    const html = '<p class="only-class"></p>';
    const out = collectData(html, 'p');
    expect(out).toStrictEqual([{}]);
    expect(out.length).toBe(1);
    expect(Object.keys(out[0]).length).toBe(0);
  });

  it('SKILLCHECK multiple matches in document order', () => {
    const html =
      '<ul>' +
      '<li data-id="1" data-name="a"></li>' +
      '<li data-id="2" data-name="b"></li>' +
      '<li data-id="3" data-name="c"></li>' +
      '</ul>';
    expect(collectData(html, 'li')).toStrictEqual([
      { id: '1', name: 'a' },
      { id: '2', name: 'b' },
      { id: '3', name: 'c' },
    ]);
  });

  it('SKILLCHECK mixed elements: some with, some without data attrs', () => {
    const html =
      '<ul>' +
      '<li data-id="1"></li>' +
      '<li class="plain"></li>' +
      '<li data-id="3" data-tag="x"></li>' +
      '</ul>';
    expect(collectData(html, 'li')).toStrictEqual([
      { id: '1' },
      {},
      { id: '3', tag: 'x' },
    ]);
  });

  it('SKILLCHECK no selector match returns empty array', () => {
    expect(collectData('<p></p>', '.none')).toStrictEqual([]);
    expect(collectData('<div data-id="1"></div>', 'span')).toStrictEqual([]);
  });

  it('SKILLCHECK class selector picks only matching elements', () => {
    const html =
      '<div data-id="skip"></div>' +
      '<div class="pick" data-id="keep" data-x="y"></div>';
    expect(collectData(html, '.pick')).toStrictEqual([
      { id: 'keep', x: 'y' },
    ]);
  });

  it('SKILLCHECK empty-string data value preserved', () => {
    const html = '<b data-label="" data-id="5"></b>';
    expect(collectData(html, 'b')).toStrictEqual([{ label: '', id: '5' }]);
  });

  it('SKILLCHECK does not numerically coerce leading-zero / float-looking', () => {
    const html = '<u data-code="007" data-rate="1.50"></u>';
    expect(collectData(html, 'u')).toStrictEqual([
      { code: '007', rate: '1.50' },
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

    def test_l1_data_collect_source_exists(self):
        """L1: src/api/data-collect.ts exists and exports collectData."""
        assert os.path.isfile(DATA_COLLECT_TS), f"missing {DATA_COLLECT_TS}"
        content = open(DATA_COLLECT_TS, encoding="utf-8").read()
        assert "collectData" in content, "data-collect.ts must define collectData"
        assert "export" in content, "data-collect.ts must export collectData"
        assert len(content) > 150, "data-collect.ts unexpectedly small"

    def test_l1_data_collect_spec_exists(self):
        """L1: src/api/data-collect.spec.ts exists and exercises collectData."""
        assert os.path.isfile(DATA_COLLECT_SPEC), f"missing {DATA_COLLECT_SPEC}"
        content = open(DATA_COLLECT_SPEC, encoding="utf-8").read()
        assert "collectData" in content, "spec must call collectData(...)"

    def test_l1_source_references_data_prefix_logic(self):
        """L1: source addresses the `data-` prefix (not a no-op stub)."""
        content = open(DATA_COLLECT_TS, encoding="utf-8").read()
        assert "data-" in content or "data" in content, (
            "data-collect.ts must reference the data- attribute prefix"
        )

    def test_l1_spec_covers_required_cases(self):
        """L1: the agent's spec covers the contract's required scenarios."""
        content = open(DATA_COLLECT_SPEC, encoding="utf-8").read()
        # Empty-result case and an empty-object/no-data case should be present.
        assert "[]" in content, "spec must cover the empty-result ([]) case"

    # ----------------------- L2: dynamic execution -----------------------

    def test_l2_injected_spec_runs_clean(self):
        """L2: the injected independent spec compiles and runs (vitest exit 0).

        This is the gate: collectData is imported and exercised directly, so a
        missing/incorrect implementation drives a non-zero exit code.
        """
        result = _get_injected_result()
        assert result["returncode"] == 0, (
            "Injected vitest spec failed.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )

    def test_l2_basic_camelcase_and_class_excluded(self):
        """L2: data-* collected, camelCased, non-data class excluded."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "basic data attrs with camelCase and class excluded",
                "single-segment key keeps name without prefix",
            ],
        )

    def test_l2_multi_hyphen_camelcase(self):
        """L2: multi-hyphen keys are fully camelCased across all boundaries."""
        _assert_titles_passed(
            _get_injected_result(),
            ["multi-hyphen key camelCased fully"],
        )

    def test_l2_values_stay_raw_strings(self):
        """L2: values remain raw strings (no numeric/boolean coercion)."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "values stay raw strings (no numeric coercion)",
                "does not numerically coerce leading-zero / float-looking",
            ],
        )

    def test_l2_non_data_attributes_excluded(self):
        """L2: href/id/class/title and other non-data attrs are excluded."""
        _assert_titles_passed(
            _get_injected_result(),
            ["non-data attributes are excluded"],
        )

    def test_l2_no_data_attrs_yields_empty_object(self):
        """L2: an element with no data-* attrs contributes {} (still one entry)."""
        _assert_titles_passed(
            _get_injected_result(),
            ["element with no data attrs yields empty object"],
        )

    def test_l2_multiple_matches_document_order(self):
        """L2: one record per matched element, in document order."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "multiple matches in document order",
                "mixed elements: some with, some without data attrs",
            ],
        )

    def test_l2_empty_result_on_no_match(self):
        """L2: selector matching nothing returns []."""
        _assert_titles_passed(
            _get_injected_result(),
            ["no selector match returns empty array"],
        )

    def test_l2_class_selector_filters(self):
        """L2: collection honors the selector (only matching elements)."""
        _assert_titles_passed(
            _get_injected_result(),
            ["class selector picks only matching elements"],
        )

    def test_l2_empty_string_value_preserved(self):
        """L2: empty-string data values are preserved verbatim."""
        _assert_titles_passed(
            _get_injected_result(),
            ["empty-string data value preserved"],
        )

    def test_l2_repo_spec_passes(self):
        """L2: the agent's own data-collect.spec.ts passes under vitest run.

        This drives the doc's native acceptance command:
            npx vitest run src/api/data-collect.spec.ts
        """
        rel = os.path.join("src", "api", "data-collect.spec.ts")
        result = _run_vitest(rel, timeout=600)
        assert result["returncode"] == 0, (
            "Repo's data-collect.spec.ts must pass under `vitest run`.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )
