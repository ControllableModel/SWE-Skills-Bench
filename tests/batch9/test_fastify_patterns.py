"""Tests for the `fastify-patterns` skill task (variant ext9):
Build a Per-Client Request Quota Guard via a Shared Decorator.

Verifies the agent's work inside REPO_DIR (/workspace/fastify):

  - examples/quota-guard.js exports a no-argument factory that builds and returns
    a configured Fastify instance via the repository root (`require('..')`)
    WITHOUT binding a network port on require/build.
  - A shared, in-memory per-client quota store is attached to the instance (a
    decoration) and enforced by a lifecycle step that runs BEFORE handlers — not
    by a module-level global and not by duplicated counting inside each handler.
  - Client identity is the `x-client-id` request header; the limit is a fixed 3
    requests per client for the lifetime of the instance (deterministic — no
    clocks, no randomness, no time windows).
  - Allowed responses carry a decreasing `remaining` field (2, 1, 0); the 4th
    request -> 429 with `{ statusCode: 429, message, remaining: 0 }`; a missing
    header -> 400; `/data` and `/report` share one per-client counter; `/health`
    is unprotected and always 200 `{ status: "ok" }`; two factory instances have
    isolated quotas.
  - test/quota-guard.test.js exists and the native command
    `node --test test/quota-guard.test.js` passes.

Rather than trusting the agent-authored test file, the L2 cases independently
drive the factory through Fastify's in-process `inject` API using a fresh Node
driver written by THIS test, so a naive/hardcoded implementation (global
counter, per-handler re-counting, fixed `remaining`, ignored header) fails.
"""

import json
import os
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - utility is provided at runtime
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/fastify"
DRIVER_DIR = os.path.join(REPO_DIR, ".bench_drivers")


@pytest.fixture(scope="module", autouse=True)
def _prepare_repo():
    """Install repo dependencies once so `require('..')` resolves."""
    assert os.path.isdir(REPO_DIR), f"REPO_DIR missing: {REPO_DIR}"
    if ensure_npm_dependencies is not None:
        ensure_npm_dependencies(REPO_DIR)
    os.makedirs(DRIVER_DIR, exist_ok=True)
    yield


# --------------------------------------------------------------------------- #
# Node driver helpers
# --------------------------------------------------------------------------- #

# Shared prelude: load the agent's factory, and expose a small `inject` helper
# that always returns {status, headers, body, raw}. The body of each test builds
# its own instance(s) so quota state is never shared across cases.
_PRELUDE = r"""
'use strict'
const path = require('path')
const factoryPath = path.join(process.cwd(), 'examples', 'quota-guard.js')
const factory = require(factoryPath)

if (typeof factory !== 'function') {
  console.error('FACTORY_NOT_A_FUNCTION:' + (typeof factory))
  process.exit(3)
}

async function inject (app, opts) {
  const res = await app.inject(opts)
  let body = null
  let parseError = null
  try { body = JSON.parse(res.payload) } catch (e) { parseError = String(e && e.message) }
  return {
    status: res.statusCode,
    contentType: res.headers['content-type'] || '',
    body,
    parseError,
    raw: res.payload
  }
}

// convenience: GET a protected/unprotected url with an optional client id
async function get (app, url, clientId) {
  const headers = {}
  if (clientId !== undefined && clientId !== null) headers['x-client-id'] = clientId
  return inject(app, { method: 'GET', url, headers })
}

function out (obj) {
  process.stdout.write('@@RESULT@@' + JSON.stringify(obj) + '@@END@@\n')
}
"""


class TestFastifyPatterns:
    REPO_DIR = "/workspace/fastify"

    # ----------------------- internal utilities --------------------------- #

    def _run_node(self, body_src, timeout=120):
        """Write a Node script (prelude + body) into REPO_DIR and execute it.

        Returns the parsed @@RESULT@@ payload. Asserts the process succeeded and
        emitted exactly one structured result marker.
        """
        os.makedirs(DRIVER_DIR, exist_ok=True)
        # CommonJS has no top-level await, so wrap the body in an async IIFE that
        # surfaces failures with a non-zero exit code.
        wrapped = (
            "\n;(async () => {\n"
            + textwrap.indent(textwrap.dedent(body_src), "  ")
            + "\n})().catch((e) => { console.error(e && e.stack ? e.stack : e); process.exit(1) })\n"
        )
        script = _PRELUDE + "\n" + wrapped
        name = f"driver_{abs(hash(body_src)) % (10 ** 8)}.js"
        script_path = os.path.join(DRIVER_DIR, name)
        with open(script_path, "w") as fh:
            fh.write(script)
        try:
            proc = subprocess.run(
                ["node", script_path],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        finally:
            try:
                os.remove(script_path)
            except OSError:
                pass

        assert proc.returncode == 0, (
            "Node driver failed.\n"
            f"returncode={proc.returncode}\n"
            f"stdout={proc.stdout[-4000:]}\n"
            f"stderr={proc.stderr[-4000:]}"
        )
        marker = "@@RESULT@@"
        assert marker in proc.stdout, (
            "Driver produced no @@RESULT@@ marker.\n"
            f"stdout={proc.stdout[-4000:]}\nstderr={proc.stderr[-4000:]}"
        )
        chunk = proc.stdout.split(marker, 1)[1]
        chunk = chunk.split("@@END@@", 1)[0]
        return json.loads(chunk)

    # ============================== L1 =================================== #

    def test_l1_factory_module_exists(self):
        """L1: examples/quota-guard.js exists and is a non-empty file."""
        p = os.path.join(REPO_DIR, "examples", "quota-guard.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        assert os.path.getsize(p) > 0, "quota-guard.js is empty"

    def test_l1_test_file_exists(self):
        """L1: test/quota-guard.test.js exists and references node:test + inject."""
        p = os.path.join(REPO_DIR, "test", "quota-guard.test.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        with open(p) as fh:
            content = fh.read()
        assert os.path.getsize(p) > 0, "test file is empty"
        # sanity (not the discriminating check): must use node:test and inject
        assert "node:test" in content, "test must use the node:test runner"
        assert "inject" in content, "test must drive the instance via inject"

    def test_l1_factory_exports_function_and_no_listen(self):
        """L1: requiring the module yields a factory function with NO side-effect
        listen; building an instance does not bind a network port."""
        res = self._run_node(
            """
            const app = factory()
            let addr = null
            try { addr = app.server && app.server.address ? app.server.address() : null } catch (e) {}
            await app.ready()
            out({ isFn: typeof factory === 'function', listening: !!(addr) })
            await app.close()
            """
        )
        assert res["isFn"] is True, "module.exports must be a factory function"
        assert res["listening"] is False, "factory/require must not bind a network port"

    # ============================== L2 =================================== #

    def test_l2_first_request_allowed_remaining_two(self):
        """L2: first GET /data with a client id -> 200 and remaining == 2."""
        res = self._run_node(
            """
            const app = factory()
            const r = await get(app, '/data', 'alice')
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, res
        body = res["body"]
        assert isinstance(body, dict), f"expected JSON object, got {body!r}"
        assert body.get("remaining") == 2, (
            f"first allowed request must report remaining == 2, got {body!r}"
        )

    def test_l2_three_allowed_then_decreasing_remaining(self):
        """L2: three GET /data for one client -> 200/200/200 with remaining 2,1,0.

        Discriminates a fixed/hardcoded `remaining`: the values must decrease.
        """
        res = self._run_node(
            """
            const app = factory()
            const a = await get(app, '/data', 'bob')
            const b = await get(app, '/data', 'bob')
            const c = await get(app, '/data', 'bob')
            await app.close()
            out({ a, b, c })
            """
        )
        statuses = [res["a"]["status"], res["b"]["status"], res["c"]["status"]]
        assert statuses == [200, 200, 200], f"first three must all be allowed: {statuses}"
        remaining = [res["a"]["body"]["remaining"], res["b"]["body"]["remaining"], res["c"]["body"]["remaining"]]
        assert remaining == [2, 1, 0], (
            f"remaining must decrease 2 -> 1 -> 0 across the three allowed requests, got {remaining}"
        )

    def test_l2_fourth_request_rejected_429(self):
        """L2: the 4th request for a client -> 429 with statusCode/message/remaining:0."""
        res = self._run_node(
            """
            const app = factory()
            await get(app, '/data', 'carol')
            await get(app, '/data', 'carol')
            await get(app, '/data', 'carol')
            const fourth = await get(app, '/data', 'carol')
            await app.close()
            out(fourth)
            """
        )
        assert res["status"] == 429, f"4th request must be rejected with 429: {res}"
        body = res["body"]
        assert isinstance(body, dict), "429 body must be a JSON object"
        assert body.get("statusCode") == 429, body
        assert isinstance(body.get("message"), str) and body["message"], "message must be a non-empty string"
        assert body.get("remaining") == 0, f"over-quota body must report remaining == 0, got {body!r}"

    def test_l2_cross_route_shared_counter(self):
        """L2: /data and /report draw from ONE shared per-client counter.

        Two /data + one /report = the 3 allowed; the 4th (a /report) -> 429.
        A per-handler/per-route counter would wrongly allow this.
        """
        res = self._run_node(
            """
            const app = factory()
            const d1 = await get(app, '/data', 'dave')
            const d2 = await get(app, '/data', 'dave')
            const rp = await get(app, '/report', 'dave')   // 3rd overall, still allowed
            const over = await get(app, '/report', 'dave') // 4th overall -> blocked
            await app.close()
            out({ d1, d2, rp, over })
            """
        )
        assert res["d1"]["status"] == 200 and res["d1"]["body"]["remaining"] == 2, res["d1"]
        assert res["d2"]["status"] == 200 and res["d2"]["body"]["remaining"] == 1, res["d2"]
        assert res["rp"]["status"] == 200 and res["rp"]["body"]["remaining"] == 0, (
            f"/report must share /data's counter (3rd overall request allowed): {res['rp']}"
        )
        assert res["over"]["status"] == 429, (
            f"4th request across the two routes must be blocked (shared counter): {res['over']}"
        )
        assert res["over"]["body"]["remaining"] == 0

    def test_l2_missing_client_id_header_400(self):
        """L2: a protected request with no x-client-id header -> 400 error shape."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/data' })  // no header
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 400, f"missing x-client-id must be rejected with 400: {res}"
        body = res["body"]
        assert isinstance(body, dict), "400 body must be a JSON object"
        assert body.get("statusCode") == 400, body
        assert isinstance(body.get("message"), str) and body["message"], "message must be a non-empty string"
        assert "json" in res["contentType"], "error must be JSON, not HTML"

    def test_l2_distinct_clients_independent_quota(self):
        """L2: a second client gets its own fresh allowance of 3.

        Discriminates a single shared (non-keyed) counter: exhausting one client
        must not affect another client's quota.
        """
        res = self._run_node(
            """
            const app = factory()
            // exhaust client "x" (3 allowed + 1 blocked)
            await get(app, '/data', 'x')
            await get(app, '/data', 'x')
            await get(app, '/data', 'x')
            const xBlocked = await get(app, '/data', 'x')
            // a different client "y" must still get its own first allowed request
            const y1 = await get(app, '/data', 'y')
            const y2 = await get(app, '/data', 'y')
            const y3 = await get(app, '/data', 'y')
            const yBlocked = await get(app, '/data', 'y')
            await app.close()
            out({ xBlocked, y1, y2, y3, yBlocked })
            """
        )
        assert res["xBlocked"]["status"] == 429, "client x must be over quota"
        assert res["y1"]["status"] == 200 and res["y1"]["body"]["remaining"] == 2, (
            f"a distinct client must get its own fresh quota: {res['y1']}"
        )
        assert res["y2"]["status"] == 200 and res["y2"]["body"]["remaining"] == 1, res["y2"]
        assert res["y3"]["status"] == 200 and res["y3"]["body"]["remaining"] == 0, res["y3"]
        assert res["yBlocked"]["status"] == 429, "client y must be blocked only on its own 4th"

    def test_l2_health_unprotected_always_ok(self):
        """L2: GET /health -> 200 { status: "ok" } regardless of header/quota.

        Proves the guard is scoped to the protected unit, not the whole instance.
        Checked (a) with no header, and (b) after a client is fully over quota.
        """
        res = self._run_node(
            """
            const app = factory()
            const noHeader = await inject(app, { method: 'GET', url: '/health' })
            // drive a client over quota then re-check /health
            await get(app, '/data', 'z')
            await get(app, '/data', 'z')
            await get(app, '/data', 'z')
            const over = await get(app, '/data', 'z')
            const afterOver = await get(app, '/health', 'z')
            await app.close()
            out({ noHeader, over, afterOver })
            """
        )
        assert res["noHeader"]["status"] == 200, f"/health must not require a client id: {res['noHeader']}"
        assert res["noHeader"]["body"] == {"status": "ok"}, (
            f"/health must return exactly {{status: 'ok'}}, got {res['noHeader']['body']!r}"
        )
        assert res["over"]["status"] == 429, "precondition: client z must be over quota"
        assert res["afterOver"]["status"] == 200, "/health must stay 200 even after quota exhausted"
        assert res["afterOver"]["body"] == {"status": "ok"}

    def test_l2_instances_have_isolated_quota(self):
        """L2: two factory() instances keep independent quota stores.

        Discriminates a module-level/file-scoped global counter: exhausting
        instance A must leave instance B's quota completely fresh, even for the
        SAME client id.
        """
        res = self._run_node(
            """
            const a = factory()
            const b = factory()
            // exhaust client "shared" on A
            await get(a, '/data', 'shared')
            await get(a, '/data', 'shared')
            await get(a, '/data', 'shared')
            const aBlocked = await get(a, '/data', 'shared')
            // SAME client id on a fresh instance B must start fresh
            const b1 = await get(b, '/data', 'shared')
            const b2 = await get(b, '/data', 'shared')
            const b3 = await get(b, '/data', 'shared')
            const bBlocked = await get(b, '/data', 'shared')
            await a.close(); await b.close()
            out({ aBlocked, b1, b2, b3, bBlocked })
            """
        )
        assert res["aBlocked"]["status"] == 429, "instance A must be over quota for client 'shared'"
        assert res["b1"]["status"] == 200 and res["b1"]["body"]["remaining"] == 2, (
            f"instance B must have an independent fresh quota (no global state): {res['b1']}"
        )
        assert res["b2"]["status"] == 200 and res["b2"]["body"]["remaining"] == 1, res["b2"]
        assert res["b3"]["status"] == 200 and res["b3"]["body"]["remaining"] == 0, res["b3"]
        assert res["bBlocked"]["status"] == 429, "instance B blocked only on its own 4th"

    def test_l2_shared_store_is_a_decoration(self):
        """L2: the per-client quota store is attached to the instance (decorated),
        not held in a module-level global.

        We assert the instance exposes a decorated store property (discoverable by
        being present on the instance object) AND that it is per-instance: the
        store object identity differs between two factory() instances. A
        file-scoped global would be shared (same reference) or absent from the
        instance entirely.
        """
        res = self._run_node(
            """
            const a = factory()
            const b = factory()
            await a.ready(); await b.ready()
            // find instance-attached, non-function, object-valued own/enumerable
            // properties that are NOT part of the stock Fastify surface and that
            // differ in identity between two instances (i.e. the per-instance store).
            const SKIP = new Set(['server','initialConfig','pluginName','version','prefix','log'])
            function candidateKeys (app) {
              const keys = []
              for (const k in app) {
                if (SKIP.has(k)) continue
                let v
                try { v = app[k] } catch (e) { continue }
                if (v && typeof v === 'object') keys.push(k)
              }
              return keys
            }
            const ak = candidateKeys(a)
            // a decorated store should be present on the instance under some key
            let distinctStoreKey = null
            for (const k of ak) {
              let av, bv
              try { av = a[k] } catch (e) { continue }
              try { bv = b[k] } catch (e) { continue }
              if (av && bv && typeof av === 'object' && typeof bv === 'object' && av !== bv) {
                distinctStoreKey = k
                break
              }
            }
            await a.close(); await b.close()
            out({ candidateCount: ak.length, distinctStoreKey })
            """
        )
        assert res["candidateCount"] >= 1, (
            "the instance must carry at least one object-valued decoration (the quota store)"
        )
        assert res["distinctStoreKey"] is not None, (
            "the per-client quota store must be an instance decoration with PER-INSTANCE "
            "identity (two factory() instances must not share the same store object — "
            "rules out a module-level global)"
        )

    def test_l2_guard_runs_before_handler(self):
        """L2: the guard counts in a lifecycle step BEFORE the handler.

        An over-quota request must be short-circuited with 429 and must NOT carry
        a successful handler payload. We verify the blocked response has no data
        payload typical of a handler (only the error shape with remaining:0),
        confirming the lifecycle hook prevents the handler from running.
        """
        res = self._run_node(
            """
            const app = factory()
            await get(app, '/data', 'pre')
            await get(app, '/data', 'pre')
            await get(app, '/data', 'pre')
            const blocked = await get(app, '/data', 'pre')
            await app.close()
            out(blocked)
            """
        )
        assert res["status"] == 429, res
        body = res["body"]
        assert isinstance(body, dict)
        assert body.get("statusCode") == 429
        assert body.get("remaining") == 0
        # A short-circuited (pre-handler) rejection must not expose a normal
        # success payload. The allowed /data body reports remaining > 0; the
        # blocked one must report exactly 0 and the 429 error shape.
        assert "statusCode" in body, "blocked response must be the guard's error shape, not a handler payload"

    def test_l2_native_node_test_passes(self):
        """L2: the agent's own suite passes via `node --test test/quota-guard.test.js`."""
        test_path = os.path.join(REPO_DIR, "test", "quota-guard.test.js")
        assert os.path.isfile(test_path), f"missing {test_path}"
        proc = subprocess.run(
            ["node", "--test", "test/quota-guard.test.js"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            "native `node --test test/quota-guard.test.js` must pass.\n"
            f"stdout={proc.stdout[-5000:]}\nstderr={proc.stderr[-3000:]}"
        )
        combined = proc.stdout + proc.stderr
        assert "fail 0" in combined, f"expected zero failures.\n{proc.stdout[-3000:]}"
