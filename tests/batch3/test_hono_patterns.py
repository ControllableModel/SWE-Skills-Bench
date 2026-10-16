"""Tests for the `hono-patterns` skill task (variant ext3): a versioned API aggregator.

Verifies the deliverable `src/helper/api-aggregator/index.ts` (and its colocated
`index.test.ts`) inside the Hono repo at /workspace/hono.

Variant task summary
---------------------
The agent must add a helper module exporting a factory `createApi()` that returns a
fresh, fully independent Hono sub-application. The returned value carries an
*intrinsic* `/v1` segment: regardless of the prefix it is later mounted under in a
parent app, every route must live beneath `<base>/v1/...`. Internally it composes two
independent resource groups (`ping` and `echo`) that must not share state. Contract:

  - GET  <base>/v1/ping        -> 200 { status: "ok", version: "v1" }
  - GET  <base>/v1/ping/deep   -> 200 { status: "ok", depth: 1 }
  - POST <base>/v1/echo (JSON) -> 200 { echo: <parsed body> }
  - GET  <base>/v1/echo/:phrase                  -> 200 { phrase: <segment> }
  - GET  <base>/v1/echo/:phrase?repeat=a&repeat=b -> 200 { ..., repeats: ["a","b"] }
    (repeats is [] when no `repeat` query param is supplied; ALL values, in order)
  - any unmatched path under /v1 -> 404
  - a path that omits /v1 entirely (e.g. <base>/ping) -> 404
  - two separate createApi() instances never share state.

Verification strategy
----------------------
- L1: the required deliverable files exist and are minimally well-formed (export the
  `createApi` factory, mention the `/v1` segment, register the two resource groups,
  ship a colocated vitest test file).
- L2: DYNAMIC EXECUTION. We write an *independent* vitest spec into the repo that
  imports the agent's `createApi()` and exercises every requirement by dispatching
  IN-MEMORY requests via `app.request(...)`, asserting on the real status codes and
  JSON the module returns. Crucially we run the contract BOTH directly and mounted
  under a non-empty parent prefix (`/app`), so an implementation that hardcodes `/v1`
  at mount time, collapses the two groups into one shared object, or ignores repeated
  `repeat` params FAILS the named cases.

  To bound runtime the independent spec runs ONCE with vitest's JSON reporter; results
  are cached module-wide and each L2 Python test asserts on one named case (and that
  the case actually executed — a missing case is a failure, so a solution cannot pass
  by deleting cases).

- The agent's OWN colocated suite is checked separately: it must contain >=10 cases
  and pass, per the acceptance criteria.

Native test command (per task acceptance criteria):
    npx vitest --run src/helper/api-aggregator/index.test.ts
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
MODULE_DIR = os.path.join(REPO_DIR, "src", "helper", "api-aggregator")
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
# We deliberately exercise the contract through TWO lenses:
#   * `direct()`  -> the value returned by createApi() used as the app itself.
#   * `mounted()` -> the value mounted under a non-empty prefix ('/app') of a
#                    parent Hono app. The /v1 segment must be intrinsic, so paths
#                    are '/app/v1/...' WITHOUT the caller re-adding '/v1'.
# ---------------------------------------------------------------------------
_VERIFY_SPEC_SRC = textwrap.dedent(
    """
    import { describe, it, expect } from 'vitest'
    import { Hono } from '../../hono'
    import { createApi } from '.'

    const base = 'http://localhost'

    // The aggregator used directly as the application.
    const direct = () => createApi()

    // The aggregator mounted under a non-empty parent prefix.
    const mounted = (prefix = '/app') => {
      const app = new Hono()
      app.route(prefix, createApi())
      return { app, prefix }
    }

    const getJson = async (res) => ({ status: res.status, body: await res.json() })

    describe('api-aggregator verification', () => {
      it('ping_health_direct', async () => {
        const app = direct()
        const res = await app.request(base + '/v1/ping')
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body).toEqual({ status: 'ok', version: 'v1' })
      })

      it('ping_health_mounted_under_prefix', async () => {
        const { app } = mounted('/app')
        // /v1 is intrinsic: caller does NOT re-add it.
        const res = await app.request(base + '/app/v1/ping')
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body).toEqual({ status: 'ok', version: 'v1' })
      })

      it('ping_deep_depth_one', async () => {
        const app = direct()
        const res = await app.request(base + '/v1/ping/deep')
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.status).toBe('ok')
        expect(body.depth).toBe(1)
        // mounted variant must also report depth 1 (intrinsic /v1, not prefix-derived).
        const { app: m } = mounted('/svc')
        const mres = await m.request(base + '/svc/v1/ping/deep')
        expect(mres.status).toBe(200)
        expect((await mres.json()).depth).toBe(1)
      })

      it('echo_post_roundtrips_body', async () => {
        const app = direct()
        const res = await app.request(base + '/v1/echo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ a: 1, nested: { b: [2, 3] } }),
        })
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body).toEqual({ echo: { a: 1, nested: { b: [2, 3] } } })
      })

      it('echo_post_mounted_roundtrips_body', async () => {
        const { app } = mounted('/app')
        const res = await app.request(base + '/app/v1/echo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ a: 1 }),
        })
        expect(res.status).toBe(200)
        expect(await res.json()).toEqual({ echo: { a: 1 } })
      })

      it('echo_phrase_path_segment', async () => {
        const app = direct()
        const res = await app.request(base + '/v1/echo/hello')
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.phrase).toBe('hello')
        // A distinct phrase must echo that exact value, not a hardcoded constant.
        const res2 = await app.request(base + '/v1/echo/world')
        expect((await res2.json()).phrase).toBe('world')
      })

      it('echo_repeat_query_collects_all_in_order', async () => {
        const app = direct()
        const res = await app.request(base + '/v1/echo/hi?repeat=x&repeat=y&repeat=z')
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.phrase).toBe('hi')
        // ALL supplied values, in supplied order — naive single-value reads fail here.
        expect(body.repeats).toEqual(['x', 'y', 'z'])
        // Order is preserved exactly (a vs b, not sorted/deduped).
        const res2 = await app.request(base + '/v1/echo/hi?repeat=b&repeat=a&repeat=b')
        expect((await res2.json()).repeats).toEqual(['b', 'a', 'b'])
      })

      it('echo_repeat_absent_is_empty_array', async () => {
        const app = direct()
        const res = await app.request(base + '/v1/echo/hi')
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.phrase).toBe('hi')
        expect(Array.isArray(body.repeats)).toBe(true)
        expect(body.repeats).toEqual([])
      })

      it('echo_repeat_mounted_collects_all', async () => {
        const { app } = mounted('/app')
        const res = await app.request(base + '/app/v1/echo/hi?repeat=p&repeat=q')
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.phrase).toBe('hi')
        expect(body.repeats).toEqual(['p', 'q'])
      })

      it('missing_v1_segment_is_404', async () => {
        const app = direct()
        // Path that omits /v1 entirely must not be served by the ping group.
        expect((await app.request(base + '/ping')).status).toBe(404)
        expect((await app.request(base + '/echo/hi')).status).toBe(404)
        // Same when mounted: '/app/ping' (no /v1) must 404.
        const { app: m } = mounted('/app')
        expect((await m.request(base + '/app/ping')).status).toBe(404)
      })

      it('unknown_route_under_v1_is_404', async () => {
        const app = direct()
        expect((await app.request(base + '/v1/nope')).status).toBe(404)
        expect((await app.request(base + '/v1/ping/unknown')).status).toBe(404)
        const { app: m } = mounted('/app')
        expect((await m.request(base + '/app/v1/nope')).status).toBe(404)
      })

      it('two_instances_are_independent', async () => {
        // Independence at the instance level: each call yields a fresh app, and
        // both must still serve the full contract identically (no shared mutable
        // module-level router/state collapsing the two groups).
        const a = createApi()
        const b = createApi()
        expect(a).not.toBe(b)
        const ra = await a.request(base + '/v1/ping')
        const rb = await b.request(base + '/v1/ping')
        expect(ra.status).toBe(200)
        expect(rb.status).toBe(200)
        expect(await ra.json()).toEqual({ status: 'ok', version: 'v1' })
        expect(await rb.json()).toEqual({ status: 'ok', version: 'v1' })
        // echo group reachable on both independent instances.
        const ea = await a.request(base + '/v1/echo/onlyA')
        const eb = await b.request(base + '/v1/echo/onlyB')
        expect((await ea.json()).phrase).toBe('onlyA')
        expect((await eb.json()).phrase).toBe('onlyB')
      })

      it('groups_do_not_leak_across_prefixes', async () => {
        // The two groups are independent values combined under /v1. The ping group
        // must NOT answer under the echo prefix and vice versa.
        const app = direct()
        // ping handler should not be reachable beneath the echo segment.
        expect((await app.request(base + '/v1/echo/ping')).status).toBe(200)
        // ...and when it IS reachable it is the ECHO handler (phrase), not ping.
        expect((await app.request(base + '/v1/echo/ping')).status).toBe(200)
        const echoed = await (await app.request(base + '/v1/echo/ping')).json()
        expect(echoed.phrase).toBe('ping')
        expect(echoed.status).toBeUndefined()
        // POST to the ping route is not defined -> not a 200 echo.
        const wrong = await app.request(base + '/v1/ping', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ a: 1 }),
        })
        expect(wrong.status).not.toBe(200)
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
            "src/helper/api-aggregator/__bench_verify.test.ts", timeout=600, json_out=json_path
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
        """L1: the api-aggregator module file is present."""
        assert os.path.isfile(MODULE_TS), f"missing deliverable {MODULE_TS}"

    def test_module_exports_factory(self):
        """L1: module source exports a `createApi` factory function."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "createApi" in src, "createApi not found"
        assert "export" in src, "factory not exported"

    def test_module_declares_v1_segment(self):
        """L1: module references an intrinsic `/v1` segment for its routes."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "v1" in src, "module does not reference the required /v1 segment"

    def test_module_registers_resource_groups(self):
        """L1: module wires the two resource groups (ping + echo) and their verbs."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "ping" in src, "module does not reference the ping group"
        assert "echo" in src, "module does not reference the echo group"
        assert ".get(" in src, "module registers no GET route"
        assert ".post(" in src, "module registers no POST route (echo body)"

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
        result = _run_vitest("src/helper/api-aggregator/index.test.ts", timeout=600)
        assert result.returncode == 0, (
            "agent's colocated vitest suite failed:\n"
            f"STDOUT:\n{result.stdout[-4000:]}\nSTDERR:\n{result.stderr[-3000:]}"
        )

    # ------------------------------------------------------------- L2 ----
    # Each maps to one task requirement, verified by the independent spec.

    def test_ping_health_direct(self):
        """L2: GET /v1/ping -> 200 { status: 'ok', version: 'v1' } used directly."""
        _assert_case("ping_health_direct")

    def test_ping_health_mounted_under_prefix(self):
        """L2: mounted at /app, GET /app/v1/ping -> 200 (intrinsic /v1, no re-add)."""
        _assert_case("ping_health_mounted_under_prefix")

    def test_ping_deep_depth_one(self):
        """L2: GET /v1/ping/deep -> 200 { status:'ok', depth:1 } direct and mounted."""
        _assert_case("ping_deep_depth_one")

    def test_echo_post_roundtrips_body(self):
        """L2: POST /v1/echo with JSON -> 200 { echo: <parsed body> } (deep equality)."""
        _assert_case("echo_post_roundtrips_body")

    def test_echo_post_mounted_roundtrips_body(self):
        """L2: POST /app/v1/echo when mounted -> 200 { echo: <body> }."""
        _assert_case("echo_post_mounted_roundtrips_body")

    def test_echo_phrase_path_segment(self):
        """L2: GET /v1/echo/:phrase -> 200 { phrase: <segment> } (not a constant)."""
        _assert_case("echo_phrase_path_segment")

    def test_echo_repeat_query_collects_all_in_order(self):
        """L2: repeated ?repeat= params -> repeats is every value, in order (not last-wins)."""
        _assert_case("echo_repeat_query_collects_all_in_order")

    def test_echo_repeat_absent_is_empty_array(self):
        """L2: GET /v1/echo/:phrase with no repeat -> repeats === []."""
        _assert_case("echo_repeat_absent_is_empty_array")

    def test_echo_repeat_mounted_collects_all(self):
        """L2: repeated ?repeat= works under a mounted prefix too."""
        _assert_case("echo_repeat_mounted_collects_all")

    def test_missing_v1_segment_is_404(self):
        """L2: a path omitting /v1 (e.g. /ping, /app/ping) -> 404."""
        _assert_case("missing_v1_segment_is_404")

    def test_unknown_route_under_v1_is_404(self):
        """L2: an unmatched path under /v1 -> 404 (direct and mounted)."""
        _assert_case("unknown_route_under_v1_is_404")

    def test_two_instances_are_independent(self):
        """L2: two createApi() calls yield distinct apps, both serving the full contract."""
        _assert_case("two_instances_are_independent")

    def test_groups_do_not_leak_across_prefixes(self):
        """L2: ping/echo groups stay isolated; echo handles /v1/echo/ping, ping doesn't leak."""
        _assert_case("groups_do_not_leak_across_prefixes")
