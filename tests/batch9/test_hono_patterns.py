"""Tests for the `hono-patterns` skill task (ext9): a wildcard file-tree browser module.

Verifies the deliverable `src/helper/file-tree/index.ts` (and its colocated
`index.test.ts`) inside the Hono repo at /workspace/hono.

The task asks for a factory `createFileTree(files)` that returns a mountable
sub-application serving a READ-ONLY virtual file tree, distinguishing three route
shapes:

  * GET /files/<deep/path>   -> 200 {path, content} | 404 {error}   (deep wildcard
                                capture, must include embedded slashes)
  * GET /rev/:n              -> 200 {revision, path} for a DIGIT-ONLY zero-based
                                index into insertion-ordered paths; out-of-range
                                -> 404 {error}; a NON-numeric segment must NOT match
                                the revision route (falls through to unmatched 404)
  * GET /list?prefix=...     -> 200 {prefix, paths:[...]} literal, case-sensitive,
                                insertion-ordered string-prefix filter (all paths
                                when prefix absent)

Strategy
--------
- L1: the required deliverable files exist and are minimally well-formed (export the
  `createFileTree` factory, register the three route shapes, ship a colocated vitest
  test file with >=10 cases).
- L2: DYNAMIC EXECUTION. We write an *independent* vitest spec into the repo that
  imports the agent's `createFileTree()` and exercises every requirement of the task
  by dispatching IN-MEMORY requests via `app.request(...)`, asserting on the real JSON
  and status codes the module returns. The spec runs both a directly-used instance and
  one mounted under a non-empty prefix. A naive implementation (capturing only one path
  segment, matching non-numeric revision segments, ignoring the `prefix` filter, or
  sharing state between instances) fails these named cases.

  To keep runtime bounded we run that independent spec ONCE with vitest's JSON reporter,
  cache the per-test results module-wide, and have each L2 Python test assert on one
  specific named case (and that the case actually executed — a missing case is treated
  as a failure, so a solution cannot pass by making cases disappear).

- The agent's OWN colocated suite is checked separately: it must contain >=10 cases and
  pass, per the acceptance criteria.

Native test command (per task acceptance criteria):
    npx vitest --run src/helper/file-tree/index.test.ts
"""

import json
import os
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - fallback if helper not co-located
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/hono"
MODULE_DIR = os.path.join(REPO_DIR, "src", "helper", "file-tree")
MODULE_TS = os.path.join(MODULE_DIR, "index.ts")
MODULE_TEST_TS = os.path.join(MODULE_DIR, "index.test.ts")

# Independent verification spec (unique name; never clobbers agent files).
VERIFY_SPEC = os.path.join(MODULE_DIR, "__bench_verify.test.ts")

NPX = "npx"


@pytest.fixture(scope="module", autouse=True)
def _install_deps():
    """Install repo node deps once before running native vitest."""
    if ensure_npm_dependencies is not None:
        ensure_npm_dependencies(REPO_DIR)
    yield


def _run_vitest(rel_spec, timeout, json_out=None):
    """Run vitest --run on a single spec relative to REPO_DIR.

    Coverage is disabled and the run is scoped to the `main` project to keep
    startup cheap (the repo's default vitest config enables v8 coverage and loads
    several runtime-test projects, which is needlessly slow for one spec).
    """
    cmd = [NPX, "vitest", "--run", "--project", "main", "--coverage.enabled=false"]
    if json_out:
        cmd += ["--reporter=json", f"--outputFile={json_out}"]
    cmd.append(rel_spec)
    result = subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "CI": "true"},
    )
    if result.returncode != 0 and "No test files found" in (result.stdout + result.stderr):
        # Some vitest CLIs reject --project on non-workspace runs; retry plainly.
        cmd = [NPX, "vitest", "--run", "--coverage.enabled=false"]
        if json_out:
            cmd += ["--reporter=json", f"--outputFile={json_out}"]
        cmd.append(rel_spec)
        result = subprocess.run(
            cmd,
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CI": "true"},
        )
    return result


# ---------------------------------------------------------------------------
# The single comprehensive independent verification spec. Each `it(<name>, ...)`
# maps to one task requirement; the Python L2 tests below assert on these names.
#
# Notes on the fixture data:
#   - Paths are supplied in a DELIBERATE insertion order so revision indices and
#     listing order are deterministic and checkable.
#   - `a/b/c.txt` has embedded slashes -> exercises deep wildcard capture.
#   - Prefixes `a/` and `a/b/` overlap, and `A/` (uppercase) tests case-sensitivity.
# ---------------------------------------------------------------------------
_VERIFY_SPEC_SRC = textwrap.dedent(
    """
    import { describe, it, expect } from 'vitest'
    import { Hono } from '../../hono'
    import { createFileTree } from '.'

    const base = 'http://localhost'

    // Insertion order matters: revision indices and listing order derive from it.
    const FILES = () => ({
      'a/b/c.txt': 'deep-c',
      'a/b/d.txt': 'deep-d',
      'a/readme.md': 'a-readme',
      'docs/intro.md': 'intro',
      'A/upper.txt': 'upper-cap',
    })
    const ORDER = ['a/b/c.txt', 'a/b/d.txt', 'a/readme.md', 'docs/intro.md', 'A/upper.txt']

    const PREFIX = '/repo'

    // Mount the file-tree under a non-empty prefix in a parent app.
    const mounted = (files = FILES()) => {
      const app = new Hono()
      app.route(PREFIX, createFileTree(files))
      return { app, p: (path) => base + PREFIX + path }
    }

    // Use the sub-app directly (no prefix) to prove the contract holds both ways.
    const direct = (files = FILES()) => {
      const app = createFileTree(files)
      return { app, p: (path) => base + path }
    }

    describe('file-tree verification', () => {
      it('deep_path_returns_path_and_content', async () => {
        const { app, p } = mounted()
        const res = await app.request(p('/files/a/b/c.txt'))
        expect(res.status).toBe(200)
        const body = await res.json()
        // The full deep path (with embedded slashes) must be echoed, not a single segment.
        expect(body.path).toBe('a/b/c.txt')
        expect(body.content).toBe('deep-c')
        // A different deep file resolves to its own content.
        const res2 = await app.request(p('/files/a/b/d.txt'))
        expect((await res2.json()).content).toBe('deep-d')
      })

      it('deep_path_capture_includes_embedded_slashes', async () => {
        // A naive single-segment capture (':name') would 404 here or echo only 'a'.
        const { app, p } = mounted()
        const res = await app.request(p('/files/a/b/c.txt'))
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.path).toBe('a/b/c.txt')
        expect(body.path).not.toBe('a')
        expect(body.path).not.toBe('c.txt')
        // A shallow (single-segment) path that does exist still works.
        const shallow = await app.request(p('/files/a/readme.md'))
        expect(shallow.status).toBe(200)
        expect((await shallow.json()).path).toBe('a/readme.md')
      })

      it('deep_path_missing_returns_404_error', async () => {
        const { app, p } = mounted()
        const res = await app.request(p('/files/a/b/missing'))
        expect(res.status).toBe(404)
        const body = await res.json()
        expect(typeof body.error).toBe('string')
        // A path that is a prefix of a real key but not itself a key still 404s.
        const res2 = await app.request(p('/files/a/b'))
        expect(res2.status).toBe(404)
      })

      it('revision_zero_based_index_in_insertion_order', async () => {
        const { app, p } = mounted()
        for (let i = 0; i < ORDER.length; i++) {
          const res = await app.request(p('/rev/' + i))
          expect(res.status).toBe(200)
          const body = await res.json()
          expect(body.revision).toBe(i)
          expect(typeof body.revision).toBe('number')
          expect(body.path).toBe(ORDER[i])
        }
      })

      it('revision_out_of_range_returns_404_error', async () => {
        const { app, p } = mounted()
        const res = await app.request(p('/rev/999'))
        expect(res.status).toBe(404)
        expect(typeof (await res.json()).error).toBe('string')
        // The first index beyond the last valid one is also out of range.
        const res2 = await app.request(p('/rev/' + ORDER.length))
        expect(res2.status).toBe(404)
      })

      it('revision_non_numeric_segment_is_unmatched_404', async () => {
        // A naive ':n' (no digit constraint) would match 'abc' and try to index it.
        const { app, p } = mounted()
        const res = await app.request(p('/rev/abc'))
        expect(res.status).toBe(404)
        // Mixed alphanumeric must also fall through.
        const res2 = await app.request(p('/rev/1a'))
        expect(res2.status).toBe(404)
        const res3 = await app.request(p('/rev/a1'))
        expect(res3.status).toBe(404)
      })

      it('list_with_prefix_filters_in_insertion_order', async () => {
        const { app, p } = mounted()
        const res = await app.request(p('/list?prefix=a/'))
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.prefix).toBe('a/')
        // Only paths literally starting with 'a/' (lowercase), insertion order.
        expect(body.paths).toEqual(['a/b/c.txt', 'a/b/d.txt', 'a/readme.md'])
      })

      it('list_nested_prefix_is_literal_string_prefix', async () => {
        const { app, p } = mounted()
        const res = await app.request(p('/list?prefix=a/b/'))
        const body = await res.json()
        expect(body.paths).toEqual(['a/b/c.txt', 'a/b/d.txt'])
        // A prefix matching nothing yields an empty list (not all paths).
        const none = await app.request(p('/list?prefix=zzz'))
        expect((await none.json()).paths).toEqual([])
      })

      it('list_prefix_is_case_sensitive', async () => {
        const { app, p } = mounted()
        // Uppercase 'A/' must only match the uppercase key, never the lowercase ones.
        const res = await app.request(p('/list?prefix=A/'))
        const body = await res.json()
        expect(body.paths).toEqual(['A/upper.txt'])
      })

      it('list_without_prefix_returns_all_paths_in_order', async () => {
        const { app, p } = mounted()
        const res = await app.request(p('/list'))
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.paths).toEqual(ORDER)
      })

      it('contract_holds_when_used_directly_without_prefix', async () => {
        // Same assertions but against the sub-app used directly (no mount prefix).
        const { app, p } = direct()
        const file = await app.request(p('/files/a/b/c.txt'))
        expect(file.status).toBe(200)
        expect((await file.json()).path).toBe('a/b/c.txt')
        const rev = await app.request(p('/rev/0'))
        expect((await rev.json()).path).toBe('a/b/c.txt')
        const bad = await app.request(p('/rev/abc'))
        expect(bad.status).toBe(404)
        const list = await app.request(p('/list?prefix=docs/'))
        expect((await list.json()).paths).toEqual(['docs/intro.md'])
      })

      it('instances_hold_independent_file_maps', async () => {
        const one = createFileTree({ 'only/in-one.txt': 'x' })
        const two = createFileTree({ 'only/in-two.txt': 'y' })
        const r1 = await one.request(base + '/files/only/in-one.txt')
        expect(r1.status).toBe(200)
        expect((await r1.json()).content).toBe('x')
        // in-one must NOT be visible from the second instance (no shared state).
        const cross = await two.request(base + '/files/only/in-one.txt')
        expect(cross.status).toBe(404)
        const l1 = await (await one.request(base + '/list')).json()
        const l2 = await (await two.request(base + '/list')).json()
        expect(l1.paths).toEqual(['only/in-one.txt'])
        expect(l2.paths).toEqual(['only/in-two.txt'])
      })
    })
    """
)


def _collect_assertion_results(json_path):
    """Parse vitest JSON output into {test_title: 'passed'|'failed'|...}."""
    with open(json_path) as f:
        report = json.load(f)
    results = {}
    for suite in report.get("testResults", []):
        for assertion in suite.get("assertionResults", []):
            results[assertion.get("title")] = assertion.get("status")
    return results


# Module-scoped cache so the independent spec runs exactly once.
_VERIFY_CACHE = {}


def _verify_results():
    if _VERIFY_CACHE:
        return _VERIFY_CACHE["results"]
    os.makedirs(MODULE_DIR, exist_ok=True)
    with open(VERIFY_SPEC, "w") as f:
        f.write(_VERIFY_SPEC_SRC)
    json_path = os.path.join(REPO_DIR, "__bench_verify_report.json")
    try:
        proc = _run_vitest(
            "src/helper/file-tree/__bench_verify.test.ts", timeout=600, json_out=json_path
        )
        assert os.path.isfile(json_path), (
            "vitest produced no JSON report; the independent verification spec "
            "failed to run (likely a compile/import error in the module).\n"
            f"STDOUT:\n{proc.stdout[-4000:]}\nSTDERR:\n{proc.stderr[-3000:]}"
        )
        results = _collect_assertion_results(json_path)
    finally:
        for p in (VERIFY_SPEC, json_path):
            try:
                os.remove(p)
            except OSError:
                pass
    _VERIFY_CACHE["results"] = results
    _VERIFY_CACHE["proc"] = proc
    return results


def _assert_case(name):
    """Assert a named verification case ran and passed."""
    results = _verify_results()
    status = results.get(name)
    assert status is not None, (
        f"verification case {name!r} did not run; available cases: "
        f"{sorted(results.keys())}\nvitest stderr:\n"
        f"{_VERIFY_CACHE.get('proc').stderr[-2000:] if _VERIFY_CACHE.get('proc') else ''}"
    )
    assert status == "passed", f"verification case {name!r} status={status} (expected passed)"


class TestHonoPatterns:
    REPO_DIR = "/workspace/hono"

    # ------------------------------------------------------------- L1 ----

    def test_module_file_exists(self):
        """L1: the file-tree module file is present."""
        assert os.path.isfile(MODULE_TS), f"missing deliverable {MODULE_TS}"

    def test_module_exports_factory(self):
        """L1: module source exports a `createFileTree` factory."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "createFileTree" in src, "createFileTree not found"
        assert "export" in src, "factory not exported"

    def test_module_registers_three_route_shapes(self):
        """L1: module references the three distinguishing route shapes (files / rev / list)."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert ".get(" in src, "module registers no GET route"
        assert "/files" in src, "module does not declare a /files route"
        assert "/rev" in src, "module does not declare a /rev route"
        assert "/list" in src, "module does not declare a /list route"

    def test_colocated_test_file_exists(self):
        """L1: the colocated deterministic test file exists."""
        assert os.path.isfile(MODULE_TEST_TS), f"missing {MODULE_TEST_TS}"

    def test_agent_suite_has_min_cases_and_passes(self):
        """L2/acceptance: agent's colocated suite has >=10 cases and passes via vitest."""
        with open(MODULE_TEST_TS) as f:
            test_src = f.read()
        case_count = test_src.count("it(") + test_src.count("test(")
        assert case_count >= 10, (
            f"colocated suite has only {case_count} cases; task requires >=10"
        )
        result = _run_vitest("src/helper/file-tree/index.test.ts", timeout=600)
        assert result.returncode == 0, (
            "agent's colocated vitest suite failed:\n"
            f"STDOUT:\n{result.stdout[-4000:]}\nSTDERR:\n{result.stderr[-3000:]}"
        )

    # ------------------------------------------------------------- L2 ----
    # Each maps to one task requirement, verified by the independent spec.

    def test_deep_path_returns_path_and_content(self):
        """L2: GET /files/<deep/path> -> 200 {path, content} for an existing deep key."""
        _assert_case("deep_path_returns_path_and_content")

    def test_deep_path_capture_includes_embedded_slashes(self):
        """L2: the /files route captures the FULL remaining path incl. embedded slashes."""
        _assert_case("deep_path_capture_includes_embedded_slashes")

    def test_deep_path_missing_returns_404_error(self):
        """L2: GET /files/<absent> -> 404 {error}; a partial-prefix path also 404s."""
        _assert_case("deep_path_missing_returns_404_error")

    def test_revision_zero_based_index_in_insertion_order(self):
        """L2: GET /rev/:n returns the n-th inserted path (zero-based) with numeric revision."""
        _assert_case("revision_zero_based_index_in_insertion_order")

    def test_revision_out_of_range_returns_404_error(self):
        """L2: GET /rev/<too-big> -> 404 {error}."""
        _assert_case("revision_out_of_range_returns_404_error")

    def test_revision_non_numeric_segment_is_unmatched_404(self):
        """L2: a non-digit /rev segment must NOT match the revision route (unmatched 404)."""
        _assert_case("revision_non_numeric_segment_is_unmatched_404")

    def test_list_with_prefix_filters_in_insertion_order(self):
        """L2: GET /list?prefix=a/ -> 200 {prefix, paths} of matching paths in insertion order."""
        _assert_case("list_with_prefix_filters_in_insertion_order")

    def test_list_nested_prefix_is_literal_string_prefix(self):
        """L2: prefix matching is a literal string-prefix test; a non-matching prefix -> []."""
        _assert_case("list_nested_prefix_is_literal_string_prefix")

    def test_list_prefix_is_case_sensitive(self):
        """L2: prefix matching is case-sensitive (uppercase prefix excludes lowercase keys)."""
        _assert_case("list_prefix_is_case_sensitive")

    def test_list_without_prefix_returns_all_paths_in_order(self):
        """L2: GET /list with no prefix returns every path in insertion order."""
        _assert_case("list_without_prefix_returns_all_paths_in_order")

    def test_contract_holds_when_used_directly_without_prefix(self):
        """L2: all three route shapes behave identically on a directly-used (unmounted) instance."""
        _assert_case("contract_holds_when_used_directly_without_prefix")

    def test_instances_hold_independent_file_maps(self):
        """L2: two createFileTree() instances never share file maps."""
        _assert_case("instances_hold_independent_file_maps")
