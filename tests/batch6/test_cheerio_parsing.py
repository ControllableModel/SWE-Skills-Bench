"""Tests for the `cheerio-parsing` skill (variant ext6).

Skill task (ext6): build a pagination-link extractor in the cheerio repo.

  * `src/api/pagination.ts` (new) exports `extractPaginationLinks(html)`, which
    loads `html` with cheerio and returns the list of href strings from anchors
    *inside a `.pagination` container*, with these filters applied:
      - only anchors that are descendants of a `.pagination` element count;
      - hrefs are returned as raw strings in document order;
      - anchors with no `href` are excluded;
      - anchors whose `href` contains a `#` anywhere are excluded;
      - duplicate hrefs are de-duplicated, keeping the first occurrence;
      - anchors outside any `.pagination` container are ignored;
      - no `.pagination` container -> `[]`.
  * `src/api/pagination.spec.ts` (new) — deterministic vitest cases.

The agent edits the cheerio repo at REPO_DIR. After it finishes, this file is
run with pytest. Verification strategy:

  * L1 -- the deliverable files exist and are minimally well-formed (the
    function is exported, the spec exercises the new API).
  * L2 -- DYNAMIC EXECUTION: we drop an INDEPENDENT vitest spec into the repo's
    own ``src/api`` directory that imports the agent's real, freshly-built
    ``extractPaginationLinks`` through the module path ``./pagination.js`` and
    asserts the full contract with concrete expected arrays. Each `it(...)` has
    a stable, greppable title so the Python layer asserts on individual
    outcomes. A naive/stub implementation -- returning a fixed array, ignoring
    the `#`/missing-href/de-dup/outside-container rules, or hardcoding output --
    fails these specs. We also drive the doc's native acceptance command
    (`npx vitest run src/api/pagination.spec.ts`) against the agent's own spec.

Native acceptance command (from the doc): npx vitest run src/api/pagination.spec.ts
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
PAGINATION_TS = os.path.join(REPO_DIR, "src", "api", "pagination.ts")
PAGINATION_SPEC = os.path.join(REPO_DIR, "src", "api", "pagination.spec.ts")
API_DIR = os.path.join(REPO_DIR, "src", "api")

# Name of the independent spec we inject. Distinct from pagination.spec.ts so the
# repo's own typecheck/scoping never gates our behavioral assertions.
INJECTED_SPEC_NAME = "pagination_skillcheck.spec.ts"
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
        # Our injected spec is runtime-only; don't gate it on typecheck.
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
# Imports the agent's real implementation via the public module path and pins
# the full contract with concrete expected arrays. Each `it(...)` title is
# stable + greppable so the Python layer can assert individual outcomes.

_INJECTED_SPEC = r"""
import { describe, expect, it } from 'vitest';
import { extractPaginationLinks } from './pagination.js';

const PAGINATION = `
  <div class="pagination">
    <a href="?page=1">1</a>
    <a href="?page=2">2</a>
    <a href="#">skip</a>
    <a href="?page=2">2 again</a>
    <a>missing</a>
  </div>
`;

describe('extractPaginationLinks skillcheck', () => {
  it('SKILLCHECK basic dedup hash and missing-href filtering', () => {
    expect(extractPaginationLinks(PAGINATION)).toStrictEqual([
      '?page=1',
      '?page=2',
    ]);
  });

  it('SKILLCHECK no pagination container yields empty array', () => {
    const html = `
      <nav>
        <a href="?page=1">1</a>
        <a href="?page=2">2</a>
      </nav>
    `;
    expect(extractPaginationLinks(html)).toStrictEqual([]);
  });

  it('SKILLCHECK ignores anchors outside the pagination container', () => {
    const html = `
      <a href="?outside=1">out-before</a>
      <div class="pagination">
        <a href="?page=1">1</a>
      </div>
      <a href="?outside=2">out-after</a>
    `;
    expect(extractPaginationLinks(html)).toStrictEqual(['?page=1']);
  });

  it('SKILLCHECK excludes any href containing a hash anywhere', () => {
    const html = `
      <div class="pagination">
        <a href="#">hash-only</a>
        <a href="?page=1#frag">mid-hash</a>
        <a href="javascript:void(0)#">js-hash</a>
        <a href="?page=2">keep</a>
      </div>
    `;
    expect(extractPaginationLinks(html)).toStrictEqual(['?page=2']);
  });

  it('SKILLCHECK excludes anchors with no href attribute', () => {
    const html = `
      <div class="pagination">
        <a>no href</a>
        <a href="?page=1">1</a>
        <a>another no href</a>
      </div>
    `;
    expect(extractPaginationLinks(html)).toStrictEqual(['?page=1']);
  });

  it('SKILLCHECK dedup keeps first-occurrence order', () => {
    const html = `
      <div class="pagination">
        <a href="/b">b</a>
        <a href="/a">a</a>
        <a href="/b">b again</a>
        <a href="/c">c</a>
        <a href="/a">a again</a>
      </div>
    `;
    expect(extractPaginationLinks(html)).toStrictEqual(['/b', '/a', '/c']);
  });

  it('SKILLCHECK preserves document order across multiple containers', () => {
    const html = `
      <div class="pagination">
        <a href="?page=1">1</a>
        <a href="?page=2">2</a>
      </div>
      <div class="pagination">
        <a href="?page=3">3</a>
        <a href="?page=1">dup across container</a>
      </div>
    `;
    expect(extractPaginationLinks(html)).toStrictEqual([
      '?page=1',
      '?page=2',
      '?page=3',
    ]);
  });

  it('SKILLCHECK includes anchors nested deep inside the container', () => {
    const html = `
      <div class="pagination">
        <ul>
          <li><span><a href="?page=1">1</a></span></li>
          <li><a href="?page=2">2</a></li>
        </ul>
      </div>
    `;
    expect(extractPaginationLinks(html)).toStrictEqual(['?page=1', '?page=2']);
  });

  it('SKILLCHECK empty pagination container yields empty array', () => {
    const html = `<div class="pagination"></div>`;
    expect(extractPaginationLinks(html)).toStrictEqual([]);
  });

  it('SKILLCHECK returns an array, never a non-array', () => {
    const out = extractPaginationLinks(`<div class="pagination"></div>`);
    expect(Array.isArray(out)).toBe(true);
  });

  it('SKILLCHECK preserves raw href strings verbatim', () => {
    const html = `
      <div class="pagination">
        <a href="https://example.com/list?page=2&amp;sort=asc">2</a>
      </div>
    `;
    // The &amp; entity decodes to & in the attribute value; verify raw value.
    expect(extractPaginationLinks(html)).toStrictEqual([
      'https://example.com/list?page=2&sort=asc',
    ]);
  });

  it('SKILLCHECK pagination as a non-div element still matches by class', () => {
    const html = `
      <nav class="pagination">
        <a href="?page=1">1</a>
      </nav>
    `;
    expect(extractPaginationLinks(html)).toStrictEqual(['?page=1']);
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

    def test_l1_pagination_source_exists(self):
        """L1: src/api/pagination.ts exists and is non-trivial TypeScript."""
        assert os.path.isfile(PAGINATION_TS), f"missing {PAGINATION_TS}"
        content = open(PAGINATION_TS, encoding="utf-8").read()
        assert len(content) > 120, "pagination.ts unexpectedly small/empty"

    def test_l1_exports_extract_pagination_links(self):
        """L1: pagination.ts exports an extractPaginationLinks function."""
        content = open(PAGINATION_TS, encoding="utf-8").read()
        assert "extractPaginationLinks" in content, (
            "pagination.ts must define extractPaginationLinks"
        )
        assert re.search(
            r"export\s+(?:default\s+)?(?:async\s+)?function\s+extractPaginationLinks"
            r"|export\s+const\s+extractPaginationLinks"
            r"|export\s*\{[^}]*\bextractPaginationLinks\b",
            content,
        ), "pagination.ts must EXPORT extractPaginationLinks"

    def test_l1_source_uses_cheerio_and_pagination_class(self):
        """L1: the implementation actually loads HTML and targets `.pagination`."""
        content = open(PAGINATION_TS, encoding="utf-8").read()
        assert re.search(r"\bload\b|cheerio", content), (
            "pagination.ts must load html with cheerio (import { load } ...)"
        )
        assert "pagination" in content, (
            "pagination.ts must reference the .pagination container"
        )

    def test_l1_spec_exists_and_exercises_api(self):
        """L1: src/api/pagination.spec.ts exists and calls extractPaginationLinks."""
        assert os.path.isfile(PAGINATION_SPEC), f"missing {PAGINATION_SPEC}"
        content = open(PAGINATION_SPEC, encoding="utf-8").read()
        assert "extractPaginationLinks" in content, (
            "spec must exercise extractPaginationLinks"
        )

    def test_l1_spec_covers_required_cases(self):
        """L1: the spec references the documented edge cases (hash, dedup, etc.)."""
        content = open(PAGINATION_SPEC, encoding="utf-8").read()
        assert "pagination" in content, "spec must use a .pagination fixture"
        assert "#" in content, "spec must cover the hash-href exclusion rule"

    # ----------------------- L2: dynamic execution -----------------------

    def test_l2_injected_spec_runs_clean(self):
        """L2: the injected independent spec compiles and runs (vitest exit 0).

        This is the gate: it imports the agent's real extractPaginationLinks and
        asserts the full contract. An unimplemented or stub function drives a
        non-zero exit code here.
        """
        result = _get_injected_result()
        assert result["returncode"] == 0, (
            "Injected vitest spec failed.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )

    def test_l2_basic_dedup_hash_missing(self):
        """L2: combined fixture -> dedup + hash + missing-href filtering."""
        _assert_titles_passed(
            _get_injected_result(),
            ["basic dedup hash and missing-href filtering"],
        )

    def test_l2_no_container_empty(self):
        """L2: a document with no .pagination container returns []."""
        _assert_titles_passed(
            _get_injected_result(),
            ["no pagination container yields empty array"],
        )

    def test_l2_ignores_outside_container(self):
        """L2: anchors outside the .pagination container are ignored."""
        _assert_titles_passed(
            _get_injected_result(),
            ["ignores anchors outside the pagination container"],
        )

    def test_l2_excludes_hash_anywhere(self):
        """L2: any href containing '#' (anywhere) is excluded."""
        _assert_titles_passed(
            _get_injected_result(),
            ["excludes any href containing a hash anywhere"],
        )

    def test_l2_excludes_missing_href(self):
        """L2: anchors with no href attribute are excluded."""
        _assert_titles_passed(
            _get_injected_result(),
            ["excludes anchors with no href attribute"],
        )

    def test_l2_dedup_first_occurrence_order(self):
        """L2: duplicate hrefs are removed, keeping first-occurrence order."""
        _assert_titles_passed(
            _get_injected_result(),
            ["dedup keeps first-occurrence order"],
        )

    def test_l2_document_order_across_containers(self):
        """L2: order is preserved (and dedup applied) across two containers."""
        _assert_titles_passed(
            _get_injected_result(),
            ["preserves document order across multiple containers"],
        )

    def test_l2_deeply_nested_anchors(self):
        """L2: anchors nested deep inside the container are included."""
        _assert_titles_passed(
            _get_injected_result(),
            ["includes anchors nested deep inside the container"],
        )

    def test_l2_empty_container_and_array_type(self):
        """L2: empty container -> [] and the result is always an array."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "empty pagination container yields empty array",
                "returns an array, never a non-array",
            ],
        )

    def test_l2_raw_href_and_class_match(self):
        """L2: raw href strings preserved; .pagination matches any element."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "preserves raw href strings verbatim",
                "pagination as a non-div element still matches by class",
            ],
        )

    def test_l2_native_acceptance_command_passes(self):
        """L2: the doc's native command on the agent's own spec passes.

        Drives exactly: npx vitest run src/api/pagination.spec.ts
        """
        rel = os.path.join("src", "api", "pagination.spec.ts")
        result = _run_vitest(rel, timeout=600)
        assert result["returncode"] == 0, (
            "`npx vitest run src/api/pagination.spec.ts` must pass.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )
