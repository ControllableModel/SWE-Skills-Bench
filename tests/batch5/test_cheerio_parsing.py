"""Tests for the `cheerio-parsing` skill (variant ext5).

Skill task (ext5): add two defensive accessor helpers to cheerio in a NEW
module ``src/api/safe-access.ts`` that read text and attributes from an
already-loaded cheerio ``$`` API while tolerating missing elements:

  * ``safeText($, selector, defaultValue = '')`` -- returns the *trimmed* text
    of the first element matching ``selector``; returns ``defaultValue`` when no
    element matches. Never throws.
  * ``safeAttr($, selector, attr, defaultValue = null)`` -- returns the named
    attribute of the first matching element; returns ``undefined`` when the
    element exists but lacks the attribute (distinct from the no-match case);
    returns ``defaultValue`` when no element matches. Never throws.

The agent edits the cheerio repo at REPO_DIR. After it finishes this file is run
with pytest. Verification strategy:

  * L1 -- the deliverable files exist and are minimally well-formed (the new
    module exports both helpers; the spec exercises them).
  * L2 -- DYNAMIC EXECUTION: we drop an INDEPENDENT vitest spec into the repo's
    own ``src/api`` directory so it imports the agent's freshly-built helpers
    through the real module path and asserts on concrete return values. Each
    ``it(...)`` has a stable, greppable title so the Python layer can assert on
    individual outcomes -- a naive/stub implementation (returning a fixed value,
    ignoring trimming, conflating missing-element vs missing-attribute, or
    throwing on a non-matching selector) fails these specs. We also re-run the
    agent's own ``safe-access.spec.ts`` via the native acceptance command.

Native acceptance command (from the doc):
    npx vitest run src/api/safe-access.spec.ts
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
SAFE_TS = os.path.join(API_DIR, "safe-access.ts")
SAFE_SPEC = os.path.join(API_DIR, "safe-access.spec.ts")

# Name of the independent spec we inject. Distinct from the agent's own spec so
# the repo's typecheck (scoped to its committed spec) does not gate it.
INJECTED_SPEC_NAME = "safe_access_skillcheck.spec.ts"
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
    None), and `assertions` (flattened list of {title, status, ...} dicts).
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
# Exercises safeText / safeAttr strictly through the agent's new module path.
# We construct documents inline (no reliance on repo fixtures) so the assertions
# pin exact return values from the doc's "Expected Functionality" section.

_INJECTED_SPEC = r"""
import { describe, expect, it } from 'vitest';
import { load } from '../load-parse.js';
import { safeText, safeAttr } from './safe-access.js';

const DOC = `
  <h1 class="title">  Hi
</h1>
  <p class="empty"></p>
  <ul>
    <li class="item">  alpha  </li>
    <li class="item">beta</li>
  </ul>
  <a href="/x">first</a>
  <a href="/y" rel="next">second</a>
`;

describe('safe-access skillcheck', () => {
  it('SKILLCHECK safeText trims surrounding whitespace and newlines', () => {
    const $ = load(DOC);
    expect(safeText($, '.title')).toBe('Hi');
  });

  it('SKILLCHECK safeText returns empty-string default for no match', () => {
    const $ = load(DOC);
    expect(safeText($, '.missing')).toBe('');
  });

  it('SKILLCHECK safeText custom default used for no match', () => {
    const $ = load(DOC);
    expect(safeText($, '.missing', 'N/A')).toBe('N/A');
  });

  it('SKILLCHECK safeText first match only in document order', () => {
    const $ = load(DOC);
    // Two .item elements; first is "  alpha  " -> trimmed "alpha".
    expect(safeText($, '.item')).toBe('alpha');
  });

  it('SKILLCHECK safeText empty element yields empty string not default', () => {
    const $ = load(DOC);
    // Element matches but text is empty; trimmed empty string is the real text,
    // so the default must NOT kick in (match exists).
    expect(safeText($, '.empty', 'FALLBACK')).toBe('');
  });

  it('SKILLCHECK safeText does not throw on non-matching selector', () => {
    const $ = load(DOC);
    expect(() => safeText($, '.nope')).not.toThrow();
  });

  it('SKILLCHECK safeAttr returns attribute of first match', () => {
    const $ = load(DOC);
    expect(safeAttr($, 'a', 'href')).toBe('/x');
  });

  it('SKILLCHECK safeAttr first match only when multiple match', () => {
    const $ = load(DOC);
    // The second <a> has rel="next"; the first does not. First-match-only means
    // querying rel on `a` returns undefined (missing attr on first match).
    expect(safeAttr($, 'a', 'rel')).toBeUndefined();
  });

  it('SKILLCHECK safeAttr missing attribute on present element is undefined', () => {
    const $ = load(DOC);
    // Element matches but lacks the attribute -> undefined, even with a default.
    expect(safeAttr($, '.title', 'data-x', 'DEF')).toBeUndefined();
  });

  it('SKILLCHECK safeAttr no-match returns null default', () => {
    const $ = load(DOC);
    expect(safeAttr($, '.missing', 'href')).toBe(null);
  });

  it('SKILLCHECK safeAttr no-match returns custom default override', () => {
    const $ = load(DOC);
    expect(safeAttr($, '.missing', 'href', 'OVERRIDE')).toBe('OVERRIDE');
  });

  it('SKILLCHECK safeAttr distinguishes missing-attr from no-match', () => {
    const $ = load(DOC);
    // Same custom default supplied to both calls; the present-but-missing-attr
    // case must IGNORE the default (undefined), the no-match case must USE it.
    const presentMissing = safeAttr($, '.title', 'data-x', 'SENTINEL');
    const noMatch = safeAttr($, '.missing', 'data-x', 'SENTINEL');
    expect(presentMissing).toBeUndefined();
    expect(noMatch).toBe('SENTINEL');
  });

  it('SKILLCHECK safeAttr does not throw on non-matching selector', () => {
    const $ = load(DOC);
    expect(() => safeAttr($, '.nope', 'href')).not.toThrow();
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

    def test_l1_safe_access_source_exists(self):
        """L1: src/api/safe-access.ts exists and is non-trivial TypeScript."""
        assert os.path.isfile(SAFE_TS), f"missing {SAFE_TS}"
        content = open(SAFE_TS, encoding="utf-8").read()
        assert len(content) > 150, "safe-access.ts unexpectedly small"

    def test_l1_exports_both_helpers(self):
        """L1: safe-access.ts exports both safeText and safeAttr."""
        content = open(SAFE_TS, encoding="utf-8").read()
        assert re.search(r"\bexport\b[\s\S]{0,40}\bsafeText\b", content), (
            "safe-access.ts must export safeText"
        )
        assert re.search(r"\bexport\b[\s\S]{0,40}\bsafeAttr\b", content), (
            "safe-access.ts must export safeAttr"
        )

    def test_l1_spec_exists(self):
        """L1: src/api/safe-access.spec.ts exists and references the helpers."""
        assert os.path.isfile(SAFE_SPEC), f"missing {SAFE_SPEC}"
        content = open(SAFE_SPEC, encoding="utf-8").read()
        assert "safeText" in content and "safeAttr" in content, (
            "spec must exercise both safeText and safeAttr"
        )

    def test_l1_spec_covers_required_paths(self):
        """L1: the agent's spec mentions the required behavioral paths."""
        content = open(SAFE_SPEC, encoding="utf-8").read()
        # Doc requires coverage of trimming, defaults, first-match, missing-attr.
        assert "undefined" in content, (
            "spec must cover the match-but-missing-attribute (undefined) case"
        )

    # ----------------------- L2: dynamic execution -----------------------

    def test_l2_injected_spec_runs_clean(self):
        """L2: the injected independent spec compiles and runs (vitest exit 0).

        Gate: if the helpers are unimplemented or wrongly shaped, the import or
        the behavioral assertions below fail, driving a non-zero exit code.
        """
        result = _get_injected_result()
        assert result["returncode"] == 0, (
            "Injected vitest spec failed.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )

    def test_l2_safeText_trims(self):
        """L2: safeText trims leading/trailing whitespace and newlines."""
        _assert_titles_passed(
            _get_injected_result(),
            ["safeText trims surrounding whitespace"],
        )

    def test_l2_safeText_default_value(self):
        """L2: safeText returns the empty-string default and a custom default."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "safeText returns empty-string default",
                "safeText custom default used for no match",
            ],
        )

    def test_l2_safeText_first_match_only(self):
        """L2: safeText operates on the first match in document order only."""
        _assert_titles_passed(
            _get_injected_result(),
            ["safeText first match only"],
        )

    def test_l2_safeText_empty_element_not_default(self):
        """L2: a matching empty element yields '' (real text), not the default."""
        _assert_titles_passed(
            _get_injected_result(),
            ["safeText empty element yields empty string not default"],
        )

    def test_l2_safeText_no_throw(self):
        """L2: safeText does not throw on a non-matching selector."""
        _assert_titles_passed(
            _get_injected_result(),
            ["safeText does not throw on non-matching"],
        )

    def test_l2_safeAttr_reads_attribute(self):
        """L2: safeAttr returns the attribute value of the first match."""
        _assert_titles_passed(
            _get_injected_result(),
            ["safeAttr returns attribute of first match"],
        )

    def test_l2_safeAttr_first_match_only(self):
        """L2: safeAttr reads the attribute from the first match only."""
        _assert_titles_passed(
            _get_injected_result(),
            ["safeAttr first match only when multiple match"],
        )

    def test_l2_safeAttr_missing_attr_is_undefined(self):
        """L2: present element lacking the attribute -> undefined (not default)."""
        _assert_titles_passed(
            _get_injected_result(),
            ["safeAttr missing attribute on present element is undefined"],
        )

    def test_l2_safeAttr_no_match_default(self):
        """L2: no match -> null default, or a caller-provided override default."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "safeAttr no-match returns null default",
                "safeAttr no-match returns custom default override",
            ],
        )

    def test_l2_safeAttr_distinguishes_cases(self):
        """L2: missing-attribute (undefined) is distinct from no-match (default)."""
        _assert_titles_passed(
            _get_injected_result(),
            ["safeAttr distinguishes missing-attr from no-match"],
        )

    def test_l2_safeAttr_no_throw(self):
        """L2: safeAttr does not throw on a non-matching selector."""
        _assert_titles_passed(
            _get_injected_result(),
            ["safeAttr does not throw on non-matching"],
        )

    def test_l2_native_acceptance_command_passes(self):
        """L2: the doc's native command passes (agent's own committed spec).

        Drives exactly: `npx vitest run src/api/safe-access.spec.ts`.
        """
        rel = os.path.join("src", "api", "safe-access.spec.ts")
        result = _run_vitest(rel, timeout=600)
        assert result["returncode"] == 0, (
            "Repo's safe-access.spec.ts must pass under `vitest run`.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )
