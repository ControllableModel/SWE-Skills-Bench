"""Tests for the `hono-patterns` skill task (ext5 variant): a content-negotiating
representation module.

Verifies the deliverable `src/helper/representation/index.ts` (and its colocated
`index.test.ts`) inside the Hono repo at /workspace/hono.

Task summary
------------
The agent must add a helper module exporting a factory `createRepresentation()`.
Each call returns a fresh, independent, *mountable* sub-application that serves a
single in-memory resource (`{ name, count }`) and selects its representation from
the request's `Accept` header:

  - Accept: application/json  -> 200, JSON `{ name, count }`, Content-Type begins
    with `application/json`.
  - Accept: text/html         -> 200, HTML containing both `name` and the string
    form of `count`, Content-Type begins with `text/html`.
  - Accept: text/plain        -> 200, body exactly `<name>:<count>`, Content-Type
    begins with `text/plain`.
  - Accept: */*               -> JSON representation (200).
  - Unrecognized / unsupported Accept (e.g. application/xml, missing) -> 406 with
    JSON `{ error }`, and NO mutation of the resource.

  - POST `{ name }` -> updates name, increments count by one, returns 200 with the
    new `{ name, count }`. `count` starts at 0 and advances ONLY via POST.

Verification strategy
---------------------
- L1: the required deliverable files exist and are minimally well-formed (export
  the `createRepresentation` factory, ship a colocated vitest test file).
- L2: DYNAMIC EXECUTION. We inject an *independent* vitest spec into the repo that
  imports the agent's `createRepresentation()` and exercises every requirement by
  dispatching IN-MEMORY requests via `app.request(...)` against BOTH a directly
  used instance and one mounted under a non-empty prefix. It asserts on real status
  codes, JSON fields, plain/HTML body shapes, the `Content-Type` response header,
  count progression, isolation between instances, and that a 406 never mutates.
  A naive implementation (always returning JSON, ignoring `Accept`, advancing
  `count` on reads, or sharing state across instances) fails named cases.

  The independent spec runs ONCE with vitest's JSON reporter; results are cached
  module-wide and each L2 Python test asserts on one specific named case (and that
  the case actually executed — a missing case is a failure, so a solution cannot
  pass by making cases disappear).

- The agent's OWN colocated suite is checked separately: it must contain >=10 cases
  and pass, per the acceptance criteria.

Native test command (per task acceptance criteria):
    npx vitest --run src/helper/representation/index.test.ts
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
MODULE_DIR = os.path.join(REPO_DIR, "src", "helper", "representation")
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
# We do NOT assume a particular seed name: we read the initial JSON representation
# to discover the seed `name`, then assert the contract relative to it. The only
# hard requirement is that `count` starts at 0 and advances only on POST.
# ---------------------------------------------------------------------------
_VERIFY_SPEC_SRC = textwrap.dedent(
    """
    import { describe, it, expect } from 'vitest'
    import { Hono } from '../../hono'
    import { createRepresentation } from '.'

    const base = 'http://localhost'
    const PREFIX = '/res'

    // Parent app with the resource mounted under a non-empty prefix.
    const mounted = () => {
      const app = new Hono()
      app.route(PREFIX, createRepresentation())
      return app
    }
    const url = base + PREFIX
    const getAccept = (app, accept) =>
      app.request(url, accept === undefined ? {} : { headers: { Accept: accept } })
    const postName = (app, body) =>
      app.request(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

    // Discover the seed state via the JSON representation.
    const seedState = async (app) => {
      const res = await getAccept(app, 'application/json')
      expect(res.status).toBe(200)
      return res.json()
    }

    describe('representation verification', () => {
      it('json_representation_initial_count_zero', async () => {
        const app = mounted()
        const res = await getAccept(app, 'application/json')
        expect(res.status).toBe(200)
        const ct = res.headers.get('content-type') || ''
        expect(ct.startsWith('application/json')).toBe(true)
        const body = await res.json()
        expect(typeof body.name).toBe('string')
        expect(body.name.length).toBeGreaterThan(0)
        expect(body.count).toBe(0)
      })

      it('plain_representation_exact_name_colon_count', async () => {
        const app = mounted()
        const seed = await seedState(app)
        const res = await getAccept(app, 'text/plain')
        expect(res.status).toBe(200)
        const ct = res.headers.get('content-type') || ''
        expect(ct.startsWith('text/plain')).toBe(true)
        const text = await res.text()
        expect(text).toBe(seed.name + ':' + seed.count)
      })

      it('html_representation_contains_name_and_count', async () => {
        const app = mounted()
        const seed = await seedState(app)
        const res = await getAccept(app, 'text/html')
        expect(res.status).toBe(200)
        const ct = res.headers.get('content-type') || ''
        expect(ct.startsWith('text/html')).toBe(true)
        const html = await res.text()
        expect(html.includes(seed.name)).toBe(true)
        expect(html.includes(String(seed.count))).toBe(true)
      })

      it('wildcard_accept_selects_json', async () => {
        const app = mounted()
        const res = await getAccept(app, '*/*')
        expect(res.status).toBe(200)
        const ct = res.headers.get('content-type') || ''
        expect(ct.startsWith('application/json')).toBe(true)
        const body = await res.json()
        expect(typeof body.name).toBe('string')
        expect(typeof body.count).toBe('number')
      })

      it('unsupported_accept_xml_406_json_error', async () => {
        const app = mounted()
        const res = await getAccept(app, 'application/xml')
        expect(res.status).toBe(406)
        const ct = res.headers.get('content-type') || ''
        expect(ct.startsWith('application/json')).toBe(true)
        const body = await res.json()
        expect(typeof body.error).toBe('string')
      })

      it('missing_accept_header_406', async () => {
        const app = mounted()
        const res = await getAccept(app, undefined)
        expect(res.status).toBe(406)
        const body = await res.json()
        expect(typeof body.error).toBe('string')
      })

      it('406_does_not_mutate_resource', async () => {
        const app = mounted()
        const before = await seedState(app)
        const bad1 = await getAccept(app, 'application/xml')
        expect(bad1.status).toBe(406)
        const bad2 = await getAccept(app, undefined)
        expect(bad2.status).toBe(406)
        const after = await seedState(app)
        expect(after.name).toBe(before.name)
        expect(after.count).toBe(before.count)
        expect(after.count).toBe(0)
      })

      it('get_never_advances_count', async () => {
        const app = mounted()
        // Many GETs across representations must not move count off its seed value.
        for (const a of ['application/json', 'text/plain', 'text/html', '*/*']) {
          const r = await getAccept(app, a)
          expect(r.status).toBe(200)
        }
        const body = await seedState(app)
        expect(body.count).toBe(0)
      })

      it('post_updates_name_and_increments_count', async () => {
        const app = mounted()
        const res = await postName(app, { name: 'next' })
        expect(res.status).toBe(200)
        const ct = res.headers.get('content-type') || ''
        expect(ct.startsWith('application/json')).toBe(true)
        const body = await res.json()
        expect(body).toEqual({ name: 'next', count: 1 })
        // The JSON representation must now reflect the new state.
        const after = await seedState(app)
        expect(after).toEqual({ name: 'next', count: 1 })
      })

      it('post_reflected_across_all_representations', async () => {
        const app = mounted()
        await postName(app, { name: 'alpha' })
        await postName(app, { name: 'beta' })
        const j = await seedState(app)
        expect(j).toEqual({ name: 'beta', count: 2 })
        const plain = await (await getAccept(app, 'text/plain')).text()
        expect(plain).toBe('beta:2')
        const html = await (await getAccept(app, 'text/html')).text()
        expect(html.includes('beta')).toBe(true)
        expect(html.includes('2')).toBe(true)
      })

      it('count_advances_only_by_post_sequence', async () => {
        const app = mounted()
        for (let i = 1; i <= 3; i++) {
          const res = await postName(app, { name: 'v' + i })
          expect(res.status).toBe(200)
          const body = await res.json()
          expect(body.name).toBe('v' + i)
          expect(body.count).toBe(i)
          // Interleave reads; they must not change the count.
          await getAccept(app, 'application/json')
          await getAccept(app, 'text/plain')
        }
        const final = await seedState(app)
        expect(final).toEqual({ name: 'v3', count: 3 })
      })

      it('instances_are_isolated', async () => {
        const a = mounted()
        const b = mounted()
        await postName(a, { name: 'in-a' })
        await postName(a, { name: 'in-a-2' })
        const sa = await seedState(a)
        const sb = await seedState(b)
        expect(sa.count).toBe(2)
        expect(sa.name).toBe('in-a-2')
        // Fresh instance untouched: starts at count 0, unaffected by a's mutations.
        expect(sb.count).toBe(0)
        expect(sb.name).not.toBe('in-a-2')
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
            "src/helper/representation/__bench_verify.test.ts",
            timeout=600,
            json_out=json_path,
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
        """L1: the representation module file is present."""
        assert os.path.isfile(MODULE_TS), f"missing deliverable {MODULE_TS}"

    def test_module_exports_factory(self):
        """L1: module source exports a `createRepresentation` factory."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "createRepresentation" in src, "createRepresentation not found"
        assert "export" in src, "module exports nothing"

    def test_module_negotiates_and_mutates(self):
        """L1: module reads the Accept header and registers GET + POST routes."""
        with open(MODULE_TS) as f:
            src = f.read()
        # Content negotiation must inspect the actual Accept header.
        assert "Accept" in src or "accept" in src, "module never references the Accept header"
        assert ".get(" in src, "module does not register a GET route"
        assert ".post(" in src, "module does not register a POST route"

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
        result = _run_vitest("src/helper/representation/index.test.ts", timeout=600)
        assert result.returncode == 0, (
            "agent's colocated vitest suite failed:\n"
            f"STDOUT:\n{result.stdout[-4000:]}\nSTDERR:\n{result.stderr[-3000:]}"
        )

    # ------------------------------------------------------------- L2 ----
    # Each maps to one task requirement, verified by the independent spec.

    def test_json_representation_initial_count_zero(self):
        """L2: Accept: application/json -> 200 JSON {name,count}, count starts at 0, JSON Content-Type."""
        _assert_case("json_representation_initial_count_zero")

    def test_plain_representation_exact_name_colon_count(self):
        """L2: Accept: text/plain -> 200 body exactly `<name>:<count>` with text/plain Content-Type."""
        _assert_case("plain_representation_exact_name_colon_count")

    def test_html_representation_contains_name_and_count(self):
        """L2: Accept: text/html -> 200 HTML containing name and count, text/html Content-Type."""
        _assert_case("html_representation_contains_name_and_count")

    def test_wildcard_accept_selects_json(self):
        """L2: Accept: */* selects the JSON representation."""
        _assert_case("wildcard_accept_selects_json")

    def test_unsupported_accept_xml_406_json_error(self):
        """L2: Accept: application/xml -> 406 with JSON {error}."""
        _assert_case("unsupported_accept_xml_406_json_error")

    def test_missing_accept_header_406(self):
        """L2: a request with no recognizable Accept header -> 406 {error}."""
        _assert_case("missing_accept_header_406")

    def test_406_does_not_mutate_resource(self):
        """L2: a 406 response never mutates the resource (name/count unchanged)."""
        _assert_case("406_does_not_mutate_resource")

    def test_get_never_advances_count(self):
        """L2: GETs across every representation never advance count off the seed (stays 0)."""
        _assert_case("get_never_advances_count")

    def test_post_updates_name_and_increments_count(self):
        """L2: POST {name:'next'} -> 200 {name:'next',count:1}, reflected on subsequent GET."""
        _assert_case("post_updates_name_and_increments_count")

    def test_post_reflected_across_all_representations(self):
        """L2: after POSTs, every representation (json/plain/html) reflects the new name+count."""
        _assert_case("post_reflected_across_all_representations")

    def test_count_advances_only_by_post_sequence(self):
        """L2: count advances by exactly one per POST; interleaved GETs do not change it."""
        _assert_case("count_advances_only_by_post_sequence")

    def test_instances_are_isolated(self):
        """L2: two createRepresentation() instances never share state."""
        _assert_case("instances_are_isolated")
