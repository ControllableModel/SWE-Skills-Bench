"""Tests for the `cheerio-parsing` skill (variant ext8).

Skill task: build a document-metadata extractor on top of cheerio. The agent
must create:

  * ``src/api/metadata.ts`` exporting ``extractMetadata(html: string)`` that
    loads the markup and returns
    ``{ title, description, canonical, og }`` where

      - ``title``       -> trimmed text of ``<title>``, else ``null``;
      - ``description`` -> ``content`` of ``<meta name="description">``, else
        ``null``;
      - ``canonical``   -> ``href`` of ``<link rel="canonical">``, else
        ``null``;
      - ``og``          -> object of every ``<meta property="og:*">`` keyed by
        the property with the leading ``og:`` stripped (last duplicate wins),
        else ``{}``.

  * ``src/api/metadata.spec.ts`` with deterministic coverage.

The agent edits the cheerio repo at REPO_DIR. After it finishes, this file is
run with pytest. Verification strategy:

  * L1 -- the deliverable files exist and are minimally well-formed.
  * L2 -- DYNAMIC EXECUTION: we drop an INDEPENDENT vitest spec into the repo's
    own ``src/api`` directory that imports the agent's real, freshly-built
    ``extractMetadata`` through ``./metadata.js`` and asserts on concrete
    return values for full extraction, all-absent defaults, title trimming,
    ``og:`` prefix stripping, last-wins on duplicate og props, empty-og
    default, exact attribute matching, and no-throw on missing tags. A naive
    implementation (hardcoded result, ignored input, missing trim, kept
    ``og:`` prefix, wrong duplicate handling) FAILS these specs. We also run
    the agent's own ``metadata.spec.ts`` via the native acceptance command.

The native acceptance command driven by L2 is:

    npx vitest run src/api/metadata.spec.ts
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
METADATA_TS = os.path.join(REPO_DIR, "src", "api", "metadata.ts")
METADATA_SPEC = os.path.join(REPO_DIR, "src", "api", "metadata.spec.ts")
API_DIR = os.path.join(REPO_DIR, "src", "api")

# Name of the independent spec file we inject. Distinct from metadata.spec.ts so
# the repo's vitest typecheck (scoped to extract.spec.ts) does not gate it and so
# we never collide with the agent's own deliverable spec.
INJECTED_SPEC_NAME = "metadata_skillcheck.spec.ts"
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
# This spec exercises the metadata extractor strictly through the agent's
# exported `extractMetadata`. Every `it(...)` maps to a contract requirement and
# carries a stable, greppable title so the Python layer can assert on individual
# outcomes (not just an aggregate pass), making naive impls detectable.

_INJECTED_SPEC = r"""
import { describe, expect, it } from 'vitest';
import { extractMetadata } from './metadata.js';

const FULL = `
<!doctype html>
<html>
  <head>
    <title>  Home Page  </title>
    <meta name="description" content="A friendly homepage">
    <link rel="canonical" href="https://example.com/home">
    <meta property="og:title" content="OG Home">
    <meta property="og:type" content="website">
  </head>
  <body><p>hi</p></body>
</html>
`;

const EMPTY = `<!doctype html><html><head></head><body><p>nothing</p></body></html>`;

describe('extractMetadata skillcheck', () => {
  it('SKILLCHECK full extraction returns all fields', () => {
    expect(extractMetadata(FULL)).toStrictEqual({
      title: 'Home Page',
      description: 'A friendly homepage',
      canonical: 'https://example.com/home',
      og: { title: 'OG Home', type: 'website' },
    });
  });

  it('SKILLCHECK all-absent defaults to nulls and empty og', () => {
    expect(extractMetadata(EMPTY)).toStrictEqual({
      title: null,
      description: null,
      canonical: null,
      og: {},
    });
  });

  it('SKILLCHECK title text is trimmed', () => {
    const html = '<html><head><title>\n  Spaced Title  \n</title></head></html>';
    expect(extractMetadata(html).title).toBe('Spaced Title');
  });

  it('SKILLCHECK missing title yields null not empty string', () => {
    const html = '<html><head><meta name="description" content="d"></head></html>';
    const md = extractMetadata(html);
    expect(md.title).toBeNull();
  });

  it('SKILLCHECK description reads content of meta name=description', () => {
    const html =
      '<html><head><meta name="description" content="Read me"></head></html>';
    expect(extractMetadata(html).description).toBe('Read me');
  });

  it('SKILLCHECK description matching is exact on name attribute', () => {
    // name="keywords" must NOT be picked up as the description.
    const html =
      '<html><head><meta name="keywords" content="a,b,c"></head></html>';
    expect(extractMetadata(html).description).toBeNull();
  });

  it('SKILLCHECK canonical reads href of link rel=canonical', () => {
    const html =
      '<html><head><link rel="canonical" href="/abs/path"></head></html>';
    expect(extractMetadata(html).canonical).toBe('/abs/path');
  });

  it('SKILLCHECK canonical matching is exact on rel attribute', () => {
    // rel="stylesheet" must NOT be treated as canonical.
    const html =
      '<html><head><link rel="stylesheet" href="/x.css"></head></html>';
    expect(extractMetadata(html).canonical).toBeNull();
  });

  it('SKILLCHECK og keys strip the og: prefix', () => {
    const html =
      '<html><head><meta property="og:image" content="/img.png"></head></html>';
    const md = extractMetadata(html);
    expect(md.og).toStrictEqual({ image: '/img.png' });
    // The raw, un-stripped key must NOT be present.
    expect('og:image' in md.og).toBe(false);
  });

  it('SKILLCHECK multiple og tags collected into one object', () => {
    const html =
      '<html><head>' +
      '<meta property="og:title" content="T">' +
      '<meta property="og:description" content="D">' +
      '<meta property="og:url" content="U">' +
      '</head></html>';
    expect(extractMetadata(html).og).toStrictEqual({
      title: 'T',
      description: 'D',
      url: 'U',
    });
  });

  it('SKILLCHECK duplicate og property last one wins', () => {
    const html =
      '<html><head>' +
      '<meta property="og:title" content="First">' +
      '<meta property="og:title" content="Second">' +
      '</head></html>';
    expect(extractMetadata(html).og).toStrictEqual({ title: 'Second' });
  });

  it('SKILLCHECK no og tags yields empty object', () => {
    const html =
      '<html><head><meta name="description" content="d"></head></html>';
    const md = extractMetadata(html);
    expect(md.og).toStrictEqual({});
    expect(Object.keys(md.og).length).toBe(0);
  });

  it('SKILLCHECK non-og property meta is ignored from og', () => {
    // property without og: prefix (e.g. article:author) must not appear.
    const html =
      '<html><head>' +
      '<meta property="article:author" content="Jane">' +
      '<meta property="og:title" content="Keep">' +
      '</head></html>';
    expect(extractMetadata(html).og).toStrictEqual({ title: 'Keep' });
  });

  it('SKILLCHECK does not throw on empty document', () => {
    expect(() => extractMetadata('')).not.toThrow();
    const md = extractMetadata('');
    expect(md.title).toBeNull();
    expect(md.description).toBeNull();
    expect(md.canonical).toBeNull();
    expect(md.og).toStrictEqual({});
  });

  it('SKILLCHECK ignores body-level title and uses head metadata', () => {
    // Even with a body title, the description/canonical/og come from head meta.
    const html =
      '<html><head>' +
      '<title>Head Title</title>' +
      '<meta name="description" content="HeadDesc">' +
      '<link rel="canonical" href="/c">' +
      '</head><body><p>content</p></body></html>';
    expect(extractMetadata(html)).toStrictEqual({
      title: 'Head Title',
      description: 'HeadDesc',
      canonical: '/c',
      og: {},
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

    def test_l1_metadata_source_exists(self):
        """L1: src/api/metadata.ts exists and is non-trivial TypeScript."""
        assert os.path.isfile(METADATA_TS), f"missing {METADATA_TS}"
        content = open(METADATA_TS, encoding="utf-8").read()
        assert len(content) > 200, "metadata.ts unexpectedly small"

    def test_l1_metadata_exports_extract_metadata(self):
        """L1: metadata.ts exports an `extractMetadata` function."""
        content = open(METADATA_TS, encoding="utf-8").read()
        assert re.search(
            r"export\s+(?:async\s+)?function\s+extractMetadata\b", content
        ) or re.search(
            r"export\s+(?:const|let)\s+extractMetadata\b", content
        ) or re.search(
            r"export\s*\{[^}]*\bextractMetadata\b", content
        ), "metadata.ts must export `extractMetadata`"

    def test_l1_metadata_references_head_metadata_concepts(self):
        """L1: metadata.ts references the metadata concepts it must extract."""
        content = open(METADATA_TS, encoding="utf-8").read()
        assert re.search(r"\bcanonical\b", content), (
            "metadata.ts must reference the canonical link"
        )
        assert re.search(r"\bog\b|og:", content), (
            "metadata.ts must reference Open Graph (og) handling"
        )
        assert re.search(r"\bdescription\b", content), (
            "metadata.ts must reference the description meta"
        )

    def test_l1_metadata_spec_exists(self):
        """L1: src/api/metadata.spec.ts exists and exercises extractMetadata."""
        assert os.path.isfile(METADATA_SPEC), f"missing {METADATA_SPEC}"
        content = open(METADATA_SPEC, encoding="utf-8").read()
        assert "extractMetadata" in content, (
            "metadata.spec.ts must exercise extractMetadata"
        )

    def test_l1_spec_covers_required_cases(self):
        """L1: metadata.spec.ts covers the doc's required scenarios."""
        content = open(METADATA_SPEC, encoding="utf-8").read()
        # Doc requires coverage of og prefix handling and duplicate/last-wins.
        assert "og:" in content or "og " in content or '"og"' in content, (
            "metadata.spec.ts must cover Open Graph extraction"
        )
        assert "canonical" in content, "metadata.spec.ts must cover canonical"

    # ----------------------- L2: dynamic execution -----------------------

    def test_l2_injected_spec_runs_clean(self):
        """L2: the injected independent spec compiles and runs (vitest exit 0).

        This is the gate: if extractMetadata is missing, mis-shaped, or naive,
        the behavioral assertions below drive a non-zero exit code.
        """
        result = _get_injected_result()
        assert result["returncode"] == 0, (
            "Injected vitest spec failed.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )

    def test_l2_full_extraction(self):
        """L2: full document yields title/description/canonical/og together."""
        _assert_titles_passed(
            _get_injected_result(),
            ["full extraction returns all fields"],
        )

    def test_l2_all_absent_defaults(self):
        """L2: a document with no metadata returns nulls and empty og."""
        _assert_titles_passed(
            _get_injected_result(),
            ["all-absent defaults to nulls and empty og"],
        )

    def test_l2_title_trimmed_and_null(self):
        """L2: title text is trimmed; absent title is null (not '')."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "title text is trimmed",
                "missing title yields null not empty string",
            ],
        )

    def test_l2_description_exact_match(self):
        """L2: description reads exact name=description; others ignored."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "description reads content of meta name=description",
                "description matching is exact on name attribute",
            ],
        )

    def test_l2_canonical_exact_match(self):
        """L2: canonical reads href of rel=canonical only."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "canonical reads href of link rel=canonical",
                "canonical matching is exact on rel attribute",
            ],
        )

    def test_l2_og_prefix_stripped(self):
        """L2: og keys strip the leading `og:` prefix."""
        _assert_titles_passed(
            _get_injected_result(),
            ["og keys strip the og: prefix"],
        )

    def test_l2_og_collected_and_filtered(self):
        """L2: multiple og tags collected; non-og property meta excluded."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "multiple og tags collected into one object",
                "non-og property meta is ignored from og",
            ],
        )

    def test_l2_og_duplicate_last_wins(self):
        """L2: when og properties repeat, the last in document order wins."""
        _assert_titles_passed(
            _get_injected_result(),
            ["duplicate og property last one wins"],
        )

    def test_l2_og_empty_default(self):
        """L2: absence of og tags yields an empty object `{}`."""
        _assert_titles_passed(
            _get_injected_result(),
            ["no og tags yields empty object"],
        )

    def test_l2_no_throw_on_empty(self):
        """L2: extractMetadata does not throw on empty/degenerate input."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "does not throw on empty document",
                "ignores body-level title and uses head metadata",
            ],
        )

    def test_l2_agent_metadata_spec_passes(self):
        """L2: the agent's own metadata.spec.ts passes (native acceptance cmd).

        Drives exactly `npx vitest run src/api/metadata.spec.ts`.
        """
        rel = os.path.join("src", "api", "metadata.spec.ts")
        result = _run_vitest(rel, timeout=600)
        assert result["returncode"] == 0, (
            "Agent's metadata.spec.ts must pass under `vitest run`.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )
