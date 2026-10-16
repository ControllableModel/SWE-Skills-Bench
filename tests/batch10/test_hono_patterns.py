"""Tests for the `hono-patterns` skill task (variant ext10): a streaming activity-feed module.

Verifies the deliverable `src/helper/activity-feed/index.ts` (and its colocated
`index.test.ts`) inside the Hono repo at /workspace/hono.

Task under test
---------------
The agent must add a helper module exporting a factory `createFeed()` that returns a
fresh mountable sub-application holding its own private, ordered, in-memory list of
activity lines. Routes:
  * POST   /events  {line:string}  -> 201 {index:<n>} (zero-based append index),
                                       400 {error} when `line` is not a string (no mutation).
  * GET    /stream                 -> 200, Content-Type starts with text/plain, body is
                                       every buffered line, each terminated by '\\n', in
                                       buffer order; empty buffer -> empty body; the stream
                                       must be finite / fully readable to completion.
  * GET    /count                  -> 200 {count:<n>}.
  * DELETE /events                 -> 200 {count:0}, buffer emptied.
The contract must hold both directly and when mounted under a non-empty prefix; two
calls to createFeed() must have isolated buffers.

Strategy
--------
- L1: the required deliverable files exist and are minimally well-formed (export the
  `createFeed` factory, register the POST/GET/DELETE routes, ship a colocated vitest
  test file with >=10 cases).
- L2: DYNAMIC EXECUTION. We write an *independent* vitest spec into the repo that
  imports the agent's `createFeed()` and exercises every requirement by dispatching
  IN-MEMORY requests via `app.request(...)` and reading the *streamed* response body
  fully as text. It asserts on real status codes, JSON fields, exact streamed bytes,
  ordering, the text/plain Content-Type, isolation, and the 400/empty/clear edge
  cases. A naive implementation (non-terminating stream, wrong ordering, missing
  trailing newline, shared global buffer, ignoring the 400 path) fails named cases.

  To keep runtime bounded we run that independent spec ONCE with vitest's JSON
  reporter, cache the per-test results module-wide, and have each L2 Python test
  assert on one specific named case (and that the case actually executed — a missing
  case is treated as a failure, so a solution can't pass by deleting cases).

- The agent's OWN colocated suite is checked separately: it must contain >=10 cases
  and pass, per the acceptance criteria.

Native test command (per task acceptance criteria):
    npx vitest --run src/helper/activity-feed/index.test.ts
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
MODULE_DIR = os.path.join(REPO_DIR, "src", "helper", "activity-feed")
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
# Notes on robustness of these assertions:
#   * We always read the streamed body via `res.text()` to completion -> if the
#     stream never terminates, vitest's per-test timeout fails the case (a
#     non-terminating naive stream cannot pass).
#   * We assert EXACT streamed bytes (including trailing '\n' on the last line),
#     so a missing-trailing-newline or wrong-order impl fails.
#   * The prefix used for the mounted app is non-empty and non-root ('/feed/v1')
#     so a module that hardcodes '/' or assumes no prefix fails.
# ---------------------------------------------------------------------------
_VERIFY_SPEC_SRC = textwrap.dedent(
    """
    import { describe, it, expect } from 'vitest'
    import { Hono } from '../../hono'
    import { createFeed } from '.'

    const base = 'http://localhost'
    const PREFIX = '/feed/v1'

    // Parent app with the feed mounted under a non-empty, non-root prefix.
    const mounted = () => {
      const app = new Hono()
      app.route(PREFIX, createFeed())
      return app
    }
    const post = (app, body) =>
      app.request(base + PREFIX + '/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    const del = (app) => app.request(base + PREFIX + '/events', { method: 'DELETE' })
    const get = (app, path) => app.request(base + PREFIX + path)

    describe('activity-feed verification', () => {
      it('append_returns_201_and_zero_based_index', async () => {
        const app = mounted()
        const r0 = await post(app, { line: 'a' })
        expect(r0.status).toBe(201)
        const j0 = await r0.json()
        expect(j0.index).toBe(0)
        const r1 = await post(app, { line: 'b' })
        expect(r1.status).toBe(201)
        const j1 = await r1.json()
        expect(j1.index).toBe(1)
      })

      it('stream_exact_body_with_trailing_newlines_in_order', async () => {
        const app = mounted()
        await post(app, { line: 'a' })
        await post(app, { line: 'b' })
        const res = await get(app, '/stream')
        expect(res.status).toBe(200)
        const ct = res.headers.get('Content-Type') || ''
        expect(ct.startsWith('text/plain')).toBe(true)
        const body = await res.text()
        // exact: each line, including the last, terminated by a single '\\n'
        expect(body).toBe('a\\nb\\n')
      })

      it('stream_preserves_insertion_order_not_sorted', async () => {
        const app = mounted()
        // Intentionally non-sorted insertion order to catch sort()-based impls.
        for (const line of ['banana', 'apple', 'cherry']) {
          await post(app, { line })
        }
        const body = await (await get(app, '/stream')).text()
        expect(body).toBe('banana\\napple\\ncherry\\n')
      })

      it('empty_feed_streams_empty_body', async () => {
        const app = mounted()
        const res = await get(app, '/stream')
        expect(res.status).toBe(200)
        const body = await res.text()
        expect(body).toBe('')
      })

      it('count_reflects_buffer_size', async () => {
        const app = mounted()
        const c0 = await (await get(app, '/count')).json()
        expect(c0.count).toBe(0)
        await post(app, { line: 'x' })
        await post(app, { line: 'y' })
        await post(app, { line: 'z' })
        const c3res = await get(app, '/count')
        expect(c3res.status).toBe(200)
        const c3 = await c3res.json()
        expect(c3.count).toBe(3)
      })

      it('non_string_line_400_no_mutation_no_index_skip', async () => {
        const app = mounted()
        const ok = await (await post(app, { line: 'first' })).json()
        expect(ok.index).toBe(0)
        // non-string line -> 400 {error}, nothing appended
        const bad = await post(app, { line: 123 })
        expect(bad.status).toBe(400)
        expect(typeof (await bad.json()).error).toBe('string')
        // missing line entirely -> 400 too
        const bad2 = await post(app, { note: 'nope' })
        expect(bad2.status).toBe(400)
        // buffer unchanged: count still 1, next index is 1 (not 2/3)
        const c = await (await get(app, '/count')).json()
        expect(c.count).toBe(1)
        const next = await (await post(app, { line: 'second' })).json()
        expect(next.index).toBe(1)
        const body = await (await get(app, '/stream')).text()
        expect(body).toBe('first\\nsecond\\n')
      })

      it('delete_clears_buffer_returns_count_zero', async () => {
        const app = mounted()
        await post(app, { line: 'a' })
        await post(app, { line: 'b' })
        const d = await del(app)
        expect(d.status).toBe(200)
        const dj = await d.json()
        expect(dj.count).toBe(0)
        const c = await (await get(app, '/count')).json()
        expect(c.count).toBe(0)
        const body = await (await get(app, '/stream')).text()
        expect(body).toBe('')
      })

      it('append_index_resets_after_clear', async () => {
        const app = mounted()
        await post(app, { line: 'a' })
        await post(app, { line: 'b' })
        await del(app)
        // after a clear the next appended line is at index 0 again
        const r = await post(app, { line: 'fresh' })
        const j = await r.json()
        expect(j.index).toBe(0)
        const body = await (await get(app, '/stream')).text()
        expect(body).toBe('fresh\\n')
      })

      it('instances_have_isolated_buffers', async () => {
        const a = new Hono(); a.route(PREFIX, createFeed())
        const b = new Hono(); b.route(PREFIX, createFeed())
        await a.request(base + PREFIX + '/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ line: 'only-in-a' }),
        })
        const ca = await (await a.request(base + PREFIX + '/count')).json()
        const cb = await (await b.request(base + PREFIX + '/count')).json()
        expect(ca.count).toBe(1)
        expect(cb.count).toBe(0)
        const bodyB = await (await b.request(base + PREFIX + '/stream')).text()
        expect(bodyB).toBe('')
      })

      it('works_directly_without_prefix', async () => {
        // Use the feed app as the top-level app (mounted at root '').
        const app = createFeed()
        const r0 = await app.request(base + '/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ line: 'a' }),
        })
        expect(r0.status).toBe(201)
        expect((await r0.json()).index).toBe(0)
        await app.request(base + '/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ line: 'b' }),
        })
        const body = await (await app.request(base + '/stream')).text()
        expect(body).toBe('a\\nb\\n')
        const c = await (await app.request(base + '/count')).json()
        expect(c.count).toBe(2)
      })

      it('lines_with_special_chars_preserved_verbatim', async () => {
        const app = mounted()
        // lines that are not appended via '\\n' joining must still be exact;
        // catches impls that strip/escape or that split on something else.
        for (const line of ['a b', 'tab\\tend', 'quote"q', '  spaced  ']) {
          await post(app, { line })
        }
        const body = await (await get(app, '/stream')).text()
        expect(body).toBe('a b\\ntab\\tend\\nquote"q\\n  spaced  \\n')
        const c = await (await get(app, '/count')).json()
        expect(c.count).toBe(4)
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
            "src/helper/activity-feed/__bench_verify.test.ts", timeout=600, json_out=json_path
        )
        assert os.path.isfile(json_path), (
            "vitest produced no JSON report; the independent verification spec "
            "failed to run (likely a compile/import error in the module, or a "
            "non-terminating stream that hung the run).\n"
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
        """L1: the activity-feed module file is present."""
        assert os.path.isfile(MODULE_TS), f"missing deliverable {MODULE_TS}"

    def test_module_exports_factory(self):
        """L1: module source exports a `createFeed` factory."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "createFeed" in src, "createFeed not found"
        assert "export" in src and "createFeed" in src, "factory not exported"

    def test_module_registers_required_routes(self):
        """L1: module registers the verbs needed for the append/stream/count/clear contract."""
        with open(MODULE_TS) as f:
            src = f.read()
        for verb in (".post(", ".get(", ".delete("):
            assert verb in src, f"module does not register a {verb!r} route"

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
        result = _run_vitest("src/helper/activity-feed/index.test.ts", timeout=600)
        assert result.returncode == 0, (
            "agent's colocated vitest suite failed:\n"
            f"STDOUT:\n{result.stdout[-4000:]}\nSTDERR:\n{result.stderr[-3000:]}"
        )

    # ------------------------------------------------------------- L2 ----
    # Each maps to one task requirement, verified by the independent spec.

    def test_append_returns_201_and_zero_based_index(self):
        """L2: POST /events -> 201 {index} with zero-based, incrementing index."""
        _assert_case("append_returns_201_and_zero_based_index")

    def test_stream_exact_body_with_trailing_newlines_in_order(self):
        """L2: GET /stream -> 200, text/plain, exact 'a\\nb\\n' (trailing newline per line)."""
        _assert_case("stream_exact_body_with_trailing_newlines_in_order")

    def test_stream_preserves_insertion_order_not_sorted(self):
        """L2: streamed lines follow insertion order, not sorted order."""
        _assert_case("stream_preserves_insertion_order_not_sorted")

    def test_empty_feed_streams_empty_body(self):
        """L2: GET /stream on a fresh feed -> 200 with an empty body (finite stream)."""
        _assert_case("empty_feed_streams_empty_body")

    def test_count_reflects_buffer_size(self):
        """L2: GET /count -> 200 {count} equal to the number of buffered lines."""
        _assert_case("count_reflects_buffer_size")

    def test_non_string_line_400_no_mutation_no_index_skip(self):
        """L2: non-string/missing line -> 400 {error}; buffer & next index unchanged."""
        _assert_case("non_string_line_400_no_mutation_no_index_skip")

    def test_delete_clears_buffer_returns_count_zero(self):
        """L2: DELETE /events -> 200 {count:0}; count and stream go empty."""
        _assert_case("delete_clears_buffer_returns_count_zero")

    def test_append_index_resets_after_clear(self):
        """L2: after DELETE, the next appended line is index 0 again."""
        _assert_case("append_index_resets_after_clear")

    def test_instances_have_isolated_buffers(self):
        """L2: two createFeed() instances never share buffer state."""
        _assert_case("instances_have_isolated_buffers")

    def test_works_directly_without_prefix(self):
        """L2: the feed app used directly at root behaves identically to the mounted one."""
        _assert_case("works_directly_without_prefix")

    def test_lines_with_special_chars_preserved_verbatim(self):
        """L2: appended line content is streamed verbatim (no stripping/escaping)."""
        _assert_case("lines_with_special_chars_preserved_verbatim")
