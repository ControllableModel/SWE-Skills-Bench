"""Tests for the `hono-patterns` skill task (ext4 variant): a multi-method
webhook dispatcher module.

Verifies the deliverable `src/helper/webhook-dispatcher/index.ts` (and its
colocated `index.test.ts`) inside the Hono repo at /workspace/hono.

Task summary
------------
The module must export a factory `createWebhook(secret)` returning a fresh,
fully isolated, mountable Hono sub-application with its own private in-memory
event log and id counter. The contract:

- A single hook endpoint at the collection ROOT accepts POST / PUT / DELETE.
  Each authorized request appends `{ method: <UPPER>, id: <int> }` to the log
  and returns 202 with the appended record as JSON. ids are distinct,
  monotonically increasing integers within the instance.
- GET on the root is NOT an accepted method -> 405 with `{ error }` JSON and an
  `Allow` response header listing the accepted methods (NOT 404).
- Every accepted method requires header `X-Webhook-Secret` to exactly equal the
  factory `secret`; missing/mismatched -> 401 `{ error }` and the log/id counter
  are NOT mutated.
- `GET /events` -> 200 `{ events: [...] }` in append order.
- `GET /events?method=<m>` filters to records whose method equals `<m>` compared
  case-insensitively as uppercase.

Verification strategy
---------------------
- L1: required deliverable files exist and are minimally well-formed (export the
  factory, register the multi-method hook + an `/events` route, ship a colocated
  vitest test file).
- L2: DYNAMIC EXECUTION. We write an INDEPENDENT vitest spec into the repo that
  imports the agent's `createWebhook()` and dispatches IN-MEMORY requests via
  `app.request(...)` against both a directly-used and a mounted-under-a-prefix
  instance, asserting on real status codes / JSON bodies / headers. We run that
  spec ONCE with vitest's JSON reporter, cache the per-test results, and have
  each L2 Python test assert on one specific named case (a missing case is a
  failure, so a solution cannot pass by deleting cases).

  A naive implementation FAILS named cases: accepting all methods (GET would be
  202), returning 404 instead of 405 for GET-root, omitting the `Allow` header,
  skipping the secret check (401 cases), mutating the log on a rejected 401,
  non-monotonic / shared ids, or a global/shared log across instances.

- The agent's OWN colocated suite is checked separately: it must contain >=10
  cases and pass, per the acceptance criteria.

Native test command (per task acceptance criteria):
    npx vitest --run src/helper/webhook-dispatcher/index.test.ts
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
MODULE_DIR = os.path.join(REPO_DIR, "src", "helper", "webhook-dispatcher")
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
    startup cheap (the repo's default vitest config enables v8 coverage and
    loads several runtime-test projects, which is needlessly slow for one spec).
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
# We exercise the dispatcher under a NON-EMPTY mount prefix to enforce that the
# routes are relative (root hook + /events) and survive mounting. The secret is
# fixed so authorization is deterministic.
# ---------------------------------------------------------------------------
_VERIFY_SPEC_SRC = textwrap.dedent(
    """
    import { describe, it, expect } from 'vitest'
    import { Hono } from '../../hono'
    import { createWebhook } from '.'

    const base = 'http://localhost'
    const SECRET = 's3cr3t'
    const PREFIX = '/api/hooks'

    // Parent app with the dispatcher mounted under a non-empty prefix.
    const mounted = (secret = SECRET) => {
      const app = new Hono()
      app.route(PREFIX, createWebhook(secret))
      return app
    }

    // Send to the ROOT hook endpoint (the collection root, i.e. the prefix).
    const hook = (app, method, opts = {}) => {
      const headers = { ...(opts.headers || {}) }
      if (opts.secret !== undefined) headers['X-Webhook-Secret'] = opts.secret
      return app.request(base + PREFIX, { method, headers })
    }
    const events = (app, query = '') =>
      app.request(base + PREFIX + '/events' + query)

    describe('webhook-dispatcher verification', () => {
      it('post_authorized_202_appends_record_id_1', async () => {
        const app = mounted()
        const res = await hook(app, 'POST', { secret: SECRET })
        expect(res.status).toBe(202)
        const rec = await res.json()
        expect(rec.method).toBe('POST')
        expect(typeof rec.id).toBe('number')
        expect(rec.id).toBe(1)
        const log = await (await events(app)).json()
        expect(log.events).toEqual([{ method: 'POST', id: 1 }])
      })

      it('put_delete_accepted_with_monotonic_ids', async () => {
        const app = mounted()
        const p = await (await hook(app, 'POST', { secret: SECRET })).json()
        const u = await (await hook(app, 'PUT', { secret: SECRET })).json()
        const d = await (await hook(app, 'DELETE', { secret: SECRET })).json()
        expect(p.id).toBe(1)
        expect(u.id).toBe(2)
        expect(d.id).toBe(3)
        expect(u.method).toBe('PUT')
        expect(d.method).toBe('DELETE')
      })

      it('events_list_in_append_order', async () => {
        const app = mounted()
        await hook(app, 'POST', { secret: SECRET })
        await hook(app, 'DELETE', { secret: SECRET })
        await hook(app, 'PUT', { secret: SECRET })
        const res = await events(app)
        expect(res.status).toBe(200)
        const log = await res.json()
        expect(Array.isArray(log.events)).toBe(true)
        expect(log.events).toEqual([
          { method: 'POST', id: 1 },
          { method: 'DELETE', id: 2 },
          { method: 'PUT', id: 3 },
        ])
      })

      it('get_root_405_with_allow_header_not_404', async () => {
        const app = mounted()
        const res = await hook(app, 'GET', { secret: SECRET })
        expect(res.status).toBe(405)
        const body = await res.json()
        expect(typeof body.error).toBe('string')
        const allow = res.headers.get('Allow') || ''
        const allowed = allow
          .split(',')
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean)
          .sort()
        expect(allowed).toEqual(['DELETE', 'POST', 'PUT'])
        // A 405 must NOT have appended anything.
        const log = await (await events(app)).json()
        expect(log.events).toEqual([])
      })

      it('missing_secret_401_no_mutation', async () => {
        const app = mounted()
        const res = await hook(app, 'POST', {}) // no secret header at all
        expect(res.status).toBe(401)
        expect(typeof (await res.json()).error).toBe('string')
        const log = await (await events(app)).json()
        expect(log.events).toEqual([])
      })

      it('wrong_secret_401_and_id_counter_not_advanced', async () => {
        const app = mounted()
        const bad = await hook(app, 'POST', { secret: 'nope' })
        expect(bad.status).toBe(401)
        expect(typeof (await bad.json()).error).toBe('string')
        // The next AUTHORIZED request must still get id 1 (counter untouched).
        const ok = await (await hook(app, 'POST', { secret: SECRET })).json()
        expect(ok.id).toBe(1)
        const log = await (await events(app)).json()
        expect(log.events).toEqual([{ method: 'POST', id: 1 }])
      })

      it('events_method_filter_case_insensitive', async () => {
        const app = mounted()
        await hook(app, 'POST', { secret: SECRET })   // id 1
        await hook(app, 'PUT', { secret: SECRET })    // id 2
        await hook(app, 'POST', { secret: SECRET })   // id 3
        await hook(app, 'DELETE', { secret: SECRET }) // id 4
        // lower-case query param must match the uppercase-stored PUT record.
        const putRes = await events(app, '?method=put')
        expect(putRes.status).toBe(200)
        const puts = (await putRes.json()).events
        expect(puts).toEqual([{ method: 'PUT', id: 2 }])
        // POST filter returns both POSTs in order.
        const posts = (await (await events(app, '?method=POST')).json()).events
        expect(posts).toEqual([
          { method: 'POST', id: 1 },
          { method: 'POST', id: 3 },
        ])
        // unfiltered returns everything.
        const all = (await (await events(app)).json()).events
        expect(all.length).toBe(4)
      })

      it('instances_isolated_separate_logs_and_counters', async () => {
        const a = mounted()
        const b = mounted()
        await hook(a, 'POST', { secret: SECRET })
        await hook(a, 'PUT', { secret: SECRET })
        const la = (await (await events(a)).json()).events
        const lb = (await (await events(b)).json()).events
        expect(la.length).toBe(2)
        expect(lb.length).toBe(0)
        // b's first authorized record must still start at id 1.
        const first = await (await hook(b, 'DELETE', { secret: SECRET })).json()
        expect(first.id).toBe(1)
      })

      it('secret_is_per_instance', async () => {
        // Two instances with different secrets must enforce their own secret.
        const a = mounted('alpha')
        const b = mounted('beta')
        expect((await hook(a, 'POST', { secret: 'alpha' })).status).toBe(202)
        expect((await hook(a, 'POST', { secret: 'beta' })).status).toBe(401)
        expect((await hook(b, 'POST', { secret: 'beta' })).status).toBe(202)
        expect((await hook(b, 'POST', { secret: 'alpha' })).status).toBe(401)
      })

      it('works_directly_without_mount_prefix', async () => {
        // Used directly (no parent prefix): root hook + /events still work.
        const app = createWebhook(SECRET)
        const res = await app.request(base + '/', {
          method: 'POST',
          headers: { 'X-Webhook-Secret': SECRET },
        })
        expect(res.status).toBe(202)
        const rec = await res.json()
        expect(rec).toEqual({ method: 'POST', id: 1 })
        const log = await (await app.request(base + '/events')).json()
        expect(log.events).toEqual([{ method: 'POST', id: 1 }])
        const denied = await app.request(base + '/', {
          method: 'GET',
          headers: { 'X-Webhook-Secret': SECRET },
        })
        expect(denied.status).toBe(405)
      })

      it('distinct_increasing_ids_over_many_events', async () => {
        const app = mounted()
        const ids = []
        const methods = ['POST', 'PUT', 'DELETE']
        for (let i = 0; i < 9; i++) {
          const rec = await (await hook(app, methods[i % 3], { secret: SECRET })).json()
          ids.push(rec.id)
        }
        // strictly increasing, distinct, starting at 1.
        expect(ids).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9])
        expect(new Set(ids).size).toBe(9)
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
            "src/helper/webhook-dispatcher/__bench_verify.test.ts",
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
        """L1: the webhook-dispatcher module file is present."""
        assert os.path.isfile(MODULE_TS), f"missing deliverable {MODULE_TS}"

    def test_module_exports_factory(self):
        """L1: module source exports a `createWebhook` factory."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "createWebhook" in src, "createWebhook not found"
        assert "export" in src, "factory not exported"

    def test_module_registers_multimethod_hook_and_events(self):
        """L1: module registers a multi-method hook and an /events GET route.

        The dispatcher needs the three write verbs on the root (POST/PUT/DELETE,
        whether via `.on([...])` or individual registrations) plus a GET handler
        for inspecting the log.
        """
        with open(MODULE_TS) as f:
            src = f.read()
        registers_writes = (".on(" in src) or all(
            v in src for v in (".post(", ".put(", ".delete(")
        )
        assert registers_writes, (
            "module does not register the POST/PUT/DELETE hook (no `.on(` and "
            "not all of .post/.put/.delete present)"
        )
        assert ".get(" in src, "module does not register a GET route (needed for /events)"
        assert "events" in src, "module does not reference an /events path"

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
        result = _run_vitest("src/helper/webhook-dispatcher/index.test.ts", timeout=600)
        assert result.returncode == 0, (
            "agent's colocated vitest suite failed:\n"
            f"STDOUT:\n{result.stdout[-4000:]}\nSTDERR:\n{result.stderr[-3000:]}"
        )

    # ------------------------------------------------------------- L2 ----
    # Each maps to one task requirement, verified by the independent spec.

    def test_post_authorized_202_appends_record_id_1(self):
        """L2: authorized POST -> 202 with `{method:'POST', id:1}`; logged."""
        _assert_case("post_authorized_202_appends_record_id_1")

    def test_put_delete_accepted_with_monotonic_ids(self):
        """L2: PUT and DELETE are accepted; ids are distinct and increasing (1,2,3)."""
        _assert_case("put_delete_accepted_with_monotonic_ids")

    def test_events_list_in_append_order(self):
        """L2: GET /events -> 200 {events:[...]} in append order."""
        _assert_case("events_list_in_append_order")

    def test_get_root_405_with_allow_header_not_404(self):
        """L2: GET on the root -> 405 {error} with an `Allow` header listing POST/PUT/DELETE (NOT 404)."""
        _assert_case("get_root_405_with_allow_header_not_404")

    def test_missing_secret_401_no_mutation(self):
        """L2: missing X-Webhook-Secret -> 401 {error}; log unchanged."""
        _assert_case("missing_secret_401_no_mutation")

    def test_wrong_secret_401_and_id_counter_not_advanced(self):
        """L2: wrong secret -> 401 and the id counter is NOT advanced (next OK record is id 1)."""
        _assert_case("wrong_secret_401_and_id_counter_not_advanced")

    def test_events_method_filter_case_insensitive(self):
        """L2: GET /events?method= filters case-insensitively against uppercase-stored methods."""
        _assert_case("events_method_filter_case_insensitive")

    def test_instances_isolated_separate_logs_and_counters(self):
        """L2: two createWebhook() instances never share log or id counter."""
        _assert_case("instances_isolated_separate_logs_and_counters")

    def test_secret_is_per_instance(self):
        """L2: each instance enforces its own secret (cross-secret requests are 401)."""
        _assert_case("secret_is_per_instance")

    def test_works_directly_without_mount_prefix(self):
        """L2: the sub-app works when used directly (no parent prefix) as well as mounted."""
        _assert_case("works_directly_without_mount_prefix")

    def test_distinct_increasing_ids_over_many_events(self):
        """L2: many accepted events get distinct, strictly increasing ids starting at 1."""
        _assert_case("distinct_increasing_ids_over_many_events")
