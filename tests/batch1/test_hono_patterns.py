"""Tests for the `hono-patterns` skill task: a mountable in-memory notes resource.

Verifies the deliverable `src/helper/notes-resource/index.ts` (and its colocated
`index.test.ts`) inside the Hono repo at /workspace/hono.

Strategy
--------
- L1: the required deliverable files exist and are minimally well-formed (export the
  factory, register the CRUD verbs, ship a colocated vitest test file).
- L2: DYNAMIC EXECUTION. We write an *independent* vitest spec into the repo that
  imports the agent's `createNotesResource()` and exercises every requirement of the
  task (isolation, listing shape, multi-tag AND filtering, exact case-sensitive
  matching, CRUD round-trips, numeric-only id routing, 400/404 paths, store
  immutability on errors, mounted-under-a-prefix behavior). It dispatches IN-MEMORY
  requests via `app.request(...)` and asserts on the real JSON / status codes the
  module returns. A naive implementation (shared global store, ignoring repeated
  `tag` params, treating non-numeric ids as valid lookups, or omitting the 400/404
  paths) fails these named cases.

  To keep runtime bounded we run that independent spec ONCE with vitest's JSON
  reporter, cache the per-test results module-wide, and have each L2 Python test
  assert on one specific named case (and that the case actually executed — a missing
  case is treated as a failure, so a solution can't pass by making cases disappear).

- The agent's OWN colocated suite is checked separately: it must contain >=10 cases
  and pass, per the acceptance criteria.

Native test command (per task acceptance criteria):
    npx vitest --run src/helper/notes-resource/index.test.ts
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
MODULE_DIR = os.path.join(REPO_DIR, "src", "helper", "notes-resource")
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
# ---------------------------------------------------------------------------
_VERIFY_SPEC_SRC = textwrap.dedent(
    """
    import { describe, it, expect } from 'vitest'
    import { Hono } from '../../hono'
    import { createNotesResource } from '.'

    const base = 'http://localhost'

    // Parent app with the resource mounted under a non-empty prefix.
    const mounted = (prefix = '/api/notes') => {
      const app = new Hono()
      app.route(prefix, createNotesResource())
      return app
    }
    const post = (app, body) =>
      app.request(base + '/api/notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    const get = (app, path = '') => app.request(base + '/api/notes' + path)

    describe('notes-resource verification', () => {
      it('create_201_assigns_numeric_id_empty_tags', async () => {
        const app = mounted()
        const res = await post(app, { title: 'hello' })
        expect(res.status).toBe(201)
        const n = await res.json()
        expect(n.title).toBe('hello')
        expect(Array.isArray(n.tags)).toBe(true)
        expect(n.tags).toEqual([])
        expect(typeof n.id).toBe('string')
        expect(/^[0-9]+$/.test(n.id)).toBe(true)
      })

      it('create_missing_title_400_no_mutation', async () => {
        const app = mounted()
        const bad = await post(app, { tags: ['x'] })
        expect(bad.status).toBe(400)
        expect(typeof (await bad.json()).error).toBe('string')
        const bad2 = await post(app, { title: 123 })
        expect(bad2.status).toBe(400)
        const list = await (await get(app)).json()
        expect(list.notes).toEqual([])
      })

      it('list_shape_and_read_round_trip', async () => {
        const app = mounted()
        const created = await (await post(app, { title: 'rt', tags: ['a', 'b'] })).json()
        const listRes = await get(app)
        expect(listRes.status).toBe(200)
        const data = await listRes.json()
        expect(Array.isArray(data.notes)).toBe(true)
        expect(data.notes.length).toBe(1)
        expect(data.notes[0].id).toBe(created.id)
        const oneRes = await get(app, '/' + created.id)
        expect(oneRes.status).toBe(200)
        const got = await oneRes.json()
        expect(got).toMatchObject({ id: created.id, title: 'rt', tags: ['a', 'b'] })
      })

      it('instances_are_isolated', async () => {
        const a = new Hono(); a.route('/api/notes', createNotesResource())
        const b = new Hono(); b.route('/api/notes', createNotesResource())
        await post(a, { title: 'only-in-a' })
        const la = await (await get(a)).json()
        const lb = await (await get(b)).json()
        expect(la.notes.length).toBe(1)
        expect(lb.notes.length).toBe(0)
      })

      it('multi_tag_filter_is_AND', async () => {
        const app = mounted()
        const both = await (await post(app, { title: 'both', tags: ['work', 'home'] })).json()
        await post(app, { title: 'workOnly', tags: ['work'] })
        await post(app, { title: 'homeOnly', tags: ['home'] })
        await post(app, { title: 'extra', tags: ['work', 'home', 'misc'] })
        const res = await get(app, '?tag=work&tag=home')
        expect(res.status).toBe(200)
        const data = await res.json()
        const titles = data.notes.map((n) => n.title).sort()
        expect(titles).toEqual(['both', 'extra'])
        expect(data.notes.some((n) => n.id === both.id)).toBe(true)
      })

      it('single_tag_exact_case_sensitive', async () => {
        const app = mounted()
        await post(app, { title: 'exact', tags: ['work'] })
        await post(app, { title: 'substr', tags: ['workplace'] })
        await post(app, { title: 'upper', tags: ['WORK'] })
        const res = await get(app, '?tag=work')
        const data = await res.json()
        expect(data.notes.map((n) => n.title)).toEqual(['exact'])
        const all = await (await get(app)).json()
        expect(all.notes.length).toBe(3)
      })

      it('get_unknown_numeric_id_404', async () => {
        const app = mounted()
        const res = await get(app, '/999999')
        expect(res.status).toBe(404)
        expect(typeof (await res.json()).error).toBe('string')
      })

      it('non_numeric_id_unmatched_404', async () => {
        const app = mounted()
        expect((await get(app, '/abc')).status).toBe(404)
        expect((await app.request(base + '/api/notes/abc', { method: 'DELETE' })).status).toBe(404)
        const put = await app.request(base + '/api/notes/12a', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: 'x' }),
        })
        expect(put.status).toBe(404)
      })

      it('put_replaces_preserves_id_and_404_missing', async () => {
        const app = mounted()
        const created = await (await post(app, { title: 'old', tags: ['a'] })).json()
        const res = await app.request(base + '/api/notes/' + created.id, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: 'new', tags: ['b', 'c'] }),
        })
        expect(res.status).toBe(200)
        const updated = await res.json()
        expect(updated.id).toBe(created.id)
        expect(updated.title).toBe('new')
        expect(updated.tags).toEqual(['b', 'c'])
        const reread = await (await get(app, '/' + created.id)).json()
        expect(reread.title).toBe('new')
        expect(reread.tags).toEqual(['b', 'c'])
        const missing = await app.request(base + '/api/notes/424242', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: 'z' }),
        })
        expect(missing.status).toBe(404)
        expect(typeof (await missing.json()).error).toBe('string')
      })

      it('delete_then_read_404_and_delete_missing_404', async () => {
        const app = mounted()
        const created = await (await post(app, { title: 'doomed' })).json()
        const del = await app.request(base + '/api/notes/' + created.id, { method: 'DELETE' })
        expect(del.status).toBe(200)
        expect((await get(app, '/' + created.id)).status).toBe(404)
        const list = await (await get(app)).json()
        expect(list.notes.length).toBe(0)
        const missing = await app.request(base + '/api/notes/777777', { method: 'DELETE' })
        expect(missing.status).toBe(404)
        expect(typeof (await missing.json()).error).toBe('string')
      })

      it('distinct_stable_ids_within_instance', async () => {
        const app = mounted()
        const ids = []
        for (let i = 0; i < 5; i++) {
          const n = await (await post(app, { title: 't' + i })).json()
          expect(/^[0-9]+$/.test(n.id)).toBe(true)
          ids.push(n.id)
        }
        expect(new Set(ids).size).toBe(5)
        const got = await (await get(app, '/' + ids[0])).json()
        expect(got.id).toBe(ids[0])
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
        proc = _run_vitest("src/helper/notes-resource/__bench_verify.test.ts", timeout=600, json_out=json_path)
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
        """L1: the notes-resource module file is present."""
        assert os.path.isfile(MODULE_TS), f"missing deliverable {MODULE_TS}"

    def test_module_exports_factory(self):
        """L1: module source exports a `createNotesResource` factory."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "createNotesResource" in src, "createNotesResource not found"
        assert "export" in src and "createNotesResource" in src, "factory not exported"

    def test_module_registers_crud_routes(self):
        """L1: module registers the four HTTP verbs needed for the CRUD contract."""
        with open(MODULE_TS) as f:
            src = f.read()
        for verb in (".get(", ".post(", ".put(", ".delete("):
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
        result = _run_vitest("src/helper/notes-resource/index.test.ts", timeout=600)
        assert result.returncode == 0, (
            "agent's colocated vitest suite failed:\n"
            f"STDOUT:\n{result.stdout[-4000:]}\nSTDERR:\n{result.stderr[-3000:]}"
        )

    # ------------------------------------------------------------- L2 ----
    # Each maps to one task requirement, verified by the independent spec.

    def test_create_201_assigns_numeric_id_empty_tags(self):
        """L2: POST -> 201 with assigned numeric id; missing tags default to []."""
        _assert_case("create_201_assigns_numeric_id_empty_tags")

    def test_create_missing_title_400_no_mutation(self):
        """L2: POST without a string title -> 400 {error}; store unchanged."""
        _assert_case("create_missing_title_400_no_mutation")

    def test_list_shape_and_read_round_trip(self):
        """L2: GET collection returns {notes:[...]} and a note round-trips by id under a prefix."""
        _assert_case("list_shape_and_read_round_trip")

    def test_instances_are_isolated(self):
        """L2: two createNotesResource() instances never share state."""
        _assert_case("instances_are_isolated")

    def test_multi_tag_filter_is_AND(self):
        """L2: repeated ?tag= params require a note to contain EVERY supplied tag."""
        _assert_case("multi_tag_filter_is_AND")

    def test_single_tag_exact_case_sensitive(self):
        """L2: single ?tag filter is exact and case-sensitive (no substring/case match)."""
        _assert_case("single_tag_exact_case_sensitive")

    def test_get_unknown_numeric_id_404(self):
        """L2: GET a well-formed-but-missing numeric id -> 404 {error}."""
        _assert_case("get_unknown_numeric_id_404")

    def test_non_numeric_id_unmatched_404(self):
        """L2: non-numeric id segment never matches single-note routes (GET/PUT/DELETE -> 404)."""
        _assert_case("non_numeric_id_unmatched_404")

    def test_put_replaces_preserves_id_and_404_missing(self):
        """L2: PUT replaces title+tags, preserves id, returns 200; missing id -> 404."""
        _assert_case("put_replaces_preserves_id_and_404_missing")

    def test_delete_then_read_404_and_delete_missing_404(self):
        """L2: DELETE existing -> 200 then read 404; DELETE missing -> 404 {error}."""
        _assert_case("delete_then_read_404_and_delete_missing_404")

    def test_distinct_stable_ids_within_instance(self):
        """L2: every created note within an instance receives a distinct, stable numeric id."""
        _assert_case("distinct_stable_ids_within_instance")
