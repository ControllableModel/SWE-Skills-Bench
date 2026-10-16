"""Tests for the `cheerio-parsing` skill.

Skill task: extend cheerio's `extract` API (`src/api/extract.ts`) with two new
descriptor capabilities:

  * an optional per-descriptor ``transform`` function that post-processes the
    extracted value (single and array descriptors, including nested maps), and
  * an optional ``limit`` on array descriptors that caps the number of matched
    elements collected, in document order.

The agent edits the cheerio repo at REPO_DIR. After it finishes, this file is
run with pytest. We verify the behavior by:

  * L1 -- the deliverable files exist and are minimally well-formed.
  * L2 -- DYNAMIC EXECUTION: we drop an INDEPENDENT vitest spec into the repo's
    own ``src/api`` directory (so it imports the real, freshly-built behavior
    through the public ``extract`` API) and assert on its pass/fail results.
    A solution that merely renames fields, hardcodes, or fails to implement the
    semantics will fail these specs. We also re-run the repo's own
    ``extract.spec.ts`` to confirm pre-existing behavior is preserved.

Document fixture used throughout: the `eleven` fixture, whose `.red` elements in
document order have text: "Four", "Five", "Nine".
"""

import json
import os
import re
import shutil
import subprocess

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - fallback if helper not present
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/cheerio"
EXTRACT_TS = os.path.join(REPO_DIR, "src", "api", "extract.ts")
EXTRACT_SPEC = os.path.join(REPO_DIR, "src", "api", "extract.spec.ts")
API_DIR = os.path.join(REPO_DIR, "src", "api")

# Name of the independent spec file we inject. Distinct from extract.spec.ts so
# the repo's vitest typecheck (scoped to extract.spec.ts) does not gate it.
INJECTED_SPEC_NAME = "extract_skillcheck.spec.ts"
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
            subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=1800)
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
    # vitest json reporter prints the JSON object; locate the outermost {...}.
    out = proc.stdout
    start = out.find("{")
    end = out.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = out[start : end + 1]
        try:
            report = json.loads(candidate)
        except json.JSONDecodeError:
            # Fall back: try line-by-line for a parseable JSON object.
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
# This spec exercises the NEW behavior strictly through the public extract API.
# Every `it(...)` maps to a requirement. We give each a stable, greppable title
# so the Python layer can assert on individual outcomes (not just an aggregate
# pass), making partial/naive implementations detectable.

_INJECTED_SPEC = r"""
import { describe, expect, it } from 'vitest';
import * as fixtures from '../__fixtures__/fixtures.js';
import { load } from '../load-parse.js';

describe('extract skillcheck (transform + limit)', () => {
  it('SKILLCHECK transform single uppercases', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    const out = $root.extract({
      n: { selector: '.red', value: 'textContent', transform: (v: any) => v && v.toUpperCase() },
    });
    expect(out).toStrictEqual({ n: 'FOUR' });
  });

  it('SKILLCHECK transform default value source is textContent', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    // No explicit value -> defaults to textContent ('Four'); transform receives it.
    const out = $root.extract({
      n: { selector: '.red', transform: (v: any) => `<${v}>` },
    });
    expect(out).toStrictEqual({ n: '<Four>' });
  });

  it('SKILLCHECK transform not called on non-matching single descriptor', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    let called = false;
    const out = $root.extract({
      n: { selector: '.missing', transform: () => { called = true; return 'X'; } },
    });
    expect(out).toStrictEqual({ n: undefined });
    expect(called).toBe(false);
  });

  it('SKILLCHECK transform may change type to number', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    const out: any = $root.extract({
      n: { selector: '.red', transform: (v: any) => v.length },
    });
    expect(out.n).toBe(4);
    expect(typeof out.n).toBe('number');
  });

  it('SKILLCHECK transform may return undefined and it is stored', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    const out: any = $root.extract({
      n: { selector: '.red', transform: () => undefined },
    });
    expect('n' in out).toBe(true);
    expect(out.n).toBeUndefined();
  });

  it('SKILLCHECK transform applied per element of array descriptor', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    const out = $root.extract({
      n: [{ selector: '.red', transform: (v: any) => v.toUpperCase() }],
    });
    expect(out).toStrictEqual({ n: ['FOUR', 'FIVE', 'NINE'] });
  });

  it('SKILLCHECK transform applied to nested extracted object', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    const out: any = $root.extract({
      section: {
        selector: 'ul:nth(1)',
        value: { red: '.red', sel: '.blue' },
        transform: (obj: any) => Object.keys(obj).sort().join(','),
      },
    });
    // nested object is { red: 'Five', sel: 'Seven' } -> keys 'red,sel'
    expect(out).toStrictEqual({ section: 'red,sel' });
  });

  it('SKILLCHECK limit caps array to first N in document order', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    const out = $root.extract({ n: [{ selector: '.red', limit: 2 }] });
    expect(out).toStrictEqual({ n: ['Four', 'Five'] });
  });

  it('SKILLCHECK limit one yields first match only', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    const out = $root.extract({ n: [{ selector: '.red', limit: 1 }] });
    expect(out).toStrictEqual({ n: ['Four'] });
  });

  it('SKILLCHECK limit zero yields empty array', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    const out = $root.extract({ n: [{ selector: '.red', limit: 0 }] });
    expect(out).toStrictEqual({ n: [] });
  });

  it('SKILLCHECK limit >= match count behaves as unlimited', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    const exactly = $root.extract({ n: [{ selector: '.red', limit: 3 }] });
    expect(exactly).toStrictEqual({ n: ['Four', 'Five', 'Nine'] });
    const over = $root.extract({ n: [{ selector: '.red', limit: 99 }] });
    expect(over).toStrictEqual({ n: ['Four', 'Five', 'Nine'] });
  });

  it('SKILLCHECK limit has no effect on single descriptor', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    // limit is ignored for non-array descriptors; still returns the single value.
    const out = $root.extract({ n: { selector: '.red', limit: 0 } as any });
    expect(out).toStrictEqual({ n: 'Four' });
  });

  it('SKILLCHECK limit combined with transform', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    const out = $root.extract({
      n: [{ selector: '.red', limit: 2, transform: (v: any) => v.length }],
    });
    expect(out).toStrictEqual({ n: [4, 4] });
  });

  it('SKILLCHECK array transform receives custom value-function output', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    const out = $root.extract({
      n: [{ selector: '.red', value: (el: any) => $(el).text(), transform: (v: any) => v[0] }],
    });
    // first char of each red text: Four->F, Five->F, Nine->N
    expect(out).toStrictEqual({ n: ['F', 'F', 'N'] });
  });

  it('SKILLCHECK no transform/limit preserves original behavior', () => {
    const $ = load(fixtures.eleven);
    const $root = $.root();
    expect($root.extract({ red: '.red' })).toStrictEqual({ red: 'Four' });
    expect($root.extract({ red: ['.red'] })).toStrictEqual({
      red: ['Four', 'Five', 'Nine'],
    });
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

    def test_l1_extract_source_exists(self):
        """L1: src/api/extract.ts exists and is non-trivial TypeScript."""
        assert os.path.isfile(EXTRACT_TS), f"missing {EXTRACT_TS}"
        content = open(EXTRACT_TS, encoding="utf-8").read()
        assert "export function extract" in content, (
            "extract.ts must still export the extract function"
        )
        assert len(content) > 500, "extract.ts unexpectedly small"

    def test_l1_extract_spec_exists(self):
        """L1: src/api/extract.spec.ts exists and references the extract API."""
        assert os.path.isfile(EXTRACT_SPEC), f"missing {EXTRACT_SPEC}"
        content = open(EXTRACT_SPEC, encoding="utf-8").read()
        assert ".extract(" in content, "spec must exercise .extract(...)"

    def test_l1_descriptor_mentions_transform_and_limit(self):
        """L1: the descriptor type / logic references both new option names."""
        content = open(EXTRACT_TS, encoding="utf-8").read()
        assert re.search(r"\btransform\b", content), (
            "extract.ts must reference a `transform` option"
        )
        assert re.search(r"\blimit\b", content), (
            "extract.ts must reference a `limit` option"
        )

    def test_l1_spec_adds_new_cases(self):
        """L1: extract.spec.ts adds cases for the new transform/limit behavior."""
        content = open(EXTRACT_SPEC, encoding="utf-8").read()
        assert "transform" in content, "spec must add transform coverage"
        assert "limit" in content, "spec must add limit coverage"

    # ----------------------- L2: dynamic execution -----------------------

    def test_l2_injected_spec_runs_clean(self):
        """L2: the injected independent spec compiles and runs (vitest exit 0).

        This is the gate: if the new options are unimplemented, the public
        extract API will silently ignore them and the behavioral assertions
        below will fail, driving a non-zero exit code.
        """
        result = _get_injected_result()
        assert result["returncode"] == 0, (
            "Injected vitest spec failed.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )

    def test_l2_transform_single(self):
        """L2: transform on a single descriptor post-processes the value (FOUR)."""
        _assert_titles_passed(
            _get_injected_result(),
            ["transform single uppercases", "transform default value source"],
        )

    def test_l2_transform_skipped_when_no_match(self):
        """L2: transform is NOT invoked for a non-matching single descriptor."""
        _assert_titles_passed(
            _get_injected_result(),
            ["transform not called on non-matching"],
        )

    def test_l2_transform_changes_type_and_undefined(self):
        """L2: transform may change the value's type and may return undefined."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "transform may change type to number",
                "transform may return undefined",
            ],
        )

    def test_l2_transform_per_array_element(self):
        """L2: transform applies to each element of an array descriptor."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "transform applied per element of array",
                "array transform receives custom value-function output",
            ],
        )

    def test_l2_transform_on_nested_object(self):
        """L2: transform applies to a nested extracted object value."""
        _assert_titles_passed(
            _get_injected_result(),
            ["transform applied to nested extracted object"],
        )

    def test_l2_limit_caps_first_n(self):
        """L2: limit caps an array to the first N document-order matches."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "limit caps array to first N",
                "limit one yields first match only",
            ],
        )

    def test_l2_limit_zero_empty(self):
        """L2: a limit of 0 produces an empty array."""
        _assert_titles_passed(
            _get_injected_result(),
            ["limit zero yields empty array"],
        )

    def test_l2_limit_over_count_unlimited(self):
        """L2: a limit >= match count behaves as if unlimited."""
        _assert_titles_passed(
            _get_injected_result(),
            ["limit >= match count behaves as unlimited"],
        )

    def test_l2_limit_ignored_on_single(self):
        """L2: limit has no effect on a single (non-array) descriptor."""
        _assert_titles_passed(
            _get_injected_result(),
            ["limit has no effect on single descriptor"],
        )

    def test_l2_limit_with_transform(self):
        """L2: limit and transform combine: cap matches, transform each value."""
        _assert_titles_passed(
            _get_injected_result(),
            ["limit combined with transform"],
        )

    def test_l2_original_behavior_preserved(self):
        """L2: extract without transform/limit keeps original semantics."""
        _assert_titles_passed(
            _get_injected_result(),
            ["no transform/limit preserves original behavior"],
        )

    def test_l2_repo_extract_spec_passes(self):
        """L2: the repo's own extract.spec.ts still passes (pre-existing + new)."""
        rel = os.path.join("src", "api", "extract.spec.ts")
        result = _run_vitest(rel, timeout=600)
        assert result["returncode"] == 0, (
            "Repo's extract.spec.ts must pass under `vitest run`.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )
